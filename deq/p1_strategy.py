import polars as pl
from spells import summon, ColName
from spells.extension import context_cols
from spells.log import make_verbose

from deq.deq import deq_bias_set_context, BASIC_LANDS, ext

TOP_FILTER = {ColName.PLAYER_COHORT: 'Top'}
LATE_FORMAT = {'lhs': ColName.FORMAT_DAY, 'op': '>=', 'rhs': 13}
EARLY_FORMAT = {'$not': LATE_FORMAT}
META_FILTER = {'$and': [TOP_FILTER, LATE_FORMAT]}

PACK_1_FILTER = {'pack_num': 1}
PICK_1_FILTER = {'pick_num': 1}

P1P1 = {'$and': [PICK_1_FILTER, PACK_1_FILTER]}
PRECISION = 2 ** 20

metrics = ['pick_equity', 'gp_wr', 'deq_base', 'deq', 'gp_wr_bias_adj', 'gih_wr']

@make_verbose
def p1_strat_analysis(set_codes: list[str], metric: str, metric_filter: dict | None = None, results_filter: dict | None = None):
    assert isinstance(set_codes, list), "Pass a list of set_codes!"
    p1_results_filter = {'$and': [P1P1, results_filter]} if results_filter else P1P1

    metric_filter = META_FILTER if metric_filter is None else metric_filter

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
    ).select(["expansion", "name", (pl.col(metric) * PRECISION).round() / PRECISION])

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
        card_context=context_df,
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
        card_context=context_df,
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
        [(pl.col(f"{metric}_strategy_win_rate") - pl.col("actual_win_rate")).alias(f"{metric}_strat_wr_delta")])

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
    p1_results_filter = {'$and': [P1P1, results_filter]} if results_filter else P1P1

    return summon(
        set_codes, 
        columns=[ColName.PICKED_MATCH_WR, ColName.EVENT_MATCHES_SUM, 'mean_day_picked'], 
        group_by=['wr_group'], 
        extensions=ext,
        filter_spec=p1_results_filter
    ).filter(~pl.col('wr_group').is_null()).sort('wr_group')

def all_metrics_analysis(sets: list[str], metrics: list[str], metric_filter: dict | None = None, results_filter: dict | None = None):
    metrics = []
    metric_results = {metric: p1_strat_analysis(sets, metric, metric_filter, results_filter) for metric in metrics}

