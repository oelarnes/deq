import datetime as dt
import os

from great_tables import GT
import polars as pl

from spells import summon
from spells.extension import context_cols
from deq import ext
from deq.p1_strategy import P1P1, all_metrics_analysis
from deq.site_ratings import ratings_df
from deq.plot import grouped_bars, line_plot

card_attrs = summon("DFT", columns=["color_group", "rarity"], extensions=ext)
deq_ratings = pl.read_csv(os.path.expanduser("~/dft_day2_deq.csv"))
gih_wr_ratings = ratings_df(
    "DFT", start_date=dt.date(2025, 2, 11), end_date=dt.date(2025, 2, 12)
)
metric_context = deq_ratings.join(gih_wr_ratings, on="name").select(
    ["name", "gih_wr", "expansion", "deq"]
)

date_filter = {"lhs": "format_day", "op": ">", "rhs": 2}
pick_filter = {"$and": [P1P1, date_filter]}

color_palette = {
    "Colorless": "#CCCCCC",  # Light gray
    "White": "#FFFAFA",  # Snow white
    "Blue": "#4682B4",  # Steel blue
    "Black": "#2F4F4F",  # Dark slate gray
    "Red": "#CD5C5C",  # Indian red
    "Green": "#2E8B57",  # Sea green
    "Gold": "#DAA520",  # Goldenrod
}

green_palette = {
    "Run Over": "#1A5233",  # Darkest shade
    "Stampeding Scurryfoot": "#246347",  # Dark shade
    "Hazard of the Dunes": "#2E8B57",  # Original sea green
    "Migrating Ketradon": "#4BBD7E",  # Light shade
    "Pothole Mole": "#6DCD96",  # Lighter shade
    "Other": "#8FDDAD",  # Lightest shade
}

results_palette = {"Simulated": "#2E8B57", "Actual": "#E76F51"}

green_commons = card_attrs.filter(
    (pl.col("color_group") == "Green") & (pl.col("rarity") == "common")
)["name"].to_list()

result = all_metrics_analysis(
    metrics=["gih_wr", "deq"],
    metric_context=metric_context,
    sets=["DFT"],
    results_filter=date_filter,
)

deq_results = (
    result.metric_results["deq"]
    .mapped_df.group_by("name")
    .sum()
    .select(
        [
            "name",
            "seen_deq_is_greatest",
            pl.col("win_weight").alias("deq_win_weight"),
            pl.col("weight").alias("deq_weight"),
        ]
    )
)

gih_wr_results = (
    result.metric_results["gih_wr"]
    .mapped_df.group_by("name")
    .sum()
    .select(
        [
            "name",
            "seen_gih_wr_is_greatest",
            pl.col("win_weight").alias("gih_wr_win_weight"),
            pl.col("weight").alias("gih_wr_weight"),
        ]
    )
)

actual_results = summon(
    "DFT",
    columns=["num_taken", "event_match_wins_sum", "event_matches_sum"],
    filter_spec=pick_filter,
)

summary_results = (
    actual_results.join(deq_results, on="name", how="full")
    .join(gih_wr_results, on="name", how="full")
    .join(metric_context, on="name")
    .join(card_attrs, on="name")
)

deq_win_rate = (pl.col("deq_win_weight") / pl.col("deq_weight")).alias("deq_win_rate")
gih_wr_win_rate = (pl.col("gih_wr_win_weight") / pl.col("gih_wr_weight")).alias(
    "gih_wr_win_rate"
)
actual_win_rate = (pl.col("event_match_wins_sum") / pl.col("event_matches_sum")).alias(
    "actual_win_rate"
)

# 3. Color Summaries

color_totals = (
    summary_results.group_by(["color_group"])
    .sum()
    .select(
        "color_group", "seen_deq_is_greatest", "seen_gih_wr_is_greatest", "num_taken"
    )
    .sort("num_taken", descending=True)
    .rename(
        {
            "seen_deq_is_greatest": "DEq",
            "seen_gih_wr_is_greatest": "GIH WR",
            "num_taken": "Actual",
        }
    )
)

count_totals = summon(
    "DFT", ["num_drafts", "event_matches_sum"], filter_spec=pick_filter, group_by=[]
).rename({"num_drafts": "Drafts", "event_matches_sum": "Matches"})

color_win_rates = (
    summary_results.group_by(["color_group"])
    .sum()
    .select(
        "color_group",
        deq_win_rate,
        gih_wr_win_rate,
        actual_win_rate,
    )
    .rename(
        {
            "deq_win_rate": "DEq",
            "gih_wr_win_rate": "GIH WR",
            "actual_win_rate": "Actual",
        }
    )
)

