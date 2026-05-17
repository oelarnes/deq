"""Regression test for live_deq() pinned to a 50-card BLB snapshot.

For every card in the trimmed fixture set we lock in expected values for
seven derived metrics: the four DEq components (pick_equity, mwr,
deq_bias_adj, deq_meta_adj), pct_top, the combined deq, and npr. A
regression on any single metric is reported with the per-card
actual/expected/diff line so the failing metric is obvious.

color_sets is restricted to the 10 two-color pairs — BLB is a clean two-color
format and the fixture only ships those pair files.

Regenerating the EXPECTED table after an intentional model change:

    pdm run python tests/test_deq_model.py regenerate

Pipe the output back into this file (everything between the markers).
"""

from __future__ import annotations

import math
import sys
from typing import Iterable

import polars as pl
import pytest

from deq.main import live_deq

try:
    from .conftest import BLB_COLOR_SETS, BLB_END, BLB_SET, BLB_START
except ImportError:  # script-mode (regenerate)
    import datetime as _dt

    BLB_SET = "BLB"
    BLB_START = _dt.date(2024, 8, 13)
    BLB_END = _dt.date(2024, 9, 24)
    BLB_COLOR_SETS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

METRICS = (
    "pick_equity",
    "mwr",
    "deq_bias_adj",
    "deq_meta_adj",
    "pct_top",
    "deq",
    "npr",
)

