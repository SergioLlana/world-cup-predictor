/* Frontend de wcpred: lee la API JSON de webapp/server.py y pinta las vistas.
   Sin dependencias externas: las gráficas son SVG generado a mano. */

const state = {
  approach: "odds",          // toggle de cuotas: odds | history
  engine: "elo",             // motor: dc | elo | bayes
  strategy: "outcome",       // toggle de estrategia de marcador: ev | outcome
  tab: "champion",
  snapshotDate: null,        // null = último disponible
  evoMetric: "p_champion",
  meta: null,
  matches: null,
  cache: {},                 // por "<approach>|<engine>": {sims, groups, picks}
  connectivity: null,                  // /api/connectivity (solo modelo, sin approach)
  connLoading: false,
  connSelected: null,                  // equipo con el desglose abierto
  rankings: {},                        // por motor: {snapshots:[...], live:data|null}
  rankLoading: false,
  rankMetric: "rating",                // métrica de la gráfica de evolución
  evoSelected: null,                   // Set de equipos resaltados (null = top por defecto)
  rankSelected: null,                  // idem para la gráfica de rankings
};

// Etiquetas legibles para cada motor (las claves vienen del backend).
const ENGINE_LABELS = { dc: "Dixon-Coles", elo: "Elo", bayes: "Bayesiano" };
// Etiquetas legibles para cada estrategia de selección de marcador.
const STRATEGY_LABELS = {
  ev: "máximo valor esperado",
  outcome: "marcador más probable",
};
// Marcador de una fila de picks según la estrategia activa. Las filas nuevas
// traen pick_outcome; los snapshots antiguos (solo ev) caen a `pick`.
const pickOf = (row) =>
  (state.strategy === "outcome" && row.pick_outcome) ? row.pick_outcome : row.pick;
const cacheKey = (ap = state.approach, eng = state.engine) => `${ap}|${eng}`;
// Datos del approach+engine vigente; {} si aún no se han cargado.
const curCache = () => state.cache[cacheKey()] || {};

const $ = (sel) => document.querySelector(sel);
const fetchJSON = async (url) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

// ---------------------------------------------------------------- helpers

const teamInfo = (name) => state.meta.teams[name] || { code: null, es: name };
const teamES = (name) => teamInfo(name).es;
const flagImg = (name, big = false) => {
  const t = teamInfo(name);
  if (!t.code) return "";
  return `<img class="flag${big ? " big" : ""}" src="/flags/${t.code}.svg" alt="${t.es}">`;
};

const pct = (p) => {
  if (p == null || isNaN(p)) return "–";
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return Math.round(p * 100) + "%";
};

// celda sombreada según probabilidad (estilo 538)
const pcell = (p) => {
  const a = Math.min((p ?? 0) * 1.05, 0.92);
  const dark = (p ?? 0) > 0.55 ? " dark" : "";
  return `<td class="pcell${dark}" style="background:rgba(15,138,138,${a.toFixed(3)})">${pct(p)}</td>`;
};

const fmtDay = (iso) =>
  new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" })
    .format(new Date(iso + "T12:00:00"));

const fmtShort = (iso) =>
  new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" })
    .format(new Date(iso + "T12:00:00"));

