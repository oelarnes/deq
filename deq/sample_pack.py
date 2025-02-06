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

    def to_html(self):
        pick_index = [p.name for p in self.pack].index(self.pick)
        pick_class = '"draft-pack-pick"'
        card_class = '"draft-pack-card"'
        card_list = '\n        '.join([f"<img src=\"{c.image_url}\" class={pick_class if i == pick_index else card_class}>" for i, c in enumerate(self.pack)])
        return f"""
<div class="draft-pack">
    <div class="draft-pack-info-top">
        <a href="https://17lands.com/draft/{self.draft_id}" class="draft-pack-17l-link">{self.draft_id}</a>
        Record: {self.match_wins} - {self.match_losses}
    </div>
    <div class="draft-pack-cards">
        {card_list}
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

