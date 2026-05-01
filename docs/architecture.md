# DEq architecture reference

Working notes on the DEq pipeline, the P1 strategy analysis, and the web interface. Companion to the more polished explanations in `deq-math.ipynb` and `deq-docs.ipynb` — this doc is for someone modifying the code, not a draft player reading the site.

All file references are to `deq/` at the time of writing (2026-04-30). Line numbers drift; treat them as anchors, not guarantees.

---

## 1. Core DEq model

### What DEq computes

DEq (Estimated Draft Equity) is a per-card, per-format scalar that estimates the card's marginal contribution to draft win rate. Higher = better. It is a hybrid of:

1. **Pick equity** — value derived from the card being taken early (low ATA → high equity), capped by a piecewise quadratic.
2. **Game-level win-rate excess** — how much the card's `gp_wr` beats the format-mean win rate, scaled by `pct_gp`.
3. **Color-bias adjustment** — corrects for the fact that decks of certain colors win more on average; cards seen mostly in those decks should not get full credit for their inflated `gp_wr`.
4. **Meta-decay regression** — shrinks the bias adjustment by an amount that depends on how mature the format is and how far in the future we're projecting.

All four pieces come out of `deq_col_specs()` in `deq/main.py:113-245`.

### Data inputs (from spells / 17lands)

Required columns sourced through `summon()`:

- `ata_17l` — average take around (1 = early, 14 = late).
- `gp_wr_17l` — game-played win rate (filtered to rows with ≥ `SAMPLE_THRESHOLD = 500` games; see `deq/main.py:32`).
- `gp_wr_mean` — format baseline win rate.
- `pct_gp` — percent of games the card was in maindeck.
- `num_taken`, `num_seen` — pick counts.
- `deck_{color}` (per `color_sets` in `deq/main.py:45-71`) — deck color compositions used by the bias term.
- `MAIN_COLORS`, `DECK` — per-deck rollups from `spells.card_data_files.deck_color_df`.
- Skill-cohort columns: `USER_N_GAMES_BUCKET`, `USER_GAME_WIN_RATE_BUCKET` (the `UNG`/`UGWR` aliases at lines 36-37).

Required `set_context` keys (computed in `deq_bias_set_context()`, `deq/main.py:458-516`):

- `observed_days`, `projection_days` — feed `meta_decay_factor()`.
- `game_wr_excess_{colors}` — per color combination, the win-rate excess over baseline; one entry for each member of `color_sets`, plus `game_wr_excess_other`.

### Pipeline

```
config[set_code]            (DEqConfig: start_date, end_date, is_pick_two, cube)
        │
        ▼
deq_bias_set_context(set)   → set_context dict (color excesses + day counts)
        │
        ▼
deq_col_specs(...)          → dict of ColSpec entries for the metric family
        │
        ▼
live_deq(set, ...)          → blends the "all" cohort and the "top" cohort
        │                      using a piecewise weighting (see live_deq:519-767)
        │
        ▼
daily_deq(set, ...)         → caches incremental snapshots, manages dates, returns
                              the DataFrame consumed by site.py
```

### Math, step by step

Constants live at `deq/main.py:20-30`:

| Symbol | Default | Meaning |
| --- | --- | --- |
| `PICK_EQUITY_INIT` | 0.03 | Equity floor at ATA = 0 (extrapolated). |
| `PICK_EQUITY_MID` | 0.03 | Equity at ATA = `PICK_EQUITY_MID_INDEX` (= 1). |
| `PICK_EQUITY_MID_INDEX` | 1 | ATA where the piecewise switches. |
| `ZERO_EQUITY_INDEX` | 14 | ATA where pick equity reaches 0. |
| `BIAS_ADJ_COEF` | 1.0 | Scale on the bias correction. |
| `DEQ_LOSS_FACTOR` | 0.6 | Outer scale on meta-decay term. |
| `SAMPLE_DECAY` | 0.95 | Per-day decay of sample weight. |
| `META_DECAY` | 0.95 | Per-day decay of meta relevance. |
| `MAX_DEQ_DAYS` | 25 | Caps `t` in the meta-decay formula. |
| `GRADE_C_MINUS_MAX` | -0.001 | Upper bound of the C- grade. |
| `GRADE_NOTCH_INCREMENT` | 0.0075 | Width of each letter-grade band. |

