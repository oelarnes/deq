import datetime as dt
import os
from pathlib import Path

import polars as pl

from spells import ColName

START_DATE_MAP = {
    "DFT": dt.date(2025, 2, 11),
}

col_def_map = {
    ColName.NUM_SEEN: pl.col('seen_count'),
    ColName.ALSA: pl.col('avg_seen'),
    ColName.NUM_TAKEN: pl.col('pick_count'),
    ColName.ATA: pl.col('avg_pick'),
    ColName.DECK: pl.col('game_count'),
    ColName.PCT_GP: pl.col('play_rate'),
    ColName.GP_WR: pl.col('win_rate'),
    ColName.NUM_GIH: pl.col('ever_drawn_game_count'),
    ColName.GIH_WR: pl.col('ever_drawn_win_rate'),
    ColName.NAME: pl.col('name'),
}

def rating_file_path(
    set_code: str,
    format: str,
    player_cohort: str,
    deck_color: str,
    start_date: dt.date,
    end_date: dt.date,
):
    rating_dir_path = os.environ["RATINGS_FOLDER"]
    return (
        Path(rating_dir_path)
        / "card_ratings"
        / set_code
        / f"{format}_{player_cohort}_{deck_color}_"
        f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    )


def ratings_df(
    set_code: str,
    format: str = "PremierDraft",
    player_cohort: str = "all",
    deck_color: str = "any",
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
):
    if start_date is None:
        start_date = START_DATE_MAP[set_code]
    if end_date is None:
        end_date = dt.date.today() - dt.timedelta(days=1)
    df = pl.read_json(
        rating_file_path(
            set_code, format, player_cohort, deck_color, start_date, end_date
        )
    )
    return df.select([pl.lit(set_code).alias(ColName.EXPANSION), *[
        val.alias(key) for key, val in col_def_map.items()
    ]])
