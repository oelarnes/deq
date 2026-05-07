"""
P1 strategy analysis for SOS using latest cached cdfs data.
Metric context is built from the daily API pull since game parquet isn't available yet.
- DEq/pick_equity come from live_deq (handles the CARD_ATTR meta_regression_factor correctly)
- gih_wr_17l, gp_wr_17l, iwd_17l come from summon with ext only (all AGG columns)
Results are cached to /tmp/p1_sos_result.parquet.
"""

import datetime as dt
import polars as pl

from spells import summon
from spells.columns import agg_col
from spells.draft_data import CardDataFileSpec
from spells.extension import context_cols
from deq.main import ext, live_deq
from deq.p1_strategy import all_metrics_analysis, METRICS, PRECISION

SET_CODE = "SOS"
START_DATE = dt.date(2026, 4, 25)  # latest cached pull
END_DATE = dt.date(2026, 5, 6)
CACHE_PATH = "/tmp/p1_sos_result.parquet"

CUSTOM_METRICS = ["gp_gih_avg"]
ALL_METRICS = METRICS + CUSTOM_METRICS

ext_with_avg = {
    **ext,
    "gp_gih_avg": agg_col((pl.col("gih_wr_17l") + pl.col("gp_wr_17l")) / 2),
}

print(f"Building SOS metric context from cdfs ({START_DATE} to {END_DATE})...")

# live_deq handles deq + pick_equity correctly (applies meta_regression_factor via with_columns)
deq_df = live_deq(SET_CODE, start_date=START_DATE, end_date=END_DATE)
deq_context = deq_df.select("name", "deq", "pick_equity")
print(f"DEq context: {len(deq_context)} cards")

# gih_wr_17l, gp_wr_17l, iwd_17l are all AGG columns in ext — safe for cdfs summon
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
print(f"Rates context: {len(rates_context)} cards")

# Join into single metric_context df matching get_metric_context output format
metric_context = (
    deq_context.join(rates_context, on="name", how="left")
    .with_columns(pl.lit(SET_CODE).alias("expansion"))
    .select(["expansion", "name", *[(pl.col(m) * PRECISION).round() / PRECISION for m in ALL_METRICS]])
)
print(f"Metric context columns: {metric_context.columns}")

print("\nRunning p1 strategy analysis for SOS (this will take a while)...")
result = all_metrics_analysis(
    sets=[SET_CODE],
    metrics=ALL_METRICS,
    metric_context=metric_context,
    extra_ext=context_cols("gp_gih_avg"),
)

result.df.write_parquet(CACHE_PATH)
print(f"\nResult cached to {CACHE_PATH}")

print("\n=== Strategy win rate delta by skill cohort ===")
delta_cols = [c for c in result.df.columns if c.endswith("_strat_delta")]
print(result.df.select(
    pl.col("skill_cohort").str.slice(2),
    "actual_win_rate",
    *delta_cols,
).sort("skill_cohort"))

print("\n=== Weighted-average delta across all cohorts ===")
print(result.agg_df)
