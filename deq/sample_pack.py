from dataclasses import dataclass
import functools

import polars as pl

from spells import summon, view_select, ColName 
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
    seed: int
    draft_id: str
    filter_spec: dict | None
    draft_date: str
    user_n_games_bucket: int
    user_game_win_rate_bucket: float
    skill_cohort: int
    match_wins: int
    match_losses: int
    pick: DraftCard
    pack: list[DraftCard]
    pool: list[DraftCard]

_seed = 0
def reset_seed():
    global _seed
    _seed = 0
    
@functools.lru_cache(maxsize=None)
def get_picks_df(
    set_code: str,
    skill_cohort: int | None = None, # e.g. 56
    pick_nums: int | tuple[int, ...] | None = None,
    pack_nums: int | tuple[int, ...] | None = None,
    format_day_min: int = 0,
    format_day_max: int = 100,
) -> pl.DataFrame:
    filter_list = [
        {'lhs': 'format_day', 'op': '>=', 'rhs': format_day_min},
        {'lhs': 'format_day', 'op': '<=', 'rhs': format_day_max},
    ]
    if skill_cohort is not None:
        filter_list.append({'skill_cohort': skill_cohort})
    if isinstance(pick_nums, int):
        filter_list.append({'pick_num': pick_nums})
    elif isinstance(pick_nums, tuple):
        filter_list.append({'lhs': ColName.PICK_NUM, 'op': 'in', 'rhs': pick_nums})
    if isinstance(pack_nums, int):
        filter_list.append({'pack_num': pack_nums})
    elif isinstance(pack_nums, tuple):
        filter_list.append({'lhs': ColName.PICK_NUM, 'op': 'in', 'rhs': pack_nums})
    filter_spec = {'$and': filter_list}

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
        ],
        filter_spec=filter_spec, 
        extensions=ext
    ).collect()

def get_sample_pack(
    set_code: str,
    skill_cohort: str | None = None,
    pick_nums: int | tuple[int, ...] | None = None,
    pack_nums: int | tuple[int, ...] | None = None,
    format_day_min: int = 0,
    format_day_max: int = 100,
    attribute_columns: list[str] | None = None,
    card_context: pl.DataFrame | dict | None = None,
    seed: int | None = None,
) -> DraftPack: 
    if seed is None:
        global _seed
        _seed += 1
        seed = _seed
    df = get_picks_df(set_code, skill_cohort, pick_nums, pack_nums, format_day_min, format_day_max)
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

    draft_cards = {
        name: DraftCard(
            name=name,
            image_url=card_context[ColName.NAME][ColName.IMAGE_URL],
            attributes={attr: card_context[ColName.NAME][attr] for attr in attribute_columns}
        ) for name in card_context.keys()
    }

    pack_cards = 


    return DraftPack(
        set_code = row['expansion'],
        seed = seed,
        draft_id = row['draft_id'],
        filter_spec = filter_spec,
        user_n_games_bucket = row['user_n_games_bucket'],
        user_game_win_rate_bucket = row['user_game_win_rate_bucket'],
        skill_cohort = row['skill_cohort'],
        match_wins = row[ColName.EVENT_MATCH_WINS],
        match_losses = row[ColName.EVENT_MATCH_LOSSES],
        pack = pack,
        pool = pool
    )





