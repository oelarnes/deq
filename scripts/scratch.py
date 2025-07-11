from deq.deq import ext, deq_bias_set_context
from spells import summon


set_context = deq_bias_set_context(["TDM"], {"expansion": "TDM"})
summon(
    "TDM",
    ["num_gp", "gp_wr_bias_in", "gp_wr_bias_new"],
    extensions=ext,
    set_context=set_context,
)
