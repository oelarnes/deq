import json
import math
import random
import os
from pathlib import Path

from deq.deq import daily_deq


def load_html_template(template_path="deq_site_template.html"):
    """
    Load HTML template from file.
    """
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def destination_path(set_code: str | None = None) -> Path:
    base_path = Path("docs") / "_build" / "html"
    if not os.path.isdir(base_path):
        os.makedirs(base_path)
    if set_code is not None:
        return base_path / f"deq-{set_code.lower()}.html"
    else:
        return base_path / "deq.html"


def main(set_code: str | None = None):
    deq_data = daily_deq(set_code)
    table_json = json.dumps(
        deq_data.df.select(
            "deq_grade",
            "name",
            "color",
            "rarity",
            "deq",
            "ata",
            "gp_wr_b",
            "pct_gp",
            "deq_bias_adj",
            "deq_meta_adj",
        )
        .fill_nan(None)
        .sort("deq", descending=True, nulls_last=True)
        .to_dicts(),
        allow_nan=False,
    )

    select_elements = "".join([
        f'<option value="deq-{set_code.lower()}.html">{set_code}</option>' for 
        set_code in deq_data.available_sets
    ])

    date_format = "%-d %b %y"
    html_content = load_html_template().format(
        deq_table=table_json,
        set_code=deq_data.set_code,
        player_cohort=deq_data.player_cohort,
        start_date=deq_data.start_date.strftime(date_format),
        end_date=deq_data.end_date.strftime(date_format),
        version=math.floor(random.random() * 1e10),
        select_elements=select_elements
    )

    path = destination_path(deq_data.set_code)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)

    if set_code is None:
        path = destination_path(None)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

    print(f"DEq site generated: {path}")
    return path


if __name__ == "__main__":
    main()
