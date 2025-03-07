import os

import polars as pl
import numpy as np

from deq.p1_strategy import P1P1
from spells import summon, view_select 
from spells.enums import View
from spells.extension import context_cols

deq_ratings = pl.read_csv(os.path.expanduser("~/dft_deq.csv"))

view = view_select("DFT", View.DRAFT, ["draft_id", "seen_greatest_deq_name", "seen_deq_pack_sum"], 
        card_context=deq_ratings, extensions=context_cols("deq"))

filtered = view.filter(pl.col("seen_deq_pack_sum") > 0.25).collect(streaming=True)

filtered.sort("seen_deq_pack_sum", descending=True)[0]['draft_id'][0]




