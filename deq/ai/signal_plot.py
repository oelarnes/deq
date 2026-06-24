"""Signal plot analysis: as-picked win rate vs pick number.

The basic plot is pick number (when a card was taken) vs the eventual match
win rate of the drafter who took it. Two effects both raise the win rate of
later picks:

  1. Opportunity cost — taking any card at pick p means p-1 earlier (better)
     picks were already banked, so the rest of the deck is stronger. Generic
     and card-independent; this is what DEq's pick_equity curve models.
  2. Signal — being passed a *particular* card late and taking it correlates
     with an open lane, hence more synergistic cards flowing, hence a stronger
     deck. Card-specific: strongest for archetype-committal cards (gold/two-
     color), weak or absent for neutral cards (colorless, flexible).

DEq explicitly models (1). Effect (2), if real, should *also* be discounted at
P1P1 (an early drafter can't yet know the lane is open), so telling them apart
matters for valuation.

Covariates controlled
---------------------
* Player skill: cells are keyed by skill_cohort. Strong players win more
  regardless of pick; if they also prioritize a card differently, that bends
  the curve. We never compare across cohorts.
* The one-card-per-position invariant: every draft takes exactly one card at
  each position, so pooling all cards' outcomes at a fixed position just
  re-averages the same drafts — the pooled cohort-relative curve is identically
  flat and carries no signal. We instead normalize *within* (expansion, name,
  cohort): subtract each card's own mean asWR and average the within-card
  deviations, measuring how a card's drafter outcome shifts with *when* it was
  taken (the average sensitivity of cards to pick position).
* Play rate / the wheel: after the wheel (pick 9 in an 8-player pod) a strong
  card falling signals the table can't use it, so it lands with an off-color
  drafter whose results are average — depressing the late curve. The equity
  fit uses pre-wheel picks only; the full curve is reported with the wheel
  marked.

Model
-----
DEq's pick_equity curve (with mid_index=1) is PE(a) = pe_mid * (1-(a-1)/13)^2,
peaking at pe_mid for pick 1 and decaying to 0 at pick `zero_index`. The
as-picked win rate therefore *rises* from pick 1 to the tail by pe_mid, with
shape h(p) = 1 - (1-(p-1)/13)^2. Card-centered asWR is regressed on h(p);
the slope coefficient is the estimated pe_mid (the total rise = the pick
equity, the 2.25% vs 3% quantity).

Differentiating test (gold vs colorless slope)
----------------------------------------------
* H0 (pure opportunity cost): every card shares the same asWR-vs-pick slope,
  so pe_mid estimated on gold cards equals pe_mid on colorless cards.
* H1 (signal present): gold (committal) cards have a steeper slope than
  colorless (neutral) cards, because only committal cards carry lane signal.

Run as a script:  pdm run python -m deq.ai.signal_plot SOS
or import:        deq.ai.signal_plot.run(["SOS", "DFT"])
"""

import argparse

import numpy as np
import polars as pl

from spells import summon, view_select
from spells.enums import View
from deq.main import ext

DEFAULT_WHEEL = 9  # 8-player pod: the opened pack returns on pick 9
MID_INDEX = 1  # DEq PICK_EQUITY_MID_INDEX
ZERO_INDEX = 14  # DEq ZERO_EQUITY_INDEX
MIN_MATCHES = 50  # per-cell match floor to limit binomial noise


def build_cells(set_codes: list[str], min_matches: int = MIN_MATCHES) -> pl.DataFrame:
    """One row per (expansion, name, color_group, skill_cohort, pick_num).

    Aggregates the picked card's draft-level match record. asWR is the match
    win rate of drafters who took `name` at `pick_num` within `skill_cohort`.
    """
    frames = []
    for set_code in set_codes:
        cells = (
            view_select(
                set_code,
                View.DRAFT,
                columns=[
                    "pick",
                    "pick_num",
                    "skill_cohort",
                    "event_match_wins",
                    "event_matches",
                ],
                extensions=ext,
            )
            .filter(pl.col("skill_cohort").is_not_null() & pl.col("pick").is_not_null())
            .group_by("pick", "skill_cohort", "pick_num")
            .agg(
                pl.col("event_match_wins").sum().alias("wins"),
                pl.col("event_matches").sum().alias("matches"),
            )
            .filter(pl.col("matches") >= min_matches)
            .with_columns(
                pl.lit(set_code).alias("expansion"),
                (pl.col("wins") / pl.col("matches")).alias("aswr"),
            )
            .rename({"pick": "name"})
            .collect(streaming=True)
        )

        attrs = summon(
            set_code, ["color_group", "rarity"], group_by=["name"], extensions=ext
        )
        frames.append(cells.join(attrs, on="name", how="left"))

    return pl.concat(frames, how="vertical")


