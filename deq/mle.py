from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csc_array

import polars as pl

from spells import summon, ColSpec, ColType, lazy_select, get_names, ColName
from spells.cache import save_ad_hoc_dataset, read_ad_hoc_dataset
from spells.draft_data import _get_set_context
from spells.enums import View

from deq import ext, deq_bias_set_context
from deq.main import BASIC_LANDS
from deq.p1_strategy import TOP_PLAYER

TOL = 1e-5
LAMBDA = 100
set_code = "OTJ"


def pack_pick_filter(draft_filter: dict, pack_num: int, pick_num: int) -> dict:
    return {"$and": [{"pack_num": pack_num}, {"pick_num": pick_num}, draft_filter]}


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


def hess_diag(x, wl, l_probs):
    return (
        ((wl.sum(axis=1) * l_probs * (1 - l_probs))[:, None] * x**2).sum(axis=0)
        + LAMBDA * np.ones(x.shape[1])
    ) / wl.sum()


def hess(x, wl, l_probs):
    accum = np.zeros([x.shape[1], x.shape[1]])
    chunk_size = int(2e8 / x.shape[1] ** 2)
    num_chunks = (x.shape[0] - 1) // chunk_size + 1
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

    accum += LAMBDA * np.eye(x.shape[1])
    return accum / wl.sum()


@dataclass
class QOutput:
    df: pl.DataFrame
    pick_equity_df: pl.DataFrame


@dataclass
class MarginalQOutput:
    df: pl.DataFrame
    pool_strength: NDArray[np.float64]


def find_weighted_mle(
    wl: NDArray[np.float64],
    x: NDArray[np.float64],
    alpha: NDArray[np.float64],
    train: NDArray[np.bool],
    diag: bool = False,
) -> NDArray[np.float64]:
    diff = 2 * TOL

    alpha_old = np.array(alpha)
    print(f"Starting unit entropy {entropy(alpha, x, wl):.7f}")
    while diff > TOL:
        l_probs = h(alpha, x)

        select = np.broadcast_to(train[None, :], x.shape)
        alpha_train = alpha[train]
        x_train = x[select].reshape((x.shape[0], train.sum()))

        if diag:
            H = hess_diag(x_train, wl, l_probs)
            delta = -1 / H * grad(alpha_train, x_train, wl, l_probs)

        else:
            H = hess(x_train, wl, l_probs)
            delta = -np.linalg.inv(H) @ grad(alpha_train, x_train, wl, l_probs)

        alpha[train] += delta

        print(f"New unit entropy {entropy(alpha, x, wl):.7f}")
        diff = np.abs(alpha_old - alpha).max()
        alpha_old = np.array(alpha)
    return alpha


def softmax_entropy(theta, x, y):
    odds = x * np.exp(theta)[None, :]
    return (np.log(odds.sum(axis=1)) - (y * theta[None, :]).sum(axis=1)).sum()


def p_vec(theta, x) -> csc_array:
    odds = x * np.exp(theta)[None, :]
    return csc_array(odds / odds.sum(axis=1)[:, None])


def softmax_grad(p, y):
    return (p - y).sum(axis=0)


def softmax_hess(p: csc_array) -> NDArray[np.float64]:
    assert p.shape is not None

    outer_product_rows = []
    for i in range(p.shape[1]):
        outer_product_rows.append((p * p[:, i : i + 1]).sum(axis=0))

    outer_product = np.stack(outer_product_rows)
    return np.diag(p.sum(axis=0)) - outer_product


