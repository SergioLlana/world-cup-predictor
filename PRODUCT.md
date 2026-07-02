# Product

## Register

product

## Users

Two audiences, one surface:

1. **General public / portfolio visitors** — people who land on the public
   Render deploy (or see a shared screenshot) during World Cup 2026. Mostly
   football-literate, not statistics-literate. They come to answer one
   question first: *who is going to win the World Cup?* — then browse groups,
   the calendar of predicted scorelines, and how the forecast has evolved.
2. **The author** (local, full mode) — runs data refreshes, compares the
   three engines (Dixon-Coles / Elo / Bayesian), inspects connectivity
   diagnostics. Expert user; density and controls matter more than hand-holding.

Context: a browser tab on a desktop at home or work, daytime, often revisited
across tournament days. Bilingual EN/ES (default EN).

## Product Purpose

A forecast dashboard for FIFA World Cup 2026 built on the `wcpred` model
suite. It publishes date-stamped predictions (champion probabilities, group
standings, per-match scoreline picks optimised for Penka points) and makes the
modelling legible and credible. Success: a stranger trusts the numbers at a
glance, and the author is proud to link it as a work sample.

## Brand Personality

**Rigorous, editorial, quietly confident.** Data journalism, not sports
hype: the tone of a well-edited statistics feature — strong typographic
hierarchy, charts and tables as the heroes, color used to encode meaning and
almost never to decorate. Numbers speak in a measured voice ("62%", not
"🔥 LOCK 🔥").

## Anti-references

- **Betting sites** — no neon odds-boost energy, flashing highlights,
  bookmaker green/gold, urgency cues.
- **Generic SaaS dashboards** — no hero-metric cards, gradient accents,
  identical icon-card grids, cookie-cutter admin-template chrome.
- **Toy / fan projects** — nothing that reads amateur: emoji-heavy copy,
  clip-art, loud team colors splashed everywhere, default-Bootstrap flavor.
- Not the official FIFA 2026 brand kit; this is an independent analytical take.

## Design Principles

1. **The forecast is the front page.** The champion table answers the main
   question above the fold; everything else supports it.
2. **Encode, don't decorate.** Every color on screen carries data meaning
   (probability shading, outcome states, engine identity). Chrome stays
   near-monochrome.
3. **Legible to a stranger.** Labels over jargon, units on numbers, one-line
   explanations where the model does something non-obvious. The "How it
   works" tab is a feature, not an appendix.
4. **Editorial craft signals rigor.** Typography, alignment, and tabular
   numbers do the trust-building that testimonials would do elsewhere.
5. **Desktop-first density, mobile without breakage.** Wide tables and
   charts are first-class on desktop; on small screens structure collapses
   gracefully rather than shrinking.

## Accessibility & Inclusion

- WCAG 2.1 AA: body text ≥ 4.5:1 contrast, large text ≥ 3:1, visible focus
  states, keyboard-operable controls.
- **Color-blind safe encodings**: probability shading uses a single-hue ramp;
  win/draw/loss and exact/outcome/miss states never rely on red-vs-green
  alone — always paired with text labels or position.
- `prefers-reduced-motion` respected on all transitions.
- Fully bilingual EN/ES via `i18n.js`; no text baked into images or SVG
  without translation hooks.
