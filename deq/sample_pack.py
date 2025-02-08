from dataclasses import dataclass
import datetime
import json
import functools

import polars as pl

from spells import summon, view_select, ColName, get_names
from spells.enums import View

from deq.deq import ext


@dataclass
class DraftCard:
    name: str
    image_url: str
    attributes: dict

    def to_html(
        self, 
        is_pick: bool, 
        metric_1: str | None = 'deq', 
        metric_2: str | None = 'gih_wr'
    ):
        metric_span = ""
        if metric_1 is not None:
            metric_span += """<span class="metric-1">{metric_1}: {self.attributes[metric_1]}</span>"""
        if metric_2 is not None:
            metric_span += """
            <span class="metric-2">{metric_2}: {self.attributes[metric_2]}</span>"""
        return f"""<span class="draft-card">
            <img src="{self.image_url}" alt="{self.name}" class="draft-pack-card{" pick" if is_pick else ""}">
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

    def record_str(self) -> str:
        return f"Record: {self.match_wins} - {self.match_losses}"

    def draft_link(self) -> str:
        return f"https://17lands.com/draft/{self.draft_id}"

    def to_html(self, metric_1: str | None = 'deq', metric_2: str | None = 'gih_wr'):
        card_list = ''.join(
            [c.to_html(i == self.pick_index(), metric_1=metric_1, metric_2=metric_2) for i, c in enumerate(self.pack)]
        )
        pool_cards = ''.join(
            [c.to_html(False, metric_1=None, metric_2=None) for c in self.pool]
        )

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
        card_context = summon(set_code, columns=[*attribute_columns, ColName.IMAGE_URL], extensions=ext)
    
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

