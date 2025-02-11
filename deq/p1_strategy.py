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
LATE_TOP = {'$and': [TOP_FILTER, LATE_FORMAT]}
EARLY_TOP = {'$and': [TOP_FILTER, EARLY_FORMAT]}

PACK_1_FILTER = {'pack_num': 1}
PICK_1_FILTER = {'pick_num': 1}

P1P1_PICK_EQUITY = 0.025

P1P1 = {'$and': [PICK_1_FILTER, PACK_1_FILTER]}
PRECISION = 2 ** 20

GROUP_FILTER = ~pl.col('skill_cohort').is_null()

METRICS = ['pick_equity', 'gp_wr_17l', 'deq', 'gih_wr_17l', 'iwd']
LOG_TO_CONSOLE = logging.INFO

SETS = list(set(all_sets))
NEIGHBORS = 4 # 66 looks at 60 - (N-1)*2

@dataclass
class ModelDFs:
    metric: str
    weights_df: pl.DataFrame
    wr_df: pl.DataFrame
    fallback_df: pl.DataFrame
    context_df: pl.DataFrame


@dataclass
class MetricResult:
    df: pl.DataFrame
    mapped_df: pl.DataFrame


@dataclass
class AnalysisResult:
    df: pl.DataFrame
    agg_df: pl.DataFrame
    metric_results: dict[str, MetricResult]

def seen_is_greatest(
    metric: str
) -> str:
    return f"seen_{metric}_is_greatest"

def get_metric_context(
    set_codes: list[str],
    metrics: list[str],
    filter_spec: dict,
) -> pl.DataFrame:
    set_context = deq_bias_set_context(set_codes, filter_spec)

    metrics_select = [(pl.col(metric) * PRECISION).round() / PRECISION for metric in metrics]
    context_df = summon(
        set_codes, 
        columns=metrics, 
        filter_spec=filter_spec, 
        group_by=['expansion', 'name'],
        extensions=ext, 
        set_context=set_context,
    ).select(["expansion", "name", *metrics_select])
    return context_df


def get_model_dfs(
    set_codes: list[str], 
    metric: str, 
    results_filter: dict | None, 
    metric_filter: dict | None,
) -> ModelDFs:
    assert isinstance(set_codes, list), "Pass a list of set_codes!"

    p1_results_filter = {'$and': [P1P1, results_filter]} if results_filter else P1P1
    metric_filter = TOP_FILTER if metric_filter is None else metric_filter

    context_df = get_metric_context(set_codes, [metric], metric_filter)

    metric_cols = context_cols(metric, silent=True)

    logging.info("Calculating substitution weights and results")
    weights_df = summon(
        set_codes, 
        columns=[
            seen_is_greatest(metric), 
            ColName.EVENT_MATCH_WINS_SUM, 
            ColName.EVENT_MATCHES_SUM, 
            ColName.NUM_TAKEN,
        ], 
        group_by=['expansion', 'name', 'skill_cohort'], 
        filter_spec=p1_results_filter, 
        extensions=[metric_cols, ext], 
        card_context=context_df,
        use_streaming=True,
    )

    wr_df = weights_df.drop(seen_is_greatest(metric)).filter(
        GROUP_FILTER & (pl.col(ColName.NUM_TAKEN) > 0) & (pl.col(ColName.EVENT_MATCHES_SUM) > 0)
    )

    weights_df = weights_df.select(
        ['expansion', 'name', 'skill_cohort', seen_is_greatest(metric)]
    ).filter(
        (pl.col(seen_is_greatest(metric))>0) & 
        GROUP_FILTER & ~pl.col('name').is_in(BASIC_LANDS)
    )

    # assume cards picked by nobody ever provide no value as a first pick
    fallback_df = summon(
        set_codes,
        columns=[ColName.EVENT_MATCH_WINS_SUM, ColName.EVENT_MATCHES_SUM, ColName.NUM_TAKEN],
        group_by=['skill_cohort'],
        filter_spec=p1_results_filter,
        extensions=ext,
    ).select(
        [
            'skill_cohort', 
            pl.col(ColName.EVENT_MATCH_WINS_SUM) - P1P1_PICK_EQUITY * pl.col(ColName.EVENT_MATCHES_SUM), 
            pl.col(ColName.EVENT_MATCHES_SUM),
            pl.col(ColName.NUM_TAKEN)
        ]
    )

    return ModelDFs(
        metric=metric,
        weights_df=weights_df,
        wr_df=wr_df,
        fallback_df=fallback_df,
        context_df=context_df
    )


