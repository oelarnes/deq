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

