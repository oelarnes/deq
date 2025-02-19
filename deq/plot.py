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
    'gih_wr_17l': 'GIH WR',
    'gp_wr_17l': 'GP WR',
    'pick_equity': 'ATA',
    'iwd_17l': 'IWD',
    'deq_base': 'DEq Base',
    'gp_wr_bias_adj': 'GP WR Bias Adj.',
    'oh_wr': 'OH WR',
    'gns_wr': 'GNS WR',
    'alsa': 'Inverse ALSA',
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
    ax.set_xticks(analysis.df['skill_cohort'].to_numpy())
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

def p1_line_plot(
    analysis: AnalysisResult,
    mode: str = 'wr_delta',
    metrics: list[str] | None = None,
    quality_threshold: float = -3, # greater than this value
    colors: str = 'pyplot',
    title_extra: str | None = None,
) -> None:
    if metrics is None:
        metrics = ['deq', 'gih_wr_17l', 'gp_wr_17l', 'pick_equity', 'iwd_17l']

    config = {
        'wr_delta': {
            'title':  'Metric Strategy WR Delta by Skill Cohort',
            'value_template':  "{metric}_strat_delta",
            'y_label': 'Simulated Match WR Delta',
            'y_formatter': mtick.PercentFormatter(1.0, decimals=1)
        },
        'entropy': {
            'title': 'Representative Entropy by Skill Cohort',
            'value_template': "{metric}_entropy",
            'y_label': 'Representative Entropy',
        },
        'entropy_loss': {
            'title': 'Representative Entropy Loss by Skill Cohort',
            'value_template': "{metric}_entropy_loss",
            'y_label': 'Representative Entropy Loss',
        },
    }[mode]

    title = config['title'] + ('' if title_extra is None else ' - ' + title_extra)

    def graph_fn(i: int, metric: str):
        x = analysis.df['skill_cohort'].to_numpy()
        y = analysis.df[config["value_template"].format(metric=metric)].to_numpy()
        q = analysis.df[f"{metric}_entropy_loss"].to_numpy() > quality_threshold
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

    if mode=="entropy":
        x = analysis.df["skill_cohort"]
        line, = ax.plot(x, analysis.df['total_entropy'], color='black', label='Total Entropy')
        h = ax.get_legend().legend_handles
        ax.legend(handles=[line, *h])
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
    elif mode=="entropy_loss":
        x = analysis.df["skill_cohort"]
        ax.plot(x, [quality_threshold] * len(x), linestyle="dotted", color="gray")
        percent_val = 1 - 2 ** quality_threshold
        ax.text(50, quality_threshold - 0.2, f"({100 * percent_val:.2f}% information loss)", color="gray")
    ax.grid(color='lightgray')
    plt.show()


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


def cohort_summary_table(
    analysis: AnalysisResult
) -> GT:
    return GT(analysis.df.select(
        ['skill_cohort', 'actual_win_rate', 'event_matches_sum']
    )).fmt_percent(
        'actual_win_rate', decimals=1
    ).fmt_percent(
        'skill_cohort', scale_values=False, decimals=0
    ).cols_label({
        'skill_cohort': 'Skill Cohort',
        'actual_win_rate': 'Match Win Rate',
        'event_matches_sum': 'Num Matches'
    })

def set_by_set_plot(
    analyses: dict[str, AnalysisResult]
) -> None:
    x = list(analyses.keys())
    x_num = np.arange(len(x))

    _, ax = plt.subplots(figsize=FIG_SIZE)
    for metric in ['deq', 'gih_wr_17l']:
        y = np.array([val.agg_df[f"{metric}_strat_delta"] for val in analyses.values()])
        m, y_0 = np.polyfit(x_num, y, deg=1)
        fit = y_0 + x_num * m 
        line, = ax.plot(x, y, label=METRIC_LABELS[metric])
        ax.plot(x, fit, lw=2, ls=':', color=line.get_color())

    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=1))
    ax.set_title('Mean WR Delta by Set')
    ax.set_ylabel('Strategy Win Rate Delta')
    ax.set_xlabel('Set')
    ax.legend()
    ax.grid(color='lightgray')
    plt.show()

def p1_delta_bar(
    analysis: AnalysisResult,
    metrics: list[str] | None = None,
) -> None:
    df = analysis.agg_df
    if metrics is None:
        metrics = ['deq', 'gih_wr_17l', 'gp_wr_17l', 'pick_equity', 'iwd_17l']

    _, ax = plt.subplots()

    ax.bar(
        [METRIC_LABELS[metric] for metric in metrics],
        [df[f"{metric}_strat_delta"][0] for metric in metrics], 
        color=[COLOR_LIST['pyplot'][i] for i in range(len(metrics))],
    )
    ax.set_title("Win Rate Delta for Taking P1P1 by Metric")
    ax.set_ylabel('Strategy Win Rate Delta')
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=1))

    plt.show()
