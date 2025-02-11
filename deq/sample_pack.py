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
from deq.p1_strategy import get_metric_context, LATE_TOP

METRIC_FORMAT_STR = {
    'deq': '+.2%',
    'gih_wr_b': '.2%',
}
@dataclass
class DraftCard:
    name: str
    image_url: str
    attributes: dict

    def metric_label(self, metric: str) -> str:
        return f"{METRIC_LABELS[metric]}: {self.attributes[metric]:{METRIC_FORMAT_STR[metric]}}"

    def to_text(
        self,
        is_pick: bool,
        metrics: Sequence[str] = (),
        star_metrics:  Set[str] = frozenset(),
    ):
        pick_text = "*" if is_pick else ""
        metric_text = ""
        for metric in metrics:
            metric_text += f"{self.metric_label(metric)}" + ("*" if metric in star_metrics else "")
        return f"{pick_text}{self.name}{metric_text}"

        
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
            metric_span += f"""<span class="metric-{i}">{metric}: {self.attributes[metric]}</span>
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

    def pick_index(self) -> int:
        return [c.name for c in self.pack].index(self.pick)

    def metric_max_index(self, metric) -> int:
        if metric is None:
            return -1
        return int(np.argmax([c.attributes[metric] for c in self.pack]))

    def record_str(self) -> str:
        return f"Record: {self.match_wins} - {self.match_losses}"

    def draft_link(self) -> str:
        return f"https://17lands.com/draft/{self.draft_id}"

    def pack_pick_str(self) -> str:
        return f"Pack {self.pack_num} Pick {self.pick_num}"

    def to_text(self, metrics: Sequence[str] = ()):
        card_lines = ''
        for i, c in enumerate(self.pack):
            star_metrics = set()
            for metric in metrics:
                if i == self.metric_max_index(metric):
                    star_metrics.add(metric)
            card_lines += c.to_text(
                i == self.pick_index(),
                metrics,
                star_metrics
            ) + "\n"

        pool_lines = '\n'.join([c.to_text(False) for c in self.pool])
        return f"""============
    {self.set_code} Sample Pack: {self.draft_link()}
{self.record_str()}, {self.pack_pick_str()}
============
| Pack     |
============
{card_lines}
============
| Pool     |
============
{pool_lines}
"""

    def to_html(self, metric_1: str | None = 'deq', metric_2: str | None = 'gih_wr'):
        # todo
        card_list = ""
        pool_cards = ""

        return f"""
<div class="draft-pack">
    <div class="draft-pack-info-top">
        {self.draft_link}
        {self.record_str()}
    </div>
    <div class="draft-pack-cards">
        {card_list}
    </div>
    <div class="draft-pool">
        {pool_cards}
    </div>
</div>"""


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
    attribute_columns: list[str] | None = None,
    card_context: pl.DataFrame | dict | None = None,
    seed: int | None = None,
) -> DraftPack: 
    if seed is None:
        global _seed
        _seed += 1
        seed = _seed
    else:
        _seed = seed

    df = get_picks_df(set_code, json.dumps(filter_spec))
    row = df.sample(seed=seed)

    row = row.to_dicts()[0]

    if attribute_columns is None:
        attribute_columns = [ColName.SET_CODE, ColName.COLOR, ColName.RARITY]

    if card_context is None:
        deq_context = get_metric_context([set_code], attribute_columns, LATE_TOP)
        card_context = summon(set_code, columns=[*attribute_columns, ColName.IMAGE_URL], group_by=['expansion', 'name'], extensions=ext)
    
    if isinstance(card_context, pl.DataFrame):
        card_context = {
            row[ColName.NAME]: row for row in card_context.to_dicts()
        }

    card_names = get_names(set_code)

    draft_cards = {
        name: DraftCard(
            name=name,
            image_url=card_context[name][ColName.IMAGE_URL],
            attributes={attr: card_context[name][attr] for attr in attribute_columns}
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

