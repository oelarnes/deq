"""AI-driven analytic explorations for deq.

A home for exploratory analyses (often Claude-authored) that sit alongside the
production deq code but aren't part of the daily pipeline. Each submodule
exposes a `run(set_code, ...)` entry point and can also be executed directly,
e.g. `pdm run python -m deq.ai.p1 SOS`.
"""

from deq.ai import context, deq_compare, p1, signal_plot, strong_dig

__all__ = ["context", "p1", "deq_compare", "strong_dig", "signal_plot"]
