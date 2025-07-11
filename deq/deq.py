import polars as pl
import numpy as np

from spells import summon, ColName, ColType, ColSpec

BASIC_LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
P1_PICK_EQUITY = 0.025
ATA_DENOM = 13

PRECISION = 2**16

# parameters for deq metagame decay
DEQ_LOSS_FACTOR = 0.6
SAMPLE_DECAY = 0.95
META_DECAY = 0.95

SAMPLE_THRESHOLD = 500
BAYES_GAMES = 150
BAYES_MU = 0.54

METRIC_BAYES_GAMES = 200
WR_BETA_TO_ATA = -0.0033
UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

# Pick equity fit derived from mle draft_equity analysis
# based on "top_player" cohort which has wr about 63%
PICK_EQUITY_ARR = [
    0.022,  # pick one pick equity
    0.016,
    0.012,
    0.01,
    0.0086,
    0.0073,
    0.0061,
    0.005,
    0.004,
    0.0031,
    0.0023,
    0.0016,
    0.001,
    0.0005,
]

x = np.arange(1, 15)
PE_INDEX = 3
PE_COEF_1_0, PE_COEF_1_1, PE_COEF_1_2 = np.polyfit(
    x[0:PE_INDEX], PICK_EQUITY_ARR[0:PE_INDEX], 2
)
PE_COEF_2_0, PE_COEF_2_1, PE_COEF_2_2 = np.polyfit(
    x[PE_INDEX:], PICK_EQUITY_ARR[PE_INDEX:], 2
)

ADJ_FACTOR = 0.8
PE_COEF_1_0 = ADJ_FACTOR * float(PE_COEF_1_0)
PE_COEF_1_1 = ADJ_FACTOR * float(PE_COEF_1_1)
PE_COEF_1_2 = ADJ_FACTOR * float(PE_COEF_1_2)
PE_COEF_2_0 = ADJ_FACTOR * float(PE_COEF_2_0)
PE_COEF_2_1 = ADJ_FACTOR * float(PE_COEF_2_1)
PE_COEF_2_2 = ADJ_FACTOR * float(PE_COEF_2_2)


def meta_decay_factor(set_context: dict):
    t = set_context.get("observed_days")
    ft = set_context.get("projection_days")

    if t is None:
        return pl.lit(0)
    return pl.lit(
        DEQ_LOSS_FACTOR
        * (
            META_DECAY ** (t + ft)
            * (1 - SAMPLE_DECAY**t)
            * (1 - SAMPLE_DECAY * META_DECAY)
            / (1 - (SAMPLE_DECAY * META_DECAY) ** t)
            / (1 - SAMPLE_DECAY)
            - 1
        )
    )


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


def in_colors_lambda(colors):
    return lambda name: pl.col(f"deck_{name}") * pl.when(
        pl.col("main_colors") == colors
    ).then(1).otherwise(0)


def in_colors_bias_lambda(colors):
    return lambda name, set_context: pl.col(
        f"gp_in_colors_{colors}_{name}"
    ) * set_context.get(f"game_wr_excess_{colors}")


