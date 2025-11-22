from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy.optimize import minimize

from spells import ColSpec, ColName, summon, ColType
from spells.columns import agg_col
from spells.extension import context_cols

from deq.main import ext
from deq.mle import pick_priority

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


def three_factor_opt(
    set_codes: str | list[str],
) -> NDArray[np.float64]:
    """
    Use scipy.optimize to find a, b, c to best fit a NPR model to 
    the optimal softmax pick priority solution.

    All logs are natural in this model, convert to base 2 at the end
    """

    if isinstance(set_codes, str):
        set_codes = [set_codes]

    concat_list = []
    for set_code in set_codes:
        priority_df = pick_priority(set_code)
        card_data_df = prl_df(set_code)

        concat_list.append(card_data_df.join(priority_df, on="name"))

    join_df = pl.concat(concat_list)

    rho = join_df.select('pick_rate_logit_seen').to_numpy()[:,0]
    alsa = join_df.select('alsa').to_numpy()[:,0]
    theta = join_df.select('theta').to_numpy()[:,0]

    train = ~(np.isnan(rho) | np.isnan(alsa) | np.isnan(theta))

    r_t = rho[train]
    a_t = alsa[train]
    t_t = theta[train]

    A = np.stack([np.ones(t_t.shape), r_t, a_t, a_t ** 2], axis=1)

    sol = np.linalg.lstsq(A, t_t)

    return sol[0].astype(np.float64)

    

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


def pack_odds_df(
    set_code: str, filter_spec: dict[str, Any] | None = None
) -> pl.DataFrame:
    if filter_spec is None:
        filter_spec = DEFAULT_FILTER

    pack_one_filter = {"$and": [filter_spec, {"pack_num": 1}]}

    df = prl_df(set_code, filter_spec).select("name", "pick_odds")

    ext = {
        **context_cols("pick_odds"),
        "seen_pick_odds_pack_mean": agg_col(
            pl.col("seen_pick_odds_pack_sum") / pl.col("num_taken")
        ),
        "seen_pick_odds_log": agg_col(pl.col("seen_pick_odds_pack_mean")),
    }

    return summon(
        set_code,
        ["seen_pick_odds_log", "num_taken"],
        group_by=["pick_num"],
        filter_spec=pack_one_filter,
        card_context=df,
        extensions=ext,
    )