def strategy_mapped_df(
    model_dfs: ModelDFs, 
    card_parity: bool = False, 
) -> pl.DataFrame:
    wr_df = model_dfs.wr_df

    select_cols = [
        'expansion', 
        'name', 
        ColName.EVENT_MATCHES_SUM,
        ColName.NUM_TAKEN,
    ]

    join_keys = ['expansion', 'name', 'skill_cohort']
    remaining_df = model_dfs.weights_df

    substitution_df = remaining_df.join(
        wr_df.select(select_cols + [
            'skill_cohort',
            pl.col(ColName.EVENT_MATCH_WINS_SUM).cast(pl.Float64),
            pl.lit('In Group').alias('representation_class')
        ]),
        on = join_keys 
    )

    logging.info("Joining and calculating results")
    
    if not card_parity:
        remaining_df = remaining_df.join(wr_df, on = join_keys, how='anti')
        sub_dfs = []

        go_up_df = go_down_df = wr_df 
        iter = 1
        skill_control_df = p1_skill_control_df()
        for iter in range(NEIGHBORS):
            up_one_cols = [
                pl.col('skill_cohort') + 2,
                pl.col(ColName.EVENT_MATCH_WINS_SUM) - pl.col('up_one_wr_mod') * pl.col(ColName.EVENT_MATCHES_SUM),
                pl.lit(f"Up {iter}").alias('representation_class')
            ]

            down_one_cols = [
                pl.col('skill_cohort') - 2,
                pl.col(ColName.EVENT_MATCH_WINS_SUM) - pl.col('down_one_wr_mod') * pl.col(ColName.EVENT_MATCHES_SUM),
                pl.lit(f"Down {iter}").alias('representation_class')
            ]

            go_up_df = go_up_df.join(skill_control_df, on=["skill_cohort"]).select(select_cols + up_one_cols)
            go_down_df = go_down_df.join(skill_control_df, on=["skill_cohort"]).select(select_cols + down_one_cols)

            sub_dfs.append(remaining_df.join(go_up_df, on=join_keys))
            remaining_df = remaining_df.join(go_up_df, on=join_keys, how='anti')

            sub_dfs.append(remaining_df.join(go_down_df, on=join_keys))
            remaining_df = remaining_df.join(go_down_df, on=join_keys, how='anti')

        sub_dfs.append(remaining_df.join(model_dfs.fallback_df, on='skill_cohort').with_columns(
            pl.lit('Fallback').alias('representation_class')
        ).select(substitution_df.columns))

        substitution_df = pl.concat([substitution_df, *sub_dfs])

    else:
        num_skill_cohorts = len(substitution_df.group_by('skill_cohort').count())
        keys_df = substitution_df.group_by(['expansion', 'name']).count().filter(
            pl.col('count') == num_skill_cohorts).select(['expansion', 'name']
        )
        substitution_df = substitution_df.join(keys_df, on=['expansion', 'name'])

    metric = model_dfs.metric

    df = substitution_df.with_columns(
        (pl.col(seen_is_greatest(metric)) / pl.col(ColName.NUM_TAKEN)).alias("deriv")
    ).with_columns([
        (pl.col("deriv") * pl.col(ColName.EVENT_MATCHES_SUM)).alias("weight"),
        (pl.col("deriv") * pl.col(ColName.EVENT_MATCH_WINS_SUM)).alias("win_weight"),
        pl.when(pl.col('representation_class') == 'In Group').then(1).otherwise(0).alias("entropy_support"),
    ]).with_columns([
        (pl.col("entropy_support")*(-pl.col("deriv").log(base=2) * pl.col("weight"))).alias("diff_entropy"),
        (pl.col("entropy_support")*pl.col("weight")).alias("entropy_weight")
    ]) 
    return df.join(model_dfs.context_df, ["expansion", "name"])


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
        'skill_cohort', 
        pl.col('pick_equity_strategy_win_rate').diff(1).alias('down_one_wr_mod'), 
        pl.col('pick_equity_strategy_win_rate').diff(-1).alias('up_one_wr_mod')
    ])


