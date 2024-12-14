import polars as pl
from spells import summon, ColName, ColType, ColSpec
from spells.extension import stat_cols, context_cols

pl.Config.set_tbl_rows(1000)
pl.Config.set_tbl_cols(100)

P1_PICK_EQUITY = 0.03
ATA_DENOM = 14

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

ext = {
    'pick_equity': ColSpec(
        col_type=ColType.AGG,
        expr=P1_PICK_EQUITY * (1 - pl.col(ColName.ATA) / ATA_DENOM).pow(2),
    ),
    'deq_base': ColSpec(
        col_type=ColType.AGG,
        expr=(pl.col(ColName.GP_WR_EXCESS) + pl.col('pick_equity')) * pl.col(ColName.PCT_GP)
    ),
    'cohort': ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.when((UNG >= 500) & (UGWR > 0.65) | (UNG >= 100) & (UGWR > 0.73)).then(pl.lit('1 Best')).otherwise(
            pl.when((UNG >= 500) & (UGWR > 0.61) | (UNG >= 100) & (UGWR > 0.65)).then(pl.lit('2 Elite')).otherwise(
                pl.when((UNG >= 100) & (UGWR > 0.57) | (UNG >= 50) & (UGWR > 0.61)).then(pl.lit('3 Competitive')).otherwise(
                    pl.when((UNG >= 100) & (UGWR > 0.53) | (UGWR > 0.57)).then(pl.lit('4 Solid')).otherwise(pl.lit('5 Poor'))
                )
            )
        )
    ),
    'deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).over(pl.col(ColName.COLOR)).sum(),
    ),
    'won_deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).over(pl.col(ColName.COLOR)).sum(),
    ),
    'gp_wr_excess_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('won_deck_over_colors') / pl.col('deck_over_colors') - pl.col('gp_wr_mean')
    ),
    'gp_wr_bias_in': ColSpec(
        col_type=ColType.PICK_SUM,
        expr=lambda name, card_context: pl.lit(1),
    )
}

top_filter = {ColName.PLAYER_COHORT: 'Top'}
date_filter = {'lhs': ColName.FORMAT_DAY, 'op': '>=', 'rhs': 10}
meta_filter = {'$and': [top_filter, date_filter]}

sets = ['KTK', 'MKM', 'OTJ', 'MH3', 'BLB', 'DSK', 'FDN']

check_metrics = ['pick_equity', 'gp_wr', 'oh_wr', 'gih_wr', 'deq_base']

def behavior_query(set_code: str, check_metric: str):
    attr_ext = stat_cols(check_metric, silent=True)

    metric = f"{check_metric}_pwz"

    context_df = summon(set_code, columns=[metric], filter_spec=meta_filter, extensions=[ext, attr_ext])

    z_attr_ext = context_cols(metric, silent=True)
    columns = [f""]

    result_df = summon(set_code, columns=columns, group_by=['cohort'], filter_spec=date_filter, extensions=[z_attr_ext, ext], card_context=context_df)

    return result_df


def attenuate(wr, gp):
    next_gp = {
        1: 5,
        5: 10,
        10: 50,
        50: 100,
        100: 500,
        500: 1000,
        1000: 2000
    }[gp]

    assumed_games = 1/3 * next_gp + 2/3 * gp
    extra_games = 200
    extra_wr = 0.54

    new_wins = assumed_games * wr + extra_wr * extra_games
    new_total = assumed_games + extra_games

    return round(new_wins / new_total * 50) / 50
