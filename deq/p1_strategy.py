import logging
from dataclasses import dataclass
import functools

import polars as pl

from spells import summon, ColName, ColSpec, ColType
from spells.extension import context_cols
from spells.log import make_verbose
from spells.config import all_sets

from deq.deq import deq_bias_set_context, BASIC_LANDS, ext, BAYES_GAMES, BAYES_MU

TOP_FILTER = {ColName.PLAYER_COHORT: 'Top'}
LATE_FORMAT = {'lhs': ColName.FORMAT_DAY, 'op': '>=', 'rhs': 13}
EARLY_FORMAT = {'$not': LATE_FORMAT}
META_FILTER = {'$and': [TOP_FILTER, LATE_FORMAT]}

PACK_1_FILTER = {'pack_num': 1}
PICK_1_FILTER = {'pick_num': 1}

P1P1 = {'$and': [PICK_1_FILTER, PACK_1_FILTER]}
PRECISION = 2 ** 20

GROUP_FILTER = ~pl.col('wr_group').is_null()
WR_FILTER = ~pl.col(ColName.PICKED_MATCH_WR).is_null()

SEEN_IS_GREATEST = "seen_{0}_is_greatest"

metrics = ['pick_equity', 'gp_wr', 'deq_base', 'deq', 'gp_wr_bias_adj', 'gih_wr', 'iwd']

@dataclass
class ModelDFs:
    weights_df: pl.DataFrame
    greatest_taken_wr_df: pl.DataFrame
    wr_df: pl.DataFrame

@dataclass
class Mapped:
    df: pl.DataFrame
    unmapped: pl.DataFrame

@dataclass
class Result:
    df: pl.DataFrame
    mapped: Mapped

def get_model_dfs(
    set_codes: list[str], 
    metric: str, 
    results_filter: dict | None, 
    metric_filter: dict | None
) -> ModelDFs:
    if metric == ColName.IWD:
        extensions = {
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
            **ext
        }
    else:
        extensions = dict(ext)
    assert isinstance(set_codes, list), "Pass a list of set_codes!"
    p1_results_filter = {'$and': [P1P1, results_filter]} if results_filter else P1P1

    metric_filter = META_FILTER if metric_filter is None else metric_filter

    if metric in ['deq', 'gp_wr_bias_adj']:
        set_context = deq_bias_set_context(set_codes, metric_filter)
    else:
        set_context = None

    logging.info(f"Calculation metric {metric} value for context")
    context_df = summon(
        set_codes, 
        columns=[metric], 
        filter_spec=metric_filter, 
        group_by=['expansion', 'name'],
        extensions=extensions, 
        set_context=set_context
    ).select(["expansion", "name", (pl.col(metric) * PRECISION).round() / PRECISION])

    metric_cols = context_cols(metric, silent=True)

    logging.info("Calculating seen greatest counts for weights")
    weights_df = summon(
        set_codes, 
        columns=[SEEN_IS_GREATEST.format(metric), ColName.PICKED_MATCH_WR, ColName.EVENT_MATCHES_SUM, 'matches_per_pick', 'mean_day_picked'], 
        group_by=['expansion', 'name', 'wr_group'], 
        filter_spec=p1_results_filter, 
        extensions=[metric_cols, ext], 
        card_context=context_df,
        use_streaming=True,
    )

    logging.info("Calculating greatest taken df for simulation drafts")
    greatest_taken_wr_df = summon(
        set_codes,
        columns=[ColName.PICKED_MATCH_WR, 'matches_per_pick', 'mean_day_picked'], 
        group_by=['expansion', 'name', 'wr_group'],
        filter_spec={'$and': [{f"greatest_{metric}_taken": True}, p1_results_filter]},
        extensions=[metric_cols, ext],
        card_context=context_df,
        use_streaming=True,
    ).filter(GROUP_FILTER & WR_FILTER)

    wr_df = weights_df.drop(SEEN_IS_GREATEST.format(metric)).filter(GROUP_FILTER & WR_FILTER)

    weights_df = weights_df.select(
        ['expansion', 'name', 'wr_group', SEEN_IS_GREATEST.format(metric)]
    ).filter((pl.col(SEEN_IS_GREATEST.format(metric))>0) & GROUP_FILTER & ~pl.col('name').is_in(BASIC_LANDS))

    return ModelDFs(
        weights_df=weights_df,
        greatest_taken_wr_df=greatest_taken_wr_df,
        wr_df=wr_df
    )

def strategy_mapped_df(model_dfs: ModelDFs, card_parity: bool = False) -> Mapped:
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

    to_join_pair = [
        model_dfs.greatest_taken_wr_df.select(select_cols + ['wr_group']), 
        model_dfs.wr_df.select(select_cols + ['wr_group'])
    ]
    go_down_pair = list(to_join_pair)

    good_dfs = []
    remaining_df = model_dfs.weights_df

    logging.info("Joining and calculating results")
    join_keys = ['expansion', 'name', 'wr_group']
    if card_parity:
        iter = 1
        iter_max = 2
    else:
        iter = 0
        iter_max = 20
    while iter < iter_max and len(remaining_df):
        parity = iter % 2
        discrepancy = pl.lit(iter // 2).alias('discrepancy')

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

    if card_parity:
        num_wr_groups = len(final_df.group_by('wr_group').count())
        keys_df = final_df.group_by(['expansion', 'name']).count().filter(pl.col('count') == num_wr_groups).select(['expansion', 'name'])
        final_df = final_df.join(keys_df, on=['expansion', 'name'])

    return Mapped(
        df=final_df,
        unmapped=remaining_df
    )

@make_verbose(logging.INFO)
def p1_strat_analysis(
    set_codes: list[str], 
    metric: str, 
    metric_filter: dict | None = None, 
    results_filter: dict | None = None,
    card_parity: bool = False,
    luck_control: bool = False
):
    assert not card_parity or metric == "pick_equity", "use pick equity for skill control pass"
    # to use existing cache for other metrics, add to ext when convenient

    model_dfs = get_model_dfs(set_codes, metric, results_filter, metric_filter)

    mapped = strategy_mapped_df(model_dfs, card_parity)

    base_weight = pl.col(ColName.EVENT_MATCHES_SUM)
    base_wr_df = model_dfs.wr_df.select([
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

    sim_df = get_simulated_winrates(mapped.df, metric, luck_control=luck_control)
    ret_df = base_wr_df.join(sim_df, on=["wr_group"])
    ret_df = ret_df.with_columns(
        [(pl.col(f"{metric}_strategy_win_rate") - pl.col("actual_win_rate")).alias(f"{metric}_strat_wr_delta")])

    print(f"Returning, {len(mapped.unmapped)} rows unaccounted for")
    return Result(
        df=ret_df, 
        mapped=mapped
    )

def get_simulated_winrates(reweight_df: pl.DataFrame, metric: str, luck_control: bool = False) -> pl.DataFrame:
    base_weight_col = (pl.col(f'seen_{metric}_is_greatest') * pl.col('matches_per_pick'))
    weight_col = (
         base_weight_col.sum() if luck_control else base_weight_col 
    ).alias('weight')

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

@functools.lru_cache(maxsize=None)
def p1_skill_control_df():
    return p1_strat_analysis(all_sets, "pick_equity", card_parity=True, luck_control=True)
