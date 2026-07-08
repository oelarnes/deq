import json
import math
import random
import shutil
from pathlib import Path

import polars as pl

from deq.main import available_sets, deq
from deq.set_config import config


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
        raise ValueError(f"{code}: DEq range [{deq_min:.4f}, {deq_max:.4f}] outside plausible bounds")

    existing = data_dir() / f"{code}.json"
    if existing.exists():
        with open(existing) as f:
            prev = json.load(f)
        prev_rated = sum(1 for c in prev["cards"] if c["deq"] is not None)
        if prev_rated > 0 and rated_count < prev_rated * 0.80:
            raise ValueError(
                f"{code}: rated cards dropped from {prev_rated} to {rated_count} "
                f"({100 * (1 - rated_count / prev_rated):.0f}% loss)"
            )


def write_set_json(deq_data) -> Path:
    date_format = "%-d %b %y"
    days_live = (deq_data.end_date - config[deq_data.set_code].start_date).days
    payload = {
        "set_code": deq_data.set_code,
        "start_date": deq_data.start_date.strftime(date_format),
        "end_date": deq_data.end_date.strftime(date_format),
        "embargoed": days_live < 12,
        "cards": (
            deq_data.df.select(
                "deq_grade", "name", "color", "rarity",
                "deq", "mwr", "pick_equity",
                (pl.col("deq_bias_adj") + pl.col("deq_meta_adj")).alias("adj"),
                "npr", "pct_top", "pct_gp", "image_url",
            )
            .fill_nan(None)
            .sort("deq", descending=True, nulls_last=True)
            .to_dicts()
        ),
    }
    path = data_dir() / f"{deq_data.set_code}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, allow_nan=False)
    print(f"  wrote {path}")
    return path


def write_html(deq_data, sets: list[str], version: int) -> Path:
    title_map = {"Cube+-+Powered": "Cube - Powered"}
    code_map = {"Cube+-+Powered": "PCube"}
    date_format = "%-d %b %y"

    select_elements = "".join(
        f'<option value="{code}"{" selected" if code == deq_data.set_code else ""}>'
        f'{code_map.get(code, code)}</option>'
        for code in sets
    )

    html = load_html_template().format(
        set_code=title_map.get(deq_data.set_code, deq_data.set_code),
        start_date=deq_data.start_date.strftime(date_format),
        end_date=deq_data.end_date.strftime(date_format),
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


def main(set_code: str | None = None):
    version = math.floor(random.random() * 1e10)

    sync_static()

    # deq(None) returns the current set; use it as the page default
    default_data = deq(set_code)

    sets = available_sets()
    for code in sets:
        data = default_data if code == default_data.set_code else deq(code)
        sanity_check(data)
        write_set_json(data)

    write_html(default_data, sets, version)
    print("DEq site generated.")


if __name__ == "__main__":
    main()