// paso "bonito" (1/2/5 × 10^k) para ~6 líneas de rejilla en un rango dado
function niceStep(span) {
  const raw = (span || 1) / 6;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  return (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
}

// snapshot vigente: el último con fecha <= la seleccionada (o el último de todos)
function pickSnapshot(snapshots, date) {
  if (!snapshots.length) return null;
  let best = null;
  for (const s of snapshots) if (!date || s.date <= date) best = s;
  return best || snapshots[0];
}

// ------------------------------------------------------------- data load

async function loadData(ap = state.approach, eng = state.engine) {
  const key = cacheKey(ap, eng);
  if (state.cache[key]?.sims) return;
  const q = `approach=${ap}&engine=${eng}`;
  const [sims, groups, picks] = await Promise.all([
    fetchJSON(`/api/sims?${q}`),
    fetchJSON(`/api/groups?${q}`),
    fetchJSON(`/api/picks?${q}`),
  ]);
  state.cache[key] = { sims: sims.snapshots, groups: groups.snapshots, picks: picks.snapshots };
}

async function reloadAll() {
  state.cache = {};
  state.connectivity = null;          // un refresco puede traer resultados nuevos
  state.rankings = {};
  const [meta, matches] = await Promise.all([fetchJSON("/api/meta"), fetchJSON("/api/matches")]);
  state.meta = meta;
  state.matches = matches.matches;
  buildEngineSelect();
  await loadData();
  buildSnapshotSelect();
  render();
  // permalink a la matriz de un partido: #match=2026-06-11|Mexico|South Africa
  if (location.hash.startsWith("#match=")) {
    const [date, home, away] = decodeURIComponent(location.hash.slice(7)).split("|");
    activateTab("calendar");
    openMatrix(home, away, date);
  }
}

function buildEngineSelect() {
  const engines = state.meta.engines || ["dc"];
  const sel = $("#engine-select");
  sel.innerHTML = engines
    .map((e) => `<option value="${e}">${ENGINE_LABELS[e] || e}</option>`)
    .join("");
  if (!engines.includes(state.engine)) state.engine = engines[0];
  sel.value = state.engine;
  updateEngineNote();
}

function updateEngineNote() {
  const note = $("#engine-note");
  if (note) note.textContent = ENGINE_LABELS[state.engine] || state.engine;
}

function buildSnapshotSelect() {
  const dates = (state.meta.snapshots.simulations[state.approach] || {})[state.engine] || [];
  const sel = $("#snapshot-select");
  sel.innerHTML = dates.map((d) => `<option value="${d}">${fmtShort(d)}</option>`).join("");
  const wanted = state.snapshotDate && dates.includes(state.snapshotDate)
    ? state.snapshotDate : dates[dates.length - 1];
  if (wanted) sel.value = wanted;
  state.snapshotDate = wanted || null;
  $("#snapshot-note").textContent = wanted
    ? `predicciones del ${fmtDay(wanted)}`
    : "sin predicciones generadas todavía";
}

// ----------------------------------------------------------- ¿Quién gana?

const SIM_COLS = [
  ["p_win_group", "Gana grupo"],
  ["p_r16", "Octavos"],
  ["p_qf", "Cuartos"],
  ["p_sf", "Semis"],
  ["p_final", "Final"],
  ["p_champion", "Campeón"],
];

function renderChampion() {
  const snap = pickSnapshot(curCache().sims, state.snapshotDate);
  const el = $("#tab-champion");
  if (!snap) { el.innerHTML = `<p class="note">No hay simulaciones generadas. Usa «Actualizar datos».</p>`; return; }
  const rows = [...snap.rows].sort((a, b) => b.p_champion - a.p_champion);
  el.innerHTML = `
    <h2 class="section">¿Quién ganará el Mundial?</h2>
    <p class="note">Probabilidades de alcanzar cada ronda según ${snap.rows.length ? "la" : ""} simulación
       Monte Carlo del torneo completo (snapshot del ${fmtDay(snap.date)},
       ${state.approach === "odds" ? "con cuotas de mercado" : "solo modelo, sin cuotas"}).
       Los partidos ya jugados entran con su resultado real.</p>
    <div class="card" style="overflow-x:auto">
      <table class="probs">
        <thead><tr><th class="team-col">Equipo</th>
          ${SIM_COLS.map(([, h]) => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `
          <tr><td class="team-cell">${flagImg(r.team)}${teamES(r.team)}
                <span class="group-chip">${r.group}</span></td>
            ${SIM_COLS.map(([k]) => pcell(r[k])).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

// -------------------------------------------------------------- evolución

const EVO_METRICS = [
  ["p_champion", "Campeón"],
  ["p_final", "Llega a la final"],
  ["p_sf", "Semifinalista"],
  ["p_qf", "Cuartofinalista"],
  ["p_knockout", "Pasa de grupo"],
];
const PALETTE = ["#0f8a8a", "#e8632c", "#3b6bb5", "#c0392b", "#7d3bb5",
                 "#2e8b57", "#d9a514", "#7a4b2c", "#e054a0", "#44443f"];
const EVO_DEFAULT_N = 10;        // selección por defecto: las 10 mejores
const EVO_GRAY = "#cdcbc2";      // color de las selecciones de fondo (no resaltadas)

// color estable por equipo resaltado, en el orden (ordenado por métrica) dado
function evoColors(selectedOrdered) {
  const map = {};
  selectedOrdered.forEach((t, i) => (map[t] = PALETTE[i % PALETTE.length]));
  return map;
}

// leyenda interactiva: todas las selecciones como chips conmutables (clic para
// resaltar/quitar) + botón para deseleccionar todas
function selectableLegend(teamsOrdered, selected, colorOf) {
  const clear = `<button class="evo-clear" type="button"${selected.size ? "" : " disabled"}>Deseleccionar todas</button>`;
  const chips = teamsOrdered.map((t) => {
    const on = selected.has(t);
    return `<span class="item team-toggle ${on ? "on" : "off"}" data-team="${t}" title="Clic para ${on ? "quitar" : "resaltar"}">
      <span class="swatch" style="background:${on ? colorOf[t] : EVO_GRAY}"></span>
      ${flagImg(t)} ${teamES(t)}</span>`;
  }).join("");
  return `<div class="evo-legend selectable">${clear}${chips}</div>`;
}

// conecta los clics de la leyenda; selKey es "evoSelected" o "rankSelected"
function wireLegend(el, selected, selKey, rerender) {
  el.querySelectorAll(".team-toggle").forEach((n) =>
    n.addEventListener("click", () => {
      const t = n.dataset.team;
      if (selected.has(t)) selected.delete(t); else selected.add(t);
      state[selKey] = selected;
      rerender();
    }));
  const clear = el.querySelector(".evo-clear");
  if (clear) clear.addEventListener("click", () => { state[selKey] = new Set(); rerender(); });
}

function renderEvolution() {
  const snaps = curCache().sims;
  const el = $("#tab-evolution");
  if (!snaps.length) { el.innerHTML = `<p class="note">No hay simulaciones generadas.</p>`; return; }

  const metric = state.evoMetric;
  const last = snaps[snaps.length - 1];
  const ordered = [...last.rows].sort((a, b) => b[metric] - a[metric]).map((r) => r.team);
  const selected = state.evoSelected || new Set(ordered.slice(0, EVO_DEFAULT_N));
  const colorOf = evoColors(ordered.filter((t) => selected.has(t)));
  const series = ordered.map((team) => ({
    team, sel: selected.has(team), color: selected.has(team) ? colorOf[team] : EVO_GRAY,
    values: snaps.map((s) => {
      const row = s.rows.find((r) => r.team === team);
      return row ? row[metric] : null;
    }),
  }));

  const W = 920, H = 430, mL = 46, mR = 120, mT = 16, mB = 40;
  const n = snaps.length;
  const maxV = Math.max(0.02, ...series.flatMap((s) => s.values.filter((v) => v != null))) * 1.15;
  const x = (i) => n === 1 ? (mL + W - mR) / 2 : mL + (i * (W - mL - mR)) / (n - 1);
  const y = (v) => mT + (1 - v / maxV) * (H - mT - mB);

  // rejilla horizontal en pasos "bonitos" de %
  const step = maxV > 0.4 ? 0.1 : maxV > 0.15 ? 0.05 : 0.02;
  let grid = "";
  for (let v = 0; v <= maxV; v += step) {
    grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e4e2da"/>
             <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#6b6b66">${Math.round(v * 100)}%</text>`;
  }
  // eje X: fechas (máx ~12 etiquetas)
  const every = Math.max(1, Math.ceil(n / 12));
  let xaxis = "";
  snaps.forEach((s, i) => {
    if (i % every === 0 || i === n - 1)
      xaxis += `<text x="${x(i)}" y="${H - mB + 18}" text-anchor="middle" font-size="11" fill="#6b6b66">${fmtShort(s.date)}</text>`;
  });

  let lines = "";
  // fondo: las selecciones no resaltadas, en gris fino y sin puntos
  series.filter((s) => !s.sel).forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
    if (pts.length > 1)
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${EVO_GRAY}" stroke-width="1.2" opacity="0.7"/>`;
  });
  // primer plano: las resaltadas, en color y con puntos
  const fg = series.filter((s) => s.sel);
  fg.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
    if (pts.length > 1)
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${s.color}" stroke-width="2.5"/>`;
    s.values.forEach((v, i) => {
      if (v != null) lines += `<circle cx="${x(i)}" cy="${y(v)}" r="3.2" fill="${s.color}"/>`;
    });
  });

  // etiquetas finales sin solaparse: se ordenan por altura y se separan 15px
  const labels = fg
    .filter((s) => s.values[n - 1] != null)
    .map((s) => ({ s, v: s.values[n - 1], ly: y(s.values[n - 1]) }))
    .sort((a, b) => a.ly - b.ly);
  labels.forEach((l, i) => {
    if (i > 0 && l.ly < labels[i - 1].ly + 15) l.ly = labels[i - 1].ly + 15;
  });
  labels.forEach((l) => {
    const yEnd = y(l.v);
    if (Math.abs(l.ly - yEnd) > 4)
      lines += `<line x1="${x(n - 1) + 4}" y1="${yEnd}" x2="${x(n - 1) + 18}" y2="${l.ly - 4}" stroke="${l.s.color}" stroke-width="1" opacity=".6"/>`;
    lines += `<text x="${x(n - 1) + 21}" y="${l.ly}" font-size="11.5" font-weight="600" fill="${l.s.color}">${teamES(l.s.team)} ${pct(l.v)}</text>`;
  });

  const metricLabel = EVO_METRICS.find(([k]) => k === metric)[1];
  el.innerHTML = `
    <h2 class="section">Evolución día a día</h2>
    <div class="evo-controls">
      <label>Métrica
        <select id="evo-metric">${EVO_METRICS.map(([k, l]) =>
          `<option value="${k}"${k === metric ? " selected" : ""}>${l}</option>`).join("")}</select>
      </label>
      <span class="note">Las ${ordered.length} selecciones (en gris) por «${metricLabel}»
        (${state.approach === "odds" ? "con cuotas" : "sin cuotas"});
        resaltadas las ${selected.size} elegidas. Clic en una bandera de la leyenda para
        resaltarla o quitarla.
        ${n === 1 ? "Solo hay un día generado: la línea crecerá con cada nuevo snapshot." : ""}</span>
    </div>
    <svg class="evo-svg" viewBox="0 0 ${W} ${H}">${grid}${xaxis}${lines}</svg>
    ${selectableLegend(ordered, selected, colorOf)}`;

  $("#evo-metric").addEventListener("change", (e) => {
    state.evoMetric = e.target.value;
    renderEvolution();
  });
  wireLegend(el, selected, "evoSelected", renderEvolution);
}

