import polars as pl
from spells import summon, ColName, ColType, ColSpec, view_select, get_names
from spells.extension import stat_cols, context_cols
from spells.config import all_sets

pl.Config.set_tbl_rows(1000)
pl.Config.set_tbl_cols(100)

BASIC_LANDS = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']
P1_PICK_EQUITY = 0.03
ATA_DENOM = 13

BAYES_GAMES = 150
BAYES_MU = 0.54

UNG = pl.col(ColName.USER_N_GAMES_BUCKET)
UGWR = pl.col(ColName.USER_GAME_WIN_RATE_BUCKET)

ext = {
    'pick_equity': ColSpec(
        col_type=ColType.AGG,
        expr=P1_PICK_EQUITY * (1 - (pl.col(ColName.ATA)-1) / ATA_DENOM).pow(2),
    ),
    'deq_base': ColSpec(
        col_type=ColType.AGG,
        expr=pl.when(pl.col(ColName.DECK) < 100).then(None).otherwise((pl.col(ColName.GP_WR_EXCESS) + pl.col('pick_equity')) * pl.col(ColName.PCT_GP))
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
    'wr_group': ColSpec(
        col_type=ColType.GROUP_BY,
        expr=pl.min_horizontal([pl.max_horizontal([((pl.when(UNG == 1000).then(1200/(1200 + BAYES_GAMES)).otherwise(
            pl.when(UNG == 500).then(750/(750+BAYES_GAMES)).otherwise(
            pl.when(UNG == 100).then(300/(300+BAYES_GAMES)).otherwise(
            pl.when(UNG == 50).then(75/(75+BAYES_GAMES)).otherwise(
            pl.when(UNG == 10).then(30/(30+BAYES_GAMES)).otherwise(0)))))
                * (UGWR - BAYES_MU) + BAYES_MU) * 50).round() * 2, 40]), 68]),
    ),
    'deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.DECK).sum().over(pl.col(ColName.COLOR)),
    ),
    'won_deck_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.WON_DECK).sum().over(pl.col(ColName.COLOR)),
    ),
    'gp_wr_excess_over_colors': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col('won_deck_over_colors') / pl.col('deck_over_colors') - pl.col('gp_wr_mean')
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
    'matches_per_pick': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col(ColName.EVENT_MATCHES_SUM) / pl.col(ColName.NUM_TAKEN)
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

top_filter = {ColName.PLAYER_COHORT: 'Top'}
date_filter = {'lhs': ColName.FORMAT_DAY, 'op': '>=', 'rhs': 13}
meta_filter = {'$and': [top_filter, date_filter]}

pack_1_filter = {'pack_num': 1}
pick_1_filter = {'pick_num': 1}

p1p1_filter = {'$and': [pick_1_filter, pack_1_filter]}
p1p1_date_filter = {'$and': [p1p1_filter, date_filter]}

metrics = ['pick_equity', 'gp_wr', 'deq_base', 'deq', 'gp_wr_bias_adj', 'gih_wr']

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
                select
            ).rows_by_key('literal', unique=True).items()
        } for set_code in set_codes
    }
    return set_context


