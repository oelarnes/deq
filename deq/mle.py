from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

import polars as pl

from spells import summon, ColSpec, ColType, view_select, get_names, ColName
from spells.cache import save_ad_hoc_dataset, read_ad_hoc_dataset
from spells.draft_data import _get_set_context
from spells.enums import View

from deq import ext, deq_bias_set_context
from deq.deq import BASIC_LANDS, PICK_EQUITY_ARR
from deq.p1_strategy import TOP_PLAYER

TOL = 1e-5
LAMBDA = 1
set_code = "OTJ"


def pack_pick_filter(draft_filter: dict, pack_num: int, pick_num: int) -> dict:
    return {"$and": [{"pack_num": pack_num}, {"pick_num": pick_num}, draft_filter]}


def pick_equity_init_alpha(set_code: str):
    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]


def deq_init_alpha(set_code: str, metric_filter: dict | None = None):
    if metric_filter is None:
        metric_filter = TOP_PLAYER

    set_context = deq_bias_set_context([set_code], metric_filter=metric_filter)

    deq_context = summon(
        "OTJ",
        ["deq"],
        group_by=[ColName.EXPANSION, ColName.NAME],
        filter_spec=metric_filter,
        extensions=ext,
        set_context=set_context,
    )
    deq_context.filter(~pl.col("deq").is_null()).sort("deq", descending=True)
    return deq_context


def mle_ext(picks_per_pack):
    return {
        "is_pick": ColSpec(
            col_type=ColType.NAME_SUM,
            expr=lambda name: pl.when(pl.col(ColName.PICK) == name)
            .then(1)
            .otherwise(0),
        ),
        "pool_plus_pick": ColSpec(
            col_type=ColType.NAME_SUM,
            expr=lambda name: pl.col(f"is_pick_{name}") + pl.col(f"pool_{name}"),
        ),
        **{
            f"is_pick_{n}": ColSpec(
                col_type=ColType.GROUP_BY,
                expr=pl.when(pl.col(ColName.PICK_NUM) == n).then(True).otherwise(False),
            )
            for n in range(picks_per_pack + 1)  # yes, always false for zero.
        },
    }


def odds(alpha, x):
    return np.exp(np.dot(x, alpha))


def h(alpha, x):
    return 1 / (1 + odds(alpha, x))


def entropy(alpha, x, wl):
    return (
        -np.sum(
            wl[:, 0] * np.dot(x, alpha) - wl.sum(axis=1) * np.log(1 + odds(alpha, x))
        )
        / wl.sum()
    )


def grad(alpha, x, wl, l_probs):
    return (
        -np.sum(x * (wl.sum(axis=1) * l_probs - wl[:, 1])[:, None], axis=0)
        + LAMBDA * alpha
    ) / wl.sum()


def hess(x, wl, l_probs):
    accum = np.zeros([x.shape[1], x.shape[1]])
    chunk_size = int(2e8 / x.shape[1] ** 2)
    num_chunks = x.shape[0] // chunk_size
    for i in range(num_chunks):
        if not i % 10:
            print(f"Processing Hessian chunk {i} of {num_chunks}")
        accum += (
            (
                x[i * chunk_size : (i + 1) * chunk_size, :, None]
                @ x[i * chunk_size : (i + 1) * chunk_size, None, :]
            )
            * (
                wl[i * chunk_size : (i + 1) * chunk_size, :].sum(axis=1)
                * l_probs[i * chunk_size : (i + 1) * chunk_size]
                * (1 - l_probs[i * chunk_size : (i + 1) * chunk_size])
            )[:, None, None]
        ).sum(axis=0)
    accum += (
        (x[num_chunks * chunk_size :, :, None] @ x[num_chunks * chunk_size :, None, :])
        * (
            wl[num_chunks * chunk_size :, :].sum(axis=1)
            * l_probs[num_chunks * chunk_size :]
            * (1 - l_probs[num_chunks * chunk_size :])
        )[:, None, None]
    ).sum(axis=0)

    accum += LAMBDA * np.eye(x.shape[1])
    return accum / wl.sum()


@dataclass
class QOutput:
    df: pl.DataFrame
    pick_equity_df: pl.DataFrame


def find_weighted_mle(
    wl: NDArray[np.float64],
    x: NDArray[np.float64],
    alpha: NDArray[np.float64],
    train: NDArray[np.bool],
) -> NDArray:
    diff = 2 * TOL

    alpha_old = np.array(alpha)
    print(f"Starting unit entropy {entropy(alpha, x, wl):.7f}")
    while diff > TOL:
        l_probs = h(alpha, x)

        select = np.broadcast_to(train[None, :], x.shape)
        alpha_train = alpha[train]
        x_train = x[select].reshape((x.shape[0], train.sum()))

        H = hess(x_train, wl, l_probs)
        delta = -(np.linalg.inv(H) @ grad(alpha_train, x_train, wl, l_probs))
        alpha[train] += delta

        print(f"New unit entropy {entropy(alpha, x, wl):.7f}")
        diff = np.abs(alpha_old - alpha).max()
        alpha_old = np.array(alpha)
    return alpha