def sensitivity_df(cells: pl.DataFrame) -> pl.DataFrame:
    """Within-card incremental sensitivity: expected asWR rise from pick p to p+1.

    For each (expansion, name, cohort) and each adjacent position pair present
    in both, take the paired difference asWR(p+1) - asWR(p) -- the same card at
    two positions, so no card-composition change. Average across cards with the
    inverse-variance weight w = n_p * n_p1 / (n_p + n_p1), the half-harmonic-mean
    of the two adjacent match counts (n = matches, since matches are single
    games the binomial variance ~0.25 is a shared constant and drops out).

    The weight is dominated by the SMALLER of the two counts, not the starting
    one: at early indices (below most cards' ATA) observations grow with
    position, so n_p < n_p1 and w ~ n_p (the start); past ATA it flips to n_p1.
    n_start / n_end are reported so the resolution is visible.
    """
    cur = cells.select(
        "expansion", "name", "skill_cohort", "pick_num",
        pl.col("aswr"), pl.col("matches").alias("n_start"),
    )
    nxt = cells.select(
        "expansion", "name", "skill_cohort",
        (pl.col("pick_num") - 1).alias("pick_num"),
        pl.col("aswr").alias("aswr_next"), pl.col("matches").alias("n_end"),
    )
    pair = cur.join(
        nxt, on=["expansion", "name", "skill_cohort", "pick_num"], how="inner"
    ).with_columns(
        (pl.col("aswr_next") - pl.col("aswr")).alias("incr"),
        (pl.col("n_start") * pl.col("n_end") / (pl.col("n_start") + pl.col("n_end"))).alias("w"),
    )
    return (
        pair.group_by("pick_num")
        .agg(
            ((pl.col("incr") * pl.col("w")).sum() / pl.col("w").sum()).alias("sensitivity"),
            pl.col("w").sum().alias("weight"),
            pl.col("n_start").sum().alias("n_start"),
            pl.col("n_end").sum().alias("n_end"),
            pl.len().alias("n_cards"),
        )
        .sort("pick_num")
        .rename({"pick_num": "from_pick"})
    )


