"""
review_slice.py — Generate a card review slice for a set-review subagent.

Outputs a formatted text blob (stdout) containing:
  1. New set cards for the given color/rarity slice (full oracle text)
  2. Reference set cards for the same slice, with DEq ratings appended

Usage:
  pdm run python scripts/review_slice.py --set MSH --refs SOS TLA DFT --color W --rarities common uncommon
  pdm run python scripts/review_slice.py --set MSH --refs SOS TLA --color multi --rarities rare mythic

Colors: W U B R G multi colorless land
Rarities: common uncommon rare mythic (default: common uncommon)
"""

import argparse
import json
import urllib.request
from pathlib import Path

import polars as pl

SPELLS_BASE = Path.home() / ".local/share/spells"
EXTERNAL = SPELLS_BASE / "external"
DEQ_DATA = Path(__file__).resolve().parents[1] / "docs" / "_build" / "html" / "data"

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}
COLOR_NAMES = {
    "W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
    "multi": "Multicolor", "colorless": "Colorless / Artifact", "land": "Land",
    "all": "All Colors",
}
# Order for grouped "all" output (skip land)
COLOR_GROUP_ORDER = ["W", "U", "B", "R", "G", "multi", "colorless"]

DRAFT_SHEETS = {"common", "uncommon", "rareMythic", "sourceMaterial"}


# ---------------------------------------------------------------------------
# Card data loading
# ---------------------------------------------------------------------------

def _fetch_mtgjson(code: str) -> dict:
    req = urllib.request.Request(
        f"https://mtgjson.com/api/v5/{code}.json",
        headers={"User-Agent": "spells-mtg/0.1.0"},
    )
    with urllib.request.urlopen(req) as f:
        return json.loads(f.read())


def _card_df_from_mtgjson(set_code: str) -> pl.DataFrame:
    """Fetch card data from MTGJSON for sets without a local parquet."""
    d = _fetch_mtgjson(set_code)
    booster = d["data"]["booster"].get("play") or d["data"]["booster"].get("draft")
    source_codes = booster["sourceSetCodes"] if booster else [set_code]

    uuid_to_card: dict = {}
    for code in source_codes:
        data = _fetch_mtgjson(code) if code != set_code else d
        for c in data["data"]["cards"]:
            uuid_to_card[c["uuid"]] = c

    pool: dict = {}
    is_bonus: dict = {}
    for sheet_name, sheet in booster["sheets"].items():
        if sheet_name not in DRAFT_SHEETS:
            continue
        bonus = sheet_name == "sourceMaterial"
        for uuid in sheet["cards"]:
            c = uuid_to_card.get(uuid)
            if not c:
                continue
            name = c.get("faceName") or c.get("name")
            if name not in pool:
                pool[name] = c
                is_bonus[name] = bonus

    rows = []
    for name, c in pool.items():
        colors = c.get("colors", [])
        rows.append({
            "name": name,
            "set_code": c.get("setCode", set_code),
            "color": "".join(colors),
            "rarity": c.get("rarity", "common"),
            "color_identity": "".join(c.get("colorIdentity", [])),
            "card_type": " ".join(c.get("types", [])),
            "subtype": " ".join(c.get("subtypes", [])),
            "mana_value": float(c.get("manaValue", 0)),
            "mana_cost": c.get("manaCost", "") or "",
            "power": c.get("power"),
            "toughness": c.get("toughness"),
            "is_bonus_sheet": is_bonus[name],
            "oracle_text": c.get("text", "") or "",
        })

    return pl.DataFrame(rows)


def load_card_df(set_code: str) -> pl.DataFrame:
    """Load card data for a set. Uses local parquet if available, else MTGJSON."""
    path = EXTERNAL / set_code / f"{set_code}_card.parquet"
    if path.exists():
        return pl.read_parquet(path)
    print(f"[info] No parquet for {set_code}, fetching from MTGJSON...", flush=True)
    return _card_df_from_mtgjson(set_code)


def filter_cards(df: pl.DataFrame, color: str, rarities: list[str]) -> pl.DataFrame:
    """Filter to a color/rarity slice.

    color semantics:
      W/U/B/R/G  — exactly that one color (excludes multicolor)
      multi      — two or more colors
      colorless  — no colors and not a land
      land       — has Land in card_type
      all        — all non-land cards (use emit_color_groups for grouped output)
    """
    df = df.filter(pl.col("rarity").is_in(rarities))

    if color in ("W", "U", "B", "R", "G"):
        df = df.filter(pl.col("color") == color)
    elif color == "multi":
        df = df.filter(pl.col("color").str.len_chars() > 1)
    elif color == "colorless":
        df = df.filter(
            (pl.col("color") == "") & (~pl.col("card_type").str.contains("Land"))
        )
    elif color == "land":
        df = df.filter(pl.col("card_type").str.contains("Land"))
    elif color == "all":
        df = df.filter(~pl.col("card_type").str.contains("Land"))

    return df.sort(["mana_value", "name"])


def emit_color_groups(df: pl.DataFrame, deq_ratings: dict | None = None) -> list[str]:
    """Emit cards grouped by color with section headers. Used for --color all."""
    lines = []
    for grp in COLOR_GROUP_ORDER:
        if grp in ("W", "U", "B", "R", "G"):
            subset = df.filter(pl.col("color") == grp)
        elif grp == "multi":
            subset = df.filter(pl.col("color").str.len_chars() > 1)
        elif grp == "colorless":
            subset = df.filter(
                (pl.col("color") == "") & (~pl.col("card_type").str.contains("Land"))
            )
        else:
            continue
        if subset.is_empty():
            continue
        lines.append(f"-- {COLOR_NAMES[grp]} --")
        for row in subset.sort(["mana_value", "name"]).to_dicts():
            lines.append(format_card_line(row, deq_ratings))
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# DEq ratings loading
# ---------------------------------------------------------------------------

