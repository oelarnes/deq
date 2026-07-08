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
    BLB_AS_OF = BLB_END
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
        0.0098155, -0.00081956, 0.00045008, 7.8016e-05,
        0.93464, 0.0072424, -0.91645,
    ),
    'Agate-Blade Assassin': (
        0.0061297, -0.0046641, -0.0025865, -0.00023175,
        0.9347, -0.00084131, -1.588,
    ),
    "Alania's Pathmaker": (
        0.0046925, 0.00026463, 0.0015139, 9.7054e-05,
        0.93111, 0.0036308, -2.283,
    ),
    'Alania, Divergent Storm': (
        0.010262, -0.02995, 0.004221, 0.00083558,
        0.54065, -0.0050013, -0.74217,
    ),
    "Artist's Talent": (
        None, -0.065854, None, None,
        0.0, None, -1.7755,
    ),
    'Azure Beastbinder': (
        0.020617, 0.013367, -0.00042316, -0.00032452,
        0.83137, 0.027741, 2.1144,
    ),
    'Bakersbane Duo': (
        0.016002, -0.00077772, 0.0018788, 0.00074345,
        0.97099, 0.016128, 1.2993,
    ),
    "Bandit's Talent": (
        0.0081727, -0.02708, -0.00026806, -4.1847e-05,
        0.7682, -0.0099083, -1.2608,
    ),
    'Banishing Light': (
        0.016998, 0.0031365, -0.00025559, -0.00011564,
        0.94786, 0.017446, 0.65268,
    ),
    'Bark-Knuckle Boxer': (
        0.013938, -0.0074924, 0.0025664, 0.00077229,
        0.90432, 0.0081899, 0.46075,
    ),
    'Barkform Harvester': (
        0.0024564, -0.022166, 0.0020673, 6.4117e-05,
        0.86896, -0.004464, -3.1155,
    ),
    'Baylen, the Haymaker': (
        None, -0.034712, None, None,
        0.375, None, -0.86448,
    ),
    'Bellowing Crier': (
        0.0031637, -0.014716, -0.0040395, -0.00016319,
        0.91731, -0.0069902, -2.8065,
    ),
    'Beza, the Bounding Spring': (
        None, 0.023677, None, None,
        0.6299, None, 4.1194,
    ),
    "Blacksmith's Talent": (
        0.013118, 0.0024486, -0.00084722, -0.00022493,
        0.87235, 0.010644, -0.033188,
    ),
    'Blooming Blast': (
        0.011478, -0.009968, -0.00040813, -8.3183e-05,
        0.83962, 0.00074621, -0.66277,
    ),
    'Bonebind Orator': (
        0.0088938, -0.0022382, 0.001104, 0.00016099,
        0.96319, 0.006487, -0.55287,
    ),
    'Bonecache Overseer': (
        0.00893, -0.004173, 0.0035923, 0.00052895,
        0.87713, 0.0051761, -0.82204,
    ),
    'Brambleguard Captain': (
        0.011582, 0.00039956, -0.0010194, -0.00021349,
        0.81897, 0.00773, -0.75756,
    ),
    'Brambleguard Veteran': (
        0.013431, -0.001831, 0.0033749, 0.00093732,
        0.87987, 0.012109, 0.14097,
    ),
    'Brave-Kin Duo': (
        0.0041254, -0.01365, -0.0024116, -0.00013127,
        0.87013, -0.0052872, -2.7111,
    ),
    'Brazen Collector': (
        0.014375, 0.0079739, 0.00028101, 8.8838e-05,
        0.89307, 0.018951, 0.19872,
    ),
    'Brightblade Stoat': (
        0.020211, 0.006758, -0.00038925, -0.00027813,
        0.8977, 0.02305, 1.5882,
    ),
    "Builder's Talent": (
        0.011591, -0.0040771, 0.00071767, 0.00015693,
        0.90284, 0.0054234, 0.044247,
    ),
    "Bumbleflower's Sharepot": (
        0.0039265, -0.024951, 0.0024786, 0.0001285,
        0.90645, -0.0077806, -2.3627,
    ),
    'Burrowguard Mentor': (
        0.016223, 0.010045, 0.00034943, 0.00013795,
        0.88437, 0.019004, 0.73466,
    ),
    'Bushy Bodyguard': (
        0.015061, -2.9408e-05, 0.0021327, 0.00074085,
        0.9, 0.015108, 0.50879,
    ),
    'Byway Barterer': (
        0.021674, -0.0015065, 0.00036253, 0.00032988,
        0.77111, 0.017415, 1.8682,
    ),
    'Cache Grab': (
        0.0098637, -0.0019754, 0.0032446, 0.00054983,
        0.96504, 0.0083935, -0.21744,
    ),
    'Calamitous Tide': (
        0.005306, -0.013803, -0.0017738, -0.00013105,
        0.84147, -0.0048641, -1.8024,
    ),
    'Camellia, the Seedmiser': (
        0.022865, 0.0084925, 0.0014004, 0.0015336,
        0.7994, 0.027, 2.5296,
    ),
    "Caretaker's Talent": (
        0.023453, 0.0058059, 8.9435e-05, 0.00011069,
        0.77309, 0.021289, 2.458,
    ),
    'Carrot Cake': (
        0.016258, 0.0086621, -8.9965e-05, -3.6072e-05,
        0.96876, 0.021265, 1.1867,
    ),
    'Cindering Cutthroat': (
        0.0052331, -0.0079107, -0.0032797, -0.00024043,
        0.91897, -0.0033707, -2.071,
    ),
    'Clement, the Worrywort': (
        0.019215, 0.0093284, -0.0017424, -0.0010648,
        0.76031, 0.018632, 1.2999,
    ),
    'Clifftop Lookout': (
        0.011435, -0.024261, 0.00064111, 0.00013409,
        0.82521, -0.0083132, -0.68196,
    ),
    'Coiling Rebirth': (
        None, -0.018361, None, None,
        0.61832, None, 0.04344,
    ),
    'Conduct Electricity': (
        0.0022122, -0.024533, 0.0039407, 0.00011077,
        0.80514, -0.0044945, -3.376,
    ),
    'Consumed by Greed': (
        0.019821, 0.016163, 0.00011184, 7.6648e-05,
        0.93137, 0.032499, 2.1135,
    ),
    'Corpseberry Cultivator': (
        0.0072364, -0.015606, 0.0044252, 0.00048282,
        0.94231, -0.0023032, -1.2615,
    ),
    'Coruscation Mage': (
        0.010783, -0.0015532, -0.00040034, -7.9809e-05,
        0.87889, 0.0063936, -0.57181,
    ),
    "Cruelclaw's Heist": (
        None, -0.022641, None, None,
        0.65529, None, 0.04117,
    ),
    'Crumb and Get It': (
        0.0095229, -0.0010653, -0.0011295, -0.00018177,
        0.95016, 0.0056467, -0.75974,
    ),
    'Curious Forager': (
        0.014752, -0.0068651, 0.0019784, 0.00066263,
        0.91692, 0.0091101, 0.76922,
    ),
    'Daggerfang Duo': (
        0.0090759, -0.0080012, 0.0011495, 0.00017247,
        0.95857, 0.0018494, -0.59821,
    ),
    'Daring Waverider': (
        0.0094734, 0.0077079, -0.0014412, -0.00024605,
        0.90652, 0.0096349, -0.45983,
    ),
    'Darkstar Augur': (
        0.025019, 0.017439, -1.6739e-05, -2.8941e-05,
        0.84215, 0.037423, 3.6917,
    ),
    "Dawn's Truce": (
        None, -0.048347, None, None,
        0.0, None, -1.7522,
    ),
    'Dazzling Denial': (
        0.0038178, -0.0033327, -0.0016727, -8.538e-05,
        0.92653, -0.00060721, -2.4802,
    ),
    'Dewdrop Cure': (
        0.0033915, -0.017798, -0.0017793, -8.0563e-05,
        0.50224, -0.0032604, -2.8253,
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
    df = live_deq(BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS).sort("name")
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
    df = live_deq(BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=[]).sort("name")

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
    df = live_deq(BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS).sort("name")

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
        df = live_deq(BLB_SET, TimePeriod.ALL_TIME, BLB_AS_OF, color_sets=BLB_COLOR_SETS)
    return _format_expected(df)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "regenerate":
        print(regenerate_expected())
    else:
        print("Usage: python tests/test_deq_model.py regenerate", file=sys.stderr)
        sys.exit(2)
