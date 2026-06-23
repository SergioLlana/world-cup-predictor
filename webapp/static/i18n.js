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
    "match.no_pred": "No prediction for this match",
    "match.odds": "Odds:",
    "match.prob_title": "1 / X / 2 probabilities",

    // ---- score matrix modal ----
    "matrix.loading": "Fitting the model… (first time takes a few seconds)",
    "matrix.error": (p) => `Error computing the matrix: ${p.msg}`,
    "matrix.sub": (p) => `Probability (%) of each exact score · ${p.engine} model of ${p.date} · ${p.odds ? "with market odds" : "model only"} · 1X2: ${p.p1} / ${p.px} / ${p.p2} · Pred. <b>${p.pick}</b>`,
    "matrix.away_goals": (p) => `${p.team} goals →`,
    "matrix.home_goals": (p) => `${p.team} ↓`,
    "matrix.legend_pick": "Penka prediction",
    "matrix.legend_real": "real result",

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
    "conn.intro": (p) => `Anchoring a confederation means fixing its level relative to the others, so teams from different blocs are comparable on the same scale. The model can only do this through «bridge» matches between confederations. Where there are few bridges, a confederation's scale is poorly anchored to the rest and its ratings can inflate or deflate as a bloc — the limitation documented in <code>docs/known-limitations.md</code> (e.g. the AFC, and to a lesser extent CONMEBOL). The weight is the same one used in training (time decay with a 2-year half-life, data up to ${p.date}).`,
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
      <p class="note">wcpred predicts every World Cup 2026 scoreline. Here is the whole process, end to end, and where the interchangeable engines and the betting odds fit in. It is not very technical on purpose.</p>

      <div class="card doc-card">
        <h3>1 · The data that trains the model</h3>
        <p>Only <b>match results</b> train the model: every senior international since 2015, downloaded from a public dataset. Recent and competitive matches weigh more — a result's weight halves every two years. Optionally, <b>expected goals (xG)</b> can be blended in to smooth out finishing luck, but it is turned off for the World Cup because the coverage is incomplete.</p>
      </div>

      <div class="card doc-card">
        <h3>2 · The engine: from ratings to a score matrix</h3>
        <p>Each engine turns that history into two numbers per team — <b>attacking strength</b> and <b>defensive frailty</b> — plus a home-field bonus, and from them builds a full <b>probability matrix</b>: the chance of every exact scoreline (0-0, 1-0, 2-1, …). The engine is <b>interchangeable</b>; all three produce the same kind of matrix:</p>
        <ul>
          <li><b>Dixon-Coles</b> (default) — a weighted Poisson goals model with a correction for low scores. The production engine.</li>
          <li><b>Elo</b> — a points system where each team gains or loses points after every match depending on the opponent and the margin, then converted into goal expectations.</li>
          <li><b>Bayesian</b> — the same Dixon-Coles but fit with uncertainty, carrying how unsure it is about each rating into the scorelines. (Available in the local version only.)</li>
        </ul>
      </div>

      <div class="card doc-card">
        <h3>3 · The odds: a reality check at prediction time</h3>
        <p>The betting market prices things the model cannot see — injuries, suspensions, rotation. So when the <b>«Market odds»</b> toggle is on, the win/draw/win probabilities come entirely from the market and the engine only shapes the distribution of scorelines <i>within</i> each result. Turn the toggle off to see the engine on its own. The odds never train the model: they are blended in only at prediction time.</p>
      </div>

      <div class="card doc-card">
        <h3>4 · The pick: not the most likely score</h3>
        <p>The clever bit: the predictor does <b>not</b> pick the most likely scoreline. It picks the one that <b>maximises the expected Penka points</b>, given the scoring (exact result / right goal-difference-or-draw / right winner, worth more in the later rounds). That is why it leans towards «safe» scores like 1-0 or 2-1 — they cover more outcomes that still score points. The <b>«Most likely score»</b> toggle switches to a slightly different rule that tends to score a bit better.</p>
      </div>

      <div class="card doc-card">
        <h3>5 · Groups and bracket: Monte Carlo</h3>
        <p>For the group tables and the full bracket the same per-match matrix is used the other way around: instead of choosing one score, it <b>draws thousands of random tournaments</b> from the probabilities and counts how often each team wins its group, advances through each round and lifts the trophy.</p>
      </div>

      <div class="card doc-card">
        <h3>The flow at a glance</h3>
        <pre class="doc-flow">results ─┐
xG ──────┴─→ engine ──→ score matrix ──┐
                                       ├─→ best pick (max expected Penka points)