def test():
    set_code = "OTJ"
    pack_num = 1
    pick_num = 1
    pool_strength = np.zeros(34181)
    remaining_pick_q = p0_q(set_code) - 0.088
    draft_filter = None
    df_2 = marginal_pick_q(set_code, 1, 1, remaining_pick_q)
    df_2.filter(pl.col('weight') > 100)
    np.exp(1.42) / (np.exp(1.42) + 1)



def marginal_q_by_pick(set_code: str, draft_filter: dict | None = None):
    pack_num = 1

    remaining_equity = p0_q(set_code, draft_filter=draft_filter)

    dfs = []
    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]
    for pick_num in range(picks_per_pack):
        remaining_equity = remaining_equity - PICK_EQUITY_ARR[pick_num - 1]
        df = marginal_pick_q(set_code, pick_num, pack_num)


def marginal_pick_q(
    set_code: str,
    pack_num: int,
    pick_num: int,
    remaining_pick_q: float,  # exclusive of pick
    pool_strength: NDArray[np.float64] | None = None,  # n x 1
    draft_filter: dict | None = None,
) -> pl.DataFrame:
    if draft_filter is None:
        draft_filter = TOP_PLAYER

    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]
    wl_x = (
        view_select(
            set_code,
            View.DRAFT,
            [
                "event_match_wins_sum",
                "event_match_losses_sum",
                "is_pick",
            ],
            filter_spec=pack_pick_filter(draft_filter, pack_num, pick_num),
            extensions=mle_ext(picks_per_pack),
        )
        .collect(streaming=True)
        .filter(pl.col("event_match_wins_sum") + pl.col("event_match_losses_sum") > 0)
        .to_numpy()
    )

    if pool_strength is None:
        pool_strength = np.zeros(wl_x.shape[0])
    assert wl_x.shape[0] == pool_strength.shape[0], "Dimension mismatch"

    wl = wl_x[:, 0:2]
    x = np.concat(
        [wl_x[:, 2:], (pool_strength + remaining_pick_q)[:, None]],
        axis=1,
        dtype=np.float64,
    )

    weight = (wl.sum(axis=1)[:, None] * x).sum(axis=0)

    alpha = np.zeros(x.shape[1], dtype=np.float64)
    alpha[-1] = 1.0
    train = x.max(axis=0) > 0
    train[-1] = False

    alpha = find_weighted_mle(wl, x, alpha, train)

    names = get_names(set_code)
    df = pl.DataFrame(
        {
            "name": names,
            "q": alpha[: len(names)],
            "weight": weight[: len(names)],
        }
    ).sort("q", descending=True)

    return df


def p0_q(
    set_code: str,
    draft_filter: dict | None = None,
):
    """total remaining pick equity at pick 0,
    i.e. the marginal win rate of the whole cohort"""

    if draft_filter is None:
        draft_filter = TOP_PLAYER

    wl_x = (
        view_select(
            set_code,
            View.DRAFT,
            [
                "event_match_wins_sum",
                "event_match_losses_sum",
            ],
            filter_spec=pack_pick_filter(draft_filter, 1, 1),
        )
        .with_columns(pl.lit(1))
        .filter(pl.col("event_match_wins_sum") + pl.col("event_match_losses_sum") > 0)
        .collect(streaming=True)
        .to_numpy()
    )

    wl = wl_x[:, 0:2]
    x = wl_x[:, 2:]
    alpha = np.zeros(x.shape[1])
    train = np.ones(x.shape[1], dtype=np.bool)

    q = find_weighted_mle(wl, x, alpha, train)

    wr = summon(
        set_code,
        ["picked_match_wr"],
        group_by=[],
        filter_spec={"$and": [{"pack_num": 1}, {"pick_num": 1}, draft_filter]},
    )

    # the MLE should give the mean win rate
    assert np.abs((np.exp(q) / (1 + np.exp(q)))[0] - wr["picked_match_wr"][0]) < TOL

    return float(q[0])


