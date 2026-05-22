# Modal design notes

## Panel structure

| Panel | Contents | Aspect ratio | CSS wrapper |
|-------|----------|-------------|-------------|
| Card  | Card image | `745/1040` | `.modal-image-container` inside `.modal-left` |
| Stat  | NPR, % Top, MWR†, PEq†, Adj†, % GP | `745/1040` | `.modal-metrics-container` inside `.modal-data-panel` |
| Info  | DEq title badge, DEq value, Grade | `2/1` | `.modal-stats-container` inside `.modal-data-panel` |

† Hidden when embargoed (`.col-embargo` + `#modal.embargo-active`)

## Layout

**Mobile:** Card shown by default, Stat hidden. Toggle buttons (`.modal-toggle` / `.modal-toggle-back`) add/remove `.show-stats` on `.modal-body`. Info always visible below. Left/right swipe navigates cards (not panels). No vertical swipe — conflicts with pull-to-reload.

**Desktop (≥620px):** All panels visible. `.modal-body` is a flex row; `.modal-left` and `.modal-data-panel` each `flex: 1`. Stat panel fills remaining height (`aspect-ratio: unset; flex: 1; min-height: 0`). Info panel fixed height (`flex-shrink: 0; aspect-ratio: 2/1`). Toggle buttons hidden.

## Key JS state

- `openModalIdx` — index into `currentRenderedData`
- `isEmbargoed` — set in `loadSet()`; toggled as class on `#modal`
- `openModal(idx, preserveToggle)` — resets drag transform; removes `.show-stats` unless preserveToggle

## Info panel internals

Left to right: `.info-title-badge` (raised, outset shadow, carved DEq text) → `.info-score-inset` (DEq value, sunken) → `.info-grade-inset` (grade letter, sunken). Clicking the title badge switches to Stat panel and opens the DEq tooltip.

## Potential future panel: archetype breakdown

A third swipeable panel (mobile) / third column or expandable section (desktop) showing per-archetype GP% and WR for the card — the data that feeds `deq_bias_adj`. Natural home for the "where does this card get played" question. Would slot into `.modal-data-panel` alongside Stat and Info, or replace the card panel on a third toggle state.

## Invariants

- Panel content: NPR/%Top/MWR/PEq/Adj/%GP always in Stat; DEq/Grade always in Info
- Aspect ratios enforced via `aspect-ratio` on position-relative containers with `position: absolute; inset: 0` children
- No vertical swipe for panel nav (browser conflict)
- Desktop: no toggle buttons, everything always visible

## Code conventions

- Mobile-first CSS; desktop overrides in `@media (min-width: 620px)`
- Hardcoded colors only for `#2a2e33` row stripe and info badge `#4a4f58`; everything else via `var(--pst-color-*)`
- Cache DOM refs at module level; no `querySelector` inside event handlers or render loops
- Formatters: `deqFormat` (±%), `nprFormat` (2dp), `pctFormat` (1dp %)