def p1_strat_analysis(set_codes: list[str], metric: str, metric_filter: dict | None = None, results_filter: dict | None = None):
    assert isinstance(set_codes, list), "Pass a list of set_codes!"
    p1_results_filter = {'$and': [p1p1_filter, results_filter]} if results_filter else p1p1_filter

    metric_filter = meta_filter if metric_filter is None else metric_filter

    if metric in ['deq', 'gp_wr_bias_adj']:
        set_context = deq_bias_set_context(set_codes, metric_filter)
    else:
        set_context = None

    print(f"Calculation metric {metric} value for context")
    context_df = summon(
        set_codes, 
        columns=[metric], 
        filter_spec=metric_filter, 
        group_by=['expansion', 'name'],
        extensions=ext, 
        set_context=set_context
    )

    metric_cols = context_cols(metric, silent=True)
    seen_is_greatest = f"seen_{metric}_is_greatest"

    group_filter = ~pl.col('wr_group').is_null()
    wr_filter = ~pl.col(ColName.PICKED_MATCH_WR).is_null()

    print("Calculating seen greatest counts for weights")
    weights_df = summon(
        set_codes, 
        columns=[seen_is_greatest, ColName.PICKED_MATCH_WR, ColName.EVENT_MATCHES_SUM, 'matches_per_pick', 'mean_day_picked'], 
        group_by=['expansion', 'name', 'wr_group'], 
        filter_spec=p1_results_filter, 
        extensions=[metric_cols, ext], 
        card_context=context_df
    )

    wr_df = weights_df.drop(seen_is_greatest).filter(group_filter & wr_filter)

    weights_df = weights_df.select(
        ['expansion', 'name', 'wr_group', seen_is_greatest]
    ).filter((pl.col(seen_is_greatest)>0) & group_filter & ~pl.col('name').is_in(BASIC_LANDS))

    print("Calculating greatest taken df for simulation drafts")
    greatest_taken_wr_df = summon(
        set_codes, 
        columns=[ColName.PICKED_MATCH_WR, 'matches_per_pick', 'mean_day_picked'], 
        group_by=['expansion', 'name', 'wr_group'], 
        filter_spec={'$and': [{f"greatest_{metric}_taken": True}, p1_results_filter]},
        extensions=[metric_cols, ext],
        card_context=context_df
        ).filter(group_filter & wr_filter)

    out_one_col = pl.when(pl.col('wr_group') - 54 > -1).then(pl.col('wr_group') + 2).otherwise(
        pl.when(pl.col('wr_group') - 54 < -1).then(pl.col('wr_group') - 2)).alias('wr_group')

    down_one_col = (pl.col('wr_group') - 2).alias('wr_group')
    
    select_cols = [
        'expansion', 
        'name', 
        ColName.PICKED_MATCH_WR,
        'matches_per_pick',
        'mean_day_picked'
    ]

    to_join_pair = [greatest_taken_wr_df.select(select_cols + ['wr_group']), wr_df.select(select_cols + ['wr_group'])]
    go_down_pair = list(to_join_pair)

    good_dfs = []
    remaining_df = weights_df

    print("Joining and calculating results")
    iter = 0
    join_keys = ['expansion', 'name', 'wr_group']
    while iter < 20 and len(remaining_df):
        parity = iter % 2
        discrepancy = pl.lit(iter-parity).alias('discrepancy')
        join_df = remaining_df.join(to_join_pair[parity], on=join_keys)
        join_df = join_df.with_columns(discrepancy)
        good_dfs.append(join_df)
        
        remaining_df = remaining_df.join(to_join_pair[parity], on=join_keys, how='anti')

        join_df = remaining_df.join(go_down_pair[parity], on=join_keys)
        join_df = join_df.with_columns(discrepancy)
        good_dfs.append(join_df)
        
        remaining_df = remaining_df.join(go_down_pair[parity], on=join_keys, how='anti')

        if iter % 2 == 1:
            for i in [0,1]:
                to_join_pair[i] = to_join_pair[i].select(select_cols + [out_one_col])
                go_down_pair[i] = go_down_pair[i].select(select_cols + [down_one_col])
        iter += 1

    final_df = pl.concat(good_dfs)

    base_weight = pl.col(ColName.EVENT_MATCHES_SUM)
    base_wr_df = wr_df.select([
        'wr_group', 
        base_weight, 
        (base_weight * pl.col('mean_day_picked')).alias('day_weight'),
        (base_weight * pl.col(ColName.PICKED_MATCH_WR)).alias('wr_weight')
    ]).group_by('wr_group').sum().select([
        'wr_group',
        base_weight,
        (pl.col('wr_weight') / base_weight).alias("actual_win_rate"),
        (pl.col('day_weight') / base_weight).alias("mean_day_picked"),
    ]).sort('wr_group')

    sim_df = get_simulated_winrates(final_df, metric)
    ret_df = base_wr_df.join(sim_df, on=["wr_group"])
    ret_df = ret_df.with_columns(
        [(pl.col(f"{metric}_strategy_win_rate") - pl.col("actual_win_rate")).alias("f{metric}_strat_wr_delta")])

    print(f"Returning, {len(remaining_df)} rows unaccounted for")
    return ret_df, remaining_df

def get_simulated_winrates(reweight_df, metric):
    weight_col = (pl.col(f'seen_{metric}_is_greatest') * pl.col('matches_per_pick')).alias('weight')

    return reweight_df.select([
        'wr_group',
        weight_col,
        (weight_col * pl.col(ColName.PICKED_MATCH_WR)).alias('wr_weight'),
        (weight_col * pl.col('mean_day_picked')).alias('day_weight'),
        (weight_col * pl.col('discrepancy')).alias('discrepancy_weight'),
    ]).group_by(['wr_group']).sum().select([
        'wr_group',
        pl.col('weight'),
        (pl.col('wr_weight') / pl.col('weight')).alias(f'{metric}_strategy_win_rate'),
        (pl.col('day_weight') / pl.col('weight')).alias(f'{metric}_strategy_mean_day'),
        (pl.col('discrepancy_weight') / pl.col('weight')).alias(f'{metric}_strategy_discrepancy'),
    ]).sort('wr_group')

def p1p1_win_rate(set_codes, results_filter:dict | None = None):
    p1_results_filter = {'$and': [p1p1_filter, results_filter]} if results_filter else p1p1_filter

    return summon(
        set_codes, 
        columns=[ColName.PICKED_MATCH_WR, ColName.EVENT_MATCHES_SUM, 'mean_day_picked'], 
        group_by=['wr_group'], 
        extensions=ext,
        filter_spec=p1_results_filter
    ).filter(~pl.col('wr_group').is_null()).sort('wr_group')

def all_metrics_analysis(metrics: list[str], metric_filter: dict | None = None, results_filter: dict | None = None):
    pass
