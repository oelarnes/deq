import datetime as dt
import os
from dataclasses import dataclass

import polars as pl

from spells import summon, ColName, ColType, ColSpec
from spells.cache import ad_hoc_dir
from spells.draft_data import CardDataFileSpec
from spells.card_data_files import deck_color_df

BASIC_LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]

# for ensuring consistent floating point aggregations
PRECISION = 2**16

# deq parameters
PICK_EQUITY_INIT = 0.03
PICK_EQUITY_MID = 0.03
PICK_EQUITY_MID_INDEX = 1
ZERO_EQUITY_INDEX = 14
BIAS_ADJ_COEF = 0.5
DEQ_LOSS_FACTOR = 0.6
SAMPLE_DECAY = 0.95
META_DECAY = 0.95
WR_BETA_TO_ATA = -0.0033
BAYES_GAMES = 200
MAX_DEQ_DAYS = 25
GRADE_C_MINUS_MAX = -0.001
GRADE_NOTCH_INCREMENT = 0.0075

SAMPLE_THRESHOLD = 500
BAYES_GAMES = 150
BAYES_MU = 0.54

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)


color_sets = [
    "WU",
    "WB",
    "WR",
    "WG",
    "UB",
    "UR",
    "UG",
    "BR",
    "BG",
    "RG",
    "WUB",
    "WUR",
    "WUG",
    "WBR",
    "WBG",
    "WRG",
    "UBR",
    "UBG",
    "URG",
    "BRG",
]

start_dates = {
    "TDM": dt.date(2025, 4, 8),
    "FIN": dt.date(2025, 6, 10),
    "EOE": dt.date(2025, 7, 29),
}

end_dates = {
    "TDM": dt.date(2025, 6, 10),
    "FIN": dt.date(2025, 7, 29),
}


