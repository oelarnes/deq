import polars as pl

from deq.deq import ext, deq_bias_set_context
from spells import summon
pl.Config.set_tbl_rows(1000)

set_context = deq_bias_set_context(["TDM"], {"expansion": "TDM"})
summon(
    "TDM",
    ["gp_wr_bias_in", "gp_wr_bias_new", 'deq_base', 'deq', 'deq_new'],
    group_by=['name', 'expansion'],
    extensions=ext,
    set_context=set_context,
).sort('deq_new', descending=True)
