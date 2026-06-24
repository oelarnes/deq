"""P1 strategy analysis across all metrics (DEq, raw 17lands rates, gp_gih_avg).

Simulates picking P1P1 by each metric and reports win-rate deltas by skill
cohort. Importable as `deq.ai.p1.run(set_code)` or runnable as a script:

    pdm run python -m deq.ai.p1 SOS
"""

import argparse
import datetime as dt

import polars as pl

from spells.extension import context_cols
from deq.p1_strategy import all_metrics_analysis
from deq.ai.context import ALL_METRICS, build_metric_context, resolve_dates


def run(
    set_code: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    cache_path: str | None = None,
):
    """Run all-metrics p1 strategy analysis for `set_code`.

    Dates default to the observed range in the local draft parquet.
    """
    start_date, end_date = resolve_dates(set_code, start_date, end_date)
    cache_path = cache_path or f"/tmp/p1_{set_code}_result.parquet"

    print(f"Building {set_code} metric context from cdfs ({start_date} to {end_date})...")
    metric_context = build_metric_context(set_code, start_date, end_date)
    print(f"Metric context: {len(metric_context)} cards, columns: {metric_context.columns}")

    print(f"\nRunning p1 strategy analysis for {set_code} (this will take a while)...")
    result = all_metrics_analysis(
        sets=[set_code],
        metrics=ALL_METRICS,
        metric_context=metric_context,
        extra_ext=context_cols("gp_gih_avg"),
    )

    result.df.write_parquet(cache_path)
    print(f"\nResult cached to {cache_path}")

    print("\n=== Strategy win rate delta by skill cohort ===")
    delta_cols = [c for c in result.df.columns if c.endswith("_strat_delta")]
    print(
        result.df.select(
            pl.col("skill_cohort").str.slice(2),
            "actual_win_rate",
            *delta_cols,
        ).sort("skill_cohort")
    )

    print("\n=== Weighted-average delta across all cohorts ===")
    print(result.agg_df)

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set_code", help="set code, e.g. SOS")
    parser.add_argument("--start", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--end", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--cache-path", default=None)
    args = parser.parse_args()
    run(args.set_code, args.start, args.end, args.cache_path)


if __name__ == "__main__":
    main()
