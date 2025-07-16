import polars as pl

from deq.deq import ext, deq_bias_set_context, live_deq
from spells import summon
pl.Config.set_tbl_rows(1000)

set_code = "TDM"
start_date = end_date = None
player_cohort = "top"

