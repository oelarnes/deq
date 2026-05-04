"""Test fixtures for deq.

Pins real-data tests to BLB (Bloomburrow, 2024-08-13 → 2024-09-24), a
two-color-pair format — color_sets is restricted to the 10 two-color pairs so
the fixture only ships those 22 ratings files plus both deck_color files.
The ratings / deck_color JSONs under fixtures/spells_data/ are trimmed to 50
cards from the actual 17lands snapshot; we monkeypatch SPELLS_DATA_HOME to
that tree so spells reads from disk and never tries to download.
"""

from __future__ import annotations

import datetime as dt
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spells_data"

BLB_SET = "BLB"
BLB_START = dt.date(2024, 8, 13)
BLB_END = dt.date(2024, 9, 24)
BLB_COLOR_SETS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]


@pytest.fixture()
def blb_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Stage the BLB ratings + deck_color JSONs under a temp SPELLS_DATA_HOME.

    Copies (not symlinks) so spells' lazy-write code can't pollute the
    fixture tree on accident. Also points the ad_hoc cache at the temp dir
    so daily_deq history files don't leak into the developer's home dir.
    """
    monkeypatch.setenv("SPELLS_DATA_HOME", str(tmp_path))

    for sub in ("ratings", "deck_color"):
        src = FIXTURE_ROOT / sub / BLB_SET
        dst = tmp_path / sub / BLB_SET
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    (tmp_path / "ad_hoc").mkdir()
    yield tmp_path