def draft_equity(
    set_code: str,
    pack_num: int,
    threshold_pct_gp: float = 0.05,
    draft_filter: dict | None = None,
    read_cache: bool = True,
    write_cache: bool = True,
    null_cards: list | None = None,
) -> QOutput:
    null_cards_text = "_null_cards" if null_cards is not None else ""
    cache_keys = {
        "draft_equity": f"draft_equity_{set_code}_pack{pack_num}_tresholdpctgp{int(100 * threshold_pct_gp)}{null_cards_text}",
        "pick_equity": f"pick_equity_{set_code}_pack{pack_num}_tresholdpctgp{int(100 * threshold_pct_gp)}{null_cards_text}",
    }

    if draft_filter is None:
        default_filter = True
        draft_filter = TOP_PLAYER
    else:
        default_filter = False

    if default_filter and read_cache:
        df = read_ad_hoc_dataset(cache_keys["draft_equity"])
        pick_equity_df = read_ad_hoc_dataset(cache_keys["pick_equity"])

        if df is not None and pick_equity_df is not None:
            return QOutput(df=df, pick_equity_df=pick_equity_df)

    if null_cards is None:
        # 1. Determine cards for zero draft equity
        null_card_df = summon(set_code, ["pct_gp"], filter_spec=draft_filter).filter(
            (pl.col("pct_gp") < threshold_pct_gp) | pl.col("name").is_in(BASIC_LANDS)
        )

        null_cards = null_card_df["name"].to_list()
        bad_drafts = (
            (
                view_select(set_code, View.GAME, ["draft_id", "deck"], draft_filter)
                .filter(
                    pl.sum_horizontal(
                        [
                            pl.col(f"deck_{name}")
                            for name in set(null_cards) - set(BASIC_LANDS)
                        ]
                    )
                    > 0
                )
                .collect(streaming=True)
            )["draft_id"]
            .unique()
            .to_list()
        )
        print(f"Throwing out {len(bad_drafts)} drafts due to playing null cards")
    else:
        bad_drafts = []

    assert len(
        null_cards
    ), f"No cards found with GP% below threshold {threshold_pct_gp}!"

    # 2. Get training data
    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]
    wl_x = np.concat(
        [
            (
                view_select(
                    set_code,
                    View.DRAFT,
                    [
                        "draft_id",
                        "event_match_wins_sum",
                        "event_match_losses_sum",
                        "pool",
                    ],
                    filter_spec={
                        "$and": [{"pack_num": pack_num}, {"pick_num": 1}, draft_filter]
                    },
                )
                .filter(~pl.col("draft_id").is_in(bad_drafts))
                .filter(
                    pl.col("event_match_wins_sum") + pl.col("event_match_losses_sum")
                    > 0
                )
                .drop("draft_id")
                .collect(streaming=True)
                .with_columns(
                    [
                        pl.lit(True).alias(f"is_pick_{i}")
                        if i == 0
                        else pl.lit(False).alias(f"is_pick_{i}")
                        for i in range(picks_per_pack + 1)
                    ]
                )
                .to_numpy()
            ),
            (
                view_select(
                    set_code,
                    View.DRAFT,
                    [
                        "draft_id",
                        "event_match_wins_sum",
                        "event_match_losses_sum",
                        "pool_plus_pick",
                        *[f"is_pick_{n}" for n in range(picks_per_pack + 1)],
                    ],
                    extensions=mle_ext(picks_per_pack),
                    filter_spec={"$and": [{"pack_num": pack_num}, draft_filter]},
                )
                .filter(~pl.col("draft_id").is_in(bad_drafts))
                .filter(
                    pl.col("event_match_wins_sum") + pl.col("event_match_losses_sum")
                    > 0
                )
                .drop("draft_id")
                .collect(streaming=True)
                .to_numpy()
            ),
        ],
        axis=0,
    )
    print(f"Training on {wl_x.shape[0]} picks.")

    wl = wl_x[:, 0:2]
    x = wl_x[:, 2:]
    alpha = np.zeros(x.shape[1])

    names = get_names(set_code)

    train = np.concat(
        [
            np.array([name not in null_cards for name in names]),
            np.ones(picks_per_pack + 1),
        ]
    ).astype(np.bool)
    assert train.shape == alpha.shape, "train mask or alpha wrong shape"

    alpha = find_weighted_mle(wl=wl, x=x, alpha=alpha, train=train)

    df = pl.DataFrame({"name": names, "q": alpha[: len(names)]}).sort(
        "q", descending=True
    )

    pick_equity_df = pl.DataFrame(
        {
            "pick_num": np.arange(0, picks_per_pack + 1),
            "remaining_pick_equity": alpha[-picks_per_pack - 1 :],
        }
    )

    if default_filter and write_cache:
        save_ad_hoc_dataset(df, cache_keys["draft_equity"])
        save_ad_hoc_dataset(pick_equity_df, cache_keys["pick_equity"])

    return QOutput(df=df, pick_equity_df=pick_equity_df)
