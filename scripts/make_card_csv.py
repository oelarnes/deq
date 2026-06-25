"""
make_card_csv.py — Generate a card CSV for set review.

Usage (from deq/):
  pdm run python scripts/make_card_csv.py --set SOS
  pdm run python scripts/make_card_csv.py --set SOS --rarities common

Output: ~/dev/set-reviews/{SET}_cards.csv

Columns: index, name, color, rarity, mana_cost, mana_value, oracle_text, power, toughness, grade
Sorted by rarity (C→U→R→M), then color group (W→U→B→R→G→multi→colorless), then mana_value, then name.
index is 1-based and stable across runs for a given set.

For multi-face cards (prepare, adventure, transform, modal_dfc, split, flip), the back-face
oracle text is appended inline so agents see the full card. DFC handling is done by load_card_df
via _supplement_dfc_oracle (fetches MTGJSON when the local parquet has is_dfc=True cards).

Reminder text is NOT stripped here — new-mechanic reminder text explains the mechanics to agents.
"""

import argparse
import csv
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from review_slice import load_card_df

SET_REVIEWS = Path.home() / "dev" / "set-reviews"

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}
COLOR_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}


def color_sort_key(color: str) -> int:
    if len(color) == 1:
        return COLOR_ORDER.get(color, 5)
    elif color == "":
        return 6  # colorless/artifact
    return 5  # multicolor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", required=True, dest="set_code", metavar="SET")
    parser.add_argument(
        "--rarities", nargs="+",
        default=["common", "uncommon", "rare", "mythic"],
        choices=["common", "uncommon", "rare", "mythic"],
    )
    args = parser.parse_args()

    SET = args.set_code
    RARITIES = args.rarities

    df = load_card_df(SET)
    df = df.filter(
        pl.col("rarity").is_in(RARITIES)
        & ~pl.col("card_type").str.contains("Land")
    )

    rows = df.to_dicts()
    rows.sort(key=lambda r: (
        RARITY_ORDER.get(r.get("rarity", ""), 9),
        color_sort_key(r.get("color", "")),
        float(r.get("mana_value", 0)),
        r.get("name", ""),
    ))

    SET_REVIEWS.mkdir(parents=True, exist_ok=True)
    out_path = SET_REVIEWS / f"{SET}_cards.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "index", "name", "color", "rarity",
            "mana_cost", "mana_value", "oracle_text",
            "power", "toughness", "grade", "deq_est",
        ])
        for i, row in enumerate(rows, 1):
            oracle = (row.get("oracle_text") or "").replace("\n", " | ")
            rarity_abbr = row.get("rarity", "")[0].upper() if row.get("rarity") else ""
            writer.writerow([
                i,
                row.get("name", ""),
                row.get("color", ""),
                rarity_abbr,
                row.get("mana_cost", ""),
                int(row.get("mana_value", 0)),
                oracle,
                row.get("power") or "",
                row.get("toughness") or "",
                "",  # grade — filled in by agent via join_grades.py
                "",  # deq_est — filled in by join_grades.py from the grade
            ])

    print(f"Wrote {len(rows)} cards → {out_path}")


if __name__ == "__main__":
    main()
