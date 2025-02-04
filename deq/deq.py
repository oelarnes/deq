import polars as pl
from spells import summon, ColName, ColType, ColSpec

BASIC_LANDS = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']
P1_PICK_EQUITY = 0.03
ATA_DENOM = 13

PRECISION = 2 ** 20

BAYES_GAMES = 150
BAYES_MU = 0.54

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

ext = {
    ColName.GNS_WR: ColSpec(
        col_type=ColType.AGG,
        expr=(BAYES_MU * BAYES_GAMES + pl.col(ColName.WON_NUM_GNS))/ (pl.col(ColName.NUM_GNS) + BAYES_GAMES)
    ),
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
    'deq_base': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col(ColName.GP_WR_EXCESS) + pl.col('pick_equity')) * pl.col(ColName.PCT_GP)
    ),
    'skill_cohort': ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.min_horizontal([pl.max_horizontal([((pl.when(UNG == 1000).then(1200/(1200 + BAYES_GAMES)).otherwise(
            pl.when(UNG == 500).then(750/(750+BAYES_GAMES)).otherwise(
            pl.when(UNG == 100).then(300/(300+BAYES_GAMES)).otherwise(
            pl.when(UNG == 50).then(75/(75+BAYES_GAMES)).otherwise(
            pl.when(UNG == 10).then(30/(30+BAYES_GAMES)).otherwise(0)))))
                * (UGWR - BAYES_MU) + BAYES_MU) * 50).round() * 2, 42]), 66]),
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
        expr=((pl.col('won_deck_over_colors') / pl.col('deck_over_colors') - pl.col('gp_wr_mean')) * PRECISION).round() / PRECISION
    ),
    'gih_wr': ColSpec(
        col_type=ColType.AGG,
        expr=(BAYES_MU * BAYES_GAMES + pl.col(ColName.NUM_GIH_WON))/ (pl.col(ColName.NUM_GIH) + BAYES_GAMES)
    ),
    'gp_wr': ColSpec(
        col_type=ColType.AGG,
        expr=(BAYES_MU * BAYES_GAMES + pl.col(ColName.WON_DECK)) / (pl.col(ColName.DECK) + BAYES_GAMES),
    ),
    'deq_bias_adj': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col('pick_equity') / P1_PICK_EQUITY - 1) * pl.col('gp_wr_bias_in'),
    ),
    'deq': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('deq_base') + pl.col('deq_bias_adj') * pl.col('pct_gp')
    ),
    'gp_wr_bias_adj': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('gp_wr') + pl.col('deq_bias_adj')
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
        expr=lambda set_context: pl.lit(None) if 'gp_wr_excess_over_colors_W' not in set_context else pl.when(
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
}

def deq_bias_set_context(set_codes: list[str], metric_filter: dict):
    gpwr_oc = summon(
        set_codes, 
        columns=['gp_wr_excess_over_colors'], 
        group_by=['expansion', 'color'], 
        filter_spec=metric_filter, 
        extensions=ext
    )

    select = ['gp_wr_excess_over_colors_' + pl.col('color'), 'gp_wr_excess_over_colors']

    set_context = {
        set_code: {
            key:value[0] for key, value in gpwr_oc.filter(pl.col('expansion') == set_code).select(
                select).rows_by_key('literal', unique=True).items()
        } for set_code in set_codes
    }

    return set_context