def load_deq(set_code: str) -> dict[str, dict]:
    """Return name -> {deq_grade, deq} from the site-generated DEq JSON.

    File: deq/docs/_build/html/data/{SET}.json
    Generated by deq/deq/site.py via write_set_json().
    """
    path = DEQ_DATA / f"{set_code}.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return {card["name"]: card for card in data.get("cards", [])}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_card_line(row: dict, deq_ratings: dict | None = None) -> str:
    name = row["name"]
    cost = row.get("mana_cost") or ""
    pt = ""
    if row.get("power") is not None and row["power"] != "":
        pt = f" {row['power']}/{row['toughness']}"
    card_type = row.get("card_type", "")
    subtype = row.get("subtype", "")
    type_str = card_type + (f" — {subtype}" if subtype else "")
    oracle = (row.get("oracle_text") or "").replace("\n", " | ")
    if len(oracle) > 130:
        oracle = oracle[:127] + "..."
    bonus_tag = " [BONUS]" if row.get("is_bonus_sheet") else ""

    line = f"{name}{bonus_tag} | {cost}{pt} | {type_str} | {oracle}"

    if deq_ratings:
        r = deq_ratings.get(name, {})
        if r:
            grade = r.get("deq_grade", "?")
            deq_pct = r.get("deq")
            pct_gp = r.get("pct_gp")
            if deq_pct is not None:
                if deq_pct < 0 and pct_gp is not None:
                    # Show play rate for negative cards: low pct_gp means grade is near-0 noise → F in practice
                    line += f"  || {grade} ({deq_pct*100:+.2f}%, played {pct_gp*100:.0f}%)"
                else:
                    line += f"  || {grade} ({deq_pct*100:+.2f}%)"
            else:
                # No DEq grade — typically near-zero play rate; show pct_gp to distinguish
                pct_str = f", played {pct_gp*100:.0f}%" if pct_gp is not None else ""
                line += f"  || N/A (no grade{pct_str})"

    return line


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", required=True, dest="set_code", metavar="SET",
                        help="New set to review (e.g. MSH)")
    parser.add_argument("--refs", nargs="+", default=[],
                        help="Reference set codes (e.g. SOS TLA DFT)")
    parser.add_argument("--color", required=True,
                        choices=["W", "U", "B", "R", "G", "multi", "colorless", "land", "all"],
                        help="'all' emits all non-land cards grouped by color")
    parser.add_argument("--rarities", nargs="+", default=["common", "uncommon"],
                        choices=["common", "uncommon", "rare", "mythic"])
    parser.add_argument("--cohort", default="all", choices=["all", "top"],
                        help="DEq rating cohort (default: all, currently unused — DEq site JSON is pre-synthesized)")
    args = parser.parse_args()

    SET = args.set_code
    COLOR = args.color
    RARITIES = sorted(args.rarities, key=lambda r: RARITY_ORDER.get(r, 9))
    REFS = args.refs

    rarity_label = " & ".join(r.title() + "s" for r in RARITIES)
    color_label = COLOR_NAMES.get(COLOR, COLOR)

    lines = []

    # --- New set ---
    lines.append(f"=== NEW SET: {SET} | {color_label} | {rarity_label} ===")
    lines.append("")
    try:
        new_df = load_card_df(SET)
        cards = filter_cards(new_df, COLOR, RARITIES)
        if cards.is_empty():
            lines.append("[no cards in this slice]")
        elif COLOR == "all":
            lines.extend(emit_color_groups(cards))
        else:
            for row in cards.to_dicts():
                lines.append(format_card_line(row))
    except Exception as e:
        lines.append(f"[ERROR loading {SET}: {e}]")
    lines.append("")

    # --- Reference sets ---
    if REFS:
        lines.append(f"=== REFERENCE SETS | {color_label} | {rarity_label} ===")
        lines.append(
            "DEq: A+ to D+ fixed scale. DEq% = win rate added vs. basic land. C/C- ≈ 0%."
            " For negative cards, 'played X%' shows actual play rate —"
            " C- played <20% is effectively F (unplayed, grade is noise)."
            " Fields: mwr=marginal win rate, peq=pick equity (early pick → high),"
            " adj=bias+metagame correction, npr=normalized pick rate, gp=play rate, top=% top-player data."
        )
        lines.append("")
        for ref in REFS:
            lines.append(f"=== {ref} ===")
            try:
                ref_df = load_card_df(ref)
                deq_ratings = load_deq(ref)
                if not deq_ratings:
                    lines.append(f"  [no DEq data for {ref}]")
                cards = filter_cards(ref_df, COLOR, RARITIES)
                if cards.is_empty():
                    lines.append("  [no cards in this slice]")
                elif COLOR == "all":
                    lines.extend(emit_color_groups(cards, deq_ratings))
                else:
                    for row in cards.to_dicts():
                        lines.append(format_card_line(row, deq_ratings))
            except Exception as e:
                lines.append(f"  [ERROR: {e}]")
            lines.append("")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