def deq_col_specs(
    suffix: str = "",
    pick_equity_init: float = PICK_EQUITY_INIT,
    pick_equity_mid: float = PICK_EQUITY_MID,
    pick_equity_mid_index: int = PICK_EQUITY_MID_INDEX,
    zero_equity_index: int = ZERO_EQUITY_INDEX,
    bias_adj_coef: float = BIAS_ADJ_COEF,
    deq_loss_factor: float = DEQ_LOSS_FACTOR,
    sample_decay: float = SAMPLE_DECAY,
    meta_decay: float = META_DECAY,
    wr_beta_to_ata: float = WR_BETA_TO_ATA,
    bayes_games: int = BAYES_GAMES,
    max_deq_days: int = MAX_DEQ_DAYS,
    grade_c_minus_max: float = GRADE_C_MINUS_MAX,
    grade_notch_increment: float = GRADE_NOTCH_INCREMENT,
) -> dict[str, ColSpec]:
    def meta_decay_factor(set_context: dict):
        t: int | None = set_context.get("observed_days")
        ft = set_context.get("projection_days")

        if not isinstance(t, int) or not isinstance(ft, int):
            return pl.lit(0)

        t = min(t, max_deq_days)

        return pl.lit(
            deq_loss_factor
            * (
                meta_decay ** (t + ft)
                * (1 - sample_decay**t)
                * (1 - sample_decay * meta_decay)
                / (1 - (sample_decay * meta_decay) ** t)
                / (1 - sample_decay)
                - 1
            )
        )

    # fmt: off
    return {
        f"pick_equity{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.when(pl.col(ColName.ATA) >= pick_equity_mid_index)
            .then(
                pick_equity_mid
                * (
                    1
                    - (pl.col(ColName.ATA) - pick_equity_mid_index)
                    / (zero_equity_index - pick_equity_mid_index)
                ).pow(2)
            )
            .otherwise(
                pick_equity_mid
                + (
                    (
                        1
                        - (pl.col(ColName.ATA) - pick_equity_mid_index)
                        / (zero_equity_index - pick_equity_mid_index)
                    ).pow(2)
                    - 1
                )
                * (pick_equity_init - pick_equity_mid)
                / (
                    (
                        1
                        - (1 - pick_equity_mid_index)
                        / (zero_equity_index - pick_equity_mid_index)
                    )
                    ** 2
                    - 1
                )
            ),
        ),
        f"gp_wr_bayes_mu{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.col(ColName.GP_WR_MEAN) + wr_beta_to_ata * (pl.col("ata") - 7),
        ),
        f"gp_wr_b{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.col("deck_small_sample")
            * (
                pl.col(f"gp_wr_bayes_mu{suffix}") * bayes_games
                + pl.col(ColName.WON_DECK)
            )
            / (pl.col(ColName.DECK) + bayes_games),
        ),
        f"deq_base{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=(
                pl.col(f"gp_wr_b{suffix}")
                - pl.col(ColName.GP_WR_MEAN)
                + pl.col(f"pick_equity{suffix}")
            )
            * pl.col(ColName.PCT_GP),
        ),
        f"gp_bias_weight{suffix}": ColSpec(
            col_type=ColType.NAME_SUM,
            expr=lambda set_context, name: pl.col(f"deck_{name}")
            * pl.col(ColName.MAIN_COLORS).replace_strict(
                {
                    colors: set_context.get(f"game_wr_excess_{colors}")
                    for colors in color_sets
                },
                default=set_context.get("game_wr_excess_other"),
            ),
        ),
        f"gp_wr_bias{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.col(f"gp_bias_weight{suffix}") / pl.col(ColName.DECK),
        ),
        f"deq_bias_adj{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=bias_adj_coef
            * (pl.col(f"pick_equity{suffix}") / pick_equity_init - 1)
            * pl.col(f"gp_wr_bias{suffix}"),
        ),
        f"meta_regression_factor{suffix}": ColSpec(
            col_type=ColType.CARD_ATTR, expr=meta_decay_factor
        ),
        f"deq_meta_adj{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=(pl.col(f"gp_wr_bias{suffix}") + pl.col(f"deq_bias_adj{suffix}"))
            * pl.col(f"meta_regression_factor{suffix}"),
        ),
        f"deq{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.col(f"deq_base{suffix}")
            + (pl.col(f"deq_bias_adj{suffix}") + pl.col(f"deq_meta_adj{suffix}"))
            * pl.col("pct_gp"),
        ),
        f"deq_grade{suffix}": ColSpec(
            col_type=ColType.AGG,
            expr=pl.when(pl.col("deq").is_null() | pl.col("deq").is_nan())
            .then(pl.lit("N/A"))
            .otherwise(pl.when(pl.col("deq").is_null() | pl.col("deq").is_nan()
            ).then(pl.lit(None)).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max - 4 * grade_notch_increment
            ).then(pl.lit("F")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max - 3 * grade_notch_increment
            ).then(pl.lit("D-")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max - 2 * grade_notch_increment
            ).then(pl.lit("D")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max - 1 * grade_notch_increment
            ).then(pl.lit("D+")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max
            ).then(pl.lit("C-")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 1 * grade_notch_increment
            ).then(pl.lit("C")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 2 * grade_notch_increment
            ).then(pl.lit("C+")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 3 * grade_notch_increment
            ).then(pl.lit("B-")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 4 * grade_notch_increment
            ).then(pl.lit("B")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 5 * grade_notch_increment
            ).then(pl.lit("B+")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 6 * grade_notch_increment
            ).then(pl.lit("A-")).otherwise(pl.when(
                pl.col("deq") < grade_c_minus_max + 7 * grade_notch_increment
            ).then(pl.lit("A")).otherwise(pl.lit("A+")))))))))))))))
        ),
    }


# fmt: on

