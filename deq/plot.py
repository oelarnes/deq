from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import matplotlib.lines as mlines

from deq.p1_strategy import AnalysisResult
# default plotly colors
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

FIG_SIZE = (4,3)

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

def make_two_phase_line_graph(
    seed_graph: MultiPhaseLineGraph,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    q: NDArray[np.bool_],
):
    if max(len(x), len(y), len(q)) <= 1:
        return seed_graph

    style = 'dot' if not (q[0] and q[1]) else 'solid'

    new_segment = StyledSegment(
        x=x[0:2],
        y=y[0:2],
        style=style
    )

    graph = MultiPhaseLineGraph(
        name=seed_graph.name,
        color=seed_graph.color,
        segments=[*seed_graph.segments, new_segment]
    )

    return make_two_phase_line_graph(
        graph,
        x[1:],
        y[1:],
        q[1:],
    )

def p1strat_line_graphs(
    analysis: AnalysisResult,
    metrics: list[str] | None = None,
    value_template: str = "{metric}_strat_delta",
    quality_template: str = "{metric}_misrep",
    quality_threshold: float = 0.20,
    colors = 'pyplot'
):
    if metrics is None:
        metrics = ['deq', 'gih_wr', 'gp_wr', 'pick_equity', 'iwd']

def plot_two_phase_series_pyplot(
    title: str,
    graphs: list[TwoPhaseLineGraph],
    x_label: str,
    y_label: str,
):
    _, ax = plt.subplots(figsize=FIG_SIZE)

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)

    handles = []
    for graph in graphs:
        for seg in graph.solid_segments:
                ax.plot(seg[0], seg[1], color=graph.color)

        for seg in graph.dotted_segments:
            ax.plot(seg[0], seg[1], color=graph.color, linestyle=':') 

        handles.append(mlines.Line2D([], [], color=graph.color, label=graph.name))
    ax.legend(handles=handles)

    return ax

def strat_delta_line_plot(
    analysis: AnalysisResult,
    metrics: list[str] | None = None,
    misrep: bool = False,
    misrep_threshold: float = .10,
    display: bool = True,
    save_to_file: str | None = None,
) -> go.Figure:
    df = analysis.df
    fig = go.Figure()

    for i, metric in enumerate(metrics):
        label=METRIC_LABELS[metric]
        color=COLOR_LIST['plotly'][i]
        value_col = f"{metric}_strat_delta" 
        
        x_vals = df['wr_group'].to_numpy()
        y_vals = df[value_col].to_numpy()
        quality = df[f"{metric}_misrep"].to_numpy() <= misrep_threshold
        
        quality_x = x_vals[quality]
        if quality_x.size > 0:
            fig.add_trace(go.Scatter(
                x=quality_x,
                y=y_vals[quality],
                mode='lines',
                line={'dash': 'solid', 'color': color},
                showlegend=True,
                name=label
            ))
        
        if quality_x.size > 0 and not quality[0]:
            opening_dash_mask = x_vals <= quality_x[0]
            fig.add_trace(go.Scatter(
                x=x_vals[opening_dash_mask],
                y=y_vals[opening_dash_mask],
                mode='lines',
                line={'dash': 'dot', 'color': color},
                showlegend=False,
                name=label
            ))

        if quality_x.size > 0 and not quality[-1]:
            closing_dash_mask = x_vals >= quality_x[-1]
            fig.add_trace(go.Scatter(
                x=x_vals[closing_dash_mask],
                y=y_vals[closing_dash_mask],
                mode='lines',
                line={'dash': 'dot', 'color': color},
                showlegend=False,
                name=label
            ))

        if not quality_x.size > 0:
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=y_vals,
                mode='lines',
                line={'dash': 'dot', 'color': color},
                showlegend=True,
                name=label
            ))

    fig.update_layout(
        title='Metric Strategy Delta by WR Group',
        xaxis_title='WR Group',
        yaxis_title='Strategy Delta',
        xaxis=dict(
            tickmode='array',
            tickvals=[x for x in range(42, 67, 2)],
            ticktext=[str(x) for x in range(42, 67, 2)]
        ),
        width=800,
        height=500,
        margin=dict(l=50, r=50, t=50, b=50),
        hovermode='x unified',
        template='plotly_white'
    )

    if save_to_file:
        fig.write_html(save_to_file)
    if display:
        fig.show()
    return fig
