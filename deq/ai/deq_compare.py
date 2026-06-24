"""Compare DEq parameter variants on P1 strategy simulation.

Grid (default):
  pick_equity_mid in {0.030, 0.025}
  bias_adj_coef   in {0.0, 0.5, 1.0}
  deq_loss_factor = 0 (fixed — metric and result averaged over the same window)

Variant names: deq_{pem*1000:02d}_{bac*10:02d}, e.g. deq_30_00, deq_25_05.

Importable as `deq.ai.deq_compare.run(set_code)` or runnable as a script:

    pdm run python -m deq.ai.deq_compare SOS
"""

import argparse
import datetime as dt
import itertools

import polars as pl

from spells.extension import context_cols
from deq.main import live_deq
from deq.p1_strategy import all_metrics_analysis, PRECISION
from deq.ai.context import resolve_dates

PICK_EQUITY_MIDS = [0.030, 0.025]
BIAS_ADJ_COEFS = [0.0, 0.5, 1.0]


def variant_name(pem: float, bac: float) -> str:
    return f"deq_{round(pem * 1000):02d}_{round(bac * 10):02d}"


def run(
    set_code: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    pick_equity_mids: list[float] = PICK_EQUITY_MIDS,
    bias_adj_coefs: list[float] = BIAS_ADJ_COEFS,
    cache_path: str | None = None,
):
    """Run the parameter grid for `set_code` over the parquet date window."""
    start_date, end_date = resolve_dates(set_code, start_date, end_date)
    cache_path = cache_path or f"/tmp/p1_{set_code}_deq_compare.parquet"

    variants = [
        (variant_name(pem, bac), pem, bac)
        for pem, bac in itertools.product(pick_equity_mids, bias_adj_coefs)
    ]

    print(f"{set_code} DEq parameter comparison ({start_date} to {end_date})")
    print(f"Variants: {[v[0] for v in variants]}\n")

    # Build metric_context: one deq column per variant.
    contexts = []
    for name, pem, bac in variants:
        print(f"  live_deq {name} (pick_equity_mid={pem}, bias_adj_coef={bac})...")
        df = live_deq(
            set_code,
            start_date=start_date,
            end_date=end_date,
            pick_equity_mid=pem,
            bias_adj_coef=bac,
            deq_loss_factor=0.0,
        ).select("name", pl.col("deq").alias(name))
        contexts.append(df)

    metric_context = contexts[0]
    for df in contexts[1:]:
        metric_context = metric_context.join(df, on="name", how="left")

    metric_names = [v[0] for v in variants]
    metric_context = metric_context.with_columns(
        pl.lit(set_code).alias("expansion")
    ).select(
        [
            "expansion",
            "name",
            *[(pl.col(m) * PRECISION).round() / PRECISION for m in metric_names],
        ]
    )
    print(f"\nMetric context: {len(metric_context)} cards, columns: {metric_context.columns}\n")

    extra_ext = {}
    for name in metric_names:
        extra_ext.update(context_cols(name))

    print("Running p1 strategy analysis (this will take a while)...")
    result = all_metrics_analysis(
        sets=[set_code],
        metrics=metric_names,
        metric_context=metric_context,
        extra_ext=extra_ext,
    )

    result.df.write_parquet(cache_path)
    print(f"\nResult cached to {cache_path}")

    delta_cols = [f"{m}_strat_delta" for m in metric_names]
    print("\n=== Strategy win rate delta by skill cohort (pp) ===")
    print(
        result.df.select(
            pl.col("skill_cohort").str.slice(2),
            "actual_win_rate",
            *delta_cols,
        )
        .with_columns([pl.col(c) * 100 for c in delta_cols])
        .sort("skill_cohort")
    )

    print("\n=== Weighted-average delta (pp) ===")
    print(result.agg_df.select(*[pl.col(c) * 100 for c in delta_cols]))

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set_code", help="set code, e.g. SOS")
    parser.add_argument("--start", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--end", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--cache-path", default=None)
    args = parser.parse_args()
    run(args.set_code, args.start, args.end, cache_path=args.cache_path)


if __name__ == "__main__":
    main()
