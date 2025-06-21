import datetime as dt
from typing import Any, Sequence

from great_tables import GT
import polars as pl

from spells import summon, ColType, ColSpec
from spells.extension import context_cols
from deq import ext, deq_bias_set_context
from deq.p1_strategy import P1P1, all_metrics_analysis, card_detail_df, metric_wr_cols
from deq.site_ratings import ratings_df
from deq.plot import grouped_bars, line_plot

set_code = "TDM"
card_attrs = summon(set_code, columns=["color_group", "rarity"], extensions=ext)

SKILL_COHORT = "skill_cohort"
name_map = {
    "deq": "DEq",
    "gih_wr_17l": "GIH WR",
    "deq_dragons": "DEq Dragons",
    "deq_mardu": "DEq Mardu",
    "actual": "Actual",
}

soft_force_boost = 0.015
mardu_cards = [
    "Shock Brigade",
    "Salt Road Packbeast",
    "Fortress Kin-Guard",
    "Mardu Devotee",
    "Bearer of Glory",
    "Coordinated Assault",
    "Underfoot Underdogs",
    "Rebellious Strike",
    "Molten Exhale",
    "Reigning Victor",
    "Bloodfell Caves",
    "Scoured Barrens",
    "Wind-Scarred Crag",
    "Mardu Monument",
    "Sonic Shrieker",
    "Frontline Rush",
    "Nomad Outpost",
    "War Effort",
    "Shocking Sharpshooter",
    "Zurgo's Vanguard",
    "Bone-Cairn Butcher",
    "Descendant of Storms",
    "Dalkovian Packbeast",
    "Sunpearl Kirin",
    "Rally the Monastery",
    "Sunset Strikemaster",
    "Venerated Stormsinger",
    "Furious Forebear",
    "Duty Beyond Death",
    "Zurgo, Thunder's Decree",
    "Inevitable Defeat",
    "Thunder of Unity",
    "Mardu Siegebreaker",
    "Stadium Headliner",
    "Windcrag Siege",
    "Dalkovian Encampment",
    "Voice of Victory",
    "All-Out Assault",
    "Tersa Lightshatter",
    "Sage of the Skies",
    "Cori-Steel Cutter",
    "Neriv, Heart of the Storm",
    "Hardened Tactician",
    "Inevitable Defeat",
    "Fleeting Effigy",
    "Marshal of the Lost",
]

dragon_cards = [
    "Dragonstorm Globe",
    "Dismal Backwater",
    "Sibsig Appraiser",
    "Sagu Wildling",
    "Trainquil Cove",
    "Sonic Shrieker",
    "Thornwood Falls",
    "Molten Exhale",
    "Caustic Exhale",
    "Jungle Hollow",
    "Dispelling Exhale",
    "Evolving Wilds",
    "Roiling Dragonstorm",
    "Temur Monument",
    "Sultai Monument",
    "Traveling Botanist",
    "Jeskai Monument",
    "Encroaching Dragonstorm",
    "Teeming Dragonstorm",
    "Dragonbroods' Relic",
    "Jeskai Shrinekeeper",
    "Dirgur Island Dragon",
    "Rakshasa's Bargain",
    "Twinmaw Stormbrood",
    "Disruptive Stormbrood",
    "Karakyk Guardian",
    "Lie in Wait",
    "Opulent Palace",
    "Dragon's Prey",
    "Purging Stormbrood",
    "Fangkeeper's Familiar",
    "Roar of Endless Song",
    "Dragonologist",
    "Scavenger Regent",
    "Death Begets Life",
    "Shiko, Paragon of the Way",
    "Ambling Stormshell",
    "Lotuslight Dancers",
    "Dragonback Assault",
    "Murang River Regent",
    "Betor, Kin to All",
    "Bloomvine Regent",
    "Ureni, the Song Unending",
    "Teval, Arbiter of Virtue",
    "Stormscale Scion",
    "Fresh Start",
]

metric_filter = {
    "$and": [{"lhs": "format_day", "op": "<=", "rhs": 31}, {"player_cohort": "Top"}]
}

deq_context = deq_bias_set_context([set_code], metric_filter)

metric_context = summon(
    set_code,
    ["deq", "gih_wr_17l"],
    filter_spec=metric_filter,
    group_by=["expansion", "name"],
    extensions=ext,
    set_context=deq_context,
)

metric_context = metric_context.with_columns(
    pl.when(pl.col("name").is_in(mardu_cards)).then(1).otherwise(0).alias("is_mardu"),
    pl.when(pl.col("name").is_in(dragon_cards))
    .then(1)
    .otherwise(0)
    .alias("is_dragons"),
).with_columns(
    (pl.col("deq") + pl.col("is_mardu") * soft_force_boost).alias("deq_mardu"),
    (pl.col("deq") + pl.col("is_dragons") * soft_force_boost).alias("deq_dragons"),
)