# fmt: off
ext = {
    ColName.NUM_GNS: ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name: pl.max_horizontal(
            0,
            pl.col(f"deck_{name}")
            - pl.col(f"drawn_{name}")
            - pl.col(f"opening_hand_{name}"),
        ), # lazy way to use SNC and NEO which don't have "tutored"
    ),
    ColName.DECK_TOTAL: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).sum().over('expansion'),
    ),
    ColName.WON_DECK_TOTAL: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).sum().over('expansion'),
    ),
    ColName.GP_WR_MEAN: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK_TOTAL) / pl.col(ColName.DECK_TOTAL),
    ),
    ColName.GP_WR_EXCESS: ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.GP_WR) - pl.col(ColName.GP_WR_MEAN),
    ),
    'pick_equity': ColSpec(
        col_type=ColType.AGG,
        expr=P1_PICK_EQUITY * (1 - (pl.col(ColName.ATA)-1) / ATA_DENOM).pow(2),
    ),
    'pick_equity_new': ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(pl.col(ColName.ATA) < PE_INDEX + 1).then(
            PE_COEF_1_0 * pl.col(ColName.ATA).pow(2) + 
            PE_COEF_1_1 * pl.col(ColName.ATA) + 
            PE_COEF_1_2
        ).otherwise(
            PE_COEF_2_0 * pl.col(ColName.ATA).pow(2) + 
            PE_COEF_2_1 * pl.col(ColName.ATA) + 
            PE_COEF_2_2
        )
    ),
    'deq_base': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col('gp_wr_b') - pl.col(ColName.GP_WR_MEAN) + 
              pl.col('pick_equity')) * pl.col(ColName.PCT_GP)
    ),
    'deq_base_new': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col('gp_wr_b') - pl.col(ColName.GP_WR_MEAN) + 
              pl.col('pick_equity_new')) * pl.col(ColName.PCT_GP)
    ),
    'skill_cohort_raw': ColSpec(
        col_type=ColType.GROUP_BY,
        expr=(pl.when(UNG == 1000).then(1200/(1200 + BAYES_GAMES)).otherwise(
            pl.when(UNG == 500).then(750/(750+BAYES_GAMES)).otherwise(
            pl.when(UNG == 100).then(300/(300+BAYES_GAMES)).otherwise(
            pl.when(UNG == 50).then(75/(75+BAYES_GAMES)).otherwise(
            pl.when(UNG == 10).then(30/(30+BAYES_GAMES)).otherwise(0)))))
                * (UGWR - BAYES_MU) + BAYES_MU)),
    'skill_cohort': ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.when(pl.col('skill_cohort_raw') < 0.49).then(pl.lit('1_Weak')).otherwise(
            pl.when(pl.col('skill_cohort_raw') < 0.52).then(pl.lit('2_Average')).otherwise(
                pl.when(pl.col('skill_cohort_raw') < 0.55).then(pl.lit('3_Above Average')).otherwise(
                    pl.when(pl.col('skill_cohort_raw') < 0.58).then(pl.lit('4_Competitive')).otherwise(
                        pl.when(pl.col('skill_cohort_raw') < 0.61).then(pl.lit('5_Strong')).otherwise(
                            pl.lit('6_Elite'))))))
    ),
    'deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).sum().over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)]),
    ),
    'won_deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).sum().over([pl.col(ColName.EXPANSION), pl.col(ColName.COLOR)]),
    ),
    'gp_wr_excess_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=((pl.col('won_deck_over_colors') / pl.col('deck_over_colors') - pl.col('gp_wr_mean')
               ) * PRECISION).round() / PRECISION
    ),
    'deck_small_sample': ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(pl.col(ColName.NAME).is_in(BASIC_LANDS) | (pl.col(ColName.DECK) < SAMPLE_THRESHOLD)
                     ).then(None).otherwise(1.0)
    ),
    'gp_wr_bayes_mu': ColSpec(
        col_type=ColType.AGG,
        expr =pl.col('gp_wr_mean') + WR_BETA_TO_ATA * (pl.col('ata') - 7)
    ),
    'gp_wr_b': ColSpec(
        col_type=ColType.AGG,
        expr = pl.col('deck_small_sample') * (
            pl.col('gp_wr_bayes_mu') * METRIC_BAYES_GAMES + pl.col(ColName.WON_DECK)
        ) / (pl.col(ColName.DECK) + METRIC_BAYES_GAMES)
    ),
    'gih_wr_17l': ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(pl.col(ColName.NAME).is_in(BASIC_LANDS) | (pl.col(ColName.NUM_GIH) < SAMPLE_THRESHOLD)
                     ).then(None).otherwise(pl.col(ColName.NUM_GIH_WON))/ (pl.col(ColName.NUM_GIH))
    ),
    'gp_wr_17l': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deck_small_sample') * pl.col(ColName.WON_DECK) / (pl.col(ColName.DECK))
    ),
    'gns_wr_17l': ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(pl.col(ColName.NAME).is_in(BASIC_LANDS) | (pl.col(ColName.NUM_GNS) < SAMPLE_THRESHOLD)
                     ).then(None).otherwise(pl.col(ColName.WON_NUM_GNS))/ (pl.col(ColName.NUM_GNS))
    ),
    'iwd_17l': ColSpec(
        col_type=ColType.AGG,
        expr = pl.col('gih_wr_17l') - pl.col('gns_wr_17l')
    ),
    'deq_bias_adj': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col('pick_equity') / P1_PICK_EQUITY - 1) * pl.col('gp_wr_bias_in'),
    ),
    'deq': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deq_base') + (pl.col('deq_bias_adj') + pl.col('deq_meta_adj')) * pl.col('pct_gp')
    ),
    'deq_new': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deq_base_new') + (pl.col('deq_bias_adj') + pl.col('deq_meta_adj')) * pl.col('pct_gp')
    ),
    'gp_wr_bias_adj': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('gp_wr_b') + pl.col('deq_bias_adj')
    ),
    'format_day_sum': ColSpec(
        col_type=ColType.PICK_SUM,
        expr=pl.col(ColName.FORMAT_DAY)
    ),
    'mean_day_picked': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('format_day_sum') / pl.col(ColName.NUM_TAKEN)
    ),
    'gp_wr_bias_in': ColSpec(
        col_type=ColType.CARD_ATTR,
        expr=lambda set_context: pl.lit(None) if 'gp_wr_excess_over_colors_W' 
        not in set_context else pl.when(
            pl.col(ColName.COLOR) == "UW").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_UW', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_W', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_U', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "BW").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_BW', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_W', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "RW").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_RW', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_W', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_R', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "GW").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_GW', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_W', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_G', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "BW").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_BW', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_W', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "BU").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_BU', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_U', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "RU").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_RU', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_U', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_R', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "GU").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_GU', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_U', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_G', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "BR").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_BR', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_R', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "BG").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_BG', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_G', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "GR").then(
                0.5 * set_context.get('gp_wr_excess_over_colors_GR', 0) 
                + 0.25 * set_context.get('gp_wr_excess_over_colors_G', 0)
                + 0.25 * set_context.get('gp_wr_excess_over_colors_R', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "W").then(
                set_context.get('gp_wr_excess_over_colors_W', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "U").then(
                set_context.get('gp_wr_excess_over_colors_U', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "B").then(
                set_context.get('gp_wr_excess_over_colors_B', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "R").then(
                set_context.get('gp_wr_excess_over_colors_R', 0)
            ).otherwise(pl.when(pl.col(ColName.COLOR) == "G").then(
                set_context.get('gp_wr_excess_over_colors_G', 0)
            ).otherwise(0))))))))))))))))
    ),
    'meta_regression_factor': ColSpec(
        col_type=ColType.CARD_ATTR,
        expr=meta_decay_factor
    ),
    'deq_meta_adj': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col('gp_wr_bias_in') + pl.col('deq_bias_adj')) * pl.col('meta_regression_factor')
    ),
    'color_group': ColSpec(
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
        )
    ),
    'deck_commons': ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name, card_context: pl.col(f'deck_{name}') * (
            1 if card_context[name]['rarity'] == 'common' else 0
        )
    ),
    'deck_rares': ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name, card_context: pl.col(f'deck_{name}') * (
            1 if card_context[name]['rarity'] == 'rare' else 0
        )
    ),
    'deck_commons_mean': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deck_commons') / pl.col('deck')
    ),
    'deck_rares_mean': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deck_rares') / pl.col('deck')
    ),
    **{
        f'gp_in_colors_{colors}': ColSpec(
            col_type=ColType.NAME_SUM,
            expr= in_colors_lambda(colors)
        ) for colors in color_sets
    },
    **{
        f'gp_bias_weight_in_colors_{colors}': ColSpec(
            col_type=ColType.NAME_SUM,
            expr = in_colors_bias_lambda(colors)
        ) for colors in color_sets
    },
    **{
        f'gp_wr_bias_in_colors_{colors}': ColSpec(
            col_type=ColType.AGG,
            expr = pl.col(f'gp_bias_weight_in_colors_{colors}') / pl.col(ColName.DECK)
        ) for colors in color_sets
    },
    'gp_in_colors_others': ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name: pl.col(f'deck_{name}') * pl.when(
            ~pl.col('main_colors').is_in(color_sets)).then(1).otherwise(0)
    ),
    'gp_bias_weight_in_colors_others': ColSpec(
        col_type=ColType.NAME_SUM,
        expr=lambda name, set_context: pl.col(f'gp_in_colors_others_{name}') * set_context.get('game_wr_excess_other')
    ),
    'gp_wr_bias_in_colors_other': ColSpec(
        col_type=ColType.AGG,
        expr = pl.col('gp_bias_weight_in_colors_others') / pl.col(ColName.DECK)
    ),
    'gp_wr_bias_new': ColSpec(
        col_type=ColType.AGG,
        expr = pl.sum_horizontal(
            [pl.col(f'gp_wr_bias_in_colors_{colors}') for colors in color_sets]
        ) + pl.col('gp_wr_bias_in_colors_other')
    )
}
# fmt: on


def deq_bias_set_context(
    set_codes: list[str],
    metric_filter: dict,
    observed_days: int | None = None,
    projection_days: int = 1,
):
    gpwr_oc = summon(
        set_codes,
        columns=["gp_wr_excess_over_colors"],
        group_by=["expansion", "color"],
        filter_spec=metric_filter,
        extensions=ext,
    )

    color_select = [
        "gp_wr_excess_over_colors_" + pl.col("color"),
        "gp_wr_excess_over_colors",
    ]

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
                for key, value in gpwr_oc.filter(pl.col("expansion") == set_code)
                .select(color_select)
                .rows_by_key("literal", unique=True)
                .items()
            },
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
            .select(
                pl.col(ColName.NUM_WON) / pl.col(ColName.NUM_GAMES)
            )[ColName.NUM_WON][0],
            "observed_days": observed_days,
            "projection_days": projection_days,
        }
        for set_code in set_codes
    }

    return set_context
