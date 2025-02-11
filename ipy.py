# ruff: noqa
import importlib
import os

import polars as pl
from spells.config import all_sets
import numpy as np

from spells import *
from spells.extension import stat_cols, context_cols

from deq import *
from deq.deq import BASIC_LANDS
from deq.p1_strategy import get_model_dfs, strategy_mapped_df, LATE_FORMAT, EARLY_FORMAT, P1P1, SETS, p1_skill_control_df
from deq.sample_pack import get_sample_pack

pl.Config.set_tbl_rows(1000)
pl.Config.set_tbl_cols(100)

DAY_ONE = {'format_day': 1}
DAY_THREE = {'format_day': 3}
DAYS_3_TO_7 = {'$and': [
    {'lhs': 'format_day', 'op': '>=', 'rhs': 3},
    {'lhs': 'format_day', 'op': '<=', 'rhs': 7},
]}
SKILL_56 = {'skill_cohort': 56}

SAMPLE_FILTER = {'$and': [
    P1P1,
    DAYS_3_TO_7,
    SKILL_56,
]}

# p = get_sample_pack('FDN', SAMPLE_FILTER, ['deq', 'gih_wr'])

x = summon("OTJ", ["gp_wr", "gp_wr_mean_over_rarity", "gp_wr_b"], group_by= ["expansion", "name"], extensions=ext)
