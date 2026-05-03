"""One-time script to create BLB test fixtures from the cached 17Lands data.

Reads BLB data from SPELLS_DATA_HOME (or ~/.local/share/spells/), trims to the
first 50 cards alphabetically, and writes only the 'any' + 10 two-color pair
ratings files plus both deck_color files into tests/fixtures/spells_data/.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

SPELLS_DATA_HOME = Path(
    os.environ.get("SPELLS_DATA_HOME", Path.home() / ".local/share/spells")
)
FIXTURE_ROOT = Path(__file__).parent.parent / "tests" / "fixtures" / "spells_data"

SET_CODE = "BLB"
START = "2024-08-13"
END = "2024-09-24"
DATE_RANGE = f"{START}_{END}"
FORMAT = "PremierDraft"
NUM_CARDS = 50

TEN_PAIRS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]
COHORTS = ["all", "top"]


def load_json(path: Path) -> list | dict:
    with open(path) as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    print(f"  wrote {path.relative_to(FIXTURE_ROOT.parent.parent)}")


def main():
    # Determine the 50 card names from the all/any file
    any_src = SPELLS_DATA_HOME / "ratings" / SET_CODE / f"{FORMAT}_all_any_{DATE_RANGE}.json"
    all_cards: list[dict] = load_json(any_src)
    card_names_50 = sorted(c["name"] for c in all_cards)[:NUM_CARDS]
    card_names_set = set(card_names_50)
    print(f"Keeping {NUM_CARDS} cards: {card_names_50[0]!r} … {card_names_50[-1]!r}")

    # Wipe existing BLB fixture dirs
    for sub in ("ratings", "deck_color"):
        dest = FIXTURE_ROOT / sub / SET_CODE
        if dest.exists():
            shutil.rmtree(dest)
            print(f"  removed existing {dest.relative_to(FIXTURE_ROOT)}")

    # Copy and trim ratings files
    colors_needed = ["any"] + TEN_PAIRS
    for cohort in COHORTS:
        for color in colors_needed:
            filename = f"{FORMAT}_{cohort}_{color}_{DATE_RANGE}.json"
            src = SPELLS_DATA_HOME / "ratings" / SET_CODE / filename
            if not src.exists():
                print(f"  MISSING: {src}")
                continue
            cards: list[dict] = load_json(src)
            trimmed = [c for c in cards if c["name"] in card_names_set]
            write_json(FIXTURE_ROOT / "ratings" / SET_CODE / filename, trimmed)

    # Copy deck_color files as-is
    for cohort in COHORTS:
        filename = f"{FORMAT}_{cohort}_{DATE_RANGE}.json"
        src = SPELLS_DATA_HOME / "deck_color" / SET_CODE / filename
        if not src.exists():
            print(f"  MISSING: {src}")
            continue
        data = load_json(src)
        write_json(FIXTURE_ROOT / "deck_color" / SET_CODE / filename, data)

    print(f"\nDone. {len(colors_needed) * len(COHORTS)} ratings files + 2 deck_color files.")
    print(f"\nBLB constants for conftest.py / test_deq_model.py:")
    print(f"  BLB_SET = {SET_CODE!r}")
    print(f"  BLB_START = dt.date(2024, 8, 13)")
    print(f"  BLB_END = dt.date(2024, 9, 24)")


if __name__ == "__main__":
    main()