// ----------------------------------------------------------------- grupos

function renderGroups() {
  const snap = pickSnapshot(curCache().groups, state.snapshotDate);
  const el = $("#tab-groups");
  if (!snap) { el.innerHTML = `<p class="note">No hay standings generados.</p>`; return; }
  const byGroup = {};
  snap.rows.forEach((r) => (byGroup[r.group] ||= []).push(r));

  el.innerHTML = `
    <h2 class="section">Fase de grupos</h2>
    <p class="note">Probabilidad de cada posición final y de clasificarse para dieciseisavos
      (1º, 2º o uno de los 8 mejores terceros). Snapshot del ${fmtDay(snap.date)}.</p>
    <div class="groups-grid">${Object.keys(state.meta.groups).map((g) => {
      const rows = (byGroup[g] || []).sort((a, b) => b.xPts - a.xPts);
      return `<div class="card group-card"><h3>Grupo ${g}</h3>
        <table class="gtable">
          <thead><tr><th>Equipo</th><th>1º</th><th>2º</th><th>3º</th><th>4º</th>
            <th>Clasifica</th><th>xPts</th></tr></thead>
          <tbody>${rows.map((r) => `
            <tr><td class="team-cell">${flagImg(r.team)}${teamES(r.team)}</td>
              ${pcell(r.P1)}${pcell(r.P2)}${pcell(r.P3)}${pcell(r.P4)}${pcell(r.qualify)}
              <td>${r.xPts?.toFixed(1) ?? "–"}</td></tr>`).join("")}
          </tbody>
        </table></div>`;
    }).join("")}</div>`;
}

// -------------------------------------------------------------- calendario

const ROUND_ORDER = ["j1", "j2", "j3", "r32", "r16", "qf", "sf", "p3", "f", "ko"];

// predicción vigente para un partido: el snapshot de picks más reciente cuya
// fecha sea <= la del partido (lo que se habría pronosticado ese día)
function predictionFor(match) {
  const snap = pickSnapshot(curCache().picks, match.date);
  if (!snap) return null;
  let row = snap.rows.find((r) => r.home === match.home && r.away === match.away && r.date === match.date)
         || snap.rows.find((r) => r.home === match.home && r.away === match.away);
  if (row) return { ...row, snapDate: snap.date };
  row = snap.rows.find((r) => r.home === match.away && r.away === match.home);
  if (row) {
    // Partido con local/visitante invertidos respecto al feed: hay que dar la
    // vuelta a las probabilidades y a AMBOS marcadores antes de elegir cuál
    // mostrar (pickOf lee pick/pick_outcome ya invertidos).
    const flip = (s) => s ? s.split("-").reverse().join("-") : s;
    return {
      ...row, P_1: row.P_2, P_2: row.P_1,
      pick: flip(row.pick), pick_outcome: flip(row.pick_outcome),
      snapDate: snap.date,
    };
  }
  return null;
}

function pickBadge(match, pred) {
  if (!match.played || !pred) return "";
  const [ph, pa] = pickOf(pred).split("-").map(Number);
  if (ph === match.home_score && pa === match.away_score)
    return `<span class="badge exact">Exacta</span>`;
  if (Math.sign(ph - pa) === Math.sign(match.home_score - match.away_score))
    return `<span class="badge outcome">1X2 ✓</span>`;
  return `<span class="badge miss">Fallo</span>`;
}

function matchCard(m) {
  const pred = predictionFor(m);
  const score = m.played
    ? `<span class="score">${m.home_score} – ${m.away_score}</span>`
    : `<span class="score future">vs</span>`;
  // etiqueta según quepa: "1 · 68%" → "68%" → nada (el title siempre la lleva)
  const segLabel = (prefix, p) =>
    p >= 0.17 ? `${prefix} · ${pct(p)}` : p >= 0.09 ? pct(p) : "";
  const seg = (cls, prefix, p) =>
    `<span class="seg ${cls}" style="width:${p * 100}%" title="${prefix}: ${pct(p)}">${segLabel(prefix, p)}</span>`;
  const probBar = pred ? `
    <div class="prob-bar" title="Probabilidades 1 / X / 2">
      ${seg("p1", "1", pred.P_1)}${seg("px", "X", pred.P_X)}${seg("p2", "2", pred.P_2)}
    </div>` : "";
  const predLine = pred ? `
    <div class="pred-line">
      <span class="pick-chip" title="Estrategia: ${STRATEGY_LABELS[state.strategy]}">Pred. ${pickOf(pred)}</span>
      ${pickBadge(m, pred)}
    </div>` : `<div class="pred-line"><span class="xp">Sin predicción para este partido</span></div>`;
  const oddsLine = m.odds ? `
    <div class="odds-line">Cuotas:
      <span class="o">1&nbsp;${m.odds[0].toFixed(2)}</span>
      <span class="o">X&nbsp;${m.odds[1].toFixed(2)}</span>
      <span class="o">2&nbsp;${m.odds[2].toFixed(2)}</span>
    </div>` : "";
  return `<div class="match-card" data-home="${m.home}" data-away="${m.away}" data-date="${m.date}"
       title="Clic para ver la matriz de marcadores">
    <div class="meta"><span>${m.city}${m.group ? ` · Grupo ${m.group}` : ""}</span>
      <span>${fmtShort(m.date)}</span></div>
    <div class="match-row">
      <span class="team">${flagImg(m.home, true)}<span>${teamES(m.home)}</span></span>
      ${score}
      <span class="team away">${flagImg(m.away, true)}<span>${teamES(m.away)}</span></span>
    </div>
    ${predLine}${probBar}${oddsLine}
  </div>`;
}