# --- BEGIN EXPECTED ---
EXPECTED: dict[str, tuple[float | None, ...]] = {
    'Agate Assault': (
        0.0098155, -0.00081956, 0.0001332, 2.5125e-05,
        0.93464, 0.0069612, -0.91645,
    ),
    'Agate-Blade Assassin': (
        0.0061297, -0.0046641, -0.0032026, -0.00028604,
        0.9347, -0.0012582, -1.588,
    ),
    "Alania's Pathmaker": (
        0.0046925, 0.00026463, 0.00098428, 6.3009e-05,
        0.93111, 0.0033192, -2.283,
    ),
    'Alania, Divergent Storm': (
        0.010262, -0.02995, 0.0042804, 0.00084542,
        0.54065, -0.0049777, -0.74217,
    ),
    "Artist's Talent": (
        0.0068516, -0.065854, 0.0070968, 0.00072665,
        0.0, -0.0087909, -1.7755,
    ),
    'Azure Beastbinder': (
        0.020617, 0.013367, -0.00040279, -0.00030902,
        0.83137, 0.027771, 2.1144,
    ),
    'Bakersbane Duo': (
        0.016002, -0.00077772, 0.0016016, 0.00063376,
        0.97099, 0.015778, 1.2993,
    ),
    "Bandit's Talent": (
        0.0081727, -0.02708, -0.00049249, -6.9505e-05,
        0.7682, -0.010038, -1.2608,
    ),
    'Banishing Light': (
        0.016998, 0.0031365, -0.00014824, -6.7276e-05,
        0.94786, 0.017583, 0.65268,
    ),
    'Bark-Knuckle Boxer': (
        0.013938, -0.0074924, 0.0022135, 0.00066609,
        0.90432, 0.0078056, 0.46075,
    ),
    'Barkform Harvester': (
        0.0024564, -0.022166, 0.0024635, 7.6462e-05,
        0.86896, -0.0043602, -3.1155,
    ),
    'Baylen, the Haymaker': (
        0.010638, -0.034712, 0.0024401, 0.00046381,
        0.375, -0.005197, -0.86448,
    ),
    'Bellowing Crier': (
        0.0031637, -0.014716, -0.0038797, -0.00015672,
        0.91731, -0.0069165, -2.8065,
    ),
    'Beza, the Bounding Spring': (
        0.027898, 0.023677, -5.7719e-06, -2.6494e-05,
        0.6299, 0.044919, 4.1194,
    ),
    "Blacksmith's Talent": (
        0.013118, 0.0024486, -0.0010253, -0.00027231,
        0.87235, 0.010479, -0.033188,
    ),
    'Blooming Blast': (
        0.011478, -0.009968, -0.00080198, -0.00016661,
        0.83962, 0.00039663, -0.66277,
    ),
    'Bonebind Orator': (
        0.0088938, -0.0022382, 0.00092448, 0.00013482,
        0.96319, 0.0063185, -0.55287,
    ),
    'Bonecache Overseer': (
        0.00893, -0.004173, 0.0038014, 0.00055971,
        0.87713, 0.005316, -0.82204,
    ),
    'Brambleguard Captain': (
        0.011582, 0.00039956, -0.0014318, -0.0003007,
        0.81897, 0.0073707, -0.75756,
    ),
    'Brambleguard Veteran': (
        0.013431, -0.001831, 0.0027833, 0.00077343,
        0.87987, 0.011534, 0.14097,
    ),
    'Brave-Kin Duo': (
        0.0041254, -0.01365, -0.0026068, -0.0001417,
        0.87013, -0.0053773, -2.7111,
    ),
    'Brazen Collector': (
        0.014375, 0.0079739, -6.897e-05, -2.2978e-05,
        0.89307, 0.018565, 0.19872,
    ),
    'Brightblade Stoat': (
        0.020211, 0.006758, -0.00031073, -0.00022222,
        0.8977, 0.023167, 1.5882,
    ),
    "Builder's Talent": (
        0.011591, -0.0040771, 0.0011268, 0.00024648,
        0.90284, 0.0057458, 0.044247,
    ),
    "Bumbleflower's Sharepot": (
        0.0039265, -0.024951, 0.0024553, 0.00012729,
        0.90645, -0.007791, -2.3627,
    ),
    'Burrowguard Mentor': (
        0.016223, 0.010045, 0.00022096, 8.5932e-05,
        0.88437, 0.018875, 0.73466,
    ),
    'Bushy Bodyguard': (
        0.015061, -2.9408e-05, 0.0022374, 0.00077725,
        0.9, 0.015227, 0.50879,
    ),
    'Byway Barterer': (
        0.021674, -0.0015065, 2.9414e-05, 3.5487e-05,
        0.77111, 0.016892, 1.8682,
    ),
    'Cache Grab': (
        0.0098637, -0.0019754, 0.003109, 0.00052687,
        0.96504, 0.0082797, -0.21744,
    ),
    'Calamitous Tide': (
        0.005306, -0.013803, -0.0014655, -0.00010817,
        0.84147, -0.0047092, -1.8024,
    ),
    'Camellia, the Seedmiser': (
        0.022865, 0.0084925, 0.0014753, 0.0016155,
        0.7994, 0.027124, 2.5296,
    ),
    "Caretaker's Talent": (
        0.023453, 0.0058059, 0.00028506, 0.00035303,
        0.77309, 0.021606, 2.458,
    ),
    'Carrot Cake': (
        0.016258, 0.0086621, 1.1354e-05, 5.4942e-06,
        0.96876, 0.021387, 1.1867,
    ),
    'Cindering Cutthroat': (
        0.0052331, -0.0079107, -0.0044976, -0.00032897,
        0.91897, -0.0040813, -2.071,
    ),
    'Clement, the Worrywort': (
        0.019215, 0.0093284, -0.0015848, -0.00096943,
        0.76031, 0.018815, 1.2999,
    ),
    'Clifftop Lookout': (
        0.011435, -0.024261, 0.00033797, 7.0565e-05,
        0.82521, -0.0085662, -0.68196,
    ),
    'Coiling Rebirth': (
        0.015529, -0.018361, 0.00013327, 4.9474e-05,
        0.61832, -0.0015241, 0.04344,
    ),
    'Conduct Electricity': (
        0.0022122, -0.024533, 0.0037101, 0.00010468,
        0.80514, -0.0045528, -3.376,
    ),
    'Consumed by Greed': (
        0.019821, 0.016163, 6.3678e-05, 4.4135e-05,
        0.93137, 0.032426, 2.1135,
    ),
    'Corpseberry Cultivator': (
        0.0072364, -0.015606, 0.0044903, 0.00048993,
        0.94231, -0.0022551, -1.2615,
    ),
    'Coruscation Mage': (
        0.010783, -0.0015532, -0.00051001, -0.00010117,
        0.87889, 0.0062978, -0.57181,
    ),
    "Cruelclaw's Heist": (
        0.015973, -0.022641, -0.00030917, -0.00012179,
        0.65529, -0.0047594, 0.04117,
    ),
    'Crumb and Get It': (
        0.0095229, -0.0010653, -0.0011411, -0.00018362,
        0.95016, 0.0056361, -0.75974,
    ),
    'Curious Forager': (
        0.014752, -0.0068651, 0.0017301, 0.00057949,
        0.91692, 0.0088234, 0.76922,
    ),
    'Daggerfang Duo': (
        0.0090759, -0.0080012, 0.0011622, 0.00017438,
        0.95857, 0.0018607, -0.59821,
    ),
    'Daring Waverider': (
        0.0094734, 0.0077079, -0.0013628, -0.00023333,
        0.90652, 0.0096916, -0.45983,
    ),
    'Darkstar Augur': (
        0.025019, 0.017439, 8.4386e-08, 2.954e-07,
        0.84215, 0.037463, 3.6917,
    ),
    "Dawn's Truce": (
        0.00788, -0.048347, -0.0005567, -6.8603e-05,
        0.0, -0.0093048, -1.7522,
    ),
    'Dazzling Denial': (
        0.0038178, -0.0033327, -0.0013134, -6.7216e-05,
        0.92653, -0.00042716, -2.4802,
    ),
    'Dewdrop Cure': (
        0.0033915, -0.017798, -0.0015844, -7.3348e-05,
        0.50224, -0.0032199, -2.8253,
    ),
}
# --- END EXPECTED ---