ext = {
    **deq_col_specs(),
    ColName.NUM_GNS: ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name: pl.max_horizontal(
            0,
            pl.col(f"deck_{name}")
            - pl.col(f"drawn_{name}")
            - pl.col(f"opening_hand_{name}"),
        ),  # lazy way to use SNC and NEO which don't have "tutored"
    ),
    ColName.DECK_TOTAL: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).sum().over("expansion"),
    ),
    ColName.WON_DECK_TOTAL: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).sum().over("expansion"),
    ),
    ColName.GP_WR_MEAN: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK_TOTAL) / pl.col(ColName.DECK_TOTAL),
    ),
    ColName.GP_WR_EXCESS: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.GP_WR) - pl.col(ColName.GP_WR_MEAN),
    ),
    "skill_cohort_raw": ColSpec(
        col_type=ColType.GROUP_BY,
        expr=(
            pl.when(UNG == 1000)
            .then(1200 / (1200 + BAYES_GAMES))
            .otherwise(
                pl.when(UNG == 500)
                .then(750 / (750 + BAYES_GAMES))
                .otherwise(
                    pl.when(UNG == 100)
                    .then(300 / (300 + BAYES_GAMES))
                    .otherwise(
                        pl.when(UNG == 50)
                        .then(75 / (75 + BAYES_GAMES))
                        .otherwise(
                            pl.when(UNG == 10)
                            .then(30 / (30 + BAYES_GAMES))
                            .otherwise(0)
                        )
                    )
                )
            )
            * (UGWR - BAYES_MU)
            + BAYES_MU
        ),
    ),
    "skill_cohort": ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.when(pl.col("skill_cohort_raw") < 0.49)
        .then(pl.lit("1_Weak"))
        .otherwise(
            pl.when(pl.col("skill_cohort_raw") < 0.52)
            .then(pl.lit("2_Average"))
            .otherwise(
                pl.when(pl.col("skill_cohort_raw") < 0.55)
                .then(pl.lit("3_Above Average"))
                .otherwise(
                    pl.when(pl.col("skill_cohort_raw") < 0.58)
                    .then(pl.lit("4_Competitive"))
                    .otherwise(
                        pl.when(pl.col("skill_cohort_raw") < 0.61)
                        .then(pl.lit("5_Strong"))
                        .otherwise(pl.lit("6_Elite"))
                    )
                )
            )
        ),
    ),
    "deck_over_colors": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK)
        .sum()
        .over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)]),
    ),
    "won_deck_over_colors": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK)
        .sum()
        .over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)]),
    ),
    "deck_small_sample": ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.DECK) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(1.0),
    ),
    "gih_wr_17l": ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.NUM_GIH) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(pl.col(ColName.NUM_GIH_WON))
        / (pl.col(ColName.NUM_GIH)),
    ),
    "gp_wr_17l": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col("deck_small_sample")
        * pl.col(ColName.WON_DECK)
        / (pl.col(ColName.DECK)),
    ),
    "gns_wr_17l": ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.NUM_GNS) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(pl.col(ColName.WON_NUM_GNS))
        / (pl.col(ColName.NUM_GNS)),
    ),
    "iwd_17l": ColSpec(
        col_type=ColType.AGG, expr=pl.col("gih_wr_17l") - pl.col("gns_wr_17l")
    ),
    "format_day_sum": ColSpec(
        col_type=ColType.PICK_SUM, expr=pl.col(ColName.FORMAT_DAY)
    ),
    "mean_day_picked": ColSpec(
        col_type=ColType.AGG, expr=pl.col("format_day_sum") / pl.col(ColName.NUM_TAKEN)
    ),
    "color_group": ColSpec(
        col_type=ColType.CARD_ATTR,
        expr=(
            pl.when(pl.col("color") == "")
            .then(pl.lit("Colorless"))
            .otherwise(
                pl.when(pl.col("color") == "W")
                .then(pl.lit("White"))
                .otherwise(
                    pl.when(pl.col("color") == "U")
                    .then(pl.lit("Blue"))
                    .otherwise(
                        pl.when(pl.col("color") == "B")
                        .then(pl.lit("Black"))
                        .otherwise(
                            pl.when(pl.col("color") == "R")
                            .then(pl.lit("Red"))
                            .otherwise(
                                pl.when(pl.col("color") == "G")
                                .then(pl.lit("Green"))
                                .otherwise(pl.lit("Gold"))
                            )
                        )
                    )
                )
            )
        ),
    ),
    "deck_commons": ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name, card_context: pl.col(f"deck_{name}")
        * (1 if card_context[name]["rarity"] == "common" else 0),
    ),
    "deck_rares": ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name, card_context: pl.col(f"deck_{name}")
        * (1 if card_context[name]["rarity"] == "rare" else 0),
    ),
    "deck_commons_mean": ColSpec(
        col_type=ColType.AGG, expr=pl.col("deck_commons") / pl.col("deck")
    ),
    "deck_rares_mean": ColSpec(
        col_type=ColType.AGG, expr=pl.col("deck_rares") / pl.col("deck")
    ),
}


