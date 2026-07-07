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
import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from deq.set_config import DEqConfig, config

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spells_data"

BLB_SET = "BLB"
BLB_START = dt.date(2024, 8, 13)
BLB_END = dt.date(2024, 9, 24)
# Fixtures are cached as an ALL_TIME snapshot as of BLB_END (the spells
# cache_usage/time_period scheme replaced literal start_date/end_date windows).
BLB_AS_OF = BLB_END
BLB_COLOR_SETS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

_GAME_FIELDS = (
    "game_count", "pool_count", "play_rate", "win_rate",
    "opening_hand_game_count", "opening_hand_win_rate",
    "drawn_game_count", "drawn_win_rate",
    "ever_drawn_game_count", "ever_drawn_win_rate",
    "never_drawn_game_count", "never_drawn_win_rate",
    "drawn_improvement_win_rate",
)


@pytest.fixture()
def blb_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Stage the BLB ratings + deck_color JSONs under a temp SPELLS_DATA_HOME.

    Copies (not symlinks) so spells' lazy-write code can't pollute the
    fixture tree on accident. Also injects a BLB entry into deq.set_config's
    `config` dict for the test's duration — live_deq() reads config[set_code]
    directly for is_pick_two/start_date, and production config is trimmed
    down to just MSH while the spells 0.14.0 migration is being verified.
    """
    monkeypatch.setenv("SPELLS_DATA_HOME", str(tmp_path))
    monkeypatch.setitem(config, BLB_SET, DEqConfig(start_date=BLB_START, end_date=BLB_END))

    for sub in ("ratings", "deck_color"):
        src = FIXTURE_ROOT / sub / BLB_SET
        dst = tmp_path / sub / BLB_SET
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    yield tmp_path


@pytest.fixture()
def blb_no_top_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """BLB fixture with all game data zeroed out in the top-cohort files.

    Simulates a set like OM1 where 17Lands returns no game data for the top
    player cohort (deck=0 for all cards). Used to test that the synthesis
    falls back cleanly to all-cohort values rather than propagating nulls.
    """
    monkeypatch.setenv("SPELLS_DATA_HOME", str(tmp_path))
    monkeypatch.setitem(config, BLB_SET, DEqConfig(start_date=BLB_START, end_date=BLB_END))

    for sub in ("ratings", "deck_color"):
        src = FIXTURE_ROOT / sub / BLB_SET
        dst = tmp_path / sub / BLB_SET
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    # Zero out game fields in every top-cohort ratings file
    for f in (tmp_path / "ratings" / BLB_SET).glob("*_top_*.json"):
        cards = json.loads(f.read_text())
        for card in cards:
            for field in _GAME_FIELDS:
                if field in card:
                    card[field] = 0
        f.write_text(json.dumps(cards))

    yield tmp_path
