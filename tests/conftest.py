"""Test fixtures for deq.

Pins real-data tests to TDM (closed format, 2025-04-22 → 2025-10-28). The
ratings / deck_color JSONs under fixtures/spells_data/ are the actual
17lands snapshot used in production; we monkeypatch SPELLS_DATA_HOME to
that tree so spells reads from disk and never tries to download.
"""

from __future__ import annotations

import datetime as dt
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spells_data"

TDM_SET = "TDM"
TDM_START = dt.date(2025, 4, 22)
TDM_END = dt.date(2025, 10, 28)


@pytest.fixture()
def tdm_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Stage the TDM ratings + deck_color JSONs under a temp SPELLS_DATA_HOME.

    Copies (not symlinks) so spells' lazy-write code can't pollute the
    fixture tree on accident. Also points the ad_hoc cache at the temp dir
    so daily_deq history files don't leak into the developer's home dir.
    """
    monkeypatch.setenv("SPELLS_DATA_HOME", str(tmp_path))

    for sub in ("ratings", "deck_color"):
        src = FIXTURE_ROOT / sub / TDM_SET
        dst = tmp_path / sub / TDM_SET
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    (tmp_path / "ad_hoc").mkdir()
    yield tmp_path