odds ──→ market 1X2 ────────────────────┘
                                       └─→ Monte Carlo ──→ groups + bracket</pre>
      </div>`,
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
    "match.no_pred": "Sin predicción para este partido",
    "match.odds": "Cuotas:",
    "match.prob_title": "Probabilidades 1 / X / 2",

    // ---- score matrix modal ----
    "matrix.loading": "Ajustando el modelo… (la primera vez tarda unos segundos)",
    "matrix.error": (p) => `Error calculando la matriz: ${p.msg}`,
    "matrix.sub": (p) => `Probabilidad (%) de cada marcador exacto · modelo ${p.engine} del ${p.date} · ${p.odds ? "con cuotas de mercado" : "solo modelo"} · 1X2: ${p.p1} / ${p.px} / ${p.p2} · Pred. <b>${p.pick}</b>`,
    "matrix.away_goals": (p) => `Goles de ${p.team} →`,
    "matrix.home_goals": (p) => `${p.team} ↓`,
    "matrix.legend_pick": "predicción Penka",
    "matrix.legend_real": "resultado real",

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
    "conn.intro": (p) => `Anclar una confederación es fijar su nivel respecto al de las demás, para que los equipos de bloques distintos sean comparables en una misma escala. El modelo solo puede hacerlo a través de los partidos «puente» entre confederaciones. Donde hay pocos puentes, la escala de una confederación queda mal anclada al resto y sus ratings pueden inflarse o desinflarse en bloque — la limitación documentada en <code>docs/known-limitations.md</code> (p. ej. la AFC, y en menor medida la CONMEBOL). El peso es el mismo del entrenamiento (decaimiento temporal con vida media de 2 años, datos hasta el ${p.date}).`,
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
    "rank.class_h3": (p) => `Clasificación ${p.live ? "(en vivo)" : "del " + p.date}`,
    "rank.evo_h3": "Evolución del ranking",
    "rank.evo_note": (p) => `Las ${p.total} selecciones (en gris) por «${p.metric}»; resaltadas las ${p.selected} elegidas. Clic en una bandera de la leyenda para resaltarla o quitarla. ${p.oneDay ? "Solo hay un día generado: la línea crecerá con cada nuevo snapshot." : p.n + " snapshots."}${p.isRank ? " Eje invertido: el 1.º arriba." : ""}`,
    "rank.m.rating": "Rating (ataque − defensa)",
    "rank.m.elo": "Puntuación Elo",
    "rank.m.rank": "Posición en el ranking",
    "rank.m.opp": "Dificultad de rivales",

    // ---- documentation tab ----
    "docs.html": () => `
      <h2 class="section">Cómo funciona el predictor</h2>
      <p class="note">wcpred predice todos los marcadores del Mundial 2026. Aquí está el proceso completo, de principio a fin, y dónde encajan los motores intercambiables y las cuotas de las casas de apuestas. A propósito, no es muy técnico.</p>

      <div class="card doc-card">
        <h3>1 · Los datos que entrenan el modelo</h3>
        <p>Solo los <b>resultados de los partidos</b> entrenan el modelo: todos los internacionales absolutos desde 2015, descargados de un conjunto de datos público. Los partidos recientes y competitivos pesan más — el peso de un resultado se reduce a la mitad cada dos años. Opcionalmente se pueden mezclar los <b>goles esperados (xG)</b> para suavizar la suerte de cara a portería, pero está desactivado para el Mundial porque la cobertura es incompleta.</p>
      </div>

      <div class="card doc-card">
        <h3>2 · El motor: de los ratings a una matriz de marcadores</h3>
        <p>Cada motor convierte ese histórico en dos números por selección — <b>fuerza ofensiva</b> y <b>debilidad defensiva</b> — más un plus de jugar en casa, y con ellos construye una <b>matriz de probabilidad</b> completa: la probabilidad de cada marcador exacto (0-0, 1-0, 2-1, …). El motor es <b>intercambiable</b>; los tres producen el mismo tipo de matriz:</p>
        <ul>
          <li><b>Dixon-Coles</b> (por defecto) — un modelo de goles Poisson ponderado con una corrección para los marcadores bajos. Es el motor de producción.</li>
          <li><b>Elo</b> — un sistema de puntos donde cada selección sube o baja tras cada partido según el rival y la diferencia de goles, y luego se traduce a goles esperados.</li>
          <li><b>Bayesiano</b> — el mismo Dixon-Coles pero ajustado con incertidumbre, que arrastra hasta los marcadores lo poco o mucho que sabe de cada rating. (Solo en la versión local.)</li>
        </ul>
      </div>

      <div class="card doc-card">
        <h3>3 · Las cuotas: un contraste con la realidad al predecir</h3>
        <p>El mercado de apuestas precia cosas que el modelo no ve — lesiones, sanciones, rotaciones. Por eso, cuando el interruptor <b>«Cuotas de mercado»</b> está activado, las probabilidades de victoria/empate/victoria salen íntegramente del mercado y el motor solo da forma al reparto de marcadores <i>dentro</i> de cada resultado. Desactívalo para ver el motor por sí solo. Las cuotas nunca entrenan el modelo: se mezclan solo en el momento de predecir.</p>
      </div>

      <div class="card doc-card">
        <h3>4 · La elección: no el marcador más probable</h3>
        <p>Lo ingenioso: el predictor <b>no</b> elige el marcador más probable. Elige el que <b>maximiza los puntos Penka esperados</b>, según el baremo (resultado exacto / diferencia-de-goles-o-empate / ganador, que valen más en las rondas finales). Por eso tiende a marcadores «seguros» como 1-0 o 2-1 — cubren más resultados que también puntúan. El interruptor <b>«Marcador más probable»</b> cambia a una regla ligeramente distinta que suele puntuar algo mejor.</p>
      </div>

      <div class="card doc-card">
        <h3>5 · Grupos y cuadro: Monte Carlo</h3>
        <p>Para las tablas de grupos y el cuadro completo se usa la misma matriz por partido al revés: en vez de elegir un marcador, <b>sortea miles de torneos aleatorios</b> a partir de las probabilidades y cuenta con qué frecuencia cada selección gana su grupo, cruza cada ronda y levanta el trofeo.</p>
      </div>

      <div class="card doc-card">
        <h3>El flujo de un vistazo</h3>
        <pre class="doc-flow">resultados ─┐
xG ─────────┴─→ motor ──→ matriz de marcadores ──┐
                                                 ├─→ mejor pick (máx. puntos Penka esperados)
cuotas ──→ 1X2 del mercado ───────────────────────┘
                                                 └─→ Monte Carlo ──→ grupos + cuadro</pre>
      </div>`,
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
