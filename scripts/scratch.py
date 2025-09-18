import polars as pl

from deq.main import ext, deq_bias_set_context, live_deq
from spells import summon, ColSpec, ColType
from spells.enums import View
from spells.draft_data import view_select
pl.Config.set_tbl_rows(1000)

set_code = "MKM"

df = view_select(
    "MKM", 
    View.DRAFT, 
    ["draft_id", "pick"], 
    filter_spec={'op': '>', 'lhs': 'pack_card_Evolutionary Leap', 'rhs': 0},
    extensions={'pack_card_Evolutionary Leap': ColSpec(
        col_type=ColType.GROUP_BY,
        views=[View.CARD],
    ),}
)




