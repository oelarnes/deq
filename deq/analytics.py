from typing import Sequence, Any

from great_tables import GT
import polars as pl

from spells import summon, ColSpec
from deq import ext


def skill_adj_comparison(
    set_code: str,
    values: Sequence[Any],
    win_weight_field: str = "event_match_wins_sum",
    weight_field: str = "event_matches_sum",
    comparison_field: str = "name",
    skill_field: str = "skill_cohort",
    plot_axis_field: str = "pick_num",
    extensions: dict[str, ColSpec] = ext,
    weight_threshold=5000,
) -> pl.DataFrame:
    base_df = (
        summon(
            set_code,
            columns=[win_weight_field, weight_field],
            group_by=[skill_field, comparison_field, plot_axis_field],
            extensions=extensions,
        )
        .filter(pl.col(comparison_field).is_in(values))
        .with_columns(
            pl.col(weight_field)
            .sum()
            .over(skill_field, plot_axis_field)
            .alias("skill_adj_weight"),
        )
        .with_columns(
            (
                pl.col(win_weight_field)
                * pl.col("skill_adj_weight")
                / pl.col(weight_field)
            ).alias("skill_adj_win_weight"),
        )
    )
    return (
        (
            base_df.drop(skill_field)
            .group_by(comparison_field, plot_axis_field)
            .sum()
            .filter(pl.col(weight_field) > weight_threshold)
            .with_columns(
                (pl.col("skill_adj_win_weight") / pl.col("skill_adj_weight")).alias(
                    "skill_adj_wr"
                )
            )
        )
        .select(comparison_field, plot_axis_field, "skill_adj_wr")
        .sort(plot_axis_field, comparison_field)
        .pivot(on="name", index=plot_axis_field, values="skill_adj_wr")
    )


def metric_summary_display_table(
    card_df: pl.DataFrame,
    metric: str,
    name_map: dict[str, str],
    top_n: int = 10,
    comparison: str = "actual",
):
    return (
        GT(
            card_df.sort(f"{metric}_vs_{comparison}_taken", descending=True)
            .head(top_n)
            .select(
                [
                    "name",
                    f"{metric}_vs_{comparison}_taken",
                    f"{metric}_win_rate",
                    f"{metric}_actual",
                    f"{metric}_margin",
                    metric,
                ]
            )
            .rename(
                {
                    "name": "Name",
                    f"{metric}_vs_{comparison}_taken": "Additional Picks",
                    f"{metric}_win_rate": "Simulated Win Rate",
                    f"{metric}_actual": "Replaced Win Rate",
                    f"{metric}_margin": "Diff",
                    metric: name_map[metric],
                }
            )
        )
        .fmt_percent(
            columns=[
                "Simulated Win Rate",
                "Replaced Win Rate",
                "Diff",
                name_map[metric],
            ]
        )
        .tab_header(title=f"{name_map[metric]} High Picks vs {name_map[comparison]}")
    )
