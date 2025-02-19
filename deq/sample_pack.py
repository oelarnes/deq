from typing import Sequence
from collections.abc import Set
from dataclasses import dataclass
import datetime
import json
import functools

import numpy as np
import polars as pl

from spells import summon, view_select, ColName, get_names
from spells.enums import View

from deq.deq import ext
from deq.plot import METRIC_LABELS
from deq.p1_strategy import get_metric_context, TOP_PLAYER

METRIC_CELL_WIDTH = 16
NAME_CELL_WIDTH = 32

METRIC_FORMAT_STR = {
    'deq': '+.2%',
    'gih_wr_17l': '.2%',
}
@dataclass
class DraftCard:
    name: str
    image_url: str
    attributes: dict

    def metric_label(self, metric: str) -> str:
        label = f"{METRIC_LABELS[metric]}: "
        value = self.attributes[metric]
        metric_text = "NA" if value is None else f"{value:{METRIC_FORMAT_STR[metric]}}"
        metric_text_padded = metric_text + " " * (METRIC_CELL_WIDTH - len(metric_text) - len(label))
        return label + metric_text_padded

    def to_text(
        self,
        is_pick: bool,
        metrics: Sequence[str] = ('gih_wr_17l', 'deq'),
        star_metrics:  Set[str] = frozenset(),
    ):
        pick_text = "*" if is_pick else " "
        metric_text = "|"
        for metric in metrics:
            metric_text += f"{('*' if metric in star_metrics else ' ')}{self.metric_label(metric)}" + "|"
        return f"{pick_text}{self.name + ' ' * (NAME_CELL_WIDTH - len(self.name))}{metric_text}"

        
    def to_html(
        self, 
        is_pick: bool, 
        metrics: Sequence[str] = (),
        star_metrics:  Set[str] = frozenset(),
    ):
        classes = ["draft_pack_card"]
        if is_pick:
            classes.append("pick")

        metric_span = ""
        for i, metric in enumerate(metrics):
            metric_span += f"""<span class="metric-{i}">{self.metric_label(metric)}</span>
            """
            if metric in star_metrics:
                classes.append(f"m{i}_star")
        alt = self.to_text(is_pick, metrics, star_metrics)
        return f"""<span class="draft-card">
            <img src="{self.image_url}" alt="{alt}" class="{" ".join(classes)}">
            {metric_span}
        </span>"""


@dataclass
class DraftPack:
    set_code: str
    event_type: str
    draft_id: str
    pick_num: int
    pack_num: int
    draft_date: datetime.date
    user_n_games_bucket: int
    user_game_win_rate_bucket: float
    skill_cohort: int
    match_wins: int
    match_losses: int
    pick: str
    pack: list[DraftCard]
    pool: list[DraftCard]

    def get_pack_list(self, order_by: str='deq', desc: bool=True):
        return sorted(self.pack, key=lambda c: c.attributes[order_by] if c.attributes[order_by] is not None else -100, reverse=desc)

    def metric_max_value(self, metric) -> int:
        if metric is None:
            return -1
        return max([c.attributes[metric] or -100 for c in self.pack])

    def record_str(self) -> str:
        return f"Record: {self.match_wins} - {self.match_losses}"

    def draft_link(self) -> str:
        return f"https://17lands.com/draft/{self.draft_id}"

    def pack_pick_str(self) -> str:
        return f"Pack {self.pack_num} Pick {self.pick_num}"

    def to_text(self, metrics: Sequence[str] = ('gih_wr_17l', 'deq')):
        line_length = NAME_CELL_WIDTH + 2 + len(metrics) * (METRIC_CELL_WIDTH + 2)
        card_lines = ''
        marked_pick = False
        for c in self.get_pack_list():
            if c.name == self.pick and not marked_pick:
                is_pick = True
                marked_pick = True
            else:
                is_pick = False
            star_metrics = set()
            for metric in metrics:
                if c.attributes[metric] == self.metric_max_value(metric):
                    star_metrics.add(metric)
            card_lines += c.to_text(
                is_pick,
                metrics,
                star_metrics
            ) + "\n"

        pool_lines = '\n'.join([c.to_text(False) for c in self.pool])
        return "=" * line_length + f"""
{self.set_code} Sample Pack 
{self.draft_link()}
{self.draft_date.isoformat()} - {self.record_str()} - {self.pack_pick_str()} - Skill Cohort: {int(self.skill_cohort)}%
""" + "=" * line_length + """
Pack
""" + "=" * line_length + f"""
{card_lines}
""" + "=" * line_length + """
Pool     
""" + ("=" * line_length + f"""
{pool_lines}
""") if pool_lines else ""

    
    def log(self, metrics: Sequence[str] = ('gih_wr_17l', 'deq')):
        print(self.to_text(metrics))

    def to_html(self, metrics: Sequence[str] = ('gih_wr_17l', 'deq'), as_page=False):
        card_elements = ""
        marked_pick = False
        for c in self.get_pack_list():
            if c.name == self.pick and not marked_pick:
                is_pick = True
                marked_pick = True
            else:
                is_pick = False
            star_metrics = set()
            for metric in metrics:
                if c.attributes[metric] == self.metric_max_value(metric):
                    star_metrics.add(metric)
            card_elements += c.to_html(
                is_pick,
                metrics,
                star_metrics
            ) + "\n"

        pool_elements = '\n'.join([c.to_html(False) for c in self.pool])

        frame = """<html lang="en-US">
    <head>
        <meta charset="utf-8">
        <title>Sample Pack</title>
    </head>
    <body>
    {content}
    </body>
</html>
""" if as_page else "{content}"

        return frame.format(content=f"""
<div class="draft-pack">
    <a href="{self.draft_link()}">17Lands.com</a>
    <div class="draft-pack-info-top">
{self.draft_date.isoformat()} - {self.record_str()} - {self.pack_pick_str()} - Skill Cohort: {int(self.skill_cohort)}%
    </div>
    <div class="draft-pack-cards">
        {card_elements}
    </div>
    <div class="draft-pool">
        {pool_elements}
    </div>
</div>""")


