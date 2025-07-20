import polars as pl

from deq.deq import ext, deq_bias_set_context, live_deq
from spells import summon
pl.Config.set_tbl_rows(1000)

set_code = "TDM"
start_date = end_date = None
player_cohort = "top"

metrics = ["deq"]
set_codes = ["TDM"]
filter_spec = {'player_cohort': 'Top'}
deq_days = 12

as_of = None
gp_top_min_games = 70000
gp_all_min_games = 300000

