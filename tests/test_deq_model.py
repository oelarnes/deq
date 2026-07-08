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

import polars as pl
import pytest

from spells import TimePeriod

from deq.main import live_deq

try:
    from .conftest import BLB_AS_OF, BLB_COLOR_SETS, BLB_SET, BLB_START, BLB_END
except ImportError:  # script-mode (regenerate)
    import datetime as _dt

    BLB_SET = "BLB"
    BLB_START = _dt.date(2024, 8, 13)
    BLB_END = _dt.date(2024, 9, 24)
    BLB_AS_OF = _dt.date(2026, 7, 8)
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
        0.010219, -0.0040932, 0.0025072, 0.00044926,
        0.96677, 0.0069098, -0.85091,
    ),
    'Agate-Blade Assassin': (
        0.0061736, 0.0019432, -0.0045957, -0.00041227,
        0.96623, 0.0019314, -1.6411,
    ),
    "Alania's Pathmaker": (
        0.0047191, -0.0044092, 0.0032036, 0.00020681,
        0.96543, 0.0020865, -2.2699,
    ),
    'Alania, Divergent Storm': (
        0.011053, -0.044758, 0.010538, 0.0022507,
        0.66986, -0.0075812, -0.71047,
    ),
    "Artist's Talent": (
        0.0069327, -0.065974, 0.012093, 0.0013174,
        0.39431, -0.007413, -1.7381,
    ),
    'Azure Beastbinder': (
        0.020587, 0.0074449, 0.00097879, 0.00074231,
        0.89019, 0.024262, 1.8304,
    ),
    'Bakersbane Duo': (
        0.014761, 0.0012219, 0.00042938, 0.00014424,
        0.98622, 0.014871, 1.0919,
    ),
    "Bandit's Talent": (
        0.0082265, -0.026288, -0.0019761, -0.00026035,
        0.87075, -0.010223, -1.2161,
    ),
    'Banishing Light': (
        0.017567, 0.0031224, 0.00020716, 0.00010098,
        0.97574, 0.018756, 0.85499,
    ),
    'Bark-Knuckle Boxer': (
        0.014031, -0.0010978, 0.00089012, 0.00027134,
        0.95607, 0.011826, 0.60442,
    ),
    'Barkform Harvester': (
        0.0022457, -0.019766, 0.00070113, 1.9809e-05,
        0.9171, -0.0037101, -3.2448,
    ),
    'Baylen, the Haymaker': (
        0.011524, -0.012114, 0.0015697, 0.00033548,
        0.59383, 0.00036228, -0.59123,
    ),
    'Bellowing Crier': (
        0.0032504, -0.017727, -0.00082879, -3.4029e-05,
        0.95633, -0.0068687, -2.8012,
    ),
    'Beza, the Bounding Spring': (
        0.028102, 0.024093, 1.1632e-05, 6.3427e-05,
        0.77493, 0.046152, 4.1361,
    ),
    "Blacksmith's Talent": (
        0.011646, 0.001239, 0.00090043, 0.00019788,
        0.93177, 0.0095762, -0.35682,
    ),
    'Blooming Blast': (
        0.012232, -0.011063, 0.0018082, 0.00043301,
        0.9157, 0.0025608, -0.53984,
    ),
    'Bonebind Orator': (
        0.0082765, 0.00295, -0.0011303, -0.00014893,
        0.98056, 0.0079372, -0.80327,
    ),
    'Bonecache Overseer': (
        0.008979, -0.00073816, 0.0005908, 8.9155e-05,
        0.93831, 0.0052369, -0.80332,
    ),
    'Brambleguard Captain': (
        0.011709, -0.0019873, 0.0011778, 0.00026147,
        0.91083, 0.0080755, -0.62413,
    ),
    'Brambleguard Veteran': (
        0.014022, -0.0053085, 0.001637, 0.00049539,
        0.9416, 0.0084806, 0.29041,
    ),
    'Brave-Kin Duo': (
        0.0047434, -0.0082651, -0.00041694, -2.756e-05,
        0.94739, -0.0019627, -2.3897,
    ),
    'Brazen Collector': (
        0.014509, 0.0020568, 0.0014244, 0.00046138,
        0.94492, 0.015249, 0.2825,
    ),
    'Brightblade Stoat': (
        0.020361, 0.0063118, 4.233e-06, 3.3161e-06,
        0.94935, 0.023495, 1.644,
    ),
    "Builder's Talent": (
        0.009799, -0.0018714, 0.0005838, 9.9031e-05,
        0.92986, 0.0049474, -0.7677,
    ),
    "Bumbleflower's Sharepot": (
        0.0032434, -0.026928, 0.00062684, 2.5872e-05,
        0.93793, -0.0078693, -2.6952,
    ),
    'Burrowguard Mentor': (
        0.015988, 0.01341, -0.0014149, -0.00055926,
        0.94565, 0.01992, 0.76792,
    ),
    'Bushy Bodyguard': (
        0.015572, 0.0046288, 0.00034535, 0.00012837,
        0.95464, 0.017753, 0.77773,
    ),
    'Byway Barterer': (
        0.022224, -0.0098548, 0.00087132, 0.00086245,
        0.87512, 0.011897, 1.9902,
    ),
    'Cache Grab': (
        0.0091187, 0.0027613, 0.00081219, 0.00012318,
        0.98318, 0.0089513, -0.40516,
    ),
    'Calamitous Tide': (
        0.0057496, -0.011498, 0.0025224, 0.00020699,
        0.915, -0.0014613, -1.7377,
    ),
    'Camellia, the Seedmiser': (
        0.022768, 0.016623, 0.0004448, 0.00047396,
        0.89142, 0.031975, 2.5272,
    ),
    "Caretaker's Talent": (
        0.02281, 0.0083513, -0.00021497, -0.00023629,
        0.86169, 0.021954, 2.0799,
    ),
    'Carrot Cake': (
        0.014298, 0.011518, -0.00048265, -0.00015156,
        0.98466, 0.021092, 0.71982,
    ),
    'Cindering Cutthroat': (
        0.0054052, -0.0023286, -0.0038082, -0.00028979,
        0.95977, -0.00056577, -1.9944,
    ),
    'Clement, the Worrywort': (
        0.01949, 0.0058364, -0.0014846, -0.00094066,
        0.86398, 0.016369, 1.3862,
    ),
    'Clifftop Lookout': (
        0.012557, -0.019302, -0.00029572, -7.3855e-05,
        0.91909, -0.0050925, -0.31656,
    ),
    'Coiling Rebirth': (
        0.015627, -0.014057, -0.0010223, -0.00039487,
        0.7698, 9.0079e-05, 0.16445,
    ),
    'Conduct Electricity': (
        0.0024483, -0.024862, 0.0066316, 0.00020624,
        0.89338, -0.0039935, -3.2958,
    ),
    'Consumed by Greed': (
        0.018823, 0.01543, -0.00085822, -0.00049994,
        0.96406, 0.02946, 1.8472,
    ),
    'Corpseberry Cultivator': (
        0.0071376, -0.012193, 0.0011344, 0.00012107,
        0.97109, -0.0024705, -1.2597,
    ),
    'Coruscation Mage': (
        0.011223, -0.010033, 0.0028614, 0.00059132,
        0.92988, 0.003353, -0.55995,
    ),
    "Cruelclaw's Heist": (
        0.015657, -0.022398, -0.0012272, -0.00046854,
        0.78814, -0.0054551, 0.10715,
    ),
    'Crumb and Get It': (
        0.0088401, 0.0018335, -0.00029938, -4.3418e-05,
        0.97566, 0.0080471, -0.87654,
    ),
    'Curious Forager': (
        0.014768, -0.0049109, 0.00032797, 0.00011068,
        0.95904, 0.0088674, 0.83037,
    ),
    'Daggerfang Duo': (
        0.0082604, -0.0063576, -0.00073128, -9.6149e-05,
        0.97867, 0.00081571, -0.83325,
    ),
    'Daring Waverider': (
        0.0093613, -0.00068896, 0.0023651, 0.00036348,
        0.94145, 0.0067487, -0.62586,
    ),
    'Darkstar Augur': (
        0.024671, 0.019482, -0.00047382, -0.00076079,
        0.90905, 0.037867, 3.457,
    ),
    "Dawn's Truce": (
        0.0090958, -0.045152, -0.00043609, -6.564e-05,
        0.0, -0.0099618, -1.6246,
    ),
    'Dazzling Denial': (
        0.0038433, -0.0078534, 0.0046483, 0.00023657,
        0.95761, 0.00040561, -2.5217,
    ),
    'Dewdrop Cure': (
        0.0037804, -0.013935, -0.0014687, -7.9611e-05,
        0.6997, -0.0025077, -2.6161,
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
    df = live_deq(
        BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS, as_of=BLB_AS_OF
    ).sort("name")
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
    df = live_deq(
        BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=[], as_of=BLB_AS_OF
    ).sort("name")

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
    df = live_deq(
        BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS, as_of=BLB_AS_OF
    ).sort("name")

    assert (df["pct_top"] == 0).all(), "all cards should have pct_top=0 with no top game data"

    # Every card with a non-null mwr must also have a non-null deq
    has_mwr = df.filter(pl.col("mwr").is_not_null() & pl.col("mwr").is_finite())
    null_deq = has_mwr.filter(pl.col("deq").is_null() | pl.col("deq").is_nan())
    assert null_deq.is_empty(), (
        f"deq is null for {null_deq.height} card(s) with valid mwr: "
        f"{null_deq['name'].to_list()}"
    )


def _fmt_val(x: float | None, sig: int = 5) -> str:
    if x is None or math.isnan(x):
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
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines)


def regenerate_expected() -> str:
    """Recompute live_deq on the current fixtures and return the source for EXPECTED.

    Run as `pdm run python tests/test_deq_model.py regenerate` and paste the
    output between the BEGIN/END EXPECTED markers in this file.
    """
    import os
    import shutil
    import tempfile
    from pathlib import Path

    from deq.set_config import DEqConfig, config

    config[BLB_SET] = DEqConfig(start_date=BLB_START, end_date=BLB_END)

    src = Path(__file__).parent / "fixtures" / "spells_data"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        os.environ["SPELLS_DATA_HOME"] = str(td_path)
        for sub in ("ratings", "deck_color"):
            shutil.copytree(src / sub, td_path / sub)
        df = live_deq(
            BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS, as_of=BLB_AS_OF
        )
    return _format_expected(df)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "regenerate":
        print(regenerate_expected())
    else:
        print("Usage: python tests/test_deq_model.py regenerate", file=sys.stderr)
        sys.exit(2)
