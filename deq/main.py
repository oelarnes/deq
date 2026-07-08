import datetime as dt
import math
from dataclasses import dataclass

import polars as pl

from spells import summon, ColName, ColType, ColSpec, EventType, TimePeriod, card_ratings_view
from spells.columns import agg_col
from spells.card_data_files import deck_color_df, CacheUsage
from deq.set_config import DEqConfig, config

BASIC_LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]

# for ensuring consistent floating point aggregations
PRECISION = 2**16

# deq parameters
PICK_EQUITY_INIT = 0.03
PICK_EQUITY_MID = 0.03
PICK_EQUITY_MID_INDEX = 1
ZERO_EQUITY_INDEX = 14
BIAS_ADJ_COEF = 1.0
DEQ_LOSS_FACTOR = 0.6
SAMPLE_DECAY = 0.95
META_DECAY = 0.95
MAX_DEQ_DAYS = 25
GRADE_C_MINUS_MAX = -0.001
GRADE_NOTCH_INCREMENT = 0.0075
DEQ_BAYES_GAMES = 1000

SAMPLE_THRESHOLD = 500
BAYES_GAMES = 150
BAYES_MU = 0.54

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

PR_ODDS_0 = 1.0 / 13.0
MAX_PRL = 10.0

NPR_ALSA_COEF = -0.12
NPR_ALSA_SQ_COEF = -0.04