def deq_bias_set_context(
    set_codes: list[str],
    metric_filter: dict,
    observed_days: int | None = None,
    projection_days: int = 0,
):
    if isinstance(set_codes, str):
        set_codes = [set_codes]

    gpwr_by_deck = summon(
        set_codes,
        columns=[
            ColName.GAME_WR,
            ColName.NUM_GAMES,
            ColName.NUM_WON,
            ColName.GP_WR_MEAN,
        ],
        group_by=["expansion", "main_colors"],
        filter_spec=metric_filter,
        extensions=ext,
    )

    deck_select = [
        "game_wr_excess_" + pl.col("main_colors"),
        (pl.col(ColName.GAME_WR) - pl.col(ColName.GP_WR_MEAN)),
    ]

    set_context = {
        set_code: {
            **{
                key: value[0]
                for key, value in gpwr_by_deck.filter(
                    (pl.col("expansion") == set_code)
                    & pl.col("main_colors").is_in(color_sets)
                )
                .select(deck_select)
                .rows_by_key("literal", unique=True)
                .items()
            },
            "game_wr_excess_other": gpwr_by_deck.filter(
                (pl.col("expansion") == set_code)
                & ~pl.col("main_colors").is_in(color_sets)
            )
            .select(
                pl.col(ColName.NUM_WON)
                - pl.col(ColName.GP_WR_MEAN) * pl.col(ColName.NUM_GAMES),
                (ColName.NUM_GAMES),
            )
            .sum()
            .select(pl.col(ColName.NUM_WON) / pl.col(ColName.NUM_GAMES))[
                ColName.NUM_WON
            ][0],
            "observed_days": observed_days,
            "projection_days": projection_days,
        }
        for set_code in set_codes
    }

    return set_context