function renderCalendar() {
  const el = $("#tab-calendar");
  if (!state.matches?.length) { el.innerHTML = `<p class="note">No hay partidos en results.csv.</p>`; return; }

  const byRound = {};
  state.matches.forEach((m) => (byRound[m.round_id] ||= []).push(m));

  el.innerHTML = `
    <h2 class="section">Calendario y predicciones partido a partido</h2>
    <p class="note">Para cada partido se muestra la predicción vigente ese día (el último snapshot
      anterior o igual a la fecha del partido) y las cuotas 1X2 si están disponibles.
      Los partidos eliminatorios aparecerán cuando se conozcan los cruces.</p>
    ${ROUND_ORDER.filter((r) => byRound[r]).map((rid) => {
      const ms = byRound[rid];
      const byDay = {};
      ms.forEach((m) => (byDay[m.date] ||= []).push(m));
      return `<div class="round-block"><h2>${ms[0].round_name}</h2>
        ${Object.keys(byDay).sort().map((d) => `
          <div class="day-label">${fmtDay(d)}</div>
          <div class="match-grid">${byDay[d].map(matchCard).join("")}</div>`).join("")}
      </div>`;
    }).join("")}`;
}

// ------------------------------------------------------------ conectividad

const CONF_COLORS = {
  UEFA: "#3b6bb5", CONMEBOL: "#0f8a8a", CONCACAF: "#e8632c",
  CAF: "#d9a514", AFC: "#c0392b", OFC: "#7d3bb5",
};
const CONF_UNKNOWN = "#b6b3a7";

async function loadConnectivity() {
  if (state.connLoading) return;
  state.connLoading = true;
  const el = $("#tab-connectivity");
  el.innerHTML = `<p class="note">Calculando la conectividad… (la primera vez ajusta el modelo y tarda unos segundos)</p>`;
  try {
    state.connectivity = await fetchJSON("/api/connectivity");
  } catch (e) {
    el.innerHTML = `<p class="note">Error calculando la conectividad: ${e.message}</p>`;
    return;
  } finally {
    state.connLoading = false;
  }
  renderConnectivity();
}

// dispersión: cuota de peso puente (x) frente a rating del modelo (y)
function connScatter(d) {
  const pts = d.teams;
  const W = 920, H = 450, mL = 52, mR = 26, mT = 14, mB = 46;
  const xMax = Math.max(...pts.map((t) => t.bridge_share)) * 1.1;
  const ys = pts.map((t) => t.rating);
  const yMin = Math.min(...ys) - 0.2, yMax = Math.max(...ys) + 0.2;
  const X = (v) => mL + (v / xMax) * (W - mL - mR);
  const Y = (v) => mT + (1 - (v - yMin) / (yMax - yMin)) * (H - mT - mB);

  let grid = "";
  for (let v = 0; v <= xMax; v += 0.1) {
    grid += `<line x1="${X(v)}" y1="${mT}" x2="${X(v)}" y2="${H - mB}" stroke="#e4e2da"/>
             <text x="${X(v)}" y="${H - mB + 16}" text-anchor="middle" font-size="11" fill="#6b6b66">${Math.round(v * 100)}%</text>`;
  }
  for (let v = Math.ceil(yMin * 2) / 2; v <= yMax; v += 0.5) {
    grid += `<line x1="${mL}" y1="${Y(v)}" x2="${W - mR}" y2="${Y(v)}" stroke="#e4e2da"/>
             <text x="${mL - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="#6b6b66">${v.toFixed(1)}</text>`;
  }
  grid += `<text x="${(mL + W - mR) / 2}" y="${H - 6}" text-anchor="middle" font-size="11.5" fill="#6b6b66">Peso de entrenamiento contra otras confederaciones (partidos puente)</text>
           <text transform="rotate(-90)" x="${-(mT + H - mB) / 2}" y="13" text-anchor="middle" font-size="11.5" fill="#6b6b66">Rating del modelo (ataque − defensa)</text>`;

  let marks = "";
  pts.forEach((t) => {
    const info = teamInfo(t.team);
    const cx = X(t.bridge_share), cy = Y(t.rating);
    const sel = t.team === state.connSelected;
    marks += `<g class="conn-pt${sel ? " sel" : ""}" data-team="${t.team}">
      <circle cx="${cx}" cy="${cy}" r="13" fill="${CONF_COLORS[t.conf] || CONF_UNKNOWN}" opacity="${sel ? "0.85" : "0.3"}"/>
      ${info.code ? `<image href="/flags/${info.code}.svg" x="${cx - 10}" y="${cy - 7}" width="20" height="14"/>` : ""}
      <title>${teamES(t.team)} (${t.conf}) — rating ${t.rating.toFixed(2)} · puente ${pct(t.bridge_share)} · rival medio ${t.opp_rating.toFixed(2)}</title>
    </g>`;
  });
  return `<svg class="evo-svg" viewBox="0 0 ${W} ${H}">${grid}${marks}</svg>`;
}

// desglose del equipo seleccionado: contra qué confederaciones entrena su rating
function connDetail(d) {
  const t = d.teams.find((x) => x.team === state.connSelected);
  if (!t) return `<p class="note">Haz clic en una bandera del gráfico (o en una fila de la tabla)
    para ver contra qué confederaciones ha jugado cada equipo.</p>`;
  const known = Object.values(t.by_conf).reduce((a, b) => a + b, 0);
  const rest = 1 - known;   // rivales sin confederación inferible en la ventana
  const segs = d.confederations
    .filter((c) => t.by_conf[c] > 0.001)
    .map((c) => `<span class="seg" style="width:${t.by_conf[c] * 100}%;background:${CONF_COLORS[c]}"
        title="${c}: ${pct(t.by_conf[c])}">${t.by_conf[c] >= 0.09 ? c : ""}</span>`)
    .join("");
  return `
    <div class="conn-detail-head">${flagImg(t.team, true)} <b>${teamES(t.team)}</b>
      <span class="group-chip" style="color:${CONF_COLORS[t.conf]};border-color:${CONF_COLORS[t.conf]}">${t.conf}</span></div>
    <div class="conn-stats">
      <span><b>${t.rating.toFixed(2)}</b> rating</span>
      <span><b>${t.matches}</b> partidos en la ventana</span>
      <span><b>${pct(t.bridge_share)}</b> del peso es puente</span>
      <span><b>${t.opp_rating.toFixed(2)}</b> rating del rival medio</span>
    </div>
    <div class="prob-bar conn-bar" title="Reparto del peso de entrenamiento según la confederación del rival">
      ${segs}${rest > 0.001 ? `<span class="seg" style="width:${rest * 100}%;background:${CONF_UNKNOWN}"
        title="Rivales sin confederación inferida: ${pct(rest)}">${rest >= 0.09 ? "¿?" : ""}</span>` : ""}
    </div>`;
}