**1. ATA adjustment** (`deq/main.py:151`)

```
ata_adj = ata_17l                       # standard
ata_adj = ata_17l * 2 - 0.5             # is_pick_two formats (OM1, TLA)
```

**2. Pick equity** (`deq/main.py:152-182`) — piecewise quadratic in `ata_adj`, hitting `PICK_EQUITY_MID` at `ata_adj = 1`, decaying to 0 at `ata_adj = 14`, with a separate slope below 1 governed by `PICK_EQUITY_INIT`.

**3. DEq base** (`deq/main.py:183-189`)

```
deq_base = (gp_wr_17l - gp_wr_mean + pick_equity) * pct_gp
```

**4. Bias weight & GP bias** (`deq/main.py:190-201`)

```
gp_bias_weight_{name} = deck_{name} * lookup(MAIN_COLORS → game_wr_excess_{colors})
gp_wr_bias            = gp_bias_weight / DECK
```

This is the average per-deck win-rate excess weighted by where the card actually shows up.

**5. Bias adjustment** (`deq/main.py:202-205`)

```
deq_bias_adj = BIAS_ADJ_COEF * (pick_equity / PICK_EQUITY_INIT - 1) * gp_wr_bias
```

The `(pick_equity / 0.03 - 1)` scaling means the correction grows with how strong the pick-equity signal is — a strong card in a strong color combo gets the bias subtracted more aggressively.

**6. Meta regression factor** (`deq/main.py:128-147`)

Closed form in the `meta_decay_factor` closure. The factor sits in `[loss_factor * (something - 1), 0]` and shrinks the bias term as the format matures.

**7. Final DEq** (`deq/main.py:213-216`)

```
deq = deq_base + (deq_bias_adj + deq_meta_adj) * pct_gp
```

**8. Letter grade** (`deq/main.py:217-244`) — straight bucket on `deq` value, using `grade_c_minus_max` and `grade_notch_increment`. F → A+, with `N/A` for null/nan.

### Per-format config

`DEqConfig` (`deq/main.py:74-79`) and the dict at lines 82-110:

- `start_date` — earliest valid data point. Required.
- `end_date` — None for ongoing formats; populated when a format closes.
- `is_pick_two` — alters `ata_adj` (OM1, TLA).
- `cube` — disables the standard `max_format_day_start` check (full sample from day 1; Cube+-+Powered).

When adding a new set, add an entry here and (ideally) add or refresh a `card_ratings` fixture for tests.

### Caching & daily run

`daily_deq()` (`deq/main.py:783-905`):

1. Reads the `history_v2.parquet` cache from `ad_hoc_dir()`.
2. Walks dates backwards looking for the latest snapshot that matches the current `live_deq` parameters.
3. Computes incremental `live_deq` calls and merges into history.
4. Returns the row matching today's date.

Two known sharp edges in this loop:

- The date-walk while-loop has no max-iteration cap (`deq/main.py:842-861`).
- A silent fallback path uses the `all` cohort when the `top` cohort lacks samples (`deq/main.py:691-715`); no log line is emitted.

Both are tracked in the punch list.

---

## 2. P1 strategy analysis

`deq/p1_strategy.py` (705 lines). Distinct from core DEq; not part of the daily publish.

### Goal

Estimate the expected win-rate impact of a P1P1 choice, accounting for player skill cohort and the fact that "I'd take card X" is conditional on X being available.

### Key constants (top of file)

```python
P1P1            = {"$and": [{"pack_num": 1}, {"pick_num": 1}]}
LATE_FORMAT     = {"lhs": "format_day", "op": ">=", "rhs": 13}
EARLY_FORMAT    = {"$not": LATE_FORMAT}
P1P1_PICK_EQUITY = 0.025   # fallback equity when a card was never picked
SKILL_COHORT     = "skill_cohort"
NEIGHBORS        = 2       # substitute from ±2 skill cohorts when needed
```

### Pipeline

```
get_model_dfs            → (weights_df, wr_df, fallback_df)        lines 117-204
        │
        ▼
strategy_mapped_df       → maps observed picks → hypothetical picks lines 207-320
        │                  (substitution + card_parity branch)
        ▼
p1_skill_control_df      → skill-cohort win-rate diffs              lines 323-344
        │
        ▼
p1_strat_analysis        → per-metric delta + entropy               lines 347-411
        │
        ▼
all_metrics_analysis     → loops the above over [deq, gih_wr, …]    lines 462-524
        │
        ▼
card_detail_df           → joins color/rarity, expands per card      lines 560-661
```

