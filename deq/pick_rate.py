import polars as pl
from spells import ColSpec, ColName, summon, ColType

from deq.main import ext

ext = {
    **ext,
    'pick_odds': ColSpec(
        col_type=ColType.AGG,
        expr=pl.col("normalized_pick_rate").exp()
    )
}

def prl_df(set_code: str, filter_spec: dict[str, Any] | None = None) -> pl.DataFrame:
    df = summon(
        set_code,
        ["npr", "pick_odds", "pick_rate_logit", "rarity"], 
    )
    
