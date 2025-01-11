import numpy as np
import plotly.graph_objects as go
import polars as pl

from deq.p1_strategy import AnalysisResult

def strat_delta_line_plot(
    analysis: AnalysisResult,
    metrics: list[str] | None = None,
    misrep: bool = False,
    misrep_threshold: float = 0.0,
    display: bool = True,
    save_to_file: str | None = None,
) -> go.Figure:
    return go.Figure()
