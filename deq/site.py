import datetime as dt
import json
import math
import random
import shutil
import sys
import traceback
from pathlib import Path

import polars as pl

from spells.cards import CardListUnavailable, card_df, draftable_names

from deq.main import available_sets, card_sheet_sets, current_set, deq, is_live
from deq.set_config import config, launch_date


PUBLISHED_DATA_DIR = Path("/var/www/html/on-draft/data")


def window_label(time_period) -> str:
    """17lands' own rendering of a time period, matching its filter dropdown.

    Derived rather than mapped, so a period 17lands adds before spells does
    still renders correctly.
    """
    return " ".join(word.capitalize() for word in str(time_period).lower().split("_"))


def load_html_template(template_path="deq_site_template.html"):
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def build_dir() -> Path:
    base = Path("docs") / "_build" / "html"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_dir() -> Path:
    d = build_dir() / "data"
    d.mkdir(exist_ok=True)
    return d


def published_payload(code: str) -> dict | None:
    """The set's JSON as currently deployed, which the build dir doesn't keep:
    publish.sh cleans it before every build."""
    path = PUBLISHED_DATA_DIR / f"{code}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def sanity_check(deq_data) -> None:
    code = deq_data.set_code
    df = deq_data.df

    if len(df) == 0:
        raise ValueError(f"{code}: dataframe is empty")

    rated = df["deq"].drop_nulls()
    rated_count = len(rated)

    if rated_count == 0:
        raise ValueError(f"{code}: no cards have DEq ratings")

    deq_min, deq_max = rated.min(), rated.max()
    if not (-0.20 < deq_min < deq_max < 0.20):
        raise ValueError(
            f"{code}: DEq range [{deq_min:.4f}, {deq_max:.4f}] outside plausible bounds"
        )

    prev = published_payload(code)
    if prev is not None:
        prev_rated = sum(1 for c in prev["cards"] if c["deq"] is not None)
        if prev_rated > 0 and rated_count < prev_rated * 0.80:
            raise ValueError(
                f"{code}: rated cards dropped from {prev_rated} to {rated_count} "
                f"({100 * (1 - rated_count / prev_rated):.0f}% loss)"
            )


def write_payload(payload: dict) -> None:
    path = data_dir() / f"{payload['set_code']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, allow_nan=False)
    print(f"  wrote {path}")


def set_payload(deq_data) -> dict:
    days_live = (deq_data.end_date - launch_date(config[deq_data.set_code])).days
    return {
        "set_code": deq_data.set_code,
        "window": window_label(deq_data.time_period),
        "embargoed": days_live < 12,
        "cards": (
            deq_data.df.select(
                "deq_grade",
                "name",
                "color",
                "rarity",
                "deq",
                "mwr",
                "pick_equity",
                (pl.col("deq_bias_adj") + pl.col("deq_meta_adj")).alias("adj"),
                "npr",
                "pct_top",
                "pct_gp",
                "image_url",
            )
            .fill_nan(None)
            .sort("deq", descending=True, nulls_last=True)
            .to_dicts()
        ),
    }


def card_sheet_payload(code: str) -> dict | None:
    """The set's card list with no ratings, for browsing before 17lands has
    data. Built once from MTGJSON and republished as-is until data arrives."""
    data_day = launch_date(config[code]) + dt.timedelta(days=1)
    published = published_payload(code)
    if published is not None and published.get("card_sheet"):
        print(f"  {code}: card sheet unchanged, data expected {data_day}")
        return published

    try:
        names = draftable_names(code)
    except CardListUnavailable as e:
        print(f"  {code}: {e}, left off the site")
        return None

    cards = card_df(code, names).select("name", "color", "rarity", "image_url")
    print(f"  {code}: card sheet of {len(cards)} cards, data expected {data_day}")
    return {
        "set_code": code,
        "window": f"Card list, data from {data_day:%b} {data_day.day}",
        "embargoed": False,
        "card_sheet": True,
        "cards": [
            {
                "deq_grade": "N/A",
                **card,
                **dict.fromkeys(
                    ["deq", "mwr", "pick_equity", "adj", "npr", "pct_top", "pct_gp"]
                ),
            }
            for card in cards.to_dicts()
        ],
    }


def write_html(default: dict, sets: list[str], version: int) -> Path:
    title_map = {"Cube+-+Powered": "Cube - Powered"}
    code_map = {"Cube+-+Powered": "PCube"}

    def options(codes: list[str]) -> str:
        return "".join(
            f'<option value="{code}"'
            f'{" selected" if code == default["set_code"] else ""}>'
            f"{code_map.get(code, code)}</option>"
            for code in codes
        )

    today = dt.date.today()
    upcoming = [code for code in sets if launch_date(config[code]) > today]
    live = [code for code in sets if is_live(config[code], today)]
    ended = [code for code in sets if code not in upcoming + live]
    select_elements = "".join(
        f'<optgroup label="{label}">{options(codes)}</optgroup>'
        for label, codes in (("Upcoming", upcoming), ("Live", live), ("Ended", ended))
        if codes
    )

    html = load_html_template().format(
        set_code=title_map.get(default["set_code"], default["set_code"]),
        window=default["window"],
        select_elements=select_elements,
        version=version,
    )

    path = build_dir() / "deq.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  wrote {path}")
    return path


def sync_static() -> None:
    src = Path("docs") / "_static"
    dst = build_dir() / "_static"
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            print(f"  copied {f.name}")


def build_payload(code: str) -> dict | None:
    """Today's payload for a set, or the published one if today's can't be built.

    One set failing, such as a new set before 17lands has its data, shouldn't
    take the rest of the site down with it."""
    try:
        data = deq(code)
        sanity_check(data)
        return set_payload(data)
    except Exception:
        traceback.print_exc()
        previous = published_payload(code)
        print(
            f"  FAILED {code}: "
            + ("keeping published data" if previous else "left off the site"),
            file=sys.stderr,
        )
        return previous


def main(set_code: str | None = None):
    version = math.floor(random.random() * 1e10)

    sync_static()

    sheets = card_sheet_sets()
    codes = sheets + available_sets()
    payloads = {}
    for code in codes:
        payload = card_sheet_payload(code) if code in sheets else build_payload(code)
        if payload is not None:
            write_payload(payload)
            payloads[code] = payload

    rated = [p for p in payloads.values() if not p.get("card_sheet")]
    if not rated:
        raise RuntimeError("no set could be published")

    # payloads keeps the newest-first order of codes
    default = payloads.get(set_code or current_set()) or rated[0]
    write_html(default, list(payloads), version)

    failed = [code for code in codes if code not in payloads]
    print("DEq site generated." + (f" Left off: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