def live_deq(
    set_code: str,
    start_date: dt.date,
    end_date: dt.date,
    player_cohort: str = "top",
    suffix: str = "",
    pick_equity_init: float = PICK_EQUITY_INIT,
    pick_equity_mid: float = PICK_EQUITY_MID,
    pick_equity_mid_index: int = PICK_EQUITY_MID_INDEX,
    zero_equity_index: int = ZERO_EQUITY_INDEX,
    bias_adj_coef: float = BIAS_ADJ_COEF,
    deq_loss_factor: float = DEQ_LOSS_FACTOR,
    sample_decay: float = SAMPLE_DECAY,
    meta_decay: float = META_DECAY,
    wr_beta_to_ata: float = WR_BETA_TO_ATA,
    bayes_games: int = BAYES_GAMES,
    max_deq_days: int = MAX_DEQ_DAYS,
) -> pl.DataFrame:
    dc_df = deck_color_df(
        set_code,
        player_cohort=player_cohort,
        start_date=start_date,
        end_date=end_date,
    ).with_columns(
        pl.col(ColName.NUM_WON).sum().alias(ColName.GP_WR_MEAN)
        / pl.col(ColName.NUM_GAMES).sum()
    )
    gp_wr_mean = (
        dc_df.select([ColName.NUM_WON, ColName.NUM_GAMES])
        .sum()
        .select(pl.col(ColName.NUM_WON) / pl.col(ColName.NUM_GAMES))[ColName.NUM_WON][0]
    )

    gp_wr_excess = (
        pl.col(ColName.NUM_WON).alias(ColName.GP_WR_EXCESS) / pl.col(ColName.NUM_GAMES)
        - gp_wr_mean
    )

    excess_wr_df = pl.concat(
        [
            (
                dc_df.filter(~pl.col(ColName.MAIN_COLORS).is_in(color_sets))
                .select(ColName.NUM_GAMES, ColName.NUM_WON)
                .sum()
                .select(
                    gp_wr_excess,
                    pl.lit("other").alias(ColName.MAIN_COLORS),
                )
            ),
            (
                dc_df.filter(pl.col(ColName.MAIN_COLORS).is_in(color_sets)).select(
                    gp_wr_excess, ColName.MAIN_COLORS
                )
            ),
        ]
    )

    card_df = summon(
        set_code,
        columns=[
            ColName.COLOR,
            ColName.RARITY,
            ColName.ATA,
            ColName.DECK,
            ColName.WON_DECK,
            ColName.PCT_GP,
        ],
        cdfs=CardDataFileSpec(
            set_code=set_code,
            player_cohort=player_cohort,
            start_date=start_date,
            end_date=end_date,
        ),
    )

    if player_cohort != "all":
        fallback_ata_df = summon(
            set_code,
            columns=[ColName.ATA],
            cdfs=CardDataFileSpec(
                set_code=set_code,
                player_cohort="all",
                start_date=start_date,
                end_date=end_date,
            ),
        ).rename({ColName.ATA: "ata_fallback"})

        card_df = card_df.join(fallback_ata_df, on=["name"]).select(
            ColName.NAME,
            ColName.COLOR,
            ColName.RARITY,
            pl.when(pl.col(ColName.ATA) < 1)
            .then(pl.col("ata_fallback"))
            .otherwise(pl.col(ColName.ATA))
            .alias(ColName.ATA),
            ColName.DECK,
            ColName.WON_DECK,
            ColName.PCT_GP,
        )

    deck_counts_df = summon(
        set_code,
        columns=[ColName.DECK],
        group_by=[ColName.NAME, ColName.MAIN_COLORS],
        cdfs=CardDataFileSpec(
            set_code=set_code,
            player_cohort=player_cohort,
            deck_colors=color_sets,
            start_date=start_date,
            end_date=end_date,
        ),
    )

    other_counts_df = (
        deck_counts_df.group_by("name")
        .sum()
        .join(
            card_df.select(ColName.NAME, pl.col(ColName.DECK).alias("num_gp_all")),
            on=ColName.NAME,
        )
        .select(
            ColName.NAME,
            pl.lit("other").alias(ColName.MAIN_COLORS),
            -pl.col(ColName.DECK) + pl.col("num_gp_all"),
        )
    )

    deck_counts_df = pl.concat([deck_counts_df, other_counts_df])

    bias_adj_df = (
        deck_counts_df.join(excess_wr_df, on=ColName.MAIN_COLORS)
        .select(
            ColName.NAME,
            (pl.col(ColName.DECK) * pl.col(ColName.GP_WR_EXCESS)).alias(
                "gp_bias_weight"
            ),
            pl.col(ColName.DECK),
        )
        .group_by(ColName.NAME)
        .sum()
        .select(
            ColName.NAME,
            (pl.col("gp_bias_weight") / pl.col(ColName.DECK)).alias(
                f"gp_wr_bias{suffix}"
            ),
        )
    )

    card_df = card_df.join(bias_adj_df, on="name").with_columns(
        pl.lit(gp_wr_mean).alias(ColName.GP_WR_MEAN)
    )

    set_context = {
        "observed_days": (end_date - start_date).days + 1,
        "projection_days": 0,
    }

    deq_ext = deq_col_specs(
        suffix=suffix,
        pick_equity_init=pick_equity_init,
        pick_equity_mid=pick_equity_mid,
        pick_equity_mid_index=pick_equity_mid_index,
        zero_equity_index=zero_equity_index,
        bias_adj_coef=bias_adj_coef,
        deq_loss_factor=deq_loss_factor,
        meta_decay=meta_decay,
        sample_decay=sample_decay,
        wr_beta_to_ata=wr_beta_to_ata,
        bayes_games=bayes_games,
        max_deq_days=max_deq_days,
    )

    def deq_col(col: str) -> pl.Expr:
        expr = deq_ext[col].expr

        if isinstance(expr, pl.Expr):
            return expr.alias(col)
        if expr is None:
            raise ValueError("Unexpected")
        else:
            return expr(set_context).alias(col)

    deq_df = (
        card_df.with_columns(
            deq_col(f"pick_equity{suffix}"),
            deq_col(f"gp_wr_bayes_mu{suffix}"),
            ext["deck_small_sample"].expr.alias("deck_small_sample"),  # type: ignore
        )
        .with_columns(deq_col(f"gp_wr_b{suffix}"))
        .with_columns(
            deq_col(f"deq_base{suffix}"),
            deq_col(f"deq_bias_adj{suffix}"),
            deq_col(f"meta_regression_factor{suffix}"),
        )
        .with_columns(
            deq_col(f"deq_meta_adj{suffix}"),
        )
        .with_columns(deq_col(f"deq{suffix}"))
        .with_columns(deq_col(f"deq_grade{suffix}"))
    )

    return deq_df


