import logging
from dataclasses import dataclass
import functools

import polars as pl

from spells import summon, ColName
from spells.log import make_verbose
from spells.extension import context_cols
from spells.config import all_sets
from spells.utils import wavg

from deq.deq import deq_bias_set_context, BASIC_LANDS, ext

TOP_FILTER = {ColName.PLAYER_COHORT: 'Top'}
LATE_FORMAT = {'lhs': ColName.FORMAT_DAY, 'op': '>=', 'rhs': 13}
EARLY_FORMAT = {'$not': LATE_FORMAT}
META_FILTER = {'$and': [TOP_FILTER, LATE_FORMAT]}

PACK_1_FILTER = {'pack_num': 1}
PICK_1_FILTER = {'pick_num': 1}

P1P1_PICK_EQUITY = 0.025

P1P1 = {'$and': [PICK_1_FILTER, PACK_1_FILTER]}
PRECISION = 2 ** 20

GROUP_FILTER = ~pl.col('wr_group').is_null()
WR_FILTER = ~pl.col(ColName.PICKED_MATCH_WR).is_null()

SEEN_IS_GREATEST = "seen_{0}_is_greatest"

METRICS = ['pick_equity', 'gp_wr', 'deq_base', 'deq', 'gp_wr_bias_adj', 'gih_wr', 'iwd']
LOG_TO_CONSOLE = logging.INFO

SETS = list(set(all_sets) - {'PIO', 'SIR'})
NEIGHBORS = 4 # 66 looks at 60 - (N-1)*2

@dataclass
class ModelDFs:
    weights_df: pl.DataFrame
    wr_df: pl.DataFrame
    fallback_df: pl.DataFrame

@dataclass
class MetricResult:
    df: pl.DataFrame
    mapped_df: pl.DataFrame

@dataclass
class AnalysisResult:
    df: pl.DataFrame
    agg_df: pl.DataFrame
    metric_results: dict[str, MetricResult]


def get_model_dfs(
    set_codes: list[str], 
    metric: str, 
    results_filter: dict | None, 
    metric_filter: dict | None,
) -> ModelDFs:
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
        extensions=ext, 
        set_context=set_context,
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

    wr_df = weights_df.drop(SEEN_IS_GREATEST.format(metric)).filter(
        GROUP_FILTER & WR_FILTER
    )

    # assume cards picked by nobody ever provide no value as a first pick
    # 'matches_per_pick' will be slightly wrong...
    fallback_df = summon(
        set_codes,
        columns=[ColName.PICKED_MATCH_WR, 'matches_per_pick', 'mean_day_picked'],
        group_by=['wr_group'],
        filter_spec=p1_results_filter,
        extensions=ext,
    ).select(
        ['wr_group', pl.col(ColName.PICKED_MATCH_WR) - P1P1_PICK_EQUITY, 'mean_day_picked', 'matches_per_pick']
    )

    weights_df = weights_df.select(
        ['expansion', 'name', 'wr_group', SEEN_IS_GREATEST.format(metric)]
    ).filter(
        (pl.col(SEEN_IS_GREATEST.format(metric))>0) & 
        GROUP_FILTER & ~pl.col('name').is_in(BASIC_LANDS)
    )

    return ModelDFs(
        weights_df=weights_df,
        wr_df=wr_df,
        fallback_df=fallback_df
    )

def strategy_mapped_df(
    model_dfs: ModelDFs, 
    card_parity: bool = False, 
) -> pl.DataFrame:
    wr_df = model_dfs.wr_df
    fallback_df = model_dfs.fallback_df

    if not card_parity:
        skill_control_df = p1_skill_control_df()
        wr_df = wr_df.join(skill_control_df, on=["wr_group"])
    else:
        wr_df = wr_df.with_columns([
            pl.lit(None).alias('up_one_wr_mod'), 
            pl.lit(None).alias('down_one_wr_mod')
        ])

    up_one_cols = [
        pl.col('wr_group') + 2,
        pl.col(ColName.PICKED_MATCH_WR) - pl.col('up_one_wr_mod'),
    ]

    down_one_cols = [
        pl.col('wr_group') - 2,
        pl.col(ColName.PICKED_MATCH_WR) - pl.col('down_one_wr_mod'),
    ]
    
    select_cols = [
        'expansion', 
        'name', 
        'matches_per_pick',
        'mean_day_picked',
        'up_one_wr_mod',
        'down_one_wr_mod',
    ]

    go_up_df = wr_df.select(
        select_cols + ['wr_group', ColName.PICKED_MATCH_WR]
    )
    go_down_df = go_up_df

    good_dfs = []
    remaining_df = model_dfs.weights_df

    logging.info("Joining and calculating results")
    join_keys = ['expansion', 'name', 'wr_group']
    iter = 0
    iter_max = 1 if card_parity else NEIGHBORS
    while iter < iter_max and len(remaining_df):
        misrep = pl.lit(iter).alias('misrep')

        good_dfs.append(
            remaining_df.join(go_up_df, on=join_keys).with_columns(misrep)
        )
        remaining_df = remaining_df.join(go_up_df, on=join_keys, how='anti')

        good_dfs.append(
            remaining_df.join(go_down_df, on=join_keys).with_columns(misrep)
        )
        remaining_df = remaining_df.join(go_down_df, on=join_keys, how='anti')

        go_up_df = go_up_df.select(select_cols + up_one_cols)
        go_down_df = go_down_df.select(select_cols + down_one_cols)

        iter += 1

    good_dfs.append(remaining_df.join(fallback_df, on='wr_group').with_columns(
        [
            pl.lit(None).alias('up_one_wr_mod'), 
            pl.lit(None).alias('down_one_wr_mod'),
            pl.lit(iter_max).alias('misrep'),
        ]
    ).select(good_dfs[0].columns))

    final_df = pl.concat(good_dfs)

    if card_parity:
        num_wr_groups = len(final_df.group_by('wr_group').count())
        keys_df = final_df.group_by(['expansion', 'name']).count().filter(
            pl.col('count') == num_wr_groups).select(['expansion', 'name']
        )
        final_df = final_df.join(keys_df, on=['expansion', 'name'])

    return final_df