// matriz conf x conf con cada fila normalizada por su peso total
function connHeatmap(d) {
  const confs = d.confederations;
  const Wm = d.matrix_weight, C = d.matrix_count;
  const tot = Wm.map((row) => row.reduce((a, b) => a + b, 0));
  return `<table class="probs conn-heat">
    <thead><tr><th class="team-col">Conf.</th>${confs.map((c) => `<th>${c}</th>`).join("")}</tr></thead>
    <tbody>${confs.map((c, i) => `
      <tr><td class="team-cell" style="color:${CONF_COLORS[c]}">${c}</td>
        ${confs.map((c2, j) => {
          const share = tot[i] ? Wm[i][j] / tot[i] : 0;
          const a = Math.min(share * 1.6, 0.92);
          return `<td class="pcell${a > 0.55 ? " dark" : ""}${i === j ? " diag" : ""}"
              style="background:rgba(15,138,138,${a.toFixed(3)})"
              title="${c} – ${c2}: ${C[i][j]} partidos, peso ${Wm[i][j].toFixed(0)} (${pct(share)} del peso de ${c})">${pct(share)}</td>`;
        }).join("")}</tr>`).join("")}
    </tbody></table>`;
}

function connTable(d) {
  return `<table class="probs">
    <thead><tr><th class="team-col">Equipo</th><th>Conf.</th><th>Partidos</th>
      <th title="Fracción del peso de entrenamiento contra otras confederaciones">Peso puente</th>
      <th title="Rating medio (ponderado) de los rivales en la ventana de entrenamiento">Rival medio</th>
      <th>Rating</th></tr></thead>
    <tbody>${d.teams.map((t, i) => `
      <tr class="conn-row${t.team === state.connSelected ? " sel" : ""}" data-team="${t.team}">
        <td class="team-cell">${i + 1}. ${flagImg(t.team)}${teamES(t.team)}</td>
        <td style="color:${CONF_COLORS[t.conf]};font-weight:700">${t.conf}</td>
        <td>${t.matches}</td>${pcell(t.bridge_share)}
        <td>${t.opp_rating.toFixed(2)}</td>
        <td><b>${t.rating.toFixed(2)}</b></td></tr>`).join("")}
    </tbody></table>`;
}

