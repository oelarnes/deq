from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

import polars as pl

from spells import summon, ColSpec, ColType, view_select, get_names, ColName
from spells.draft_data import _get_set_context
from spells.enums import View

from deq import ext, deq_bias_set_context
from deq.deq import BASIC_LANDS
from deq.p1_strategy import TOP_PLAYER

set_code = "OTJ"

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
        "pool_plus_pick": ColSpec(
            col_type=ColType.NAME_SUM,
            expr=lambda name: pl.when(pl.col(ColName.PICK) == name)
            .then(pl.col(f"pool_{name}") + 1)
            .otherwise(f"pool_{name}"),
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


def grad(alpha, x, wl):
    return (
        -np.sum(x * (wl.sum(axis=1) * h(alpha, x) - wl[:, 1])[:, None], axis=0)
        / wl.sum()
    )


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
    tol: float,
) -> NDArray:
    diff = 2 * tol

    score_old = entropy(alpha, x, wl)
    print(f"Starting unit entropy {score_old:.7f}")
    while diff > tol:
        l_probs = h(alpha, x)

        alpha_train = alpha[train]

        select = np.broadcast_to(train[None, :], x.shape)
        x_train = x[select].reshape((x.shape[0], train.sum()))

        H = hess(x_train, wl, l_probs)
        delta = -(np.linalg.inv(H) @ grad(alpha_train, x_train, wl))
        alpha[train] += delta

        score_new = entropy(alpha, x, wl)
        print(f"New unit entropy {score_new:.7f}")
        diff = score_old - score_new
        score_old = score_new
    return alpha


def marginal_pick_q(
    set_code: str,
    pack_num: int,
    pick_num: int,
    pool_alpha: NDArray,
    threshold_pct_gp: float = 0.05,
    tol: float = 1e-6,
) -> QOutput: ...


def draft_equity(
    set_code: str, pack_num: int, threshold_pct_gp: float = 0.05, tol: float = 1e-8
) -> QOutput:
    # 1. Determine cards for zero draft equity
    null_card_df = summon(set_code, ["pct_gp"], filter_spec=TOP_PLAYER).filter(
        (pl.col("pct_gp") < threshold_pct_gp) | pl.col("name").is_in(BASIC_LANDS)
    )

    null_cards = null_card_df["name"].to_list()
    assert len(
        null_cards
    ), f"No cards found with GP% below threshold {threshold_pct_gp}!"

    bad_drafts = (
        (
            view_select(set_code, View.GAME, ["draft_id", "deck"], TOP_PLAYER)
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
    print(f"Throwing out {len(bad_drafts)} drafts due to drafting null cards")

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
                        "$and": [{"pack_num": pack_num}, {"pick_num": 1}, TOP_PLAYER]
                    },
                )
                .filter(~pl.col("draft_id").is_in(bad_drafts))
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
                    filter_spec={"$and": [{"pack_num": pack_num}, TOP_PLAYER]},
                )
                .filter(~pl.col("draft_id").is_in(bad_drafts))
                .drop("draft_id")
                .collect(streaming=True)
                .to_numpy()
            ),
        ],
        axis=0,
    )

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

    alpha = find_weighted_mle(wl=wl, x=x, alpha=alpha, train=train, tol=tol)

    names_df = pl.DataFrame({"name": names, "q": alpha[: len(names)] / 4}).sort(
        "q", descending=True
    )

    pick_equity = pl.DataFrame(
        {
            "pick_num": np.arange(1, picks_per_pack + 2),
            "pick_equity": alpha[-picks_per_pack - 1 :] / 4,
        }
    )

    return QOutput(df=names_df, pick_equity_df=pick_equity)


o1 = draft_equity("OTJ", 1)
o2 = draft_equity("OTJ", 2)
o3 = draft_equity("OTJ", 3)
