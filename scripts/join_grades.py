"""
join_grades.py — Merge agent-produced grades into the set review card CSV.

Usage (from deq/):
  pdm run python scripts/join_grades.py --set SOS

Reads:
  ~/dev/set-reviews/{SET}_grades.csv   (index, grade — written by review agent)
  ~/dev/set-reviews/{SET}_cards.csv    (full card list)

Writes:
  ~/dev/set-reviews/{SET}_cards.csv    (updated in-place: grade + deq_est filled in)

Grade format: A1–A9, B1–B9, C1–C9, D1–D9, F
  C6 = 0.0% DEq. Each step = 0.25%. A1 = +5.75%, D9 = -3.00%.

Grades from the agent file take precedence over existing grades.
Rows with no matching entry are left unchanged.
deq_est is computed from the grade (e.g. B5 → +2.50%).
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from review_slice import grade_to_deq

SET_REVIEWS = Path.home() / "dev" / "set-reviews"

VALID_GRADES = {
    f"{letter}{num}"
    for letter in "ABCD"
    for num in range(1, 10)
} | {"F"}


def fmt_deq_est(grade: str) -> str:
    """Format deq_est as a human-readable percentage string (e.g. '+2.50%')."""
    deq = grade_to_deq(grade)
    if deq is None:
        return ""
    return f"{deq * 100:+.2f}%"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", required=True, dest="set_code", metavar="SET")
    args = parser.parse_args()

    SET = args.set_code
    cards_path = SET_REVIEWS / f"{SET}_cards.csv"
    grades_path = SET_REVIEWS / f"{SET}_grades.csv"

    if not grades_path.exists():
        raise FileNotFoundError(f"Grades file not found: {grades_path}")
    if not cards_path.exists():
        raise FileNotFoundError(f"Cards file not found: {cards_path}")

    # Load grades from agent file
    grades: dict[int, str] = {}
    bad_grades: list[str] = []
    with open(grades_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade = row["grade"].strip().upper()
            if grade not in VALID_GRADES:
                bad_grades.append(f"  index {row['index']}: {row['grade']!r}")
                continue
            grades[int(row["index"])] = grade

    if bad_grades:
        print("WARNING: Unrecognised grades (skipped):", file=sys.stderr)
        for msg in bad_grades:
            print(msg, file=sys.stderr)

    # Load and update cards
    cards: list[dict] = []
    fieldnames: list[str] = []
    with open(cards_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            idx = int(row["index"])
            if idx in grades:
                grade = grades[idx]
                row["grade"] = grade
                if "deq_est" in row:
                    row["deq_est"] = fmt_deq_est(grade)
            cards.append(row)

    # Ensure deq_est column exists even if CSV predates it
    if "deq_est" not in fieldnames:
        fieldnames.append("deq_est")
        for card in cards:
            if "deq_est" not in card:
                card["deq_est"] = fmt_deq_est(card.get("grade", "")) if card.get("grade") else ""

    with open(cards_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cards)

    # Report
    filled = sum(1 for c in cards if c.get("grade"))
    print(f"Merged {len(grades)} grades → {filled}/{len(cards)} total graded in {cards_path.name}")

    # Grade distribution summary
    from collections import Counter
    dist: Counter = Counter()
    for c in cards:
        g = c.get("grade", "")
        if g:
            dist[g[0] if g != "F" else "F"] += 1
    buckets = [(letter, dist.get(letter, 0)) for letter in "ABCDF"]
    print("  Distribution: " + "  ".join(f"{l}={n}" for l, n in buckets if n > 0))

    # Show the newly-changed grades with their DEq estimates
    if grades:
        print(f"  Changed grades ({len(grades)}):")
        for idx, grade in sorted(grades.items()):
            est = fmt_deq_est(grade)
            card_name = next((c["name"] for c in cards if int(c["index"]) == idx), "?")
            print(f"    [{idx:3d}] {card_name:40s} → {grade}  ({est})")


if __name__ == "__main__":
    main()
