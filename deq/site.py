import datetime as dt
import json
import math
import random
from pathlib import Path

from deq.main import config, daily_deq


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


def write_set_json(deq_data) -> Path:
    date_format = "%-d %b %y"
    payload = {
        "set_code": deq_data.set_code,
        "start_date": deq_data.start_date.strftime(date_format),
        "end_date": deq_data.end_date.strftime(date_format),
        "cards": (
            deq_data.df.select(
                "deq_grade", "name", "color", "rarity",
                "deq", "npr", "pct_top", "image_url",
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


def write_html(deq_data, version: int) -> Path:
    title_map = {"Cube+-+Powered": "Cube - Powered"}
    code_map = {"Cube+-+Powered": "PCube"}
    date_format = "%-d %b %y"

    select_elements = "".join(
        f'<option value="{code}"{" selected" if code == deq_data.set_code else ""}>'
        f'{code_map.get(code, code)}</option>'
        for code in deq_data.available_sets
    )

    embargo_class = (
        "col-embargo"
        if (deq_data.end_date - config[deq_data.set_code].start_date).days < 12
        else ""
    )

    html = load_html_template().format(
        set_code=title_map.get(deq_data.set_code, deq_data.set_code),
        start_date=deq_data.start_date.strftime(date_format),
        end_date=deq_data.end_date.strftime(date_format),
        embargo_class=embargo_class,
        select_elements=select_elements,
        version=version,
    )

    path = build_dir() / "deq.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  wrote {path}")
    return path


def main(set_code: str | None = None):
    version = math.floor(random.random() * 1e10)

    # daily_deq(None) returns the latest active set; use it as the page default
    default_data = daily_deq(set_code)

    # Write JSON for every active set; reuse default_data for its set
    for code in config:
        if dt.date.today() > config[code].start_date:
            data = default_data if code == default_data.set_code else daily_deq(code)
            write_set_json(data)

    write_html(default_data, version)
    print("DEq site generated.")


if __name__ == "__main__":
    main()
