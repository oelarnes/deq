import polars as pl
from spells import summon, ColName, ColType, ColSpec
from spells.extension import stat_cols, context_cols

pl.Config.set_tbl_rows(1000)
pl.Config.set_tbl_cols(100)

P1_PICK_EQUITY = 0.03
ATA_DENOM = 13

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

ext = {
    "pick_equity": ColSpec(
        col_type=ColType.AGG,
        expr=P1_PICK_EQUITY * (1 - (pl.col(ColName.ATA) - 1) / ATA_DENOM).pow(2),
    ),
    "deq_base": ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col(ColName.GP_WR_EXCESS) + pl.col("pick_equity"))
        * pl.col(ColName.PCT_GP),
    ),
    "cohort": ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.when((UNG >= 500) & (UGWR > 0.65) | (UNG >= 100) & (UGWR > 0.73))
        .then(pl.lit("1 Best"))
        .otherwise(
            pl.when((UNG >= 500) & (UGWR > 0.61) | (UNG >= 100) & (UGWR > 0.65))
            .then(pl.lit("2 Elite"))
            .otherwise(
                pl.when((UNG >= 100) & (UGWR > 0.57) | (UNG >= 50) & (UGWR > 0.61))
                .then(pl.lit("3 Competitive"))
                .otherwise(
                    pl.when((UNG >= 100) & (UGWR > 0.53) | (UGWR > 0.57))
                    .then(pl.lit("4 Solid"))
                    .otherwise(pl.lit("5 Poor"))
                )
            )
        ),
    ),
    "deck_over_colors": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).sum().over(pl.col(ColName.COLOR)),
    ),
    "won_deck_over_colors": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).sum().over(pl.col(ColName.COLOR)),
    ),
    "gp_wr_excess_over_colors": ColSpec(
        col_type=ColType.AGG,
        expr=pl.col("won_deck_over_colors") / pl.col("deck_over_colors")
        - pl.col("gp_wr_mean"),
    ),
}