COLOR_SETS = [
    "W",
    "U",
    "R",
    "B",
    "G",
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

WIDE_WINDOW_THRESHOLD_DAYS = 21


def _resolve_window(
    cfg: DEqConfig, as_of: dt.date
) -> tuple[TimePeriod, CacheUsage | dt.date, dt.date, dt.date]:
    """Date window used for DEq along with assumed start and end date for display"""
    elapsed = (as_of - cfg.start_date).days
    is_live = cfg.end_date is None or cfg.end_date >= as_of

    if elapsed >= WIDE_WINDOW_THRESHOLD_DAYS:
        time_period = TimePeriod.ALL_EXCEPT_FIRST_WEEK
        display_start = cfg.start_date + dt.timedelta(days=7)
    else:
        assert is_live, "Did a new format end before three weeks elapsed?"
        time_period = TimePeriod.LAST_TWO_WEEKS
        display_start = as_of - dt.timedelta(days=14)

    if is_live:
        cache_usage = CacheUsage.NONE
        display_end = as_of - dt.timedelta(days=1)
    else:
        cache_usage = CacheUsage.LAST
        assert cfg.end_date is not None, "for typing"
        display_end = cfg.end_date

    return time_period, cache_usage, display_start, display_end


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
    max_deq_days: int = MAX_DEQ_DAYS,
    grade_c_minus_max: float = GRADE_C_MINUS_MAX,
    grade_notch_increment: float = GRADE_NOTCH_INCREMENT,
    is_pick_two: bool = False,
    color_sets: list[str] | None = None,
) -> dict[str, ColSpec]:
    color_sets = color_sets or COLOR_SETS

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
        f"ata_adj{suffix}": agg_col(pl.col("ata_17l") * 2 - 0.5 if is_pick_two else pl.col("ata_17l")),
        f"pick_equity{suffix}": agg_col(pl.when(pl.col(f"ata_adj{suffix}") >= pick_equity_mid_index)
            .then(
                pick_equity_mid
                * (
                    1
                    - (pl.col(f"ata_adj{suffix}") - pick_equity_mid_index)
                    / (zero_equity_index - pick_equity_mid_index)
                ).pow(2)
            )
            .otherwise(
                pick_equity_mid
                + (
                    (
                        1
                        - (pl.col(f"ata_adj{suffix}") - pick_equity_mid_index)
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
            )
        ),
        f"mwr{suffix}": agg_col(
            pl.col("gp_wr_17l") - pl.col("gp_wr_mean")
        ),
        f"deq_base{suffix}": agg_col((
                pl.col(f"mwr{suffix}") + pl.col(f"pick_equity{suffix}")
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
        f"gp_wr_bias{suffix}": agg_col(pl.col(f"gp_bias_weight{suffix}") / pl.col(ColName.DECK)),
        f"deq_bias_adj{suffix}": agg_col(
            bias_adj_coef * (pl.col(f"pick_equity{suffix}") / pick_equity_init - 1)
            * pl.col(f"gp_wr_bias{suffix}")
        ),
        f"meta_regression_factor{suffix}": ColSpec(
            col_type=ColType.CARD_ATTR, expr=meta_decay_factor
        ),
        f"deq_meta_adj{suffix}": agg_col(
            (pl.col(f"gp_wr_bias{suffix}") + pl.col(f"deq_bias_adj{suffix}"))
            * pl.col(f"meta_regression_factor{suffix}")
        ),
        f"deq{suffix}": agg_col(pl.col(f"deq_base{suffix}")
            + (pl.col(f"deq_bias_adj{suffix}") + pl.col(f"deq_meta_adj{suffix}"))
            * pl.col("pct_gp")
        ),
        f"deq_grade{suffix}": agg_col(
            pl.when(pl.col("deq").is_null() | pl.col("deq").is_nan())
            .then(pl.lit("N/A")).otherwise(pl.when(
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
            ).then(pl.lit("A")).otherwise(pl.lit("A+"))))))))))))))
        )
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
    ColName.DECK_TOTAL: agg_col(pl.col(ColName.DECK).sum().over("expansion")),
    ColName.WON_DECK_TOTAL: agg_col(pl.col(ColName.WON_DECK).sum().over("expansion")),
    ColName.GP_WR_MEAN: agg_col(
        pl.col(ColName.WON_DECK_TOTAL) / pl.col(ColName.DECK_TOTAL)
    ),
    ColName.GP_WR_EXCESS: agg_col(pl.col(ColName.GP_WR) - pl.col(ColName.GP_WR_MEAN)),
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
    "deck_over_colors": agg_col(
        pl.col(ColName.DECK)
        .sum()
        .over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)])
    ),
    "won_deck_over_colors": agg_col(
        pl.col(ColName.WON_DECK)
        .sum()
        .over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)])
    ),
    "deck_small_sample": agg_col(
        pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.DECK) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(1.0)
    ),
    "alsa_17l": agg_col(
        pl.when(pl.col(ColName.NUM_SEEN) < SAMPLE_THRESHOLD)
        .then(None)
        .otherwise(pl.col(ColName.ALSA))
    ),
    "ata_17l": agg_col(
        pl.when(pl.col(ColName.NUM_TAKEN) < 200)
        .then(None)
        .otherwise(pl.col(ColName.ATA))
    ),
    "gih_wr_17l": agg_col(
        pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.NUM_GIH) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(pl.col(ColName.NUM_GIH_WON))
        / (pl.col(ColName.NUM_GIH))
    ),
    "gp_wr_17l": agg_col(
        pl.col("deck_small_sample") * pl.col(ColName.WON_DECK) / (pl.col(ColName.DECK))
    ),
    "gns_wr_17l": agg_col(
        pl.when(
            pl.col(ColName.NAME).is_in(BASIC_LANDS)
            | (pl.col(ColName.NUM_GNS) < SAMPLE_THRESHOLD)
        )
        .then(None)
        .otherwise(pl.col(ColName.WON_NUM_GNS))
        / (pl.col(ColName.NUM_GNS))
    ),
    "iwd_17l": agg_col(pl.col("gih_wr_17l") - pl.col("gns_wr_17l")),
    "format_day_sum": ColSpec(
        col_type=ColType.PICK_SUM, expr=pl.col(ColName.FORMAT_DAY)
    ),
    "mean_day_picked": agg_col(pl.col("format_day_sum") / pl.col(ColName.NUM_TAKEN)),
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
    "deck_commons_mean": agg_col(pl.col("deck_commons") / pl.col("deck")),
    "deck_rares_mean": agg_col(pl.col("deck_rares") / pl.col("deck")),
    "pick_rate_logit_seen": agg_col(
        pl.when(pl.col(ColName.NUM_SEEN) > 0)
        .then(
            pl.when(pl.col(ColName.NUM_SEEN) > pl.col(ColName.NUM_TAKEN))
            .then(
                pl.when(pl.col(ColName.NUM_TAKEN) > 0)
                .then(
                    (
                        pl.col(ColName.NUM_TAKEN)
                        / (pl.col(ColName.NUM_SEEN) - pl.col(ColName.NUM_TAKEN))
                    ).log()
                    - pl.lit(PR_ODDS_0).log()
                )
                .otherwise(-MAX_PRL)
            )
            .otherwise(MAX_PRL)
        )
        .otherwise(None)
    ),
    "pick_rate_logit": agg_col(
        pl.when(pl.col(ColName.PACK_CARD) > 0)
        .then(
            pl.when(pl.col(ColName.PACK_CARD) > pl.col(ColName.NUM_TAKEN))
            .then(
                pl.when(pl.col(ColName.NUM_TAKEN) > 0)
                .then(
                    (
                        pl.col(ColName.NUM_TAKEN)
                        / (pl.col(ColName.PACK_CARD) - pl.col(ColName.NUM_TAKEN))
                    ).log()
                    - pl.lit(PR_ODDS_0).log()
                )
                .otherwise(-MAX_PRL)
            )
            .otherwise(MAX_PRL)
        )
        .otherwise(None)
    ),
    "npr": agg_col(
        (
            pl.col("pick_rate_logit_seen")
            + NPR_ALSA_COEF * pl.col("alsa_17l")
            + NPR_ALSA_SQ_COEF * pl.col("alsa_17l") ** 2
        )
        / math.log(2)
    ),
}


