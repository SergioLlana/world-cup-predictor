# Design

Visual system of the `wcpred` webapp (`webapp/static/`). Register: **product /
data journalism** — light, editorial, quietly confident. Charts and tables are
the heroes; chrome stays neutral. See `PRODUCT.md` for strategy.

## Theme

Light only. Cool near-white page on white surfaces — deliberately **not** a
warm cream. Every non-neutral color encodes data.

## Color tokens (`style.css :root`)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#f4f6f6` | page plane (cool tint toward the data hue) |
| `--surface` | `#ffffff` | cards, header, nav, modals |
| `--ink` | `#1f2529` | primary text, strong rules |
| `--muted` | `#4f5a5e` | secondary text (≥ 4.5:1 on bg and surface) |
| `--line` / `--line-soft` | `#dde3e3` / `#e9eded` | hairlines / row rules |
| `--data` / `--data-deep` / `--data-tint` | `#0a6c6b` / `#085453` / `#dcebea` | probability = teal, single-hue ramp |
| `--hi` / `--hi-ink` / `--hi-tint` | `#c2491d` / `#a63c12` / `#fbeae1` | our pick = vermilion (chips, active tab) |
| `--good-*` | tint `#e0f0e3`, ink `#1e6b34` | exact-hit badge |
| `--warn-*` | tint `#faf0d2`, ink `#7a5c04` | outcome-hit badge |
| `--miss-*` | tint `#e9eded`, ink `#4f5a5e` | miss badge |

All pairs verified ≥ 4.5:1. Status badges always pair color with a text label
(never color alone).

### Probability shading (`shadeCell` in `app.js`)

Single-hue teal alpha ramp over white (`rgba(10,108,107,a)`). The ramp **skips
alpha 0.70–0.88**, where neither ink nor white text reaches 4.5:1: cells at
raw ≤ 0.70 use ink text; above, the alpha jumps to ≥ 0.88 and text switches
to white. Used by the champion/groups tables, the connectivity heatmap, and
the score-matrix modal.

### Categorical chart palette (`PALETTE` in `app.js`)

`#009490 #d95926 #2a78d6 #eda100 #008300 #4a3aa7 #e34948 #e87ba4` — validated
with the dataviz skill's `validate_palette.js` (lightness band, chroma floor,
worst adjacent CVD ΔE 24.2). **Slot order is part of the guarantee; don't
reorder without re-validating.** Yellow/magenta sit below 3:1 on white, so
charts using them must keep direct labels or a legend (they do).
Confederations map to fixed slots (`CONF_COLORS`); confederation names in
tables render as a colored dot + ink text (`confLabel`), never colored text.
Chart end-labels are ink; the leader line/point carries the series hue.

## Typography

- **Display: Source Serif 4** (variable, self-hosted `fonts/…woff2`, latin
  subset) — masthead, `h2.section`, card `h3`s, round headings, modal titles.
  Weight ~650, letter-spacing −0.01em.
- **UI/data: Inter** (variable, self-hosted) — everything else. A deliberate
  "familiar sans" choice for the product register; tabular figures
  (`font-variant-numeric: tabular-nums`) on every numeric column, score, and
  axis.
- Fixed rem-ish scale: masthead 27px, section 23px, card h3 16.5px, body/UI
  14px, notes 13px, table 12.5–13.5px, uppercase table headers 10–11px with
  0.04–0.05em tracking.
- Prose capped at 75ch (`.note`, doc cards); ledes at 62ch.

## Layout & components

- 1140px content column; masthead (not sticky) + sticky underline nav
  (`.tabs`, active = 3px `--hi` underline, centered via flex spacers, scrolls
  horizontally on mobile).
- Cards: white, 1px `--line`, 8px radius, `--shadow-1`; hover on interactive
  cards elevates to `--shadow-2`. No nested cards, no side-stripe accents.
- Champion tab = front page: serif lede sentence, top-8 contenders bar chart
  (solid `--data` bars on `--line-soft` tracks, direct labels), then the full
  shaded table with rank numbers.
- 1X2 probability bars: tinted segments (teal/gray/vermilion tints, dark AA
  text) with 2px surface gaps.
- Buttons: 1px ink outline, hover inverts; primary = solid ink. Toggles fill
  `--data` when on. Selects are native with hairline borders.
- z-scale: nav 30 < modal 50 (`--z-nav`, `--z-modal`).

## Motion

150–250ms, `cubic-bezier(0.25,1,0.5,1)` (ease-out-quart). Panel switch =
180ms fade/3px rise; modal = 180ms fade/scale. State feedback only — no
scroll choreography. Everything is disabled under
`prefers-reduced-motion: reduce`.

## Accessibility

WCAG AA. `:focus-visible` = 2px `--data` outline. Color-blind-safe: validated
categorical order, single-hue sequential ramp, states always labeled. Fully
bilingual EN/ES via `i18n.js` — any new UI string needs both languages.