_seed = 0
def reset_seed():
    global _seed
    _seed = 0
    
@functools.lru_cache(maxsize=None)
def get_picks_df(
    set_code: str,
    filter_json: str,
) -> pl.DataFrame:
    filter_spec = json.loads(filter_json)

    return view_select(
        set_code, 
        view = View.DRAFT,
        columns = [
            ColName.EXPANSION,
            ColName.EVENT_TYPE,
            ColName.DRAFT_ID,
            ColName.PICK,
            ColName.DRAFT_DATE,
            ColName.USER_N_GAMES_BUCKET,
            ColName.USER_GAME_WIN_RATE_BUCKET,
            'skill_cohort',
            ColName.EVENT_MATCH_WINS,
            ColName.EVENT_MATCH_LOSSES,
            ColName.PACK_CARD,
            ColName.POOL,
            ColName.PICK_NUM,
            ColName.PACK_NUM,
        ],
        filter_spec=filter_spec, 
        extensions=ext
    ).collect()

def get_sample_pack(
    set_code: str,
    filter_spec: dict | None = None,
    metrics: Sequence[str] = (
        "gih_wr_17l",
        "deq"
    ),
    metric_filter: dict | None = None,
    deq_days: int | None = None,
    seed: int | None = None,
) -> DraftPack: 
    global _seed

    if seed is None:
        _seed += 1
        seed = _seed
    else:
        _seed = seed

    df = get_picks_df(set_code, json.dumps(filter_spec))
    row = df.sample(seed=seed)

    row = row.to_dicts()[0]

    card_attributes = summon([set_code], columns=[ColName.IMAGE_URL, ColName.COLOR, ColName.RARITY, ColName.MANA_VALUE, ColName.CARD_TYPE])
    metric_filter = TOP_PLAYER if metric_filter is None else metric_filter

    card_context = get_metric_context([set_code], list(metrics), metric_filter, deq_days).join(card_attributes, on=['name'])
    
    if isinstance(card_context, pl.DataFrame):
        card_context = {
            row[ColName.NAME]: row for row in card_context.to_dicts()
        }

    card_names = get_names(set_code)

    draft_cards = {
        name: DraftCard(
            name=name,
            image_url=card_context[name][ColName.IMAGE_URL],
            attributes={attr: card_context[name][attr] for attr in metrics}
        ) for name in card_names
    }

    pack = []
    pool = []
    for i in range(1,5):
        for name in card_names:
            if row[f"pack_card_{name}"] >= i:
                pack.append(draft_cards[name])
            if row[f"pool_{name}"]>= i:
                pool.append(draft_cards[name])


    return DraftPack(
        set_code = row['expansion'],
        event_type = row['event_type'],
        draft_id = row['draft_id'],
        draft_date = row['draft_date'],
        user_n_games_bucket = row['user_n_games_bucket'],
        user_game_win_rate_bucket = row['user_game_win_rate_bucket'],
        skill_cohort = row['skill_cohort'],
        pick_num = row['pick_num'],
        pack_num = row['pack_num'],
        match_wins = row[ColName.EVENT_MATCH_WINS],
        match_losses = row[ColName.EVENT_MATCH_LOSSES],
        pick = row['pick'],
        pack = pack,
        pool = pool
    )