results_filter = {"lhs": "format_day", "op": ">", "rhs": 3}
pick_filter = {
    "$and": [
        results_filter,
        P1P1,
    ]
}

color_palette = {
    "Colorless": "#CCCCCC",  # Light gray
    "White": "#FFFAFA",  # Snow white
    "Blue": "#4682B4",  # Steel blue
    "Black": "#2F4F4F",  # Dark slate gray
    "Red": "#CD5C5C",  # Indian red
    "Green": "#2E8B57",  # Sea green
    "Gold": "#DAA520",  # Goldenrod
}

results_palette = {"Simulated": "#2E8B57", "Actual": "#E76F51"}

metrics = ["gih_wr_17l", "deq", "deq_mardu", "deq_dragons"]
result = all_metrics_analysis(
    metrics=metrics,
    sets=[set_code],
    results_filter=results_filter,
    metric_context=metric_context,
)

card_df = card_detail_df(
    result, set_code, results_filter=results_filter, metric_context=metric_context
)

card_df = card_df.with_columns(
    (
        pl.col("seen_deq_mardu_is_greatest").cast(pl.Int64)
        - pl.col("seen_deq_dragons_is_greatest").cast(pl.Int64)
    ).alias("deq_mardu_vs_deq_dragons_taken"),
    (
        pl.col("seen_deq_dragons_is_greatest").cast(pl.Int64)
        - pl.col("seen_deq_mardu_is_greatest").cast(pl.Int64)
    ).alias("deq_dragons_vs_deq_mardu_taken"),
)

# 3. Color Summaries

color_totals = (
    card_df.group_by(["color_group"])
    .sum()
    .select(
        "color_group",
        "seen_deq_is_greatest",
        "seen_deq_mardu_is_greatest",
        "seen_deq_dragons_is_greatest",
        "seen_gih_wr_17l_is_greatest",
        "num_taken",
    )
    .sort("num_taken", descending=True)
    .rename(
        {
            "seen_deq_is_greatest": "DEq",
            "seen_gih_wr_17l_is_greatest": "GIH WR",
            "seen_deq_mardu_is_greatest": "Mardu",
            "seen_deq_dragons_is_greatest": "Dragons",
            "num_taken": "Actual",
        }
    )
)

count_totals = summon(
    set_code, ["num_drafts", "event_matches_sum"], filter_spec=pick_filter, group_by=[]
).rename({"num_drafts": "Drafts", "event_matches_sum": "Matches"})

wr_cols = metric_wr_cols(metrics)
actual_win_rate = (pl.col("event_match_wins_sum") / pl.col("event_matches_sum")).alias(
    "picked_match_wr"
)

color_win_rates = (
    card_df.group_by(["color_group"])
    .sum()
    .select(
        "color_group",
        actual_win_rate,
        wr_cols["deq"],
        wr_cols["gih_wr_17l"],
    )
    .rename(
        {
            "deq_win_rate": "DEq",
            "gih_wr_17l_win_rate": "GIH WR",
            "picked_match_wr": "Actual",
        }
    )
)

total_win_rates = (
    card_df.sum()
    .select(
        wr_cols["deq"],
        wr_cols["gih_wr_17l"],
        actual_win_rate,
    )
    .rename(
        {
            "deq_win_rate": "DEq",
            "gih_wr_17l_win_rate": "GIH WR",
            "picked_match_wr": "Actual",
        }
    )
)


def counts_bars(metrics=('GIH WR', 'DEq')):
    grouped_bars(
        color_totals.select("color_group", "Actual", *metrics),
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


boros_or_soup = ColSpec(
    col_type=ColType.GROUP_BY,
    expr=pl.when(pl.col("main_colors") == "WR")
    .then(pl.lit("Boros"))
    .otherwise(
        pl.when(
            (pl.col("has_splash").and_(pl.col("num_colors") > 2)).or_(
                pl.col("num_colors") > 3
            )
        )
        .then(pl.lit("Soup"))
        .otherwise(pl.lit("Other"))
    ),
)

ext = {**ext, "boros_or_soup": boros_or_soup}




def boros_v_soup_table():
    return (
        GT(
            summon(
                "TDM",
                ["game_wr", "num_games"],
                group_by=["boros_or_soup", SKILL_COHORT],
                filter_spec={
                    "lhs": "boros_or_soup",
                    "op": "in",
                    "rhs": ["Boros", "Soup"],
                },
                extensions=ext,
            )
            .select(
                pl.col(SKILL_COHORT).str.slice(2).alias("Skill Cohort"),
                "boros_or_soup",
                "game_wr",
                "num_games",
            )
            .rename(
                {
                    "boros_or_soup": "Boros or Soup",
                    "game_wr": "Game Win Rate",
                    "num_games": "Num Games",
                }
            )
        )
        .fmt_percent("Game Win Rate")
        .tab_header(title="Win Rates for Two Archetypes", subtitle="by Skill Cohort")
    )