function renderConnectivity() {
  if (!state.meta) return;            // aún sin /api/meta: render() repintará
  const el = $("#tab-connectivity");
  const d = state.connectivity;
  if (!d) { loadConnectivity(); return; }
  el.innerHTML = `
    <h2 class="section">¿Quién ancla a quién? Conectividad entre confederaciones</h2>
    <p class="note">Anclar una confederación es fijar su nivel respecto al de las demás, para que los
      equipos de bloques distintos sean comparables en una misma escala. El modelo solo puede hacerlo a
      través de los partidos «puente» entre confederaciones. Donde hay pocos puentes, la escala de una
      confederación queda mal anclada al resto y sus ratings pueden inflarse o desinflarse en bloque — la limitación documentada
      en <code>docs/known-limitations.md</code> (p. ej. la AFC, y en menor medida la CONMEBOL). El peso es
      el mismo del entrenamiento (decaimiento temporal con vida media de 2 años, datos hasta el
      ${fmtDay(d.as_of)}).</p>
    <div class="card">
      <h3 class="conn-h3">Los 48 clasificados: ¿cuánto se apoya cada rating en partidos puente?</h3>
      <p class="note">Cuanto más a la izquierda, más depende el rating del juego interno de su
        confederación (y de lo bien anclada que esté). Clic en una bandera para ver el desglose.</p>
      ${connScatter(d)}
      <div class="evo-legend">${d.confederations.map((c) => `
        <span class="item"><span class="swatch" style="background:${CONF_COLORS[c]};height:10px;border-radius:5px"></span>${c}</span>`).join("")}
        <span class="item"><span class="swatch" style="background:${CONF_UNKNOWN};height:10px;border-radius:5px"></span>Sin conf. inferida</span></div>
    </div>
    <div class="card" id="conn-detail">${connDetail(d)}</div>
    <div class="card">
      <h3 class="conn-h3">Matriz de conectividad</h3>
      <p class="note">Cada celda: fracción del peso de entrenamiento de la confederación de la fila jugada
        contra la de la columna. La diagonal (punteada) es el juego interno; todo lo demás son puentes.</p>
      <div style="overflow-x:auto">${connHeatmap(d)}</div>
    </div>
    <div class="card" style="overflow-x:auto">
      <h3 class="conn-h3">Detalle por equipo</h3>
      ${connTable(d)}
    </div>`;

  el.querySelectorAll(".conn-pt, .conn-row").forEach((n) =>
    n.addEventListener("click", () => {
      state.connSelected = n.dataset.team;
      renderConnectivity();
      $("#conn-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));
}

// --------------------------------------------------------------- rankings

// Una fila del CSV de snapshot (confederation/attack/defence) o del ajuste en
// vivo (conf/atk/dfn) → forma común.
function normRankRow(r) {
  return {
    team: r.team,
    conf: r.conf ?? r.confederation ?? null,
    atk: +(r.atk ?? r.attack),
    dfn: +(r.dfn ?? r.defence),
    rating: +r.rating,
    opp_rating: r.opp_rating == null ? null : +r.opp_rating,
    elo: r.elo == null ? null : +r.elo,
  };
}

async function loadRankings() {
  const eng = state.engine;
  if (state.rankLoading || state.rankings[eng]) { renderRankings(); return; }
  state.rankLoading = true;
  const el = $("#tab-rankings");
  el.innerHTML = `<p class="note">Cargando rankings…</p>`;
  try {
    const hist = await fetchJSON(`/api/rankings/history?engine=${eng}`);
    let live = null;
    if (!hist.snapshots.length) {
      // sin snapshots fechados todavía: ajuste en vivo a día de hoy
      el.innerHTML = `<p class="note">No hay snapshots de rankings generados.
        Ajustando el modelo en vivo… (la primera vez tarda unos segundos)</p>`;
      live = await fetchJSON(`/api/rankings?engine=${eng}`);
    }
    state.rankings[eng] = { snapshots: hist.snapshots, live };
  } catch (e) {
    el.innerHTML = `<p class="note">Error cargando los rankings: ${e.message}</p>`;
    return;
  } finally {
    state.rankLoading = false;
  }
  renderRankings();
}

// métricas de la gráfica de evolución (la de Elo solo si el motor la tiene)
function rankMetrics(hasElo) {
  const m = [["rating", "Rating (ataque − defensa)"]];
  if (hasElo) m.push(["elo", "Puntuación Elo"]);
  m.push(["rank", "Posición en el ranking"], ["opp_rating", "Dificultad de rivales"]);
  return m;
}

function renderRankings() {
  if (!state.meta) return;
  const el = $("#tab-rankings");
  const data = state.rankings[state.engine];
  if (!data) { loadRankings(); return; }

  const engLabel = ENGINE_LABELS[state.engine] || state.engine;
  const snaps = data.snapshots;
  // tabla: el último snapshot disponible (la evolución se ve en la gráfica), o
  // el ajuste en vivo si aún no se ha generado ninguno. La fecha de rankings es
  // independiente del selector «Día» (atado a las simulaciones).
  let rows, asOf, fromLive = false;
  if (snaps.length) {
    const snap = snaps[snaps.length - 1];
    rows = snap.rows.map(normRankRow);
    asOf = snap.date;
  } else {
    rows = data.live.teams.map(normRankRow);
    asOf = data.live.as_of;
    fromLive = true;
  }
  // solo las 48 del Mundial (el modelo puntúa muchas más, pero el ranking es del
  // torneo); el ajuste en vivo ya viene filtrado, así que esto es no-op ahí
  rows = rows.filter((r) => state.meta.teams[r.team]);
  const hasElo = rows.length > 0 && rows[0].elo != null;
  rows.sort((a, b) => (hasElo ? b.elo - a.elo : b.rating - a.rating));

  const sortLabel = hasElo ? "puntuación Elo" : "rating (ataque − defensa)";
  const tbody = rows.map((t, i) => `
    <tr class="conn-row" data-team="${t.team}">
      <td class="team-cell">${i + 1}. ${flagImg(t.team)}${teamES(t.team)}</td>
      <td style="color:${CONF_COLORS[t.conf] || CONF_UNKNOWN};font-weight:700">${t.conf || "–"}</td>
      ${hasElo ? `<td><b>${Math.round(t.elo)}</b></td>` : ""}
      <td>${t.atk.toFixed(2)}</td>
      <td>${t.dfn.toFixed(2)}</td>
      <td><b>${t.rating.toFixed(2)}</b></td>
      <td>${t.opp_rating != null ? t.opp_rating.toFixed(2) : "–"}</td>
    </tr>`).join("");

  const source = fromLive
    ? `ajuste en vivo a ${fmtDay(asOf)} (genera snapshots con
       <code>scripts/generate_rankings.sh</code> o «Actualizar datos» para ver la evolución)`
    : `snapshot del ${fmtDay(asOf)}`;

  const evoBlock = snaps.length ? rankEvolutionBlock(snaps, hasElo) : null;

  el.innerHTML = `
    <h2 class="section">Rankings del modelo · ${engLabel}</h2>
    <p class="note">Fuerza de cada selección según el motor <b>${engLabel}</b>, ordenada por ${sortLabel}
      (${source}). El <b>rating</b> es ataque − defensa: cuanto mayor, mejor.
      ${hasElo ? "La <b>puntuación Elo</b> es la del propio motor (regla de eloratings.net). " : ""}
      El <b>rival medio</b> es el rating medio (ponderado por el peso de entrenamiento) de los equipos
      contra los que ha jugado: una medida de la dificultad media de sus partidos. Usa el selector de
      <b>Motor</b> de la cabecera para cambiar de modelo.</p>
    ${evoBlock ? evoBlock.html : ""}
    <div class="card" style="overflow-x:auto">
      <h3 class="conn-h3">Clasificación ${fromLive ? "(en vivo)" : `del ${fmtShort(asOf)}`}</h3>
      <table class="probs">
        <thead><tr><th class="team-col">Equipo</th><th>Conf.</th>
          ${hasElo ? "<th title=\"Puntuación Elo del motor (regla de eloratings.net)\">Elo</th>" : ""}
          <th title="Coeficiente de ataque del modelo">Ataque</th>
          <th title="Coeficiente de defensa del modelo (menor = mejor defensa)">Defensa</th>
          <th title="Ataque − defensa: la fuerza global">Rating</th>
          <th title="Rating medio (ponderado) de los rivales en la ventana de entrenamiento">Rival medio</th>
        </tr></thead>
        <tbody>${tbody}</tbody>
      </table>
    </div>`;

  const sel = $("#rank-metric");
  if (sel) sel.addEventListener("change", (e) => {
    state.rankMetric = e.target.value;
    renderRankings();
  });
  if (evoBlock) wireLegend(el, evoBlock.selected, "rankSelected", renderRankings);
}

// bloque de la gráfica de evolución: selector de métrica + SVG + leyenda.
// Devuelve {html, selected} para que renderRankings conecte los clics.
function rankEvolutionBlock(snaps, hasElo) {
  const metrics = rankMetrics(hasElo);
  let metric = state.rankMetric;
  if (!metrics.some(([k]) => k === metric)) metric = state.rankMetric = "rating";
  const isRank = metric === "rank";
  const n = snaps.length;
  const rankKey = hasElo ? "elo" : "rating";

  // filas normalizadas y posición (por rating/elo) de cada snapshot, una sola vez
  const snapRows = snaps.map((s) => s.rows.map(normRankRow));
  const snapRank = snapRows.map((rows) => {
    const ord = [...rows].sort((a, b) => b[rankKey] - a[rankKey]);
    const pos = {}; ord.forEach((r, i) => (pos[r.team] = i + 1));
    return pos;
  });

  // valor por equipo en un snapshot dado
  const valAt = (j, team) => {
    if (isRank) return snapRank[j][team] ?? null;
    const r = snapRows[j].find((x) => x.team === team);
    return r && r[metric] != null ? r[metric] : null;
  };

  // solo las 48 del Mundial (el modelo puntúa muchas más, pero el ranking es del
  // torneo), ordenadas por la métrica elegida en el último snapshot. La posición
  // de "rank" sigue siendo la global (sobre todas las selecciones del snapshot).
  const lastIdx = n - 1;
  const ordered = [...snapRows[lastIdx]]
    .map((r) => r.team)
    .filter((t) => state.meta.teams[t])
    .sort((a, b) => isRank ? (snapRank[lastIdx][a] - snapRank[lastIdx][b])
                           : (valAt(lastIdx, b) - valAt(lastIdx, a)));
  const selected = state.rankSelected || new Set(ordered.slice(0, EVO_DEFAULT_N));
  const colorOf = evoColors(ordered.filter((t) => selected.has(t)));
  const series = ordered.map((team) => ({
    team, sel: selected.has(team), color: selected.has(team) ? colorOf[team] : EVO_GRAY,
    values: snaps.map((_, j) => valAt(j, team)),
  }));

  const W = 920, H = 430, mL = 54, mR = 150, mT = 16, mB = 40;
  const x = (i) => n === 1 ? (mL + W - mR) / 2 : mL + (i * (W - mL - mR)) / (n - 1);
  const allV = series.flatMap((s) => s.values.filter((v) => v != null));
  let lo, hi;
  if (isRank) { lo = 1; hi = Math.max(2, ...allV); }
  else {
    lo = Math.min(...allV); hi = Math.max(...allV);
    const pad = (hi - lo) * 0.1 || 0.1; lo -= pad; hi += pad;
  }
  // t en [0,1] con 0 = arriba (rating/elo: mayor arriba; posición: 1 arriba)
  const y = (v) => mT + (isRank ? (v - 1) / (hi - 1) : (hi - v) / (hi - lo)) * (H - mT - mB);

  let grid = "";
  if (isRank) {
    const rstep = hi > 12 ? Math.max(1, Math.round(niceStep(hi - 1))) : 1;
    for (let v = 1; v <= hi; v += rstep)
      grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e4e2da"/>
               <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#6b6b66">${v}</text>`;
  } else {
    const step = niceStep(hi - lo);
    const dec = step < 0.1 ? 2 : step < 1 ? 1 : 0;
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step)
      grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e4e2da"/>
               <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#6b6b66">${v.toFixed(dec)}</text>`;
  }
  const every = Math.max(1, Math.ceil(n / 12));
  let xaxis = "";
  snaps.forEach((s, i) => {
    if (i % every === 0 || i === n - 1)
      xaxis += `<text x="${x(i)}" y="${H - mB + 18}" text-anchor="middle" font-size="11" fill="#6b6b66">${fmtShort(s.date)}</text>`;
  });

  const fmtV = (v) => isRank ? `#${v}` : metric === "elo" ? Math.round(v) : v.toFixed(2);
  let lines = "";
  // fondo: selecciones no resaltadas, en gris fino y sin puntos
  series.filter((s) => !s.sel).forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
    if (pts.length > 1)
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${EVO_GRAY}" stroke-width="1.2" opacity="0.7"/>`;
  });
  // primer plano: las resaltadas, en color y con puntos
  const fg = series.filter((s) => s.sel);
  fg.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
    if (pts.length > 1)
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${s.color}" stroke-width="2.5"/>`;
    s.values.forEach((v, i) => {
      if (v != null) lines += `<circle cx="${x(i)}" cy="${y(v)}" r="3.2" fill="${s.color}"/>`;
    });
  });
  // etiquetas finales sin solaparse
  const labels = fg
    .filter((s) => s.values[n - 1] != null)
    .map((s) => ({ s, v: s.values[n - 1], ly: y(s.values[n - 1]) }))
    .sort((a, b) => a.ly - b.ly);
  labels.forEach((l, i) => {
    if (i > 0 && l.ly < labels[i - 1].ly + 15) l.ly = labels[i - 1].ly + 15;
  });
  labels.forEach((l) => {
    const yEnd = y(l.v);
    if (Math.abs(l.ly - yEnd) > 4)
      lines += `<line x1="${x(n - 1) + 4}" y1="${yEnd}" x2="${x(n - 1) + 18}" y2="${l.ly - 4}" stroke="${l.s.color}" stroke-width="1" opacity=".6"/>`;
    lines += `<text x="${x(n - 1) + 21}" y="${l.ly}" font-size="11.5" font-weight="600" fill="${l.s.color}">${teamES(l.s.team)} ${fmtV(l.v)}</text>`;
  });

  const metricLabel = metrics.find(([k]) => k === metric)[1];
  const html = `
    <div class="card">
      <h3 class="conn-h3">Evolución del ranking</h3>
      <div class="evo-controls">
        <label>Métrica
          <select id="rank-metric">${metrics.map(([k, l]) =>
            `<option value="${k}"${k === metric ? " selected" : ""}>${l}</option>`).join("")}</select>
        </label>
        <span class="note">Las ${ordered.length} selecciones (en gris) por «${metricLabel}»; resaltadas las
          ${selected.size} elegidas. Clic en una bandera de la leyenda para resaltarla o quitarla.
          ${n === 1 ? "Solo hay un día generado: la línea crecerá con cada nuevo snapshot."
            : `${n} snapshots.`}
          ${isRank ? "Eje invertido: el 1.º arriba." : ""}</span>
      </div>
      <svg class="evo-svg" viewBox="0 0 ${W} ${H}">${grid}${xaxis}${lines}</svg>
      ${selectableLegend(ordered, selected, colorOf)}
    </div>`;
  return { html, selected };
}

