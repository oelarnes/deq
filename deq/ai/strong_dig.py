"""Dig into a single skill cohort card-by-card for gp_gih_avg vs deq.

Re-runs p1_strat_analysis for those two metrics and inspects the mapped_df to
see which cards drive the cohort's outperformance.

Importable as `deq.ai.strong_dig.run(set_code)` or runnable as a script:

    pdm run python -m deq.ai.strong_dig SOS --cohort 5_Strong
"""

import argparse
import datetime as dt

import polars as pl

from spells.extension import context_cols
from deq.p1_strategy import p1_strat_analysis
from deq.ai.context import build_metric_context, resolve_dates

DEFAULT_COHORT = "5_Strong"


def _top_cards(mapped_df, metric, cohort, actual_wr, n=20):
    return (
        mapped_df.filter(pl.col("skill_cohort") == cohort)
        .select(
            "name",
            f"seen_{metric}_is_greatest",
            "weight",
            (pl.col("win_weight") / pl.col("weight")).round(4).alias("subst_wr"),
            ((pl.col("win_weight") / pl.col("weight") - actual_wr) * 100)
            .round(2)
            .alias("delta_vs_actual_pp"),
            "representation_class",
            metric,
        )
        .sort("weight", descending=True)
        .head(n)
    )


def run(
    set_code: str,
    cohort: str = DEFAULT_COHORT,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
):
    """Inspect `cohort` for deq vs gp_gih_avg over the parquet date window."""
    start_date, end_date = resolve_dates(set_code, start_date, end_date)

    print(f"Building metric context for {set_code} ({start_date} to {end_date})...")
    metric_context = build_metric_context(
        set_code, start_date, end_date, metrics=["deq", "gp_gih_avg"]
    )

    print("Running p1_strat_analysis for deq and gp_gih_avg...")
    deq_result = p1_strat_analysis(
        set_codes=[set_code],
        metric="deq",
        metric_context=metric_context,
    )
    avg_result = p1_strat_analysis(
        set_codes=[set_code],
        metric="gp_gih_avg",
        metric_context=metric_context,
        extra_ext=context_cols("gp_gih_avg"),
    )

    actual_wr = deq_result.df.filter(pl.col("skill_cohort") == cohort)[
        "actual_win_rate"
    ][0]
    print(f"\n{cohort} cohort actual WR: {actual_wr:.4f}")

    print(f"\n=== Top cards by weight — gp_gih_avg, {cohort} cohort ===")
    print(_top_cards(avg_result.mapped_df, "gp_gih_avg", cohort, actual_wr))

    print(f"\n=== Top cards by weight — deq, {cohort} cohort ===")
    print(_top_cards(deq_result.mapped_df, "deq", cohort, actual_wr))

    # Cards gp_gih_avg recommends that deq gives no weight to.
    print(f"\n=== Cards gp_gih_avg picks but deq doesn't ({cohort} cohort, top by weight) ===")
    avg_cohort = avg_result.mapped_df.filter(pl.col("skill_cohort") == cohort)
    deq_cohort = deq_result.mapped_df.filter(pl.col("skill_cohort") == cohort)
    avg_only = (
        avg_cohort.join(
            deq_cohort.select(
                "name", pl.col("seen_deq_is_greatest").alias("deq_weight")
            ),
            on="name",
            how="left",
        )
        .filter(pl.col("deq_weight").is_null() | (pl.col("deq_weight") == 0))
        .with_columns(
            (pl.col("win_weight") / pl.col("weight")).round(4).alias("subst_wr"),
        )
        .select("name", "weight", "subst_wr", "representation_class", "gp_gih_avg")
        .sort("weight", descending=True)
        .head(15)
    )
    print(avg_only)

    return deq_result, avg_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set_code", help="set code, e.g. SOS")
    parser.add_argument("--cohort", default=DEFAULT_COHORT)
    parser.add_argument("--start", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--end", type=dt.date.fromisoformat, default=None)
    args = parser.parse_args()
    run(args.set_code, args.cohort, args.start, args.end)


if __name__ == "__main__":
    main()