def _values_close(actual: float | None, expected: float | None) -> bool:
    """None matches None; NaN matches NaN; finite floats compared with isclose."""
    if expected is None:
        return actual is None or (isinstance(actual, float) and math.isnan(actual))
    if actual is None:
        return False
    if isinstance(actual, float) and math.isnan(actual):
        return False
    return math.isclose(actual, expected, rel_tol=1e-4, abs_tol=1e-9)


def test_live_deq_matches_expected(blb_data) -> None:  # noqa: ARG001 — fixture activates env
    df = live_deq(BLB_SET, BLB_START, BLB_END, color_sets=BLB_COLOR_SETS).sort("name")
    assert df.height == len(EXPECTED), (
        f"row count {df.height} != fixture card count {len(EXPECTED)}"
    )

    actual: dict[str, tuple] = {
        row["name"]: tuple(row[m] for m in METRICS)
        for row in df.select(["name", *METRICS]).iter_rows(named=True)
    }

    regressions: list[str] = []
    for name, exp_row in EXPECTED.items():
        if name not in actual:
            regressions.append(f"{name}: missing from output")
            continue
        act_row = actual[name]
        for metric, exp, act in zip(METRICS, exp_row, act_row):
            if not _values_close(act, exp):
                regressions.append(
                    f"{name:35s} {metric:14s} expected={exp!r:>26}  actual={act!r:>26}"
                )

    if regressions:
        msg = "DEq regressions on {n} metric(s):\n  ".format(n=len(regressions))
        msg += "\n  ".join(regressions)
        pytest.fail(msg)


ZEROED_BY_EMPTY_COLOR_SETS = ("deq_bias_adj", "deq_meta_adj")
UNAFFECTED_BY_BIAS = ("mwr", "pct_top", "npr")


