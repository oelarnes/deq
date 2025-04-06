import polars as pl

from deq import mle
from deq.p1_strategy import TOP_PLAYER, P1P1

from spells.cache import set_test_env, set_prod_env

PAGE_SIZE = 40
pl.Config.set_tbl_rows(PAGE_SIZE)

set_prod_env()
set_code = "DFT"
pack_num = 1
threshold_pct_gp = 0.1
tol = 1e-8

df = summon(set_code, ["picked_match_wr", "num_taken"], filter_spec=P1P1)
pages = page(df.filter(pl.col('num_taken') > 500).sort('picked_match_wr', descending=True))
next(pages)

out2 = mle.draft_equity(
    set_code,
    2,
)

def page(df: pl.DataFrame):
    i = 0
    page_size = PAGE_SIZE
    while (i + 1) * page_size < df.shape[0]:
        print(df[i * page_size : (i + 1) * page_size])
        yield
        i += 1
    print(df[i * page_size :])


card_attrs = summon(
    set_code,
    ["rarity", "color", "ata", "gp_wr_excess_over_colors"],
    group_by=["name", "expansion"],
    extensions=ext,
)

q_df = (
    out1.df.rename({"q": "q1"})
    .join(out2.df.rename({"q": "q2"}), on="name")
    .join(out3.df.rename({"q": "q3"}), on="name")
    .with_columns(
        (pl.col("q3") - pl.col("q1")).alias("diff13"),
        (pl.col("q3") - pl.col("q2")).alias("diff23"),
        (pl.col("q2") - pl.col("q1")).alias("diff12"),
    )
    .join(card_attrs, on="name")
    .sort("q1", descending=False)
)

pages = page(
    q_df.select(['name', "ata", "gp_wr_excess_over_colors", "q2"]).sort(
        "q2", descending=True
    )
)
next(pages)

pages = page(card_attrs)
next(pages)

out3.pick_equity_df
