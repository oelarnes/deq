import polars as pl

from spells import summon, ColSpec, ColType
from spells.extension import context_cols

from deq import ext, deq_bias_set_context
from deq.p1_strategy import TOP_PLAYER

TEST_SET = "OTJ"


set_context = deq_bias_set_context(["OTJ"], metric_filter=TOP_PLAYER)

deq_context = summon(
    "OTJ",
    ["deq"],
    group_by=["expansion", "name"],
    filter_spec=TOP_PLAYER,
    extensions=ext,
    set_context=set_context,
)
deq_context.filter(~pl.col("deq").is_null()).sort("deq", descending=True)

# if P(w - w_bar) = Q, and I want P(w) = exp(s + s_0) / (1 + exp(s + s_0)) - mu = Q

# odds: Q + mu / (1 - Q + mu) = exp(s + s_0)
# ->    s + s_0 = log(q + mu) - log(1 - Q - mu) - s_0
# ->    mu / 1 - mu = exp(s_0)
# ->    s_0 = log(mu) - log(1 - mu)

mu_df = summon("OTJ", ["picked_match_wr"], group_by=[])
s0 = (
    mu_df.select(
        pl.col("picked_match_wr").log() - (1 - pl.col("picked_match_wr")).log()
    )
)[0]["picked_match_wr"][0]
mu = mu_df[0]["picked_match_wr"][0]

s_context = deq_context.select(
    "name",
    ((pl.col("deq") + mu).log() - (1 - pl.col("deq") - mu).log() - s0).alias("s"),
).sort("s", descending=True).filter(~pl.col("s").is_null())

# likelihood of win:        exp(sum(s) + s_0) / (1 + exp(sum(s) + s_0)))
# log-likelihood of win:    sum(s) + s_0 - log(1 + exp(sum(s) + s_0))
# log-likelihood of loss:   - log(1 + exp(sum(s) + s_0))
# so W / L ll:              W * (sum(s) + s_0) - (W +L) * log(1 + exp(sum(s) + s_0))

mle_ext = {
    "log_denom": ColSpec(
        col_type=ColType.GROUP_BY,
        expr=lambda set_context: (
            1 + (pl.col("pool_pick_s_sum") + set_context["s0"]).exp()
        ).log(),
    ),
    "ll": ColSpec(
        col_type=ColType.PICK_SUM,
        expr=lambda set_context: pl.col("event_match_wins_sum")
        * (pl.col("pool_pick_s_sum") + set_context["s0"])
        - (pl.col("event_matches_sum") * pl.col("log_denom")),
    ),
    **ext,
    **context_cols('s')
}

s_context_alt = s_context.select(pl.lit(0).alias('s'), 'name')
s_context_alt = summon('OTJ', ['gp_wr_excess']).select(-pl.col('gp_wr_excess').alias('s'), 'name')
ll = summon('OTJ', ['ll'], group_by=[], extensions=mle_ext, card_context=s_context_alt, set_context={'OTJ': {'s0': s0}})