context_ext = {
    "gp_wr_bias_in": ColSpec(
        col_type=ColType.CARD_ATTR,
        expr=lambda set_context: pl.when(pl.col(ColName.COLOR) == "UW")
        .then(
            0.5 * set_context["gp_wr_excess_over_colors_UW"]
            + 0.25 * set_context["gp_wr_excess_over_colors_W"]
            + 0.25 * set_context["gp_wr_excess_over_colors_U"]
        )
        .otherwise(
            pl.when(pl.col(ColName.COLOR) == "BW")
            .then(
                0.5 * set_context["gp_wr_excess_over_colors_BW"]
                + 0.25 * set_context["gp_wr_excess_over_colors_W"]
                + 0.25 * set_context["gp_wr_excess_over_colors_B"]
            )
            .otherwise(
                pl.when(pl.col(ColName.COLOR) == "RW")
                .then(
                    0.5 * set_context["gp_wr_excess_over_colors_RW"]
                    + 0.25 * set_context["gp_wr_excess_over_colors_W"]
                    + 0.25 * set_context["gp_wr_excess_over_colors_R"]
                )
                .otherwise(
                    pl.when(pl.col(ColName.COLOR) == "GW")
                    .then(
                        0.5 * set_context["gp_wr_excess_over_colors_GW"]
                        + 0.25 * set_context["gp_wr_excess_over_colors_W"]
                        + 0.25 * set_context["gp_wr_excess_over_colors_G"]
                    )
                    .otherwise(
                        pl.when(pl.col(ColName.COLOR) == "BW")
                        .then(
                            0.5 * set_context["gp_wr_excess_over_colors_BW"]
                            + 0.25 * set_context["gp_wr_excess_over_colors_W"]
                            + 0.25 * set_context["gp_wr_excess_over_colors_B"]
                        )
                        .otherwise(
                            pl.when(pl.col(ColName.COLOR) == "BU")
                            .then(
                                0.5 * set_context["gp_wr_excess_over_colors_BU"]
                                + 0.25 * set_context["gp_wr_excess_over_colors_U"]
                                + 0.25 * set_context["gp_wr_excess_over_colors_B"]
                            )
                            .otherwise(
                                pl.when(pl.col(ColName.COLOR) == "RU")
                                .then(
                                    0.5 * set_context["gp_wr_excess_over_colors_RU"]
                                    + 0.25 * set_context["gp_wr_excess_over_colors_U"]
                                    + 0.25 * set_context["gp_wr_excess_over_colors_R"]
                                )
                                .otherwise(
                                    pl.when(pl.col(ColName.COLOR) == "GU")
                                    .then(
                                        0.5 * set_context["gp_wr_excess_over_colors_GU"]
                                        + 0.25
                                        * set_context["gp_wr_excess_over_colors_U"]
                                        + 0.25
                                        * set_context["gp_wr_excess_over_colors_G"]
                                    )
                                    .otherwise(
                                        pl.when(pl.col(ColName.COLOR) == "BR")
                                        .then(
                                            0.5
                                            * set_context["gp_wr_excess_over_colors_BR"]
                                            + 0.25
                                            * set_context["gp_wr_excess_over_colors_R"]
                                            + 0.25
                                            * set_context["gp_wr_excess_over_colors_B"]
                                        )
                                        .otherwise(
                                            pl.when(pl.col(ColName.COLOR) == "BG")
                                            .then(
                                                0.5
                                                * set_context[
                                                    "gp_wr_excess_over_colors_BG"
                                                ]
                                                + 0.25
                                                * set_context[
                                                    "gp_wr_excess_over_colors_G"
                                                ]
                                                + 0.25
                                                * set_context[
                                                    "gp_wr_excess_over_colors_B"
                                                ]
                                            )
                                            .otherwise(
                                                pl.when(pl.col(ColName.COLOR) == "GR")
                                                .then(
                                                    0.5
                                                    * set_context[
                                                        "gp_wr_excess_over_colors_GR"
                                                    ]
                                                    + 0.25
                                                    * set_context[
                                                        "gp_wr_excess_over_colors_G"
                                                    ]
                                                    + 0.25
                                                    * set_context[
                                                        "gp_wr_excess_over_colors_R"
                                                    ]
                                                )
                                                .otherwise(
                                                    pl.when(
                                                        pl.col(ColName.COLOR) == "W"
                                                    )
                                                    .then(
                                                        set_context[
                                                            "gp_wr_excess_over_colors_W"
                                                        ]
                                                    )
                                                    .otherwise(
                                                        pl.when(
                                                            pl.col(ColName.COLOR) == "U"
                                                        )
                                                        .then(
                                                            set_context[
                                                                "gp_wr_excess_over_colors_U"
                                                            ]
                                                        )
                                                        .otherwise(
                                                            pl.when(
                                                                pl.col(ColName.COLOR)
                                                                == "B"
                                                            )
                                                            .then(
                                                                set_context[
                                                                    "gp_wr_excess_over_colors_B"
                                                                ]
                                                            )
                                                            .otherwise(
                                                                pl.when(
                                                                    pl.col(
                                                                        ColName.COLOR
                                                                    )
                                                                    == "R"
                                                                )
                                                                .then(
                                                                    set_context[
                                                                        "gp_wr_excess_over_colors_R"
                                                                    ]
                                                                )
                                                                .otherwise(
                                                                    pl.when(
                                                                        pl.col(
                                                                            ColName.COLOR
                                                                        )
                                                                        == "G"
                                                                    )
                                                                    .then(
                                                                        set_context[
                                                                            "gp_wr_excess_over_colors_G"
                                                                        ]
                                                                    )
                                                                    .otherwise(0)
                                                                )
                                                            )
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        ),
    ),
    "deq_bias_adj": ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col("pick_equity") / P1_PICK_EQUITY - 1) * pl.col("gp_wr_bias_in"),
    ),
    "deq": ColSpec(
        col_type=ColType.AGG, expr=pl.col("deq_base") + pl.col("deq_bias_adj")
    ),
}

top_filter = {ColName.PLAYER_COHORT: "Top"}
date_filter = {"lhs": ColName.FORMAT_DAY, "op": ">=", "rhs": 10}
meta_filter = {"$and": [top_filter, date_filter]}

sets = [
    "FND",
    "DSK",
    "BLB",
    "MH3",
    "OTJ",
    "MKM",
    "LCI",
    "WOE",
    "LTR",
    "MOM",
    "ONE",
    "BRO",
    "DMU",
    "SNC",
    "NEO",
]

check_metrics = ["pick_equity", "gp_wr", "oh_wr", "gih_wr", "deq_base"]


def deq_bias_set_context(set_code: str):
    gpwr_oc = summon(
        set_code,
        columns=["gp_wr_excess_over_colors"],
        group_by=["color"],
        filter_spec=meta_filter,
        extensions=ext,
    )
    select = ["gp_wr_excess_over_colors_" + pl.col("color"), "gp_wr_excess_over_colors"]

    set_context = {
        key: value[0]
        for key, value in gpwr_oc.select(select)
        .rows_by_key("literal", unique=True)
        .items()
    }
    return set_context


def behavior_query(set_code: str, check_metric: str):
    attr_ext = stat_cols(check_metric, silent=True)

    metric = f"{check_metric}_pwz"

    context_df = summon(
        set_code, columns=[metric], filter_spec=meta_filter, extensions=[ext, attr_ext]
    )

    z_attr_ext = context_cols(metric, silent=True)
    columns = [f""]

    result_df = summon(
        set_code,
        columns=columns,
        group_by=["cohort"],
        filter_spec=date_filter,
        extensions=[z_attr_ext, ext],
        card_context=context_df,
    )

    return result_df


def attenuate(wr, gp):
    next_gp = {1: 5, 5: 10, 10: 50, 50: 100, 100: 500, 500: 1000, 1000: 2000}[gp]

    assumed_games = 1 / 3 * next_gp + 2 / 3 * gp
    extra_games = 200
    extra_wr = 0.54

    new_wins = assumed_games * wr + extra_wr * extra_games
    new_total = assumed_games + extra_games

    return round(new_wins / new_total * 50) / 50