def deq_bias_set_context(
    set_codes: list[str],
    metric_filter: dict,
    observed_days: int | None = None,
    projection_days: int = 0,
    color_sets: list[str] | None = None,
):
    color_sets = color_sets or COLOR_SETS
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
    time_period: TimePeriod = TimePeriod.ALL_EXCEPT_FIRST_WEEK,
    cache_usage: dt.date | CacheUsage = CacheUsage.NONE,
    pick_equity_init: float = PICK_EQUITY_INIT,
    pick_equity_mid: float = PICK_EQUITY_MID,
    pick_equity_mid_index: int = PICK_EQUITY_MID_INDEX,
    zero_equity_index: int = ZERO_EQUITY_INDEX,
    bias_adj_coef: float = BIAS_ADJ_COEF,
    deq_loss_factor: float = DEQ_LOSS_FACTOR,
    sample_decay: float = SAMPLE_DECAY,
    meta_decay: float = META_DECAY,
    max_deq_days: int = MAX_DEQ_DAYS,
    color_sets: list[str] | None = None,
    min_games_pct: float = 0.005,
    as_of: dt.date | None = None,
) -> pl.DataFrame:
    event_type = EventType.PICK_TWO if config[set_code].is_pick_two else EventType.PREMIER
    as_of = as_of or dt.date.today()

    set_context = {
        "observed_days": (as_of - config[set_code].start_date).days + 1,
        "projection_days": 0,
    }

    deq_ext = {
        **ext,
        **deq_col_specs(
            pick_equity_init=pick_equity_init,
            pick_equity_mid=pick_equity_mid,
            pick_equity_mid_index=pick_equity_mid_index,
            zero_equity_index=zero_equity_index,
            bias_adj_coef=bias_adj_coef,
            deq_loss_factor=deq_loss_factor,
            meta_decay=meta_decay,
            sample_decay=sample_decay,
            max_deq_days=max_deq_days,
            is_pick_two=config[set_code].is_pick_two,
            # gp_bias_weight ColSpec is unused here; bias adj is computed via direct join below
            color_sets=[],
        ),
    }

    def deq_col(col: str) -> pl.Expr:
        expr = deq_ext[col].expr

        if isinstance(expr, pl.Expr):
            return expr.alias(col)
        if expr is None:
            raise ValueError("Unexpected")
        else:
            return expr(set_context).alias(col)

    raw_deq_by_cohort = {}
    for player_cohort in ["all", "top"]:
        dc_df = deck_color_df(
            set_code,
            event_type=event_type,
            player_cohort=player_cohort,
            time_period=time_period,
            cache_usage=cache_usage,
        ).with_columns(
            pl.col(ColName.NUM_WON).sum().alias(ColName.GP_WR_MEAN)
            / pl.col(ColName.NUM_GAMES).sum()
        )
        gp_wr_mean = (
            dc_df.select([ColName.NUM_WON, ColName.NUM_GAMES])
            .sum()
            .select(pl.col(ColName.NUM_WON) / pl.col(ColName.NUM_GAMES))[
                ColName.NUM_WON
            ][0]
        )

        gp_wr_excess = (
            pl.col(ColName.NUM_WON).alias(ColName.GP_WR_EXCESS)
            / pl.col(ColName.NUM_GAMES)
            - gp_wr_mean
        )

        if color_sets is not None:
            active_colors = color_sets
        else:
            total_games = dc_df[ColName.NUM_GAMES].sum()
            active_colors = (
                dc_df.filter(pl.col(ColName.NUM_GAMES) >= min_games_pct * total_games)
                [ColName.MAIN_COLORS].to_list()
            )

        excess_wr_df = pl.concat(
            [
                (
                    dc_df.filter(~pl.col(ColName.MAIN_COLORS).is_in(active_colors))
                    .select(ColName.NUM_GAMES, ColName.NUM_WON)
                    .sum()
                    .select(
                        gp_wr_excess,
                        pl.lit("other").alias(ColName.MAIN_COLORS),
                    )
                ),
                (
                    dc_df.filter(pl.col(ColName.MAIN_COLORS).is_in(active_colors)).select(
                        gp_wr_excess, ColName.MAIN_COLORS
                    )
                ),
            ]
        )

        card_df = card_ratings_view(
            set_code,
            event_type=event_type,
            player_cohort=player_cohort,
            time_period=time_period,
            cache_usage=cache_usage,
            columns=[
                ColName.COLOR,
                ColName.RARITY,
                ColName.IMAGE_URL,
                ColName.ATA,
                ColName.ALSA,
                ColName.NUM_SEEN,
                ColName.NUM_TAKEN,
                ColName.DECK,
                ColName.WON_DECK,
                ColName.PCT_GP,
                ColName.GP_WR,
            ],
        )

        # 17lands doesn't serve cohort-filtered color-pair data, so composition
        # weights come from the all-player dataset for both cohorts
        if active_colors:
            deck_counts_df = card_ratings_view(
                set_code,
                event_type=event_type,
                player_cohort="all",
                deck_colors=active_colors,
                time_period=time_period,
                cache_usage=cache_usage,
                columns=[ColName.DECK],
                group_by=[ColName.NAME, ColName.MAIN_COLORS],
            )
        else:
            deck_counts_df = pl.DataFrame(
                {ColName.NAME: [], ColName.MAIN_COLORS: [], ColName.DECK: []},
                schema={
                    ColName.NAME: pl.String,
                    ColName.MAIN_COLORS: pl.String,
                    ColName.DECK: pl.Int64,
                },
            )

        # the "other" residual is relative to the same all-player totals
        if player_cohort == "all":
            composition_totals_df = card_df.select(ColName.NAME, ColName.DECK)
        else:
            composition_totals_df = card_ratings_view(
                set_code,
                event_type=event_type,
                player_cohort="all",
                time_period=time_period,
                cache_usage=cache_usage,
                columns=[ColName.DECK],
            )

        other_counts_df = (
            composition_totals_df.select(
                ColName.NAME, pl.col(ColName.DECK).alias("num_gp_all")
            )
            .join(
                deck_counts_df.group_by(ColName.NAME).agg(pl.col(ColName.DECK).sum()),
                on=ColName.NAME,
                how="left",
            )
            .select(
                ColName.NAME,
                pl.lit("other").alias(ColName.MAIN_COLORS),
                (pl.col("num_gp_all") - pl.col(ColName.DECK).fill_null(0)).alias(
                    ColName.DECK
                ),
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
                (pl.col("gp_bias_weight") / pl.col(ColName.DECK)).alias("gp_wr_bias"),
            )
        )

        card_df = card_df.join(bias_adj_df, on="name").with_columns(
            pl.lit(gp_wr_mean).alias(ColName.GP_WR_MEAN)
        )

        card_df = card_df.with_columns(deq_col("ata_17l"), deq_col("alsa_17l"))

        # ata fallback for top.
        if player_cohort == "top" and "all" in raw_deq_by_cohort:
            fallback_df = raw_deq_by_cohort["all"].select(
                [
                    "name",
                    pl.col("ata_17l").alias("ata_fallback"),
                    pl.col("alsa_17l").alias("alsa_fallback"),
                ]
            )
            card_df = (
                card_df.join(fallback_df, on=ColName.NAME)
                .with_columns(
                    pl.when(pl.col("ata_17l").is_null())
                    .then(pl.col("ata_fallback"))
                    .otherwise(pl.col("ata"))
                    .alias("ata_new"),
                    pl.when(pl.col("alsa_17l").is_null())
                    .then(pl.col("alsa_fallback"))
                    .otherwise(pl.col("alsa"))
                    .alias("alsa_new"),
                )
                .drop("ata_17l", "ata_fallback", "alsa_17l", "alsa_fallback")
                .rename({"ata_new": "ata_17l", "alsa_new": "alsa_17l"})
            )

        deq_df = (
            card_df.with_columns(deq_col("deck_small_sample"))
            .with_columns(deq_col("ata_adj"), deq_col("gp_wr_17l"))
            .with_columns(deq_col("mwr"), deq_col("pick_equity"))
            .with_columns(
                deq_col("deq_bias_adj"),
                deq_col("meta_regression_factor"),
            )
            .with_columns(
                deq_col("deq_meta_adj"),
            )
            .with_columns(deq_col("pick_rate_logit_seen"))
            .with_columns(
                pl.lit("N/A").alias("npr")
                if config[set_code].is_pick_two
                else deq_col("npr")
            )
        )
        raw_deq_by_cohort[player_cohort] = deq_df

    component_metrics = [
        ColName.PCT_GP,
        "mwr",
        "deq_meta_adj",
        "pick_equity",
        "deq_bias_adj",
    ]
    additive_components = ["mwr", "pick_equity", "deq_bias_adj", "deq_meta_adj"]

    deq_df = (
        raw_deq_by_cohort["top"]
        .rename({metric: f"{metric}_top" for metric in component_metrics})
        .join(
            raw_deq_by_cohort["all"].select(
                "name",
                *[
                    pl.col(metric).alias(f"{metric}_all")
                    for metric in component_metrics
                ],
            ),
            on="name",
        )
        .with_columns(
            pl.when(pl.col("mwr_top").is_not_null() & pl.col("mwr_top").is_finite())
            .then(pl.col("deck") / (DEQ_BAYES_GAMES + pl.col("deck")))
            .otherwise(pl.lit(0))
            .alias("pct_top"),
        )
        .with_columns(
            # blended GP%: fill_null(0) on the _top term for same reason as components below
            (
                (pl.col("pct_top") * pl.col("pct_gp_top")).fill_null(0.0)
                + (1 - pl.col("pct_top")) * pl.col("pct_gp_all")
            ).alias("pct_gp"),
        )
        .with_columns(
            # blend each additive component, weighted by GP% contribution per group.
            # fill_null(0) on the _top term prevents null propagation when pct_top=0
            # but mwr_top is null (top cohort has insufficient GP sample).
            *[
                pl.when(pl.col("pct_gp") > 0)
                .then(
                    (
                        (pl.col("pct_top") * pl.col("pct_gp_top") * pl.col(f"{m}_top")).fill_null(0.0)
                        + (1 - pl.col("pct_top")) * pl.col("pct_gp_all") * pl.col(f"{m}_all")
                    )
                    / pl.col("pct_gp")
                )
                .otherwise(pl.col(f"{m}_all"))
                .alias(m)
                for m in additive_components
            ],
        )
        .with_columns(
            # reassemble DEq from blended components
            (
                pl.col("pct_gp")
                * (
                    pl.col("mwr")
                    + pl.col("pick_equity")
                    + pl.col("deq_bias_adj")
                    + pl.col("deq_meta_adj")
                )
            ).alias("deq"),
        )
        .with_columns(deq_col("deq_grade"))
    )

    return deq_df


@dataclass
class DeqData:
    df: pl.DataFrame
    set_code: str
    start_date: dt.date
    end_date: dt.date
    available_sets: list[str]


def daily_deq(
    set_code: str | None = None,
    as_of: dt.date | None = None,
) -> DeqData:
    as_of = as_of or dt.date.today()
    set_code = (
        [
            key
            for key, cfg in config.items()
            if cfg.start_date < dt.date.today()
            and (
                cfg.end_date is None
                or cfg.end_date >= dt.date.today() - dt.timedelta(days=1)
            )
        ][0]
        if set_code is None
        else set_code
    )

    cfg = config[set_code]
    time_period, cache_usage, start_date, end_date = _resolve_window(cfg, as_of)

    deq_df = live_deq(set_code, time_period=time_period, cache_usage=cache_usage, as_of=as_of)

    available_sets = [s for s in sorted(
        config.keys(), key=lambda val: config[val].start_date, reverse=True
    ) if config[s].start_date <= as_of]

    return DeqData(
        df=deq_df,
        set_code=set_code,
        start_date=start_date,
        end_date=end_date,
        available_sets=available_sets,
    )
