# Modal Panel Design Plan

## Current state (as of 2026-05-18)

Three panels, each with a fixed aspect ratio, laid out differently on mobile vs desktop.

### Panel definitions

| Panel | Contents | Aspect ratio | CSS container |
|-------|----------|-------------|---------------|
| Card  | Card image | `745/1040` | `.modal-image-container` inside `.modal-left` |
| Stat  | NPR, % Top, MWR†, PEq†, Adj†, % GP | `745/1040` | `.modal-metrics-container` inside `.modal-data-panel` |
| Info  | DEq, Grade | `2/1` | `.modal-stats-container` inside `.modal-data-panel` |

† Hidden when embargoed (`.col-embargo` + `#modal.embargo-active`)

### Mobile layout

- Card panel visible by default; Stat panel hidden (`display: none`)
- Info panel always visible below whichever card/stat panel is shown
- **Toggle**: "Stats" button (`.modal-toggle`, absolute bottom-left of card panel) adds `.show-stats` to `.modal-body`; "Card" button (`.modal-toggle-back`, absolute bottom-left of stat panel) removes it
- **Swipe**: left/right swipe on the modal overlay navigates between cards (not panels)

### Desktop layout (≥620px)

- All three panels always visible, no toggle buttons shown
- `.modal-body` is a flex row; `.modal-left` (card) and `.modal-data-panel` (stat + info stacked) each take `flex: 1`
- Stat panel: `flex: 1; min-height: 0; aspect-ratio: unset` — fills remaining height above info panel
- Info panel: `flex-shrink: 0; aspect-ratio: 2/1` — fixed height from its own width

### Modal-level behavior (must not change)

- Prev/next nav buttons (`.modal-nav`) and close button remain absolute-positioned in `.modal-content`
- Embargo class toggled on `#modal` in `loadSet()`; hides `.col-embargo` rows in both stat panel and metrics table
- Card navigation resets to card view: `openModal()` removes `.show-stats` from `.modal-body`
- `currentRenderedData` index tracked as `openModalIdx`

## Design goals

### Info panel
Cleanly convey the **value of the card** in context. A reader should immediately understand how good this card is and where it sits relative to the field — not just a number, but a sense of scale. DEq and Grade are the two signals; the design should make the grade legible at a glance and the DEq value interpretable without knowing the scale by heart.

### Stat panel
Convey the **composition of the metric** — how the component values combine to produce DEq. The layout should make it apparent:
- How the components (NPR → % Top → MWR → PEq → Adj → % GP) flow into the final value
- How each component value sits on its own relative scale (is this MWR high or low for this set?)
- Tooltips must be available and visually signaled (not hidden; the `?` affordance or equivalent)
- Design must be consistent across all rows (embargo rows just disappear cleanly, no layout shift)

### Navigation
Navigation between cards (left/right) and between panels (card ↔ stat, via toggle or swipe) must be **visually apparent** with consistent design language:
- Left/right swipe → prev/next card (already implemented)
- Panel toggle is button-only; no vertical swipe (conflicts with browser pull-to-reload)
- Toggle buttons must follow the same visual style as the swipe direction they represent
- On desktop, the left/right nav buttons (‹ ›) remain; panel toggle is not needed

## Invariants for future iterations

1. **Panel content**: do not move metrics between panels; NPR/%Top/MWR/PEq/Adj/%GP always in Stat; DEq/Grade always in Info
2. **Aspect ratios**: Card `745/1040`, Stat `745/1040`, Info `2/1` — all enforced via `aspect-ratio` on position-relative containers with `position: absolute; inset: 0` children
3. **Toggle**: "Stats"/"Card" buttons overlay their respective panels at bottom-left; add/remove `.show-stats` on `.modal-body`; hidden on desktop
4. **Left/right swipe**: navigates prev/next card — do not break
5. **Panel toggle**: toggle buttons only; no vertical swipe (conflicts with browser scroll/reload gestures)
5. **Desktop**: card on left (`flex: 1`), stat+info stacked on right (`flex: 1`), no toggle buttons, everything always visible

## Design iteration notes

- The Info panel is currently two plain rows (DEq value bold, Grade value bold, labels muted). Planned: infographic-style design using the fixed 2:1 space.
- The Stat panel rows fill height via `position: absolute; inset: 0; height: 100%` on the table. Row distribution is even because the table is height-constrained.
- CSS naming: `.modal-left` (card column wrapper), `.modal-data-panel` (right column flex container), `.modal-metrics-container` (stat panel wrapper), `.modal-stats-container` (info panel wrapper), `.modal-metrics-view` (stat table), `.modal-stats` (info table)

## Code quality checklist (apply on each iteration)

- No orphaned CSS rules for removed elements
- Mobile-first: base styles apply to mobile; desktop overrides in `@media (min-width: 620px)`
- Consistent use of `var(--pst-color-*)` for theming; no hardcoded colors except `#2a2e33` row stripe
- JS: no `document.querySelector` calls inside event handlers or render loops (cache at module level)
- Formatters: `deqFormat` (±%), `nprFormat` (2dp), `pctFormat` (1dp %) — use consistently