def p1_strat_analysis(
    set_codes: list[str], 
    metric: str, 
    metric_filter: dict | None = None, 
    results_filter: dict | None = None,
    card_parity: bool = False,
    luck_control: bool = False,
):
    logging.info(f"Running p1 strategy analysis for metric {metric}")
    model_dfs = get_model_dfs(set_codes, metric, results_filter, metric_filter)

    mapped_df = strategy_mapped_df(model_dfs, card_parity)

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

    sim_df = get_simulated_winrates(mapped_df, metric, luck_control=luck_control)
    ret_df = base_wr_df.join(sim_df, on=["wr_group"])
    ret_df = ret_df.with_columns(
        [(pl.col(f"{metric}_strategy_win_rate") - pl.col("actual_win_rate")).alias(
            f"{metric}_strat_delta")]
    )

    return MetricResult(
        df=ret_df, 
        mapped_df=mapped_df
    )


def get_simulated_winrates(
    reweight_df: pl.DataFrame, 
    metric: str, 
    luck_control: bool = False
) -> pl.DataFrame:
    base_weight_col = (pl.col(f'seen_{metric}_is_greatest') * pl.col('matches_per_pick'))
    weight_col = (
         base_weight_col.sum().over(['expansion', 'name']) if luck_control else base_weight_col 
    ).alias(f'{metric}_weight')

    return reweight_df.select([
        'wr_group',
        weight_col,
        (weight_col * pl.col(ColName.PICKED_MATCH_WR)).alias('wr_weight'),
        (weight_col * pl.col('mean_day_picked')).alias('day_weight'),
        (weight_col * pl.col('misrep')).alias('misrep_weight'),
    ]).group_by(['wr_group']).sum().select([
        'wr_group',
        f'{metric}_weight',
        (pl.col('wr_weight') / pl.col('weight')).alias(f'{metric}_strategy_win_rate'),
        (pl.col('day_weight') / pl.col('weight')).alias(f'{metric}_strategy_mean_day'),
        (pl.col('misrep_weight') / pl.col('weight')).alias(f'{metric}_strategy_misrep'),
    ]).sort('wr_group')


@make_verbose(logging.INFO)
def all_metrics_analysis(
    metric_filter: dict | None = None, 
    results_filter: dict | None = None,
):
    metrics = METRICS 
    metric_results = {metric: p1_strat_analysis(
        SETS, 
        metric, 
        metric_filter=metric_filter, 
        results_filter=results_filter, 
    ) for metric in metrics}
    delta_dfs = [metric_results[metric].df.select([
        'wr_group', 
        f"{metric}_strat_delta", 
        f"{metric}_weight",
        f"{metric}_strategy_misrep"
    ]) for metric in metrics]

    result_df = functools.reduce(lambda prev, curr: prev.join(curr, on="wr_group"), delta_dfs)

    agg_df = wavg(result_df, [f"{metric}_strat_delta" for metric in metrics], [f"{metric}_weight" for metric in metrics])

    return AnalysisResult(
        df=result_df,
        agg_df=agg_df,
        metric_results=metric_results
    )
    

@functools.lru_cache(maxsize=None)
def p1_skill_control_df():
    """
    When we map events to neighboring groups, we want to adjust the observed win rates for the
    expected change in win rate due to everything about the skill cohort except the distribution
    of opening picks, since we will be controlling that.

    the analysis will generate win rates that reflect that controlled pick for each group, then
    diff(1) will take (this - prev), that is, the boost in win rate attributable to going to this
    group from the previous. So for the "down one" modification, which will map a group's results
    to be used by the group below, we want the opposite of that. So subtract.
    """
    res = p1_strat_analysis(SETS, "pick_equity", card_parity=True, luck_control=True)
    return res.df.select([
        'wr_group', 
        pl.col('pick_equity_strategy_win_rate').diff(1).alias('down_one_wr_mod'), 
        pl.col('pick_equity_strategy_win_rate').diff(-1).alias('up_one_wr_mod')
    ])