// ------------------------------------------------------------------ render

function render() {
  renderChampion();
  renderEvolution();
  renderGroups();
  renderCalendar();
  // la conectividad no depende del approach/snapshot: solo se repinta si ya
  // está cargada (o si es la pestaña activa tras un refresco de datos)
  if (state.connectivity || state.tab === "connectivity") renderConnectivity();
  // los rankings dependen del motor pero no del approach/snapshot
  if (state.rankings[state.engine] || state.tab === "rankings") renderRankings();
}

// ----------------------------------------------------------- matriz marcador

async function openMatrix(home, away, date) {
  const modal = $("#matrix-modal");
  const box = $("#matrix-content");
  modal.classList.remove("hidden");
  box.innerHTML = `<div class="matrix-loading">Ajustando el modelo… (la primera vez tarda unos segundos)</div>`;
  let d;
  try {
    const q = new URLSearchParams({ home, away, date, approach: state.approach,
                                    engine: state.engine, strategy: state.strategy });
    d = await fetchJSON(`/api/matrix?${q}`);
  } catch (e) {
    box.innerHTML = `<div class="matrix-loading">Error calculando la matriz: ${e.message}</div>`;
    return;
  }
  const m = state.matches.find((x) => x.home === home && x.away === away && x.date === date);
  const n = d.matrix.length;
  const maxP = Math.max(...d.matrix.flat());
  const [pickH, pickA] = d.pick.split("-").map(Number);

  const cell = (h, a) => {
    const p = d.matrix[h][a];
    const alpha = maxP ? Math.min((p / maxP) * 0.95, 0.95) : 0;
    const cls = [
      alpha > 0.55 ? "dark" : "",
      h === pickH && a === pickA ? "pick" : "",
      m?.played && h === m.home_score && a === m.away_score ? "real" : "",
    ].join(" ");
    const label = p >= 0.001 ? (p * 100).toFixed(1) : "·";
    return `<td class="${cls}" style="background:rgba(15,138,138,${alpha.toFixed(3)})"
                title="${h}-${a}: ${(p * 100).toFixed(2)}%">${label}</td>`;
  };

  const score = m?.played ? `${m.home_score} – ${m.away_score}` : "vs";
  box.innerHTML = `
    <div class="matrix-head">${flagImg(home, true)} ${teamES(home)}
      <span style="color:var(--muted)">${score}</span> ${teamES(away)} ${flagImg(away, true)}</div>
    <div class="matrix-sub">Probabilidad (%) de cada marcador exacto · modelo ${ENGINE_LABELS[d.engine] || d.engine} del ${fmtDay(d.as_of)}
      · ${d.odds_used ? "con cuotas de mercado" : "solo modelo"}
      · 1X2: ${pct(d.p1)} / ${pct(d.px)} / ${pct(d.p2)}
      · Pred. <b>${d.pick}</b></div>
    <table class="matrix">
      <tr><th></th><th class="axis" colspan="${n}">Goles de ${teamES(away)} →</th></tr>
      <tr><th class="axis">${teamES(home)} ↓</th>${[...Array(n)].map((_, a) => `<th>${a}</th>`).join("")}</tr>
      ${[...Array(n)].map((_, h) =>
        `<tr><th>${h}</th>${[...Array(n)].map((_, a) => cell(h, a)).join("")}</tr>`).join("")}
    </table>
    <div class="matrix-legend">
      <span><span class="key" style="outline:2.5px solid var(--orange); outline-offset:-2.5px"></span>predicción Penka</span>
      ${m?.played ? `<span><span class="key" style="outline:2.5px solid var(--ink); outline-offset:-2.5px"></span>resultado real</span>` : ""}
    </div>`;
}

