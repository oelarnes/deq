# ruff: noqa
import importlib
import os

import polars as pl
from spells.config import all_sets
import numpy as np

from spells import *
from spells.extension import stat_cols, context_cols

from deq import *

pl.Config.set_tbl_rows(1000)
pl.Config.set_tbl_cols(100)