### How it differs from core DEq

| Aspect | Core DEq | P1 strategy |
| --- | --- | --- |
| Signal source | Pick position + deck win rate | Observed match results |
| Output | Single rating + grade | Win-rate delta by skill cohort + entropy |
| Skill stratification | Pooled (`top` vs `all`) | Six cohorts, with substitution |
| Substitution | None | Yes; uses `NEIGHBORS = 2` |

---

## 3. Web interface

### Build & deploy

`publish.sh` (production cron at 04:00 and 06:00):

```
git checkout main           # always publish from main
jupyter-book clean -a docs
jupyter-book build docs     # → docs/_build/html/
cp docs/_images/* docs/_build/html/_images
.venv/bin/python deq/site.py    # → docs/_build/html/deq-{set}.html
rm -rf /var/www/html/on-draft/*
cp -r docs/_build/html/* /var/www/html/on-draft
```

Both crons write to `/tmp/deq.log`. The two-run cadence is intentional rate-limiting against 17lands.

### Site generation

`deq/site.py` (96 lines):

1. Loads `deq_site_template.html` (string template; uses `str.format()`).
2. For each set in `config`, calls `daily_deq(set_code)`.
3. Selects display columns: `deq_grade, name, color, rarity, deq, npr, pct_top, image_url`.
4. Sorts descending by `deq` with NaNs last.
5. Renders to `docs/_build/html/deq-{code}.html` plus a top-level `deq.html` index.

Template variables in use:

- `{deq_table}` — JSON card list.
- `{set_code}`, `{start_date}`, `{end_date}` — header fields. Date format uses `strftime("%-d %b %y")`, which is Linux-only (portability bug).
- `{embargo_class}` — computed but currently unused in the template.
- `{select_elements}` — `<option>` tags for the set switcher.
- `{version}` — random cache buster.

### Frontend layout

The template is a single 320-line file with inline CSS and JS. Custom CSS also lives in `docs/_static/style.css` (110 lines). The Jupyter Book theme (pydata-sphinx-theme via Sphinx) provides the surrounding chrome.

The `image_url` column is plumbed through `daily_deq()` and the JSON payload, but currently nothing in the template uses it — that hook is what the (now-discarded) `feature/modal-ui` branch was wiring up.

---

## 4. Spells dependencies

deq imports from a local-file install of spells (`spells-mtg @ file:///home/joel/dev/spells`). Breaking changes upstream can break the nightly publish.

| Symbol | Used by |
| --- | --- |
| `summon` | `main.py`, `p1_strategy.py`, `pick_rate.py`, `analytics.py` |
| `ColName`, `ColType`, `ColSpec`, `agg_col` | `main.py` |
| `deck_color_df`, `ad_hoc_dir`, `CardDataFileSpec` | `main.py` |
| `context_cols`, `wavg`, `make_verbose`, `all_sets` | `p1_strategy.py` |
| `view_select`, `View`, `get_names`, `_get_set_context` | `mle.py`, `sample_pack.py` |
| `save_ad_hoc_dataset`, `read_ad_hoc_dataset` | `mle.py` |
| `set_prod_env` | `tests/test_mle.py` (exploratory) |

When bumping `spells`, run the full deq pytest suite (once it exists) and a `pdm run deqdaily` smoke test against TDM before merging to `main`.

---

## 5. Module map

```
deq/
├── main.py            # DEq model. Authoritative.
├── site.py            # HTML generation; entry point: deqdaily.
├── p1_strategy.py     # P1 strategy analysis. Not in publish path.
├── mle.py             # MLE-based card rating experiments. Research code.
├── sample_pack.py     # Pack simulation utilities.
├── pick_rate.py       # Pick-rate analysis.
├── analytics.py       # Misc helpers.
├── dft_early.py       # DFT-specific notebook driver. Imperative script style.
├── tdm_post.py        # TDM-specific notebook driver. Imperative script style.
└── tests/             # Currently broken; see punch list.
```

`research/` does not yet exist; one of the punch-list items is to move `dft_early.py` and `tdm_post.py` there to signal they aren't library code.