def deq_ref_dir():
    return os.path.join(ad_hoc_dir(), "deq")


@dataclass
class DeqData:
    df: pl.DataFrame
    set_code: str
    start_date: dt.date
    end_date: dt.date
    player_cohort: str
    available_sets: list[str]


def daily_deq(
    set_code: str | None = None,
    as_of: dt.date | None = None,
    gp_top_min_games: int = 70000,
    gp_all_min_games: int = 300000,
    max_format_day_start: int = 15,
) -> DeqData:
    as_of = as_of or dt.date.today()
    set_code = (
        [
            d
            for d in sorted(start_dates.keys(), key=lambda x: start_dates[x])
            if start_dates[d] < dt.date.today()
        ][-1]
        if set_code is None
        else set_code
    )
    end_date = end_dates.get(set_code, as_of - dt.timedelta(days=1))

    ref_dir = deq_ref_dir()
    if not os.path.isdir(ref_dir):
        os.makedirs(ref_dir)

    history_df_path = os.path.join(ref_dir, "history.parquet")

    if not os.path.isfile(history_df_path):
        history_df = pl.DataFrame([])
        set_df = pl.DataFrame([])
        as_of_df = pl.DataFrame([])
    else:
        history_df = pl.read_parquet(history_df_path)
        set_df = history_df.filter(
            (pl.col("set_code") == set_code) & (pl.col("as_of") <= as_of)
        )
        as_of_df = set_df.filter(pl.col("as_of") == as_of)

    if set_df.is_empty():
        start_date = start_dates[set_code]
        player_cohort = "top"
        accept = False
    else:
        if as_of_df.is_empty():
            params = set_df.sort("as_of").to_dicts()[-1]
            player_cohort = params["player_cohort"]

            if player_cohort == "all":
                start_date = start_dates[set_code]
                player_cohort = "top"
            else:
                start_date = params["start_date"] + dt.timedelta(days=1)

            accept = False
        else:
            params = as_of_df.to_dicts()[0]
            player_cohort = params["player_cohort"]
            start_date = params["start_date"]
            accept = True

    while not accept:
        print(f"Trying start_date {start_date.isoformat()}")
        num_games = deck_color_df(
            set_code,
            start_date=start_date,
            end_date=end_date,
            player_cohort=player_cohort,
        )["num_games"].sum()

        game_threshold = (
            gp_top_min_games if player_cohort == "top" else gp_all_min_games
        )

        if num_games >= game_threshold:
            if (start_date - start_dates[set_code]).days + 1 >= max_format_day_start:
                accept = True
                start_date = start_dates[set_code] + dt.timedelta(
                    days=max_format_day_start - 1
                )
            else:
                start_date = start_date + dt.timedelta(days=1)
        elif start_date == start_dates[set_code]:
            if player_cohort == "top":
                player_cohort = "all"
            else:
                accept = True
        else:
            accept = True
            start_date = start_date - dt.timedelta(days=1)

    deq_df = live_deq(
        set_code,
        start_date,
        end_date,
        player_cohort,
    )

    if as_of_df.is_empty():
        history_df = pl.concat(
            [
                history_df,
                pl.DataFrame(
                    [
                        {
                            "set_code": set_code,
                            "as_of": as_of,
                            "start_date": start_date,
                            "end_date": end_date,
                            "player_cohort": player_cohort,
                        }
                    ]
                ),
            ]
        )

        print("Writing history.parquet")
        history_df.write_parquet(history_df_path)

    available_sets = list(history_df['set_code'].unique())

    return DeqData(
        df=deq_df,
        set_code=set_code,
        start_date=start_date,
        end_date=end_date,
        player_cohort=player_cohort,
        available_sets=available_sets,
    )