@make_verbose()
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

    base_wr_df = model_dfs.wr_df.select([
        'skill_cohort', 
        ColName.EVENT_MATCHES_SUM, 
        ColName.EVENT_MATCH_WINS_SUM, 
    ]).group_by('skill_cohort').sum().select([
        'skill_cohort',
        ColName.EVENT_MATCHES_SUM,
        pl.col(ColName.EVENT_MATCHES_SUM).log(base=2).alias('total_entropy'),
        (pl.col(ColName.EVENT_MATCH_WINS_SUM) / pl.col(ColName.EVENT_MATCHES_SUM)).alias("actual_win_rate"),
    ]).sort('skill_cohort')

    mapped_results_df = agg_mapped_df(mapped_df, metric, luck_control=luck_control)
    ret_df = base_wr_df.join(mapped_results_df, on=["skill_cohort"])
    ret_df = ret_df.with_columns([
        (pl.col(f"{metric}_strategy_win_rate") - pl.col("actual_win_rate")).alias(
            f"{metric}_strat_delta"),
        (pl.col(f"{metric}_entropy") - pl.col("total_entropy")).alias(f"{metric}_entropy_loss")
    ])

    return MetricResult(
        df=ret_df, 
        mapped_df=mapped_df
    )


def agg_mapped_df(
    mapped_df: pl.DataFrame, 
    metric: str, 
    luck_control: bool = False
) -> pl.DataFrame:
    weight_col = (
         pl.col('weight').sum().over(['expansion', 'name']) if luck_control else pl.col('weight') 
    ).alias(f'{metric}_weight')

    win_weight_col = pl.col('win_weight') * weight_col / pl.col("weight") if luck_control else pl.col('win_weight')

    return mapped_df.select([
        'skill_cohort',
        weight_col,
        win_weight_col,
        "diff_entropy",
        "entropy_weight",
    ]).group_by(['skill_cohort']).sum().select([
        'skill_cohort',
        f'{metric}_weight',
        (pl.col('win_weight') / pl.col(f'{metric}_weight')).alias(f'{metric}_strategy_win_rate'),
        ((pl.col("diff_entropy") + pl.col(f'{metric}_weight').log(base=2) * pl.col('entropy_weight')) / pl.col(f'{metric}_weight')).alias(f"{metric}_entropy"),
    ]).sort('skill_cohort')


@make_verbose()
def all_metrics_analysis(
    metric_filter: dict | None = None, 
    results_filter: dict | None = None,
    metrics: list[str] | None = None,
    sets: list[str] | None = None,
):
    sets = SETS if sets is None else sets

    if metrics is None:
        metrics = METRICS 
    metric_results = {metric: p1_strat_analysis(
        sets, 
        metric, 
        metric_filter=metric_filter, 
        results_filter=results_filter, 
    ) for metric in metrics}
    delta_dfs = [metric_results[metric].df.select([
        'skill_cohort', 
        f"{metric}_strat_delta", 
        f"{metric}_weight",
        f"{metric}_entropy",
        f"{metric}_entropy_loss",
    ]) for metric in metrics]

    result_df = functools.reduce(lambda prev, curr: prev.join(curr, on="skill_cohort"), delta_dfs)
    base_df = metric_results[metrics[0]].df.select([
        'skill_cohort',
        'event_matches_sum',
        'actual_win_rate',
        'total_entropy',
    ])
    result_df = result_df.join(base_df, on="skill_cohort")

    agg_df = wavg(
        result_df, 
        [f"{metric}_strat_delta" for metric in metrics], 
        [f"{metric}_weight" for metric in metrics]
    )

    return AnalysisResult(
        df=result_df,
        agg_df=agg_df,
        metric_results=metric_results
    )

def set_by_set_results(
    metric_filter: dict | None = None,
    results_filter: dict | None = None,
    metrics: list[str] | None = None,
):
    metrics = ['deq', 'gih_wr_17l'] if metrics is None else metrics
    sets = ["NEO", "SNC", "DMU", "BRO", "ONE", "SIR", "MOM", "LTR", "WOE", "LCI", 
        "KTK", "MKM", "OTJ", "MH3", "BLB", "DSK", "FDN", "PIO"]

    results = {set_: all_metrics_analysis(
        metric_filter=metric_filter,
        results_filter=results_filter,
        metrics=metrics,
        sets=[set_]
    ) for set_ in sets}

    return results 
    
