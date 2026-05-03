"""Regression test for live_deq() pinned to a 50-card BLB snapshot.

For every card in the trimmed fixture set we lock in expected values for
nine derived metrics: the four DEq components (pick_equity, deq_base,
deq_bias_adj, deq_meta_adj), the per-cohort cohort DEq (top, all), pct_top,
the combined deq, and npr. A regression on any single metric is reported
with the per-card actual/expected/diff line so the failing metric is obvious.

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
    "deq_base",
    "deq_bias_adj",
    "deq_meta_adj",
    "deq_top",
    "deq_all",
    "pct_top",
    "deq",
    "npr",
)

# --- BEGIN EXPECTED ---
EXPECTED: dict[str, tuple[float | None, ...]] = {
    'Agate Assault': (
        0.0097639, 0.0069307, -9.7296e-06, -1.624e-06,
        0.0069221, 0.0075208, 0.93464,
        0.0069612, -0.91645,
    ),
    'Agate-Blade Assassin': (
        0.0060903, 0.00077328, -0.0030496, -0.00026872,
        -0.001281, -0.00093198, 0.9347,
        -0.0012582, -1.588,
    ),
    "Alania's Pathmaker": (
        0.0047012, 0.0029751, 0.00092176, 5.9253e-05,
        0.0035198, 0.00060794, 0.93111,
        0.0033192, -2.283,
    ),
    'Alania, Divergent Storm': (
        0.0097069, -0.0031704, 0.00026198, 4.335e-05,
        -0.0030641, -0.0072299, 0.54065,
        -0.0049777, -0.74217,
    ),
    "Artist's Talent": (
        0.0068516, None, -0.00023936, -2.4508e-05,
        None, -0.0087909, 0.0,
        -0.0087909, -1.7755,
    ),
    'Azure Beastbinder': (
        0.020627, 0.02945, -0.00086425, -0.00065797,
        0.028171, 0.025798, 0.83137,
        0.027771, 2.1144,
    ),
    'Bakersbane Duo': (
        0.016006, 0.013547, 0.0016608, 0.00065712,
        0.015642, 0.02034, 0.97099,
        0.015778, 1.2993,
    ),
    "Bandit's Talent": (
        0.0078802, -0.0096064, -0.00021496, -2.6491e-05,
        -0.0097286, -0.011065, 0.7682,
        -0.010038, -1.2608,
    ),
    'Banishing Light': (
        0.016971, 0.01772, -0.00014108, -6.3567e-05,
        0.017539, 0.018376, 0.94786,
        0.017583, 0.65268,
    ),
    'Bark-Knuckle Boxer': (
        0.013957, 0.004447, 0.0024376, 0.0007336,
        0.0071019, 0.014456, 0.90432,
        0.0078056, 0.46075,
    ),
    'Barkform Harvester': (
        0.0024786, -0.0050327, 0.0026764, 8.3385e-05,
        -0.0043261, -0.0045867, 0.86896,
        -0.0043602, -3.1155,
    ),
    'Baylen, the Haymaker': (
        0.010638, -0.0051241, 0.0016483, 0.0003133,
        -0.0047205, -0.0054829, 0.375,
        -0.005197, -0.86448,
    ),
    'Bellowing Crier': (
        0.0031453, -0.0048455, -0.0044104, -0.00017869,
        -0.0068744, -0.0073833, 0.91731,
        -0.0069165, -2.8065,
    ),
    'Beza, the Bounding Spring': (
        0.027898, 0.044994, 1.227e-05, 5.632e-05,
        0.045054, 0.04469, 0.6299,
        0.044919, 4.1194,
    ),
    "Blacksmith's Talent": (
        0.013041, 0.011612, -0.0011996, -0.00031911,
        0.010498, 0.01035, 0.87235,
        0.010479, -0.033188,
    ),
    'Blooming Blast': (
        0.011394, 0.00022413, -0.0012083, -0.00025596,
        -0.00084259, 0.0068839, 0.83962,
        0.00039663, -0.66277,
    ),
    'Bonebind Orator': (
        0.0088948, 0.005307, 0.0010118, 0.00014752,
        0.0062568, 0.0079342, 0.96319,
        0.0063185, -0.55287,
    ),
    'Bonecache Overseer': (
        0.0089519, 0.0025168, 0.0044548, 0.00065542,
        0.0054951, 0.0040367, 0.87713,
        0.005316, -0.82204,
    ),
    'Brambleguard Captain': (
        0.011381, 0.0096544, -0.0018277, -0.00038648,
        0.008068, 0.004216, 0.81897,
        0.0073707, -0.75756,
    ),
    'Brambleguard Veteran': (
        0.013341, 0.0084829, 0.0030817, 0.00085373,
        0.011465, 0.012044, 0.87987,
        0.011534, 0.14097,
    ),
    'Brave-Kin Duo': (
        0.0040132, -0.0041155, -0.0028244, -0.00015089,
        -0.0053892, -0.0052976, 0.87013,
        -0.0053773, -2.7111,
    ),
    'Brazen Collector': (
        0.014404, 0.0192, -0.00016965, -5.4203e-05,
        0.019013, 0.014829, 0.89307,
        0.018565, 0.19872,
    ),
    'Brightblade Stoat': (
        0.020192, 0.023074, -0.00029548, -0.00021042,
        0.022631, 0.027875, 0.8977,
        0.023167, 1.5882,
    ),
    "Builder's Talent": (
        0.011625, 0.004604, 0.0012251, 0.00026813,
        0.0055765, 0.0073189, 0.90284,
        0.0057458, 0.044247,
    ),
    "Bumbleflower's Sharepot": (
        0.0039114, -0.0090465, 0.0027256, 0.00014136,
        -0.0078332, -0.0073815, 0.90645,
        -0.007791, -2.3627,
    ),
    'Burrowguard Mentor': (
        0.016178, 0.017441, 0.00044681, 0.00018092,
        0.017885, 0.026454, 0.88437,
        0.018875, 0.73466,
    ),
    'Bushy Bodyguard': (
        0.015037, 0.01251, 0.0025438, 0.00088434,
        0.015402, 0.013646, 0.9,
        0.015227, 0.50879,
    ),
    'Byway Barterer': (
        0.021561, 0.014227, -0.00012092, -0.00010687,
        0.014036, 0.026512, 0.77111,
        0.016892, 1.8682,
    ),
    'Cache Grab': (
        0.009864, 0.0054881, 0.0032333, 0.00054792,
        0.0082074, 0.010275, 0.96504,
        0.0082797, -0.21744,
    ),
    'Calamitous Tide': (
        0.0052988, -0.0042392, -0.002574, -0.00019101,
        -0.0055414, -0.00029189, 0.84147,
        -0.0047092, -1.8024,
    ),
    'Camellia, the Seedmiser': (
        0.022789, 0.024421, 0.0017926, 0.0019596,
        0.027395, 0.026044, 0.7994,
        0.027124, 2.5296,
    ),
    "Caretaker's Talent": (
        0.023451, 0.019483, 0.00042941, 0.00053195,
        0.020183, 0.026454, 0.77309,
        0.021606, 2.458,
    ),
    'Carrot Cake': (
        0.016276, 0.021145, 3.9995e-05, 1.6408e-05,
        0.021193, 0.027402, 0.96876,
        0.021387, 1.1867,
    ),
    'Cindering Cutthroat': (
        0.0052093, -0.0017933, -0.0044529, -0.00032369,
        -0.0043873, -0.00061058, 0.91897,
        -0.0040813, -2.071,
    ),
    'Clement, the Worrywort': (
        0.019093, 0.023188, -0.0018038, -0.0010923,
        0.021078, 0.011638, 0.76031,
        0.018815, 1.2999,
    ),
    'Clifftop Lookout': (
        0.011317, -0.0095517, 0.00042756, 8.9593e-05,
        -0.0091972, -0.0055872, 0.82521,
        -0.0085662, -0.68196,
    ),
    'Coiling Rebirth': (
        0.015529, -0.0017291, 0.00083937, 0.00031161,
        -0.0010994, -0.0022121, 0.61832,
        -0.0015241, 0.04344,
    ),
    'Conduct Electricity': (
        0.0021285, -0.0054216, 0.0031103, 8.2168e-05,
        -0.0046571, -0.0041217, 0.80514,
        -0.0045528, -3.376,
    ),
    'Consumed by Greed': (
        0.019836, 0.032507, 0.00012367, 8.3492e-05,
        0.032693, 0.028804, 0.93137,
        0.032426, 2.1135,
    ),
    'Corpseberry Cultivator': (
        0.0071976, -0.0057606, 0.0047948, 0.00052356,
        -0.0022231, -0.0027771, 0.94231,
        -0.0022551, -1.2615,
    ),
    'Coruscation Mage': (
        0.010806, 0.0070939, -0.00094555, -0.00018416,
        0.0062637, 0.0065454, 0.87889,
        0.0062978, -0.57181,
    ),
    "Cruelclaw's Heist": (
        0.015973, -0.0045891, -6.2683e-05, -2.4692e-05,
        -0.0046481, -0.0049711, 0.65529,
        -0.0047594, 0.04117,
    ),
    'Crumb and Get It': (
        0.0095033, 0.0064208, -0.0011367, -0.00018232,
        0.0053794, 0.010529, 0.95016,
        0.0056361, -0.75974,
    ),
    'Curious Forager': (
        0.014757, 0.0062346, 0.0019145, 0.00064116,
        0.0084484, 0.012962, 0.91692,
        0.0088234, 0.76922,
    ),
    'Daggerfang Duo': (
        0.0090758, 0.00073358, 0.0012343, 0.0001852,
        0.0018281, 0.0026161, 0.95857,
        0.0018607, -0.59821,
    ),
    'Daring Waverider': (
        0.0095747, 0.01108, -0.001967, -0.00031898,
        0.0096445, 0.010148, 0.90652,
        0.0096916, -0.45983,
    ),
    'Darkstar Augur': (
        0.02502, 0.03685, 8.8341e-05, 0.00015352,
        0.037064, 0.039595, 0.84215,
        0.037463, 3.6917,
    ),
    "Dawn's Truce": (
        0.00788, None, -0.00029291, -3.6096e-05,
        None, -0.0093048, 0.0,
        -0.0093048, -1.7522,
    ),
    'Dazzling Denial': (
        0.0038256, 0.0005686, -0.001926, -9.7377e-05,
        -0.00040112, -0.00075557, 0.92653,
        -0.00042716, -2.4802,
    ),
    'Dewdrop Cure': (
        0.0029002, -0.0011764, -0.00086082, -3.1869e-05,
        -0.0013165, -0.0051405, 0.50224,
        -0.0032199, -2.8253,
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
        lines.append(f"        {v[7]}, {v[8]},")
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
