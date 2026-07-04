/* Traducciones EN/ES del frontend. Cargado antes de app.js: define los globales
   `I18N` y `t()`. El idioma por defecto es inglés; la elección se guarda en
   localStorage. Las cadenas con interpolación son funciones que reciben un objeto
   de parámetros YA formateados por app.js (fechas, porcentajes, nombres), para
   que este fichero no dependa de los helpers de app.js. */

const I18N = {
  en: {
    // ---- chrome (index.html, data-i18n) ----
    "title": "World Cup 2026 · Predictions",
    "subtitle.model": "Model",
    "subtitle.opt": "optimised for Penka",
    "ctrl.odds": "Market odds",
    "ctrl.odds_title": "Blend the market 1X2 odds into the predictions",
    "ctrl.strategy": "Most likely score",
    "ctrl.strategy_title": "On: most likely score of the most likely result (strategy C, +8% Penka in the backtest). Off: score with the maximum expected points.",
    "ctrl.engine": "Engine",
    "ctrl.engine_title": "Prediction engine",
    "ctrl.day": "Day",
    "ctrl.refresh": "⟳ Refresh data",
    "ctrl.lang": "Language",
    "tab.champion": "Who wins?",
    "tab.evolution": "Evolution",
    "tab.groups": "Groups",
    "tab.calendar": "Calendar",
    "tab.rankings": "Rankings",
    "tab.connectivity": "Connectivity",
    "tab.docs": "How it works",
    "matrix.close": "Close",
    "refresh.title": "Refresh predictions",
    "refresh.inputs": "Refresh input data (results + xG + odds)",
    "refresh.engines_legend": "Engines to generate",
    "refresh.engine_bayes_hint": "(needs CmdStan; slow)",
    "refresh.sims": "Monte Carlo simulations",
    "refresh.sims_ph": "default",
    "refresh.hint": "Generates today's date-stamped CSVs for both variants (with and without odds) and the checked engines. May take several minutes.",
    "refresh.start": "Run",
    "refresh.close": "Close",

    // ---- engines / strategy ----
    "engine.dc": "Dixon-Coles",
    "engine.elo": "Elo",
    "engine.bayes": "Bayesian",
    "strategy.ev": "maximum expected value",
    "strategy.outcome": "most likely score",

    // ---- generic labels / columns ----
    "col.team": "Team",
    "col.conf": "Conf.",
    "col.matches": "Matches",
    "col.bridge": "Bridge weight",
    "col.opp": "Avg. opponent",
    "col.rating": "Rating",
    "col.attack": "Attack",
    "col.defence": "Defence",
    "col.elo": "Elo",
    "col.qualify": "Qualifies",
    "label.metric": "Metric",
    "label.group": (p) => `Group ${p.g}`,
    "pos.1": "1st", "pos.2": "2nd", "pos.3": "3rd", "pos.4": "4th",

    // ---- snapshot note ----
    "snapshot.predictions": (p) => `predictions from ${p.date}`,
    "snapshot.none": "no predictions generated yet",

    // ---- sim columns ----
    "sim.win_group": "Win group",
    "sim.r16": "Round of 16",
    "sim.qf": "Quarters",
    "sim.sf": "Semis",
    "sim.final": "Final",
    "sim.champion": "Champion",

    // ---- evolution metrics ----
    "evo.m.champion": "Champion",
    "evo.m.final": "Reaches final",
    "evo.m.sf": "Semi-finalist",
    "evo.m.qf": "Quarter-finalist",
    "evo.m.knockout": "Out of group",

    // ---- champion tab ----
    "champion.none": "No simulations generated yet.",
    "champion.title": "Who will win the World Cup?",
    "champion.lede": (p) => `${p.team} lead the field with a ${p.pct} chance of lifting the trophy; ${p.team2} follow at ${p.pct2}.`,
    "champion.intro": (p) => `Probability of reaching each round per the full-tournament Monte Carlo simulation (snapshot of ${p.date}, ${p.odds ? "with market odds" : "model only, no odds"}). Matches already played enter with their real result.`,

    // ---- legend ----
    "legend.clear": "Deselect all",
    "legend.add": "Click to highlight",
    "legend.remove": "Click to remove",

    // ---- evolution tab ----
    "evo.none": "No simulations generated.",
    "evo.title": "Day-by-day evolution",
    "evo.note": (p) => `The ${p.total} teams (in grey) by «${p.metric}» (${p.odds ? "with odds" : "without odds"}); the ${p.selected} chosen ones highlighted. Click a flag in the legend to highlight or remove it.${p.oneDay ? " Only one day generated: the line will grow with each new snapshot." : ""}`,

    // ---- groups tab ----
    "groups.none": "No standings generated.",
    "groups.title": "Group stage",
    "groups.intro": (p) => `Probability of each final position and of qualifying for the round of 32 (1st, 2nd or one of the 8 best third-placed teams). Snapshot of ${p.date}.`,

    // ---- calendar tab ----
    "cal.title": "Calendar and match-by-match predictions",
    "cal.intro": "For each match it shows the prediction in force that day (the latest snapshot on or before the match date) and the 1X2 odds when available. Knockout matches appear once the ties are known.",
    "cal.none": "No matches in results.csv.",
    "round.group": (p) => `Group stage · Matchday ${p.n}`,
    "round.r32": "Round of 32",
    "round.r16": "Round of 16",
    "round.qf": "Quarter-finals",
    "round.sf": "Semi-finals",
    "round.p3": "Third place",
    "round.f": "Final",
    "round.ko": "Knockouts",
    "badge.exact": "Exact",
    "badge.outcome": "1X2 ✓",
    "badge.miss": "Miss",
    "match.card_title": "Click to see the score matrix",
    "match.vs": "vs",
    "match.pred_prefix": "Pred.",
    "match.strategy_title": (p) => `Strategy: ${p.strategy}`,
    "match.mode_title": "Most probable score (model / odds)",
    "match.no_pred": "No prediction for this match",
    "match.odds": "Odds:",
    "match.prob_title": "1 / X / 2 probabilities",
    "match.aet": "a.e.t.",
    "match.aet_title": (p) => `After extra time — 90' score ${p.score} (what the pick is judged on)`,
    "match.pens": "pens",
    "match.pens_title": (p) => `${p.team} won on penalties — 90' score ${p.score} (what the pick is judged on)`,

    // ---- score matrix modal ----
    "matrix.loading": "Fitting the model… (first time takes a few seconds)",
    "matrix.error": (p) => `Error computing the matrix: ${p.msg}`,
    "matrix.sub": (p) => `Probability (%) of each exact score · ${p.engine} model of ${p.date} · ${p.odds ? "with market odds" : "model only"} · 1X2: ${p.p1} / ${p.px} / ${p.p2}`,
    "matrix.away_goals": (p) => `${p.team} goals →`,
    "matrix.home_goals": (p) => `${p.team} ↓`,
    "matrix.legend_pick": "Penka prediction",
    "matrix.legend_real": "90' result",

    // ---- refresh runtime (local only) ----
    "refresh.starting": "(starting…)",
    "refresh.done": "\n\n✔ Done. Reloading data…",
    "refresh.failed": (p) => `\n\n✘ Failed (code ${p.code}).`,

    // ---- init ----
    "init.error": (p) => `Error loading data: ${p.msg}. Is the server running from the project root?`,

    // ---- connectivity tab (local only) ----
    "conn.loading": "Computing connectivity… (the first time it fits the model and takes a few seconds)",
    "conn.error": (p) => `Error computing connectivity: ${p.msg}`,
    "conn.title": "Who anchors whom? Connectivity between confederations",
    "conn.intro": (p) => `Anchoring a confederation means fixing its level relative to the others, so teams from different blocs are comparable on the same scale. The model can only do this through «bridge» matches between confederations. Where there are few bridges, a confederation's scale is poorly anchored to the rest and its ratings can inflate or deflate as a bloc — a known limitation of the model (e.g. the AFC, and to a lesser extent CONMEBOL). The weight is the same one used in training (time decay with a 2-year half-life, data up to ${p.date}).`,
    "conn.scatter_h3": "The 48 qualified teams: how much does each rating rely on bridge matches?",
    "conn.scatter_note": "The further left, the more the rating depends on internal play within its confederation (and on how well anchored it is). Click a flag to see the breakdown.",
    "conn.legend_unknown": "No conf. inferred",
    "conn.detail_prompt": "Click a flag in the chart (or a row in the table) to see which confederations each team has played against.",
    "conn.stat_rating": "rating",
    "conn.stat_matches": "matches in the window",
    "conn.stat_bridge": "of the weight is bridge",
    "conn.stat_opp": "average opponent rating",
    "conn.bar_title": "Split of the training weight by the opponent's confederation",
    "conn.bar_unknown_title": (p) => `Opponents with no inferred confederation: ${p.pct}`,
    "conn.matrix_h3": "Connectivity matrix",
    "conn.matrix_note": "Each cell: fraction of the training weight of the row's confederation played against the column's. The diagonal (dotted) is internal play; everything else is bridges.",
    "conn.scatter_xaxis": "Training weight against other confederations (bridge matches)",
    "conn.scatter_yaxis": "Model rating (attack − defence)",
    "conn.table_h3": "Per-team detail",
    "conn.heat_conf": "Conf.",

    // ---- rankings tab ----
    "rank.loading": "Loading rankings…",
    "rank.live_loading": "No ranking snapshots generated. Fitting the model live… (first time takes a few seconds)",
    "rank.error": (p) => `Error loading rankings: ${p.msg}`,
    "rank.title": (p) => `Model rankings · ${p.engine}`,
    "rank.intro": (p) => `Strength of each team per the <b>${p.engine}</b> engine, sorted by ${p.sort} (${p.source}). The <b>rating</b> is attack − defence: the higher, the better. ${p.hasElo ? "The <b>Elo score</b> is the engine's own (eloratings.net rule). " : ""}The <b>average opponent</b> is the mean rating (weighted by training weight) of the teams it has played: a measure of its average schedule difficulty. Use the <b>Engine</b> selector in the header to switch model.`,
    "rank.sort_elo": "Elo score",
    "rank.sort_rating": "rating (attack − defence)",
    "rank.source_live": (p) => `live fit as of ${p.date} (generate snapshots with <code>scripts/generate_rankings.sh</code> to chart the evolution)`,
    "rank.source_snap": (p) => `snapshot of ${p.date}`,
    "rank.class_h3": (p) => `Standings ${p.live ? "(live)" : "of " + p.date}`,
    "rank.evo_h3": "Ranking evolution",
    "rank.evo_note": (p) => `The ${p.total} teams (in grey) by «${p.metric}»; the ${p.selected} chosen ones highlighted. Click a flag in the legend to highlight or remove it. ${p.oneDay ? "Only one day generated: the line will grow with each new snapshot." : p.n + " snapshots."}${p.isRank ? " Inverted axis: 1st on top." : ""}`,
    "rank.m.rating": "Rating (attack − defence)",
    "rank.m.elo": "Elo score",
    "rank.m.rank": "Ranking position",
    "rank.m.opp": "Opponent difficulty",

    // ---- documentation tab ----
    "docs.html": () => `
      <h2 class="section">How the predictor works</h2>
      <p class="note">For every World Cup 2026 match, wcpred picks the scoreline that maximises the <b>expected Penka points</b> — which is not the most likely score. The whole pipeline, as questions: click one to unfold it. Pitched at the technically curious — formulas included, derivations left out.</p>

      <pre class="doc-flow">results (2015→) ──→ engine (dc / elo / bayes) ──→ matrix P[scoreline]
                                                      │
odds ──→ margin-free 1X2 ─────────────────────────────┤  (rescales the 1X2)
                                                      ├─→ pick (max expected Penka points)
                                                      └─→ Monte Carlo ──→ groups · bracket · champion</pre>

      <details class="card doc-card">
        <summary>1 · Where do the predictions come from?</summary>
        <div class="doc-body">
          <p>Only <b>match results</b> train the model: every senior international since 2015, from the public martj42 dataset. Each match enters with a weight <code>w = exp(−ln 2 · days / 730)</code> — a two-year half-life, so a result from four years ago counts a quarter of yesterday's. Friendlies get full weight (down-weighting them was tested and hurt every metric), and teams with fewer than 10 matches are dropped.</p>
          <p><b>Expected goals (xG)</b> were tested and left out: blending them into the training goals improves log-loss by a fraction but loses pool points monotonically, and FotMob coverage only starts in mid-2022. The World Cup is predicted without xG.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>2 · How does a match history become score probabilities?</summary>
        <div class="doc-body">
          <p>Each team gets two latent parameters — <b>attacking strength</b> <code>atk</code> and <b>defensive weakness</b> <code>dfn</code> — plus a global home-advantage term. A match's expected goals are <code>λ = exp(atk_home + dfn_away + home)</code> for the home side and <code>μ = exp(atk_away + dfn_home)</code> for the away side.</p>
          <p>Two Poisson distributions with those means give the <b>probability of every exact scoreline</b>, a matrix over the 0–8 goal grid. The Dixon-Coles <b>rho correction</b> then re-weights the four low-score cells (0-0, 1-0, 0-1, 1-1), where independent Poissons are known to be wrong. The parameters are fit by maximum likelihood, weighted with the decay above.</p>
          <p>Everything downstream — the pick, the group tables, the champion probabilities — consumes this one matrix.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>3 · What role do the betting odds play?</summary>
        <div class="doc-body">
          <p>The market prices what the model cannot see — injuries, suspensions, line-ups, by the minute. With the <b>«Market odds»</b> toggle on, the bookmaker's 1X2 odds are converted to probabilities and the margin is removed by normalising them to sum to 1; then <code>λ</code> and <code>μ</code> are rescaled until the model's matrix reproduces that market 1X2 <i>exactly</i>.</p>
          <p>So the win/draw/win split is 100% market, and the engine only shapes how the scorelines distribute <i>within</i> each result — odds carry no exact-score information. The odds never train the model; they enter at prediction time only. Toggle off to see the engine on its own. (The simulator's synthetic knockout pairings have no odds, so knockouts are always model-only.)</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>4 · Why doesn't it just pick the most likely score?</summary>
        <div class="doc-body">
          <p>Penka pays for the exact score, the right goal difference (or a draw), or just the right winner — and more in later rounds: <b>5/3/2</b> points in the group stage, <b>8/5/3</b> in the rounds of 32 and 16, <b>11/7/5</b> from the quarter-finals on. Given the matrix, each candidate scoreline has an expected value <code>E[pts] = Σ P[h,a] · points(pick, (h,a))</code>, and the default pick is the argmax. That optimiser leans to «safe» scores like 1-0 on the favourite: they cover exact, difference and winner at once.</p>
          <p>It turns out to be <i>too</i> conservative. The <b>«Most likely score»</b> toggle (on by default) switches to a second strategy: take the most likely 1X2 outcome, then the most likely scoreline within it. In the backtest it scores <b>+8%</b> (643 vs 594 points) — not by predicting draws (it predicts almost none, same as the optimiser) but by choosing better win scorelines: 2-0 or 2-1 where the expected-value pick settled for 1-0.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>5 · Where do the champion and group probabilities come from?</summary>
        <div class="doc-body">
          <p>The same per-match matrix, used the other way around: instead of choosing one score, <b>sample</b> from it. Each group is simulated <b>1,000,000 times</b>; the full tournament — group tables, the 8 best thirds per FIFA's official Annex C allocation, and the bracket from the round of 32 to the final — <b>100,000 times</b>. Each team's probability of winning its group, clearing each round or lifting the trophy is just the frequency across simulations.</p>
          <p>Matches already played enter with their real result, so the probabilities update as the tournament goes. Group ties break by points, goal difference and goals scored; head-to-head is not modelled (remaining ties are sampled). Knockouts are played at a neutral venue.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>6 · Does it actually work? How was it validated?</summary>
        <div class="doc-body">
          <p>You cannot validate on one future tournament, so everything is judged by <b>backtesting six past ones</b> — the 2018 and 2022 World Cups, Euro 2021 and 2024, Copa América 2021 and 2024, ~290 matches — re-fitting the model before every matchday with only the data available then, exactly as it runs live.</p>
          <p>Tuning decisions go by <b>RPS and log-loss</b> (probabilistic scores with low variance); Penka points break ties. The production model lands at RPS ≈ 0.189 and <b>~2.2 Penka points per match</b> with the web's default strategy (643 points; 594 with the expected-value pick). Every hyperparameter was chosen this way — and most ideas tested (capping blowouts, up-weighting inter-confederation matches, external Elo priors…) <i>lost</i> and were rejected. What you see is what survived.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>7 · What does the model not see?</summary>
        <div class="doc-body">
          <p><b>Weakly connected confederations.</b> Blocs are only comparable through the scarce «bridge» matches between them (~12% of the training weight). Where bridges are thin — the AFC above all — a whole bloc's ratings can drift: Australia ranking above the USA is half real form, half an artefact of an easy intra-AFC schedule the model cannot fully discount. Several fixes were tested and rejected (see the <b>Connectivity</b> tab); in practice the market odds correct it where it matters.</p>
          <p><b>Draws are under-called.</b> The model almost never gives a draw more than ~30% probability, so it almost never predicts one — a calibration limit of the probabilities, not of the pick step.</p>
          <p><b>Neutral-venue knockouts.</b> The bracket slots carry no venue, so no host gets home advantage after the group stage — the three hosts' deep-run probabilities are slightly under-rated. And <b>injuries, suspensions and line-ups</b> reach the model only through the odds.</p>
        </div>
      </details>

      <details class="card doc-card doc-appendix">
        <summary>Appendix · The three engines, in depth</summary>
        <div class="doc-body">
          <p>The three engines share one interface: each must produce an attack and a defence rating per team, a home term and a rho — and from there the <i>same</i> code builds the score matrix. That is why the <b>Engine</b> selector swaps them freely across every tab: they differ only in how the ratings are obtained.</p>

          <h4>Dixon-Coles (dc) — the production engine</h4>
          <p>The weighted Poisson fit from question 2, solved by L-BFGS-B with an analytic gradient and an identifiability constraint (attack ratings average to zero — only differences matter). The low-score correction <b>rho</b> is estimated afterwards by grid search over the four cells (0-0, 1-0, 0-1, 1-1) where goals stop behaving independently. Every hyperparameter — training window since 2015, two-year half-life, friendlies at full weight — was chosen on the six-tournament backtest, and several tested refinements (capping blowout margins, up-weighting bridge matches, shrinkage toward a global centre) <i>lost</i> and were rejected. It fits in seconds, is byte-for-byte reproducible — the project's regenerability rule — and wins the backtest: RPS 0.1890, 594 points with the expected-value pick.</p>

          <h4>Elo — a dynamic rating first, goals second</h4>
          <p>Two stages. The first iterates the eloratings.net update over every international since 2006, in chronological order: <code>R' = R + K · G · (W − We)</code>, where <code>We = 1/(10^(−dr/400) + 1)</code> is the expected score given the rating gap <code>dr</code> (+100 when playing at home), <code>W</code> is the actual result (1/½/0), <code>K</code> depends on the competition — 60 for a World Cup, 50 for continental finals, 40 for qualifiers, 30 for the rest, 20 for friendlies — and <code>G</code> grows with the goal margin (1 / 1.5 / 1.75, then +⅛ per extra goal). Alongside the current rating it keeps a <b>10-year median Elo</b> as a second covariate: a team's long-term class, separate from its current form.</p>
          <p>The second stage is a 4-parameter weighted Poisson regression that maps those two Elo differences to expected goals, <code>log λ = β0 + βh + βe·Δelo + βlt·Δelo_lt</code> (mirrored with opposite signs for <code>μ</code>), followed by the same rho search — so out comes the same kind of matrix. It lands slightly behind dc in the backtest (~587 pts): a per-match update rule carries less information than re-fitting all ratings jointly against the whole weighted history. Tuning its knobs (a per-confederation K) gains a few points, but the engine ships with the published rule untouched.</p>

          <h4>Bayesian — the same model, with honest uncertainty</h4>
          <p>The same weighted Dixon-Coles likelihood, fit by MCMC in Stan (CmdStan, 4 chains) with a hierarchical prior aimed squarely at the connectivity limitation: each rating decomposes into a <b>confederation offset plus an individual deviation</b>, <code>atk_i = atk_conf(i) + σ·z_i</code>, with a Student-t on the deviations so genuine outliers (Argentina) are not flattened. The offsets are shared by a whole bloc, so intra-confederation matches cannot move them — <b>only bridge matches can</b>, which is exactly the constraint the maximum-likelihood fit cannot express. (Its verdict on the Australia case is instructive: the inflation survives, because it lives in Australia's <i>individual</i> deviation, not in the AFC offset.)</p>
          <p>Its other difference is what happens after the fit: instead of plugging in point ratings, the score matrix is the <b>average of the matrices produced by each posterior draw</b>, so rating uncertainty — largest across the weak bridges — genuinely widens the scoreline distribution. A dynamic variant replaces the decay weights with a random walk (each team's strength evolves per half-year block); it is the strongest Bayesian configuration and ties dc in the backtest without beating it. At ~150 s per fit, it is available in the local version only.</p>

          <p>The web defaults to <b>Dixon-Coles (dc)</b>, the same engine as the CLI and the production snapshots. With the market odds on the choice barely matters anyway: the 1X2 comes from the market and the engine only shapes the scorelines, so the differences between engines are small — but keeping dc as the default lines the web up with production.</p>
        </div>
      </details>`,
  },

  es: {
    // ---- chrome ----
    "title": "Mundial 2026 · Predicciones",
    "subtitle.model": "Modelo",
    "subtitle.opt": "optimizado para Penka",
    "ctrl.odds": "Cuotas de mercado",
    "ctrl.odds_title": "Mezclar las cuotas 1X2 del mercado en las predicciones",
    "ctrl.strategy": "Marcador más probable",
    "ctrl.strategy_title": "Activado: marcador más probable del resultado más probable (estrategia C, +8% Penka en el backtest). Desactivado: marcador de máximo valor esperado de puntos.",
    "ctrl.engine": "Motor",
    "ctrl.engine_title": "Motor de predicción",
    "ctrl.day": "Día",
    "ctrl.refresh": "⟳ Actualizar datos",
    "ctrl.lang": "Idioma",
    "tab.champion": "¿Quién gana?",
    "tab.evolution": "Evolución",
    "tab.groups": "Grupos",
    "tab.calendar": "Calendario",
    "tab.rankings": "Rankings",
    "tab.connectivity": "Conectividad",
    "tab.docs": "Cómo funciona",
    "matrix.close": "Cerrar",
    "refresh.title": "Actualizar predicciones",
    "refresh.inputs": "Refrescar datos de entrada (resultados + xG + cuotas)",
    "refresh.engines_legend": "Motores a generar",
    "refresh.engine_bayes_hint": "(necesita CmdStan; lento)",
    "refresh.sims": "Simulaciones Monte Carlo",
    "refresh.sims_ph": "por defecto",
    "refresh.hint": "Genera los CSV fechados de hoy para ambas variantes (con y sin cuotas) y los motores marcados. Puede tardar varios minutos.",
    "refresh.start": "Lanzar",
    "refresh.close": "Cerrar",

    // ---- engines / strategy ----
    "engine.dc": "Dixon-Coles",
    "engine.elo": "Elo",
    "engine.bayes": "Bayesiano",
    "strategy.ev": "máximo valor esperado",
    "strategy.outcome": "marcador más probable",

    // ---- generic labels / columns ----
    "col.team": "Equipo",
    "col.conf": "Conf.",
    "col.matches": "Partidos",
    "col.bridge": "Peso puente",
    "col.opp": "Rival medio",
    "col.rating": "Rating",
    "col.attack": "Ataque",
    "col.defence": "Defensa",
    "col.elo": "Elo",
    "col.qualify": "Clasifica",
    "label.metric": "Métrica",
    "label.group": (p) => `Grupo ${p.g}`,
    "pos.1": "1º", "pos.2": "2º", "pos.3": "3º", "pos.4": "4º",

    // ---- snapshot note ----
    "snapshot.predictions": (p) => `predicciones del ${p.date}`,
    "snapshot.none": "sin predicciones generadas todavía",

    // ---- sim columns ----
    "sim.win_group": "Gana grupo",
    "sim.r16": "Octavos",
    "sim.qf": "Cuartos",
    "sim.sf": "Semis",
    "sim.final": "Final",
    "sim.champion": "Campeón",

    // ---- evolution metrics ----
    "evo.m.champion": "Campeón",
    "evo.m.final": "Llega a la final",
    "evo.m.sf": "Semifinalista",
    "evo.m.qf": "Cuartofinalista",
    "evo.m.knockout": "Pasa de grupo",

    // ---- champion tab ----
    "champion.none": "No hay simulaciones generadas todavía.",
    "champion.title": "¿Quién ganará el Mundial?",
    "champion.lede": (p) => `${p.team} encabeza la lista con un ${p.pct} de probabilidades de levantar el trofeo; le sigue ${p.team2} con un ${p.pct2}.`,
    "champion.intro": (p) => `Probabilidades de alcanzar cada ronda según la simulación Monte Carlo del torneo completo (snapshot del ${p.date}, ${p.odds ? "con cuotas de mercado" : "solo modelo, sin cuotas"}). Los partidos ya jugados entran con su resultado real.`,

    // ---- legend ----
    "legend.clear": "Deseleccionar todas",
    "legend.add": "Clic para resaltar",
    "legend.remove": "Clic para quitar",

    // ---- evolution tab ----
    "evo.none": "No hay simulaciones generadas.",
    "evo.title": "Evolución día a día",
    "evo.note": (p) => `Las ${p.total} selecciones (en gris) por «${p.metric}» (${p.odds ? "con cuotas" : "sin cuotas"}); resaltadas las ${p.selected} elegidas. Clic en una bandera de la leyenda para resaltarla o quitarla.${p.oneDay ? " Solo hay un día generado: la línea crecerá con cada nuevo snapshot." : ""}`,

    // ---- groups tab ----
    "groups.none": "No hay standings generados.",
    "groups.title": "Fase de grupos",
    "groups.intro": (p) => `Probabilidad de cada posición final y de clasificarse para dieciseisavos (1º, 2º o uno de los 8 mejores terceros). Snapshot del ${p.date}.`,

    // ---- calendar tab ----
    "cal.title": "Calendario y predicciones partido a partido",
    "cal.intro": "Para cada partido se muestra la predicción vigente ese día (el último snapshot anterior o igual a la fecha del partido) y las cuotas 1X2 si están disponibles. Los partidos eliminatorios aparecerán cuando se conozcan los cruces.",
    "cal.none": "No hay partidos en results.csv.",
    "round.group": (p) => `Fase de grupos · Jornada ${p.n}`,
    "round.r32": "Dieciseisavos de final",
    "round.r16": "Octavos de final",
    "round.qf": "Cuartos de final",
    "round.sf": "Semifinales",
    "round.p3": "Tercer puesto",
    "round.f": "Final",
    "round.ko": "Eliminatorias",
    "badge.exact": "Exacta",
    "badge.outcome": "1X2 ✓",
    "badge.miss": "Fallo",
    "match.card_title": "Clic para ver la matriz de marcadores",
    "match.vs": "vs",
    "match.pred_prefix": "Pred.",
    "match.strategy_title": (p) => `Estrategia: ${p.strategy}`,
    "match.mode_title": "Marcador más probable (modelo / cuotas)",
    "match.no_pred": "Sin predicción para este partido",
    "match.odds": "Cuotas:",
    "match.prob_title": "Probabilidades 1 / X / 2",
    "match.aet": "pró.",
    "match.aet_title": (p) => `Tras prórroga — a los 90' iba ${p.score} (sobre eso se evalúa el pick)`,
    "match.pens": "pen.",
    "match.pens_title": (p) => `${p.team} ganó en los penaltis — a los 90' iba ${p.score} (sobre eso se evalúa el pick)`,

    // ---- score matrix modal ----
    "matrix.loading": "Ajustando el modelo… (la primera vez tarda unos segundos)",
    "matrix.error": (p) => `Error calculando la matriz: ${p.msg}`,
    "matrix.sub": (p) => `Probabilidad (%) de cada marcador exacto · modelo ${p.engine} del ${p.date} · ${p.odds ? "con cuotas de mercado" : "solo modelo"} · 1X2: ${p.p1} / ${p.px} / ${p.p2}`,
    "matrix.away_goals": (p) => `Goles de ${p.team} →`,
    "matrix.home_goals": (p) => `${p.team} ↓`,
    "matrix.legend_pick": "predicción Penka",
    "matrix.legend_real": "resultado a los 90'",

    // ---- refresh runtime ----
    "refresh.starting": "(arrancando…)",
    "refresh.done": "\n\n✔ Terminado. Recargando datos…",
    "refresh.failed": (p) => `\n\n✘ Falló (código ${p.code}).`,

    // ---- init ----
    "init.error": (p) => `Error cargando datos: ${p.msg}. ¿Está el servidor corriendo desde la raíz del proyecto?`,

    // ---- connectivity tab ----
    "conn.loading": "Calculando la conectividad… (la primera vez ajusta el modelo y tarda unos segundos)",
    "conn.error": (p) => `Error calculando la conectividad: ${p.msg}`,
    "conn.title": "¿Quién ancla a quién? Conectividad entre confederaciones",
    "conn.intro": (p) => `Anclar una confederación es fijar su nivel respecto al de las demás, para que los equipos de bloques distintos sean comparables en una misma escala. El modelo solo puede hacerlo a través de los partidos «puente» entre confederaciones. Donde hay pocos puentes, la escala de una confederación queda mal anclada al resto y sus ratings pueden inflarse o desinflarse en bloque — una limitación conocida del modelo (p. ej. la AFC, y en menor medida la CONMEBOL). El peso es el mismo del entrenamiento (decaimiento temporal con vida media de 2 años, datos hasta el ${p.date}).`,
    "conn.scatter_h3": "Los 48 clasificados: ¿cuánto se apoya cada rating en partidos puente?",
    "conn.scatter_note": "Cuanto más a la izquierda, más depende el rating del juego interno de su confederación (y de lo bien anclada que esté). Clic en una bandera para ver el desglose.",
    "conn.legend_unknown": "Sin conf. inferida",
    "conn.detail_prompt": "Haz clic en una bandera del gráfico (o en una fila de la tabla) para ver contra qué confederaciones ha jugado cada equipo.",
    "conn.stat_rating": "rating",
    "conn.stat_matches": "partidos en la ventana",
    "conn.stat_bridge": "del peso es puente",
    "conn.stat_opp": "rating del rival medio",
    "conn.bar_title": "Reparto del peso de entrenamiento según la confederación del rival",
    "conn.bar_unknown_title": (p) => `Rivales sin confederación inferida: ${p.pct}`,
    "conn.matrix_h3": "Matriz de conectividad",
    "conn.matrix_note": "Cada celda: fracción del peso de entrenamiento de la confederación de la fila jugada contra la de la columna. La diagonal (punteada) es el juego interno; todo lo demás son puentes.",
    "conn.scatter_xaxis": "Peso de entrenamiento contra otras confederaciones (partidos puente)",
    "conn.scatter_yaxis": "Rating del modelo (ataque − defensa)",
    "conn.table_h3": "Detalle por equipo",
    "conn.heat_conf": "Conf.",

    // ---- rankings tab ----
    "rank.loading": "Cargando rankings…",
    "rank.live_loading": "No hay snapshots de rankings generados. Ajustando el modelo en vivo… (la primera vez tarda unos segundos)",
    "rank.error": (p) => `Error cargando los rankings: ${p.msg}`,
    "rank.title": (p) => `Rankings del modelo · ${p.engine}`,
    "rank.intro": (p) => `Fuerza de cada selección según el motor <b>${p.engine}</b>, ordenada por ${p.sort} (${p.source}). El <b>rating</b> es ataque − defensa: cuanto mayor, mejor. ${p.hasElo ? "La <b>puntuación Elo</b> es la del propio motor (regla de eloratings.net). " : ""}El <b>rival medio</b> es el rating medio (ponderado por el peso de entrenamiento) de los equipos contra los que ha jugado: una medida de la dificultad media de sus partidos. Usa el selector de <b>Motor</b> de la cabecera para cambiar de modelo.`,
    "rank.sort_elo": "puntuación Elo",
    "rank.sort_rating": "rating (ataque − defensa)",
    "rank.source_live": (p) => `ajuste en vivo a ${p.date} (genera snapshots con <code>scripts/generate_rankings.sh</code> para ver la evolución)`,
    "rank.source_snap": (p) => `snapshot del ${p.date}`,
    "rank.class_h3": (p) => `Ranking ${p.live ? "(en vivo)" : "del " + p.date}`,
    "rank.evo_h3": "Evolución del ranking",
    "rank.evo_note": (p) => `Las ${p.total} selecciones (en gris) por «${p.metric}»; resaltadas las ${p.selected} elegidas. Clic en una bandera de la leyenda para resaltarla o quitarla. ${p.oneDay ? "Solo hay un día generado: la línea crecerá con cada nuevo snapshot." : p.n + " snapshots."}${p.isRank ? " Eje invertido: el 1.º arriba." : ""}`,
    "rank.m.rating": "Rating (ataque − defensa)",
    "rank.m.elo": "Puntuación Elo",
    "rank.m.rank": "Posición en el ranking",
    "rank.m.opp": "Dificultad de rivales",

    // ---- documentation tab ----
    "docs.html": () => `
      <h2 class="section">Cómo funciona el predictor</h2>
      <p class="note">Para cada partido del Mundial 2026, wcpred elige el marcador que maximiza los <b>puntos Penka esperados</b> — que no es el marcador más probable. Aquí está todo el proceso, en forma de preguntas: haz clic en una para desplegarla. Pensado para el curioso técnico — con fórmulas, sin derivaciones.</p>

      <pre class="doc-flow">resultados (2015→) ──→ motor (dc / elo / bayes) ──→ matriz P[marcador]
                                                        │
cuotas ──→ 1X2 sin margen ──────────────────────────────┤  (reescala el 1X2)
                                                        ├─→ pick (máx. puntos Penka esperados)
                                                        └─→ Monte Carlo ──→ grupos · cuadro · campeón</pre>

      <details class="card doc-card">
        <summary>1 · ¿De dónde salen las predicciones?</summary>
        <div class="doc-body">
          <p>Solo los <b>resultados de los partidos</b> entrenan el modelo: todos los internacionales absolutos desde 2015, del dataset público de martj42. Cada partido entra con un peso <code>w = exp(−ln 2 · días / 730)</code> — vida media de dos años, así que un resultado de hace cuatro años cuenta la cuarta parte que uno de ayer. Los amistosos van a peso completo (penalizarlos se probó y empeoraba todas las métricas), y las selecciones con menos de 10 partidos se descartan.</p>
          <p>Los <b>goles esperados (xG)</b> se probaron y se dejaron fuera: mezclarlos en los goles de entrenamiento mejora una pizca el log-loss pero pierde puntos de porra de forma monótona, y la cobertura de FotMob solo empieza a mediados de 2022. El Mundial se predice sin xG.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>2 · ¿Cómo se convierte el historial en probabilidades de marcador?</summary>
        <div class="doc-body">
          <p>Cada selección tiene dos parámetros latentes — <b>fuerza ofensiva</b> <code>atk</code> y <b>debilidad defensiva</b> <code>dfn</code> — más un término global de ventaja de campo. Los goles esperados de un partido son <code>λ = exp(atk_local + dfn_visitante + home)</code> para el local y <code>μ = exp(atk_visitante + dfn_local)</code> para el visitante.</p>
          <p>Dos distribuciones de Poisson con esas medias dan la <b>probabilidad de cada marcador exacto</b>, una matriz sobre la rejilla de 0–8 goles. La <b>corrección rho</b> de Dixon-Coles reajusta después las cuatro celdas de marcadores bajos (0-0, 1-0, 0-1, 1-1), donde dos Poisson independientes se sabe que fallan. Los parámetros se ajustan por máxima verosimilitud, ponderada con el decaimiento anterior.</p>
          <p>Todo lo que viene después — el pick, las tablas de grupos, las probabilidades de campeón — consume esta única matriz.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>3 · ¿Qué pintan las cuotas de las casas de apuestas?</summary>
        <div class="doc-body">
          <p>El mercado precia lo que el modelo no ve — lesiones, sanciones, onces, al minuto. Con el interruptor <b>«Cuotas de mercado»</b> activado, las cuotas 1X2 se convierten a probabilidades y se les quita el margen del corredor normalizándolas para que sumen 1; después <code>λ</code> y <code>μ</code> se reescalan hasta que la matriz del modelo reproduce <i>exactamente</i> ese 1X2 del mercado.</p>
          <p>Es decir: el reparto victoria/empate/victoria es 100% mercado, y el motor solo da forma a cómo se distribuyen los marcadores <i>dentro</i> de cada resultado — las cuotas no dicen nada del marcador exacto. Las cuotas nunca entrenan el modelo; entran solo al predecir. Desactiva el interruptor para ver el motor por sí solo. (Los cruces sintéticos del simulador no tienen cuotas, así que las eliminatorias son siempre solo-modelo.)</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>4 · ¿Por qué no elige el marcador más probable?</summary>
        <div class="doc-body">
          <p>Penka premia el marcador exacto, la diferencia de goles correcta (o el empate) o solo el ganador — y más en las rondas finales: <b>5/3/2</b> puntos en grupos, <b>8/5/3</b> en dieciseisavos y octavos, <b>11/7/5</b> de cuartos en adelante. Dada la matriz, cada marcador candidato tiene un valor esperado <code>E[pts] = Σ P[h,a] · puntos(pick, (h,a))</code>, y el pick por defecto es el argmax. Ese optimizador tiende a marcadores «seguros» como el 1-0 al favorito: cubren a la vez exacto, diferencia y ganador.</p>
          <p>Resulta que es <i>demasiado</i> conservador. El interruptor <b>«Marcador más probable»</b> (activado por defecto) cambia a una segunda estrategia: el resultado 1X2 más probable y, dentro de él, el marcador más probable. En el backtest puntúa un <b>+8%</b> (643 frente a 594 puntos) — no por predecir empates (casi no predice ninguno, igual que el optimizador) sino por elegir mejores marcadores de victoria: 2-0 o 2-1 donde el pick de valor esperado se conformaba con el 1-0.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>5 · ¿De dónde salen las probabilidades de campeón y de grupo?</summary>
        <div class="doc-body">
          <p>La misma matriz por partido, usada al revés: en vez de elegir un marcador, se <b>muestrea</b>. Cada grupo se simula <b>1.000.000 de veces</b>; el torneo completo — tablas de grupos, los 8 mejores terceros según el reparto oficial del Anexo C de la FIFA, y el cuadro desde dieciseisavos hasta la final — <b>100.000 veces</b>. La probabilidad de que una selección gane su grupo, cruce cada ronda o levante el trofeo es simplemente la frecuencia en las simulaciones.</p>
          <p>Los partidos ya jugados entran con su resultado real, así que las probabilidades se actualizan según avanza el torneo. Los empates de grupo se deshacen por puntos, diferencia de goles y goles a favor; el head-to-head no está modelado (lo que queda empatado se sortea). Las eliminatorias se juegan en campo neutral.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>6 · ¿Funciona de verdad? ¿Cómo se ha validado?</summary>
        <div class="doc-body">
          <p>No se puede validar con un único torneo futuro, así que todo se juzga <b>backtesteando seis pasados</b> — los Mundiales de 2018 y 2022, las Euros de 2021 y 2024, las Copas América de 2021 y 2024, ~290 partidos — reajustando el modelo antes de cada jornada solo con los datos disponibles entonces, exactamente como corre en vivo.</p>
          <p>Las decisiones de ajuste van por <b>RPS y log-loss</b> (métricas probabilísticas de poca varianza); los puntos Penka desempatan. El modelo de producción queda en RPS ≈ 0,189 y <b>~2,2 puntos Penka por partido</b> con la estrategia por defecto de la web (643 puntos; 594 con el pick de valor esperado). Cada hiperparámetro se eligió así — y la mayoría de las ideas probadas (recortar goleadas, sobreponderar partidos entre confederaciones, priors externos de Elo…) <i>perdieron</i> y se rechazaron. Lo que ves es lo que sobrevivió.</p>
        </div>
      </details>

      <details class="card doc-card">
        <summary>7 · ¿Qué no ve el modelo?</summary>
        <div class="doc-body">
          <p><b>Confederaciones mal conectadas.</b> Los bloques solo son comparables a través de los escasos partidos «puente» entre ellos (~12% del peso de entrenamiento). Donde hay pocos puentes — la AFC sobre todo — los ratings de un bloque entero pueden derivar: que Australia esté por delante de EE. UU. es mitad forma real, mitad artefacto de un calendario intra-AFC fácil que el modelo no consigue descontar del todo. Se probaron y rechazaron varias correcciones (mira la pestaña <b>Conectividad</b>); en la práctica las cuotas lo corrigen donde importa.</p>
          <p><b>Predice pocos empates.</b> El modelo casi nunca da a un empate más de un ~30% de probabilidad, así que casi nunca lo elige — un límite de calibración de las probabilidades, no del paso de selección.</p>
          <p><b>Eliminatorias en campo neutral.</b> Los cruces del cuadro no llevan sede, así que ningún anfitrión tiene ventaja de campo tras la fase de grupos — las probabilidades de ronda profunda de los tres anfitriones quedan algo infravaloradas. Y las <b>lesiones, sanciones y alineaciones</b> solo llegan al modelo a través de las cuotas.</p>
        </div>
      </details>

      <details class="card doc-card doc-appendix">
        <summary>Apéndice · Los tres motores, a fondo</summary>
        <div class="doc-body">
          <p>Los tres motores comparten una interfaz: cada uno debe producir un rating de ataque y otro de defensa por selección, un término de campo y una rho — y a partir de ahí el <i>mismo</i> código construye la matriz de marcadores. Por eso el selector <b>Motor</b> los intercambia libremente en todas las pestañas: solo se diferencian en cómo obtienen los ratings.</p>

          <h4>Dixon-Coles (dc) — el motor de producción</h4>
          <p>El ajuste Poisson ponderado de la pregunta 2, resuelto con L-BFGS-B con gradiente analítico y una restricción de identificabilidad (los ratings de ataque promedian cero — solo importan las diferencias). La corrección de marcadores bajos <b>rho</b> se estima después por búsqueda en rejilla sobre las cuatro celdas (0-0, 1-0, 0-1, 1-1) donde los goles dejan de comportarse de forma independiente. Cada hiperparámetro — ventana desde 2015, vida media de dos años, amistosos a peso completo — se eligió con el backtest de seis torneos, y varios refinamientos probados (recortar goleadas, sobreponderar partidos puente, contraer hacia un centro global) <i>perdieron</i> y se rechazaron. Ajusta en segundos, es reproducible byte a byte — la regla de regenerabilidad del proyecto — y gana el backtest: RPS 0,1890, 594 puntos con el pick de valor esperado.</p>

          <h4>Elo — primero un rating dinámico, después goles</h4>
          <p>Dos etapas. La primera itera la actualización de eloratings.net sobre todos los internacionales desde 2006, en orden cronológico: <code>R' = R + K · G · (W − We)</code>, donde <code>We = 1/(10^(−dr/400) + 1)</code> es el resultado esperado dada la diferencia de rating <code>dr</code> (+100 si se juega en casa), <code>W</code> es el resultado real (1/½/0), <code>K</code> depende de la competición — 60 en un Mundial, 50 en finales continentales, 40 en clasificatorios, 30 en el resto, 20 en amistosos — y <code>G</code> crece con el margen de goles (1 / 1,5 / 1,75, y +⅛ por gol extra). Junto al rating actual guarda un <b>Elo mediano a 10 años</b> como segunda covariable: la clase histórica de una selección, separada de su forma actual.</p>
          <p>La segunda etapa es una regresión Poisson ponderada de 4 parámetros que convierte esas dos diferencias de Elo en goles esperados, <code>log λ = β0 + βh + βe·Δelo + βlt·Δelo_lt</code> (con signos opuestos para <code>μ</code>), seguida de la misma búsqueda de rho — y de ahí sale el mismo tipo de matriz. Queda algo por detrás del dc en el backtest (~587 pts): una regla de actualización partido a partido lleva menos información que reajustar todos los ratings a la vez contra el historial ponderado completo. Afinar sus mandos (una K por confederación) gana algunos puntos, pero el motor va con la regla publicada sin tocar.</p>

          <h4>Bayesiano — el mismo modelo, con incertidumbre honesta</h4>
          <p>La misma verosimilitud Dixon-Coles ponderada, ajustada por MCMC en Stan (CmdStan, 4 cadenas) con un prior jerárquico apuntado directamente a la limitación de conectividad: cada rating se descompone en un <b>desplazamiento de confederación más una desviación individual</b>, <code>atk_i = atk_conf(i) + σ·z_i</code>, con una Student-t en las desviaciones para no aplanar a los outliers legítimos (Argentina). Los desplazamientos son compartidos por todo un bloque, así que los partidos intra-confederación no pueden moverlos — <b>solo los partidos puente pueden</b>, exactamente la restricción que el ajuste por máxima verosimilitud no sabe expresar. (Su veredicto sobre el caso Australia es instructivo: la inflación sobrevive, porque vive en la desviación <i>individual</i> de Australia, no en el desplazamiento de la AFC.)</p>
          <p>Su otra diferencia es lo que pasa tras el ajuste: en vez de enchufar ratings puntuales, la matriz de marcadores es la <b>media de las matrices que produce cada muestra del posterior</b>, así que la incertidumbre de los ratings — máxima a través de los puentes débiles — ensancha de verdad la distribución de marcadores. Una variante dinámica sustituye los pesos de decaimiento por un paseo aleatorio (la fuerza de cada selección evoluciona por bloques semestrales); es la configuración bayesiana más fuerte y empata con el dc en el backtest sin batirlo. A ~150 s por ajuste, solo está disponible en la versión local.</p>

          <p>La web usa <b>Dixon-Coles (dc)</b> por defecto, el mismo motor que la CLI y los snapshots de producción. Con las cuotas de mercado activadas la elección apenas importa: el 1X2 sale del mercado y el motor solo da forma a los marcadores, así que las diferencias entre motores son pequeñas — pero mantener dc por defecto alinea la web con producción.</p>
        </div>
      </details>`,
  },
};

function currentLang() {
  // try/catch: durante la inicialización de `const state` en app.js, `state`
  // está en la zona muerta temporal y hasta `typeof state` lanza ReferenceError.
  try { if (state && state.lang) return state.lang; } catch (e) { /* TDZ */ }
  let saved = null;
  try { saved = localStorage.getItem("wcpred_lang"); } catch (e) { /* modo privado */ }
  return (saved === "es" || saved === "en") ? saved : "en";
}

function t(key, params) {
  const dict = I18N[currentLang()] || I18N.en;
  let v = dict[key];
  if (v === undefined) v = I18N.en[key];
  if (v === undefined) return key;
  return typeof v === "function" ? v(params || {}) : v;
}
