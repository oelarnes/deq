from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray

from spells import ColSpec, ColName, summon, ColType
from spells.columns import agg_col
from spells.extension import context_cols

from deq.main import ext, ALSA_PRL_BETA, NPR_P1_OFFSET

ext = {
    **ext,
    "pick_odds": agg_col((pl.lit(2.0).log() * pl.col("npr")).exp()),
}

DEFAULT_FILTER = {
    "$and": [
        {"player_cohort": "Top"},
        {"lhs": "format_day", "op": ">", "rhs": 7},
    ]
}


def prl_df(set_code: str, filter_spec: dict[str, Any] | None = None) -> pl.DataFrame:
    if filter_spec is None:
        filter_spec = DEFAULT_FILTER

    return summon(
        set_code,
        [
            "pick_odds",
            "npr",
            "npr_seen",
            "alsa",
            "pick_rate_logit",
            "pick_rate_logit_seen",
            "num_seen",
            "num_taken",
            "pack_card",
            "rarity",
            "ata",
        ],
        filter_spec=filter_spec,
        extensions=ext,
    )


def by_pick_df(
    set_code: str, filter_spec: dict[str, Any] | None = None
) -> pl.DataFrame:
    if filter_spec is None:
        filter_spec = DEFAULT_FILTER

    pack_one_filter = {"$and": [filter_spec, {"pack_num": 1}]}

    return summon(
        set_code,
        ["pick_rate_logit", "num_seen", "num_taken", "pack_card", "rarity"],
        group_by=["name", "pick_num"],
        filter_spec=pack_one_filter,
        extensions=ext,
    )


def npr_curve(
    alsa: float,
    prl: float,
    alsa_prl_beta: float = ALSA_PRL_BETA,
    npr_p1_offset: float = NPR_P1_OFFSET,
):
    X = np.arange(1.0, alsa, step=0.01, dtype=np.float64)
    Y = (
        prl
        + ALSA_PRL_BETA * (X - alsa)
        - NPR_P1_OFFSET
        / 4.0
        * ((X <= 3.0) * (X - 3.0) ** 2 - (alsa <= 3.0) * (alsa - 3.0) ** 2)
    )

    return (X, Y)


def pack_odds_df(
    set_code: str, filter_spec: dict[str, Any] | None = None
) -> pl.DataFrame:
    if filter_spec is None:
        filter_spec = DEFAULT_FILTER

    pack_one_filter = {"$and": [filter_spec, {"pack_num": 1}]}

    df = prl_df(set_code, filter_spec).select("name", "pick_odds")

    ext = {
        **context_cols("pick_odds"),
        "seen_pick_odds_pack_mean": agg_col(pl.col("seen_pick_odds_pack_sum") / pl.col('num_taken')),
        "seen_pick_odds_log": agg_col(pl.col("seen_pick_odds_pack_mean").log(2))
    }

    return summon(
        set_code,
        ["seen_pick_odds_log", "num_taken"],
        group_by=["pick_num"],
        filter_spec=pack_one_filter,
        card_context=df,
        extensions=ext,
    )