def softmax_prep(
    x_raw: csc_array,
    y_raw: csc_array,
    theta_max: float,
    zero_ind: int,
) -> tuple[csc_array, csc_array, NDArray[np.float64], NDArray[np.bool]]:
    """
    Take the raw x, y, return a filtered set of x, y and a train
    mask such that there are nontrivial choices on each
    dimension under the train mask and the Hessian is nonsingular.

    Set theta to theta_min for dimensions without nontrivial choices,
    and set theta to zero for the dimension near the mean selection rate
    """
    assert x_raw.shape and y_raw.shape
    k = x_raw.shape[1]

    theta = np.zeros(k)
    train = np.full(k, True)

    nontrivial_choice = x_raw.sum(axis=1) > 1
    x = x_raw[nontrivial_choice]
    y = y_raw[nontrivial_choice]

    never = (y.sum(axis=0) == 0) & (x.sum(axis=0) > 0)
    theta[never] = -theta_max

    always = (y.sum(axis=0) == x.sum(axis=0)) & (y.sum(axis=0) > 0)
    theta[always] = theta_max

    train = (x.sum(axis=0) > 0) & ~never & ~always
    assert train[zero_ind], "Bad zero index provided"

    pick_counts = y.sum(axis=0)[train]
    pack_counts = x.sum(axis=0)[train]

    pick_rates = pick_counts / pack_counts
    log_odds = np.log(pick_rates / (1 - pick_rates))
    log_odds -= log_odds[np.where(train)[0] == zero_ind][0]

    theta[train] = log_odds
    train[zero_ind] = False

    return x, y, theta, train


def softmax_solve(
    x_raw: csc_array,
    y_raw: csc_array,
    zero_ind: int = 0,
    tol=1e-8,
    theta_max=10,
    iters=None,
):
    x, y, theta, train = softmax_prep(x_raw, y_raw, theta_max, zero_ind)
    assert x.shape and y.shape

    y_train = y[:, train]

    done = ~train.max()
    i = 0
    while not done and (iters is None or i < iters):
        starting_entropy = softmax_entropy(theta, x, y)
        print(f"Entropy: {starting_entropy}")
        p = p_vec(theta, x)
        p_train = p[:, train]

        H = softmax_hess(p_train)
        update = np.linalg.solve(H, softmax_grad(p_train, y_train))
        theta[train] -= update
        new_entropy = softmax_entropy(theta, x, y)

        # overshoot protection
        damp = 1
        while new_entropy > starting_entropy + tol:
            damp *= 0.5
            theta[train] += damp * update
            new_entropy = softmax_entropy(theta, x, y)

        print(f"Calculated step size {(jump := (update ** 2).sum())} damped to {damp}")
        if jump < tol:
            done = True
        i += 1

    print(f"Entropy: {softmax_entropy(theta, x, y)}")
    theta[x.sum(axis=0) == 0] = np.nan
    return theta


def pick_priority(
    set_code: str,
    pack_one_only: bool = False,
    read_cache: bool = True,
    write_cache: bool = True,
) -> pl.DataFrame:
    if pack_one_only:
        pick_filter = {
            '$and': [
                {'player_cohort': 'Top'},
                {'lhs': "format_day", "op": ">", "rhs": 7},
                {'pack_num': 1}
            ]
        }
    else:
        pick_filter = {
            '$and': [
                {'player_cohort': 'Top'},
                {'lhs': "format_day", "op": ">", "rhs": 7}
            ]
        }

    ad_hoc_filename = f"{set_code}_{'pack_one' if pack_one_only else 'all'}_pick_priority"

    if read_cache:
        df = read_ad_hoc_dataset(ad_hoc_filename)
        if df is not None:
            return df

    pick_x = csc_array(
        lazy_select(
            set_code,
            View.DRAFT,
            [
                "is_pick",
                "pack_card",
            ],
            filter_spec=pick_filter,
            extensions=mle_ext(14),
        )
        .collect(streaming=True)
        .to_numpy()
    )

    names = get_names(set_code)
    m = len(names)

    x_raw = pick_x[:, m:]
    y_raw = pick_x[:, :m]

    p1_count = x_raw.sum(axis=1).max()

    p1_counts = x_raw[x_raw.sum(axis=1) == p1_count].sum(axis=0) + 1
    p1_picks = y_raw[x_raw.sum(axis=1) == p1_count].sum(axis=0)
    pick_rates = p1_picks / p1_counts
    zero_ind = np.abs(
        pick_rates * (p1_counts > 0.25 * p1_counts.max()) - 1 / p1_count
    ).argmin()

    theta = softmax_solve(x_raw, y_raw, zero_ind=zero_ind)

    df = pl.DataFrame({"name": names, "theta": theta}).sort("theta", descending=False)

    if write_cache:
        save_ad_hoc_dataset(df, ad_hoc_filename)
    return df


