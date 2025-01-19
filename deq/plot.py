from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from great_tables import GT

import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.ticker as mtick
from matplotlib.axes import Axes

from deq.p1_strategy import AnalysisResult

COLOR_LIST = {
    'plotly': ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'],
    'pyplot': ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
}

METRIC_LABELS = {
    'deq': 'DEq',
    'gih_wr': 'GIH WR',
    'gp_wr': 'GP WR',
    'pick_equity': 'ATA',
    'iwd': 'IWD',
    'deq_base': 'DEq Base',
    'gp_wr_bias_adj': 'GP WR Bias Adj.'
}

FIG_SIZE = (8,6)

@dataclass
class StyledSegment:
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    style: str


@dataclass
class MultiPhaseLineGraph:
    "A class describing a series for a line plot with styled segments"
    name: str
    color: str
    segments: list[StyledSegment]


def style_xticks(
    analysis: AnalysisResult,
    ax: Axes,
) -> None:
    ax.set_xticks(analysis.df['wr_group'].to_numpy())
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(100, decimals=0))
    ax.set_xlabel("Skill Cohort")


def two_phase_line_graph(
    name: str,
    color: str,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    q: NDArray[np.bool_],
) -> MultiPhaseLineGraph:
    assert len(x) == len(y) == len(q), "x, y, q must be the same length"
    segments = []
    for i in range(len(x) - 1):
        style = 'solid' if q[i] and q[i+1] else 'dotted'
        segments.append(
            StyledSegment(
                x = x[i:i+2],
                y = y[i:i+2],
                style = style
            )
        )
    
    return MultiPhaseLineGraph(
        name=name,
        color=color,
        segments=segments,
    )

def p1strat_line_plot(
    analysis: AnalysisResult,
    mode: str = 'wr_delta',
    metrics: list[str] | None = None,
    quality_threshold: float = 0.15, # less than this value
    colors: str = 'pyplot',
    title_extra: str | None = None,
):
    if metrics is None:
        metrics = ['deq', 'gih_wr', 'gp_wr', 'pick_equity', 'iwd']

    config = {
        'wr_delta': {
            'title':  'Metric Strategy WR Delta by Skill Cohort',
            'value_template':  "{metric}_strat_delta",
            'y_label': 'Simulated Match WR Delta',
            'y_formatter': mtick.PercentFormatter(1.0, decimals=1)
        },
        'misrep': {
            'title': 'Metric Misrepresentation Index by Skill Cohort',
            'value_template': "{metric}_misrep",
            'y_label': 'Misrepresentation Index',
        }
    }[mode]

    title = config['title'] + ('' if title_extra is None else ' - ' + title_extra)

    def graph_fn(i: int, metric: str):
        x = analysis.df['wr_group'].to_numpy()
        y = analysis.df[config["value_template"].format(metric=metric)].to_numpy()
        q = analysis.df[f"{metric}_misrep"].to_numpy() < quality_threshold
        return two_phase_line_graph(METRIC_LABELS[metric], COLOR_LIST[colors][i], x, y, q)

    graphs = [graph_fn(i, metric) for i, metric in enumerate(metrics)]

    ax = plot_two_phase_series_pyplot(
        title,
        graphs,
        config["y_label"],
    )

    if 'y_formatter' in config:
        ax.yaxis.set_major_formatter(config['y_formatter'])
    style_xticks(analysis, ax)

    if mode=="misrep":
        x = analysis.df["wr_group"]
        ax.plot(x, [quality_threshold] * len(x), linestyle="dotted", color="gray")
        ax.text(50, 0.135, "(arbitrary threshold)", color="gray")
    elif mode=="wr_delta":
        handles = []
        for i, metric in enumerate(metrics):
            value = analysis.agg_df[config["value_template"].format(metric=metric)][0]
            h, = ax.plot(
                54, 
                value, 
                linestyle="none", 
                marker="o", 
                color=COLOR_LIST[colors][i], 
                label=f"{value * 100:.2f}%"
            )
            handles.append(h)
        leg = ax.get_legend()
        leg.set_loc(9)
        ax.legend(handles=handles, loc=1)
        ax.add_artist(leg)
    ax.grid(color='lightgray')
    return ax


def plot_two_phase_series_pyplot(
    title: str,
    graphs: list[MultiPhaseLineGraph],
    y_label: str,
) -> Axes:
    _, ax = plt.subplots(figsize=FIG_SIZE)

    ax.set_title(title)
    ax.set_ylabel(y_label)

    handles = []
    for graph in graphs:
        for seg in graph.segments:
            ax.plot(
                seg.x, 
                seg.y, 
                color=graph.color, 
                linestyle=seg.style
            ) 

        handles.append(mlines.Line2D([], [], color=graph.color, label=graph.name))

    ax.legend(handles=handles)

    return ax

def metric_weight_bar_plot(
    analysis: AnalysisResult,
    metrics: list[str] = ["iwd", "deq"],
) -> Axes:
    num_bars = len(metrics) + 1
    df = analysis.df

    _, ax = plt.subplots(figsize=FIG_SIZE)
    width = 2 / (num_bars + 1)
    offset = -1 + width 
    ax.bar(df['wr_group'] + offset, df['event_matches_sum'], width=width, label='Actual')
    for i, metric in enumerate(metrics):
        ax.bar(
            df['wr_group'] + offset + (i + 1) * width, 
            df[f'{metric}_weight'], 
            width=width, 
            label=METRIC_LABELS[metric]
        )
    style_xticks(analysis, ax)
    ax.set_ylabel('Millions of Matches')
    ax.set_title("Actual and simulated matches for some strategies")
    ax.legend()

    return ax

def cohort_summary_table(
    analysis: AnalysisResult
) -> GT:
    return GT(analysis.df.select(
        ['wr_group', 'actual_win_rate', 'event_matches_sum']
    )).fmt_percent(
        'actual_win_rate', decimals=1
    ).fmt_percent(
        'wr_group', scale_values=False, decimals=0
    ).cols_label({
        'wr_group': 'Skill Cohort',
        'actual_win_rate': 'Match Win Rate',
        'event_matches_sum': 'Num Matches'
    })