def test_empty_color_sets_zeroes_bias_adj(blb_data) -> None:  # noqa: ARG001
    """color_sets=[] means no color-pair tracking.

    deq_bias_adj and deq_meta_adj must be zero (both depend on gp_wr_bias
    which is zero when no pairs are tracked). The components that don't touch
    color-pair data — deq_base, pct_top, npr — must match EXPECTED.
    """
    df = live_deq(BLB_SET, BLB_START, BLB_END, color_sets=[]).sort("name")

    for col in ZEROED_BY_EMPTY_COLOR_SETS:
        non_zero = df.filter(
            pl.col(col).is_not_null()
            & pl.col(col).is_finite()
            & (pl.col(col).abs() > 1e-9)
        )
        assert non_zero.is_empty(), (
            f"Expected {col}=0 for all cards with color_sets=[], "
            f"got non-zero on: {non_zero['name'].to_list()}"
        )

    actual = {
        row["name"]: tuple(row[m] for m in UNAFFECTED_BY_BIAS)
        for row in df.select(["name", *UNAFFECTED_BY_BIAS]).iter_rows(named=True)
    }
    regressions: list[str] = []
    for name, exp_row in EXPECTED.items():
        if name not in actual:
            regressions.append(f"{name}: missing from output")
            continue
        act_row = actual[name]
        metric_indices = [METRICS.index(m) for m in UNAFFECTED_BY_BIAS]
        for m, idx in zip(UNAFFECTED_BY_BIAS, metric_indices):
            exp = exp_row[idx]
            act = act_row[UNAFFECTED_BY_BIAS.index(m)]
            if not _values_close(act, exp):
                regressions.append(
                    f"{name:35s} {m:14s} expected={exp!r:>26}  actual={act!r:>26}"
                )
    if regressions:
        pytest.fail(
            f"Unaffected metrics differ with color_sets=[] on {len(regressions)} case(s):\n  "
            + "\n  ".join(regressions)
        )


def test_no_top_data_falls_back_to_all(blb_no_top_data) -> None:  # noqa: ARG001
    """When the top cohort has no game data, synthesis must not null-propagate.

    Regression test for the pct_top=0 / pct_gp_top=null bug: 0*null evaluates
    to null in Polars, which previously zeroed deq for sets like OM1.
    """
    df = live_deq(BLB_SET, BLB_START, BLB_END, color_sets=BLB_COLOR_SETS).sort("name")

    assert (df["pct_top"] == 0).all(), "all cards should have pct_top=0 with no top game data"

    # Every card with a non-null mwr must also have a non-null deq
    has_mwr = df.filter(pl.col("mwr").is_not_null() & pl.col("mwr").is_finite())
    null_deq = has_mwr.filter(pl.col("deq").is_null() | pl.col("deq").is_nan())
    assert null_deq.is_empty(), (
        f"deq is null for {null_deq.height} card(s) with valid mwr: "
        f"{null_deq['name'].to_list()}"
    )


def _fmt_val(x: float | None, sig: int = 5) -> str:
    if x is None:
        return "None"
    if x == 0.0:
        return "0.0"
    d = sig - 1 - math.floor(math.log10(abs(x)))
    return f"{round(x, d):.{sig}g}"


def _format_expected(df: pl.DataFrame) -> str:
    """Render the EXPECTED dict in the multi-line format used in this file."""
    df = df.sort("name").select(["name", *METRICS])
    lines = ["EXPECTED: dict[str, tuple[float | None, ...]] = {"]
    for row in df.iter_rows(named=True):
        v = [_fmt_val(row[m]) for m in METRICS]
        lines.append(f"    {row['name']!r}: (")
        lines.append(f"        {v[0]}, {v[1]}, {v[2]}, {v[3]},")
        lines.append(f"        {v[4]}, {v[5]}, {v[6]},")
        lines.append(f"    ),")
    lines.append("}")
    return "\n".join(lines)


def regenerate_expected() -> str:
    """Recompute live_deq on the current fixtures and return the source for EXPECTED.

    Run as `pdm run python tests/test_deq_model.py regenerate` and paste the
    output between the BEGIN/END EXPECTED markers in this file.
    """
    import datetime as dt
    import os
    import shutil
    import tempfile
    from pathlib import Path

    src = Path(__file__).parent / "fixtures" / "spells_data"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        os.environ["SPELLS_DATA_HOME"] = str(td_path)
        for sub in ("ratings", "deck_color"):
            shutil.copytree(src / sub, td_path / sub)
        (td_path / "ad_hoc").mkdir()
        df = live_deq(BLB_SET, BLB_START, BLB_END, color_sets=BLB_COLOR_SETS)
    return _format_expected(df)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "regenerate":
        print(regenerate_expected())
    else:
        print("Usage: python tests/test_deq_model.py regenerate", file=sys.stderr)
        sys.exit(2)
