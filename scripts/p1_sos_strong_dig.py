"""
Dig into the Strong cohort card-by-card for gp_gih_avg vs deq.
Re-runs p1_strat_analysis for just those two metrics, then inspects
the mapped_df to see which cards are driving the Strong cohort outperformance.
"""

import datetime as dt
import polars as pl

from spells import summon
from spells.columns import agg_col
from spells.draft_data import CardDataFileSpec
from spells.extension import context_cols
from deq.main import ext, live_deq
from deq.p1_strategy import p1_strat_analysis, PRECISION

SET_CODE = "SOS"
START_DATE = dt.date(2026, 4, 25)
END_DATE = dt.date(2026, 5, 6)
STRONG = "5_Strong"

ext_with_avg = {
    **ext,
    "gp_gih_avg": agg_col((pl.col("gih_wr_17l") + pl.col("gp_wr_17l")) / 2),
}

print("Building metric context...")
deq_df = live_deq(SET_CODE, start_date=START_DATE, end_date=END_DATE)
deq_context = deq_df.select("name", "deq", "pick_equity")

cdfs = CardDataFileSpec(
    set_code=SET_CODE,
    format="PremierDraft",
    player_cohort="top",
    start_date=START_DATE,
    end_date=END_DATE,
)
rates_context = summon(
    SET_CODE,
    columns=["gih_wr_17l", "gp_wr_17l", "iwd_17l", "gp_gih_avg"],
    extensions=ext_with_avg,
    cdfs=cdfs,
).select("name", "gih_wr_17l", "gp_wr_17l", "iwd_17l", "gp_gih_avg")

metric_context = (
    deq_context.join(rates_context, on="name", how="left")
    .with_columns(pl.lit(SET_CODE).alias("expansion"))
    .select(["expansion", "name", *[(pl.col(m) * PRECISION).round() / PRECISION for m in ["deq", "gp_gih_avg"]]])
)

print("Running p1_strat_analysis for deq and gp_gih_avg...")
deq_result = p1_strat_analysis(
    set_codes=[SET_CODE],
    metric="deq",
    metric_context=metric_context,
)
avg_result = p1_strat_analysis(
    set_codes=[SET_CODE],
    metric="gp_gih_avg",
    metric_context=metric_context,
    extra_ext=context_cols("gp_gih_avg"),
)

actual_wr = deq_result.df.filter(pl.col("skill_cohort") == STRONG)["actual_win_rate"][0]
print(f"\nStrong cohort actual WR: {actual_wr:.4f}")

def top_cards(mapped_df, metric, cohort, n=20):
    return (
        mapped_df
        .filter(pl.col("skill_cohort") == cohort)
        .with_columns(
            (pl.col("win_weight") / pl.col("weight")).alias("subst_wr"),
            (pl.col("win_weight") / pl.col("weight") - actual_wr).alias("wr_vs_actual"),
        )
        .select(
            "name",
            f"seen_{metric}_is_greatest",
            "weight",
            (pl.col("win_weight") / pl.col("weight")).round(4).alias("subst_wr"),
            ((pl.col("win_weight") / pl.col("weight") - actual_wr) * 100).round(2).alias("delta_vs_actual_pp"),
            "representation_class",
            metric,
        )
        .sort("weight", descending=True)
        .head(n)
    )

print(f"\n=== Top cards by weight — gp_gih_avg, Strong cohort ===")
print(top_cards(avg_result.mapped_df, "gp_gih_avg", STRONG))

print(f"\n=== Top cards by weight — deq, Strong cohort ===")
print(top_cards(deq_result.mapped_df, "deq", STRONG))

# Cards where gp_gih_avg recommends something different from deq
print("\n=== Cards gp_gih_avg picks but deq doesn't (Strong cohort, top by weight) ===")
avg_strong = avg_result.mapped_df.filter(pl.col("skill_cohort") == STRONG)
deq_strong = deq_result.mapped_df.filter(pl.col("skill_cohort") == STRONG)

avg_only = (
    avg_strong
    .join(
        deq_strong.select("name", pl.col("seen_deq_is_greatest").alias("deq_weight")),
        on="name", how="left"
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
