"""Shared helpers for the deq.ai analytic explorations.

These build the `metric_context` DataFrame that p1 strategy analysis consumes,
and read the observed date window straight out of the local draft parquet so
callers don't have to hard-code dates.
"""

import datetime as dt

import polars as pl

from spells import summon
from spells.cache import EventType, data_file_path
from spells.columns import agg_col
from spells.draft_data import CardDataFileSpec
from spells.enums import ColName
from deq.main import ext, live_deq
from deq.p1_strategy import METRICS, PRECISION
from deq.set_config import config

# gp_gih_avg: a derived metric averaging the two raw 17lands win rates.
CUSTOM_METRICS = ["gp_gih_avg"]
ALL_METRICS = METRICS + CUSTOM_METRICS

ext_with_avg = {
    **ext,
    "gp_gih_avg": agg_col((pl.col("gih_wr_17l") + pl.col("gp_wr_17l")) / 2),
}

# Rates pulled from summon (all AGG columns, safe with cdfs).
RATE_METRICS = ["gih_wr_17l", "gp_wr_17l", "iwd_17l", "gp_gih_avg"]
# Metrics that come from live_deq rather than summon.
DEQ_METRICS = ["deq", "pick_equity"]


def event_type_for(set_code: str) -> EventType:
    return (
        EventType.PICK_TWO if config[set_code].is_pick_two else EventType.PREMIER
    )


def parquet_date_range(set_code: str) -> tuple[dt.date, dt.date]:
    """Observed [start, end] dates from the local draft parquet's draft_time.

    draft_time is a 'YYYY-MM-DD HH:MM:SS' string; we take the date part of the
    min and max.
    """
    path = data_file_path(set_code, "draft", event_type_for(set_code))
    bounds = (
        pl.scan_parquet(path)
        .select(
            pl.col(ColName.DRAFT_TIME).min().str.slice(0, 10).alias("start"),
            pl.col(ColName.DRAFT_TIME).max().str.slice(0, 10).alias("end"),
        )
        .collect()
    )
    start = dt.date.fromisoformat(bounds["start"][0])
    end = dt.date.fromisoformat(bounds["end"][0])
    return start, end


def resolve_dates(
    set_code: str,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> tuple[dt.date, dt.date]:
    """Fill in either missing date bound from the parquet's observed range."""
    if start_date is not None and end_date is not None:
        return start_date, end_date
    obs_start, obs_end = parquet_date_range(set_code)
    return start_date or obs_start, end_date or obs_end


def build_metric_context(
    set_code: str,
    start_date: dt.date,
    end_date: dt.date,
    metrics: list[str] = ALL_METRICS,
) -> pl.DataFrame:
    """Assemble a metric_context df matching get_metric_context's output format.

    DEq and pick_equity come from live_deq (which applies meta_regression_factor
    correctly); the raw win-rate metrics come from summon over the cdfs window.
    Only the requested `metrics` are kept, precision-rounded.
    """
    deq_context = live_deq(
        set_code, start_date=start_date, end_date=end_date
    ).select("name", *DEQ_METRICS)

    cdfs = CardDataFileSpec(
        set_code=set_code,
        format=event_type_for(set_code),
        player_cohort="top",
        start_date=start_date,
        end_date=end_date,
    )
    rates_context = summon(
        set_code,
        columns=RATE_METRICS,
        extensions=ext_with_avg,
        cdfs=cdfs,
    ).select("name", *RATE_METRICS)

    return (
        deq_context.join(rates_context, on="name", how="left")
        .with_columns(pl.lit(set_code).alias("expansion"))
        .select(
            [
                "expansion",
                "name",
                *[(pl.col(m) * PRECISION).round() / PRECISION for m in metrics],
            ]
        )
    )
