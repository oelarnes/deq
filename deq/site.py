import json
from pathlib import Path

from deq.deq import daily_deq


def load_html_template(template_path="deq_site_template.html"):
    """
    Load HTML template from file.
    """
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    deq_data = daily_deq()
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

    html_content = load_html_template().format(
        deq_table=table_json,
        set_code=deq_data.set_code,
        player_cohort=deq_data.player_cohort,
        start_date=deq_data.start_date,
        end_date=deq_data.end_date,
    )

    output_file = Path("docs") / "_build" / "html" / "deq.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"DEq site generated: {output_file}")
    return output_file