function setupMatrix() {
  $("#tab-calendar").addEventListener("click", (e) => {
    const card = e.target.closest(".match-card");
    if (card) openMatrix(card.dataset.home, card.dataset.away, card.dataset.date);
  });
  $("#matrix-close").addEventListener("click", () => $("#matrix-modal").classList.add("hidden"));
  $("#matrix-modal").addEventListener("click", (e) => {
    if (e.target.id === "matrix-modal") $("#matrix-modal").classList.add("hidden");
  });
}

// ------------------------------------------------------------------ refresh

let pollTimer = null;

async function pollRefresh() {
  const st = await fetchJSON("/api/refresh/status");
  const log = $("#refresh-log");
  log.classList.remove("hidden");
  log.textContent = st.log.join("\n") || "(arrancando…)";
  log.scrollTop = log.scrollHeight;
  if (st.running) {
    pollTimer = setTimeout(pollRefresh, 2000);
  } else {
    $("#refresh-start").disabled = false;
    if (st.returncode === 0) {
      log.textContent += "\n\n✔ Terminado. Recargando datos…";
      await reloadAll();
    } else if (st.returncode != null) {
      log.textContent += `\n\n✘ Falló (código ${st.returncode}).`;
    }
  }
}

function setupRefresh() {
  const modal = $("#refresh-modal");
  $("#refresh-btn").addEventListener("click", () => {
    modal.classList.remove("hidden");
    fetchJSON("/api/refresh/status").then((st) => { if (st.running) pollRefresh(); });
  });
  $("#refresh-close").addEventListener("click", () => {
    modal.classList.add("hidden");
    if (pollTimer) clearTimeout(pollTimer);
  });
  $("#refresh-start").addEventListener("click", async () => {
    $("#refresh-start").disabled = true;
    const sims = parseInt($("#refresh-sims").value, 10);
    const engines = [...document.querySelectorAll(".refresh-engine:checked")].map((c) => c.value);
    try {
      await fetch("/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          refresh_inputs: $("#refresh-inputs").checked,
          sims: isNaN(sims) ? null : sims,
          engines: engines.length ? engines : ["dc"],
        }),
      });
    } catch (e) { /* el 409 (ya en marcha) acaba igualmente en el poll */ }
    pollRefresh();
  });
}

// -------------------------------------------------------------------- init

function activateTab(tab) {
  // el hash puede llevar otras cosas (p. ej. #match=...): solo pestañas válidas
  const known = [...document.querySelectorAll(".tab")].some((b) => b.dataset.tab === tab);
  if (!known) return;
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".panel").forEach((p) =>
    p.classList.toggle("active", p.id === `tab-${tab}`));
  state.tab = tab;
  if (tab === "connectivity" && !state.connectivity && state.meta) loadConnectivity();
  if (tab === "rankings" && !state.rankings[state.engine] && state.meta) loadRankings();
}

function setupUI() {
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      activateTab(btn.dataset.tab);
      history.replaceState(null, "", `#${btn.dataset.tab}`);
    }));
  if (location.hash) activateTab(location.hash.slice(1));

  $("#odds-toggle").addEventListener("change", async (e) => {
    state.approach = e.target.checked ? "odds" : "history";
    await loadData();
    buildSnapshotSelect();
    render();
  });

  $("#engine-select").addEventListener("change", async (e) => {
    state.engine = e.target.value;
    updateEngineNote();
    await loadData();
    buildSnapshotSelect();
    render();
  });

  // La estrategia solo cambia qué columna de marcador se muestra (ambas viajan
  // en los mismos datos), así que no recarga nada: basta repintar.
  $("#strategy-toggle").addEventListener("change", (e) => {
    state.strategy = e.target.checked ? "outcome" : "ev";
    render();
  });

  $("#snapshot-select").addEventListener("change", (e) => {
    state.snapshotDate = e.target.value;
    $("#snapshot-note").textContent = `predicciones del ${fmtDay(e.target.value)}`;
    render();
  });

  setupMatrix();
  setupRefresh();
}

setupUI();
reloadAll().catch((e) => {
  document.querySelector("main").innerHTML =
    `<p class="note">Error cargando datos: ${e.message}. ¿Está el servidor corriendo desde la raíz del proyecto?</p>`;
});