def marginal_pick_q(
    set_code: str,
    pack_num: int,
    pick_num: int,
    remaining_pick_q: float,  # exclusive of pick
    pool_strength: NDArray[np.float64],  # n x 1
    draft_id_df: pl.DataFrame,
) -> MarginalQOutput:
    print(
        f"set_code: {set_code}, pack_num: {pack_num}, pick_num: {pick_num}, draft_ids: {draft_id_df.shape}"
    )
    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]
    wl_x = (
        draft_id_df.join(
            lazy_select(
                set_code,
                View.DRAFT,
                [
                    "draft_id",
                    "event_match_wins_sum",
                    "event_match_losses_sum",
                    "is_pick",
                ],
                filter_spec={"$and": [{"pick_num": pick_num}, {"pack_num": pack_num}]},
                extensions=mle_ext(picks_per_pack),
            )
            .collect(streaming=True)
            .filter(
                pl.col("event_match_wins_sum") + pl.col("event_match_losses_sum") > 0
            ),
            ["draft_id"],
        )
        .drop("draft_id")
        .to_numpy()
    )

    assert (
        draft_id_df.shape[0] == wl_x.shape[0]
    ), f"lost supposedly good drafts, found {wl_x.shape[0]} drafts out of {draft_id_df.shape[0]}"

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

    alpha = find_weighted_mle(wl, x, alpha, train, diag=True)
    pick_strength = np.dot(x[:, :-1], alpha[:-1])

    names = get_names(set_code)
    df = pl.DataFrame(
        {
            "name": names,
            "q": alpha[: len(names)],
            "weight": weight[: len(names)],
        }
    ).sort("q", descending=True)

    return MarginalQOutput(df=df, pool_strength=pool_strength + pick_strength)


def p0_q(
    set_code: str,
    draft_filter: dict | None = None,
):
    """total remaining pick equity at pick 0,
    i.e. the marginal win rate of the whole cohort"""

    if draft_filter is None:
        draft_filter = TOP_PLAYER

    wl_x = (
        lazy_select(
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

    q = find_weighted_mle(wl, x, alpha, train, diag=True)
    return float(q[0])


def marginal_q_by_pick(set_code: str, draft_filter: dict | None = None):
    if draft_filter is None:
        draft_filter = TOP_PLAYER

    pack_num = 1

    picks_per_pack = _get_set_context(set_code, None)["picks_per_pack"]

    draft_id_df = (
        lazy_select(
            set_code,
            View.DRAFT,
            ["draft_id"],
            filter_spec={
                "$and": [draft_filter, {"lhs": "event_matches", "op": ">", "rhs": 0}]
            },
        )
        .group_by("draft_id")
        .len()
        .filter(pl.col("len") == 3 * picks_per_pack)
        .select("draft_id")
        .collect(streaming=True)
    )

    pool_strength = np.zeros(len(draft_id_df))
    remaining_equity = p0_q(set_code, draft_filter=draft_filter)

    result_df = None
    for pick_num in range(1, picks_per_pack + 1):
        remaining_equity = remaining_equity - PICK_EQUITY_ARR[pick_num - 1]
        result = marginal_pick_q(
            set_code, pack_num, pick_num, remaining_equity, pool_strength, draft_id_df
        )
        if result_df is None:
            result_df = result.df.rename(
                {"q": f"pick_{pick_num}", "weight": f"pick_{pick_num}_weight"}
            )
        else:
            result_df = result_df.join(
                result.df.rename(
                    {"q": f"pick_{pick_num}", "weight": f"pick_{pick_num}_weight"}
                ),
                "name",
            )
        pool_strength = result.pool_strength
    return result_df


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
                lazy_select(set_code, View.GAME, ["draft_id", "deck"], draft_filter)
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
                lazy_select(
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
                lazy_select(
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
