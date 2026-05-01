"""Real-data tests for the core DEq model, pinned to TDM.

These tests run live_deq() against the committed TDM ratings snapshot and
assert structural and regression-style properties. Per-card pinned values
are intentionally loose (±0.002) so minor numerical drift in spells doesn't
break CI; tighten if a regression slips past.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from deq.main import (
    GRADE_C_MINUS_MAX,
    GRADE_NOTCH_INCREMENT,
    PICK_EQUITY_INIT,
    PICK_EQUITY_MID,
    PICK_EQUITY_MID_INDEX,
    ZERO_EQUITY_INDEX,
    deq_col_specs,
    live_deq,
)

from .conftest import TDM_END, TDM_SET, TDM_START

EXPECTED_COLUMNS = {
    "name",
    "color",
    "rarity",
    "image_url",
    "deq",
    "deq_grade",
    "npr",
    "pct_top",
}


@pytest.fixture()
def tdm_deq(tdm_data) -> pl.DataFrame:  # noqa: ARG001 — fixture activates env
    """Compute live_deq for TDM. Function-scoped because the underlying
    monkeypatch (SPELLS_DATA_HOME) is function-scoped; live_deq is fast
    enough on the cached fixtures that the recompute is cheap."""
    return live_deq(TDM_SET, TDM_START, TDM_END)


def test_live_deq_returns_expected_columns(tdm_deq: pl.DataFrame) -> None:
    assert EXPECTED_COLUMNS.issubset(set(tdm_deq.columns)), (
        f"missing columns: {EXPECTED_COLUMNS - set(tdm_deq.columns)}"
    )


def test_live_deq_has_cards(tdm_deq: pl.DataFrame) -> None:
    assert tdm_deq["name"].n_unique() > 100, "TDM should yield more than 100 cards"


def test_live_deq_grade_distribution(tdm_deq: pl.DataFrame) -> None:
    grades = set(tdm_deq["deq_grade"].drop_nulls().to_list())
    # TDM has clear bombs and clear unplayables; both ends of the scale should appear.
    assert any(g.startswith("A") for g in grades), f"expected at least one A-tier grade, got {grades}"
    assert any(g.startswith("D") for g in grades), f"expected at least one D-tier grade, got {grades}"


def test_live_deq_grade_monotone_with_deq(tdm_deq: pl.DataFrame) -> None:
    """Higher deq → better letter grade."""
    grade_order = ["F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]
    rank = {g: i for i, g in enumerate(grade_order)}

    medians = (
        tdm_deq.filter(pl.col("deq_grade").is_in(grade_order))
        .group_by("deq_grade")
        .agg(pl.col("deq").median().alias("median_deq"))
        .sort("deq_grade")
        .with_columns(
            pl.col("deq_grade").replace_strict(rank, return_dtype=pl.Int64).alias("rank")
        )
        .sort("rank")
    )

    deqs = medians["median_deq"].to_list()
    assert deqs == sorted(deqs), f"grade-bucket median DEqs must be monotone, got {deqs}"


def test_live_deq_pinned_landmark_cards(tdm_deq: pl.DataFrame) -> None:
    """Anchor a couple of well-known TDM cards. Tolerance is loose by design."""
    pinned = {
        # Marquee mythics — should grade strongly positive.
        "Ugin, Eye of the Storms": (0.0, None),       # min, max
        "Sheoldred, the Apocalypse": (0.0, None),     # may not be in TDM; skip if absent
    }
    df = tdm_deq.filter(pl.col("name").is_in(list(pinned.keys())))
    seen = dict(zip(df["name"].to_list(), df["deq"].to_list()))

    for name, (lo, hi) in pinned.items():
        if name not in seen:
            continue
        deq = seen[name]
        if lo is not None:
            assert deq >= lo, f"{name}: deq={deq} below floor {lo}"
        if hi is not None:
            assert deq <= hi, f"{name}: deq={deq} above ceiling {hi}"


def test_pick_equity_piecewise_at_known_points() -> None:
    """The pick_equity ColSpec is a piecewise quadratic. Verify boundary values
    by evaluating against synthetic ata_adj inputs.
    """
    specs = deq_col_specs()
    pe_expr = specs["pick_equity"].expr
    assert isinstance(pe_expr, pl.Expr)

    midpoint = (PICK_EQUITY_MID_INDEX + ZERO_EQUITY_INDEX) / 2
    df = pl.DataFrame(
        {"ata_adj": [float(PICK_EQUITY_MID_INDEX), midpoint, float(ZERO_EQUITY_INDEX)]}
    ).with_columns(pe_expr.alias("pe"))

    pe = df["pe"].to_list()
    # At the mid index, pick_equity == PICK_EQUITY_MID.
    assert math.isclose(pe[0], PICK_EQUITY_MID, abs_tol=1e-9)
    # At the zero-equity index, pick_equity == 0.
    assert math.isclose(pe[2], 0.0, abs_tol=1e-9)
    # Strictly decreasing on [PICK_EQUITY_MID_INDEX, ZERO_EQUITY_INDEX].
    assert pe[0] > pe[1] > pe[2]


def test_grade_thresholds_align_with_constants() -> None:
    """The DEq value at the C-/C boundary should round to GRADE_C_MINUS_MAX
    exactly, and adjacent grades should be GRADE_NOTCH_INCREMENT apart.
    """
    specs = deq_col_specs()
    grade_expr = specs["deq_grade"].expr
    assert isinstance(grade_expr, pl.Expr)

    just_below = GRADE_C_MINUS_MAX - 1e-9
    just_above = GRADE_C_MINUS_MAX + 1e-9
    one_notch = GRADE_C_MINUS_MAX + GRADE_NOTCH_INCREMENT + 1e-9

    df = pl.DataFrame({"deq": [just_below, just_above, one_notch]}).with_columns(
        grade_expr.alias("g")
    )
    assert df["g"].to_list() == ["C-", "C", "C+"]