total_win_rates = (
    summary_results.sum()
    .select(
        deq_win_rate,
        gih_wr_win_rate,
        actual_win_rate,
    )
    .rename(
        {
            "deq_win_rate": "DEq",
            "gih_wr_win_rate": "GIH WR",
            "actual_win_rate": "Actual",
        }
    )
)



def counts_bars():
    grouped_bars(
        color_totals,
        title="Distribution of Color of First Pick by Strategy",
        palette=color_palette,
        x_label="Pick Strategy",
    )


def wr_bars():
    grouped_bars(
        color_win_rates,
        title="Simulated Match Win Rates by Strategy and Color of First Pick",
        y_label="Match Win Rate",
        is_pct=True,
        palette=color_palette,
        x_label="Pick Strategy",
    )


# 4. Commons Analysis

deq_ext = {**ext, **context_cols("deq")}
deq_sg_result = summon(
    "DFT",
    columns=["num_drafts", "picked_match_wr"],
    group_by=[],
    extensions=deq_ext,
    filter_spec={
        "$and": [
            pick_filter,
            {"lhs": "seen_greatest_deq_name", "op": "in", "rhs": green_commons},
        ]
    },
    card_context=metric_context,
)["picked_match_wr"][0]

gih_wr_ext = {**ext, **context_cols("gih_wr")}
gih_wr_sg_result = summon(
    "DFT",
    columns=["num_drafts", "picked_match_wr"],
    group_by=[],
    extensions=gih_wr_ext,
    filter_spec={
        "$and": [
            pick_filter,
            {"lhs": "seen_greatest_gih_wr_name", "op": "in", "rhs": green_commons},
        ]
    },
    card_context=metric_context,
)["picked_match_wr"][0]

actual_result_df = pl.DataFrame(
    [
        {
            "result_type": "Actual",
            "DEq": deq_sg_result,
            "GIH WR": gih_wr_sg_result,
        }
    ]
)

commons_df = summary_results.filter(pl.col("name").is_in(green_commons)).with_columns(
    pl.when(pl.col("name").is_in(green_palette.keys()))
    .then("name")
    .otherwise(pl.lit("Other"))
    .alias("common")
)

common_ratings = commons_df.select(["name", "deq", "gih_wr"]).rename(
    {"name": "Name", "deq": "DEq", "gih_wr": "GIH WR"}
)

common_counts = (
    commons_df.group_by("common")
    .sum()
    .rename(
        {
            "seen_deq_is_greatest": "DEq",
            "seen_gih_wr_is_greatest": "GIH WR",
            "num_taken": "Actual",
        }
    )
).select(["common", "DEq", "GIH WR", "Actual"])

common_result_df = (
    commons_df.sum()
    .select(pl.lit("Simulated").alias("result_type"), deq_win_rate, gih_wr_win_rate)
    .rename({"deq_win_rate": "DEq", "gih_wr_win_rate": "GIH WR"})
)

results_df = pl.concat([actual_result_df, common_result_df])


def common_counts_bar():
    grouped_bars(
        common_counts,
        title="Counts of Some Green Commons First Picked by Strategy",
        palette=green_palette,
        x_label="Pick Strategy",
    )


def common_results_bar():
    grouped_bars(
        results_df,
        title="Simulated vs Actual Match Win Rates When Green Commons Are Top Ranked",
        y_label="Match Win Rate",
        is_pct=True,
        palette=results_palette,
        x_label="Pick Strategy",
    )

by_day_df = summon(
    "DFT",
    ["picked_match_wr"],
    group_by=["format_day"],
    filter_spec={
        "$and": [P1P1, {"lhs": "pick", "op": "in", "rhs": green_palette.keys()}],
    },
).rename({"picked_match_wr": "Picked"})

by_day_seen = summon(
    "DFT",
    ["picked_match_wr"],
    group_by=["format_day"],
    filter_spec={
        "$and": [
            P1P1,
            {"lhs": "seen_greatest_deq_name", "op": "in", "rhs": green_palette.keys()},
        ],
    },
    card_context=metric_context,
    extensions=deq_ext,
).rename({"picked_match_wr": "Top Ranked By DEq"})

by_day_df = by_day_df.join(by_day_seen, on="format_day").rename({"format_day": "Day"})

def by_day_plot():
    line_plot(
        by_day_df,
        title="Win Rate Seeing Green Commons by Day",
        y_label="Match Win Rate",
        is_pct=True,
        palette={
            "Picked": results_palette["Simulated"],
            "Top Ranked By DEq": results_palette["Actual"]
            }
        )