def _basis_h(pick_num: np.ndarray, mid: int = MID_INDEX, zero: int = ZERO_INDEX) -> np.ndarray:
    """Rising pick-equity shape h(p) = 1 - (1-(p-mid)/(zero-mid))^2, clipped."""
    t = np.clip((pick_num - mid) / (zero - mid), 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 2


def _card_center(cells: pl.DataFrame, wheel: int) -> pl.DataFrame:
    """Pre-wheel cells with asWR centered within (expansion, name, cohort).

    Removes each card's match-weighted mean win rate so only the within-card
    pick-position slope remains (kills the bomb-at-pick-1 confound).
    """
    pre = cells.filter(pl.col("pick_num") < wheel)
    card_mean = (pl.col("wins").sum() / pl.col("matches").sum()).over(
        ["expansion", "name", "skill_cohort"]
    )
    return pre.with_columns((pl.col("aswr") - card_mean).alias("aswr_dev"))


def _wls(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Weighted least squares. Returns (coefs, coef_standard_errors)."""
    rw = np.sqrt(w)
    xw, yw = x * rw[:, None], y * rw
    beta, *_ = np.linalg.lstsq(xw, yw, rcond=None)
    resid = yw - xw @ beta
    dof = len(y) - x.shape[1]
    sigma2 = (resid @ resid) / dof
    cov = sigma2 * np.linalg.inv(xw.T @ xw)
    return beta, np.sqrt(np.diag(cov))


def _fit_pe_mid(df: pl.DataFrame) -> tuple[float, float, int]:
    """Fit card-centered asWR ~ intercept + pe_mid * h(p). Returns (pe_mid, se, n)."""
    p = df["pick_num"].to_numpy().astype(float)
    x = np.column_stack([np.ones_like(p), _basis_h(p)])
    y = df["aswr_dev"].to_numpy()
    w = df["matches"].to_numpy().astype(float)
    beta, se = _wls(x, y, w)
    return float(beta[1]), float(se[1]), len(y)


def estimate_pick_equity(centered: pl.DataFrame) -> dict:
    """Overall pe_mid and per-cohort breakdown."""
    pe, se, n = _fit_pe_mid(centered)
    by_cohort = {
        cohort: _fit_pe_mid(grp)
        for (cohort,), grp in centered.group_by("skill_cohort", maintain_order=True)
    }
    return {"overall": (pe, se, n), "by_cohort": dict(sorted(by_cohort.items()))}


def signal_test(centered: pl.DataFrame, groups=("Gold", "Colorless")) -> dict:
    """Fit pe_mid per color_group and z-test the gold-vs-neutral difference."""
    fits = {
        g: _fit_pe_mid(centered.filter(pl.col("color_group") == g)) for g in groups
    }
    (pe_a, se_a, _), (pe_b, se_b, _) = fits[groups[0]], fits[groups[1]]
    diff = pe_a - pe_b
    diff_se = np.hypot(se_a, se_b)
    return {"fits": fits, "diff": diff, "diff_se": diff_se, "z": diff / diff_se}


def raw_curve(cells: pl.DataFrame) -> pl.DataFrame:
    """The signal plot: within-card asWR deviation by pick number, all picks.

    Card-centered (within expansion/name/cohort). The uncentered pooled curve
    is flat by invariant (one card per position => every position re-averages
    the same drafts), so we measure each card's own deviation by position and
    average those. Spans all picks so the post-wheel rolloff shows.
    """
    card_mean = (pl.col("wins").sum() / pl.col("matches").sum()).over(
        ["expansion", "name", "skill_cohort"]
    )
    return (
        cells.with_columns((pl.col("aswr") - card_mean).alias("aswr_dev"))
        .group_by("pick_num")
        .agg(
            (
                (pl.col("aswr_dev") * pl.col("matches")).sum() / pl.col("matches").sum()
            ).alias("aswr_dev"),
            pl.col("matches").sum().alias("matches"),
        )
        .sort("pick_num")
    )


def run(set_codes, wheel: int = DEFAULT_WHEEL, min_matches: int = MIN_MATCHES):
    if isinstance(set_codes, str):
        set_codes = [set_codes]

    print(f"Building by-pick cells for {set_codes} (min {min_matches} matches/cell)...")
    cells = build_cells(set_codes, min_matches)
    print(f"  {len(cells)} cells, {cells['matches'].sum():,} total matches")

    print("\n=== Signal plot: within-card asWR deviation by pick number ===")
    print("(rises with pick number; wheel marked — late picks contaminated by play rate)")
    curve = raw_curve(cells)
    lo = curve["aswr_dev"].min()
    for row in curve.iter_rows(named=True):
        mark = "  <- wheel" if row["pick_num"] == wheel else ""
        bar = "#" * max(0, round((row["aswr_dev"] - lo) * 1000))
        print(f"  pick {row['pick_num']:>2}  {row['aswr_dev']*100:+5.2f}pp  {bar}{mark}")

    print("\n=== Pick-by-pick sensitivity: within-card asWR rise p -> p+1 ===")
    print("(weight = half-harmonic-mean of adjacent match counts; n_start/n_end shown)")
    sens = sensitivity_df(cells)
    for row in sens.iter_rows(named=True):
        mark = "  <- wheel" if row["from_pick"] + 1 == wheel else ""
        print(
            f"  {row['from_pick']:>2}->{row['from_pick']+1:<2} "
            f"{row['sensitivity']*100:+5.2f}pp   "
            f"w={row['weight']:>10,.0f}  "
            f"n_start={row['n_start']:>9,}  n_end={row['n_end']:>9,}{mark}"
        )
    print(f"  cumulative rise pick 1 -> 14: {sens['sensitivity'].sum()*100:+.2f}pp")

    centered = _card_center(cells, wheel)

    print(f"\n=== Pick equity estimate (card-centered, pre-wheel picks 1-{wheel-1}) ===")
    est = estimate_pick_equity(centered)
    pe, se, n = est["overall"]
    print(f"  overall pe_mid = {pe*100:.3f}pp  (SE {se*100:.3f}, n={n} cells)")
    print(f"  [DEq production = 3.00pp; opportunity-cost analyses ~ 2.25pp]")
    print("  by cohort:")
    for cohort, (cpe, cse, cn) in est["by_cohort"].items():
        print(f"    {cohort:<16} {cpe*100:+6.3f}pp  (SE {cse*100:.3f}, n={cn})")

    print("\n=== Signal test: gold (committal) vs colorless (neutral) slope ===")
    sig = signal_test(centered)
    for g, (gpe, gse, gn) in sig["fits"].items():
        print(f"  {g:<10} pe_mid = {gpe*100:+6.3f}pp  (SE {gse*100:.3f}, n={gn})")
    print(f"  difference (gold - colorless) = {sig['diff']*100:+.3f}pp  z = {sig['z']:.2f}")
    if sig["z"] > 2:
        print("  => gold slope significantly steeper: SIGNAL effect present (reject H0)")
    elif sig["z"] < -2:
        print("  => gold slope significantly shallower: unexpected, inspect")
    else:
        print("  => no significant difference: consistent with pure opportunity cost (H0)")

    return {"cells": cells, "curve": curve, "estimate": est, "signal": sig}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set_codes", nargs="+", help="one or more set codes, e.g. SOS DFT")
    parser.add_argument("--wheel", type=int, default=DEFAULT_WHEEL)
    parser.add_argument("--min-matches", type=int, default=MIN_MATCHES)
    args = parser.parse_args()
    run(args.set_codes, args.wheel, args.min_matches)


if __name__ == "__main__":
    main()
