/* Frontend de wcpred: lee la API JSON de webapp/server.py y pinta las vistas.
   Sin dependencias externas: las gráficas son SVG generado a mano. Los textos
   visibles salen de i18n.js (helper `t`), cargado antes que este fichero. */

const state = {
  lang: (typeof currentLang === "function" ? currentLang() : "en"), // en | es
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

// Etiqueta legible de un motor / estrategia (traducidas en i18n.js).
const engineLabel = (e) => t("engine." + e);
const strategyLabel = (s) => t("strategy." + s);

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
// nombre de la selección según el idioma: clave martj42 (inglés) o su nombre es
const teamName = (name) => state.lang === "es" ? teamInfo(name).es : name;
const flagImg = (name, big = false) => {
  const tdata = teamInfo(name);
  if (!tdata.code) return "";
  return `<img class="flag${big ? " big" : ""}" src="/flags/${tdata.code}.svg" alt="${teamName(name)}">`;
};

const pct = (p) => {
  if (p == null || isNaN(p)) return "–";
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return Math.round(p * 100) + "%";
};

// sombreado de probabilidad: rampa teal de un solo tono (--data). La rampa
// salta la banda 0.70–0.88 de alfa, donde ni la tinta ni el blanco alcanzan
// 4.5:1 de contraste: hasta 0.70 texto tinta, desde 0.88 texto blanco.
const SHADE_RGB = "10,108,107";
const shadeAlpha = (raw) =>
  raw <= 0.70 ? raw : 0.88 + (Math.min(raw, 0.92) - 0.70) * (0.04 / 0.22);
const shadeCell = (raw) => ({
  bg: `rgba(${SHADE_RGB},${shadeAlpha(raw).toFixed(3)})`,
  dark: raw > 0.70,
});

// celda sombreada según probabilidad (estilo 538)
const pcell = (p) => {
  const { bg, dark } = shadeCell(Math.min((p ?? 0) * 1.05, 0.92));
  return `<td class="pcell${dark ? " dark" : ""}" style="background:${bg}">${pct(p)}</td>`;
};

// color de texto (tinta/blanco) más legible sobre un fondo dado
const inkFor = (hex) => {
  const c = hex.slice(1).match(/../g).map((h) => parseInt(h, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  const L = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  return 1.05 / (L + 0.05) >= (L + 0.05) / 0.05 ? "#fff" : "#1f2529";
};

const dateLocale = () => state.lang === "es" ? "es-ES" : "en-GB";

const fmtDay = (iso) =>
  new Intl.DateTimeFormat(dateLocale(), { weekday: "long", day: "numeric", month: "long" })
    .format(new Date(iso + "T12:00:00"));

const fmtShort = (iso) =>
  new Intl.DateTimeFormat(dateLocale(), { day: "numeric", month: "short" })
    .format(new Date(iso + "T12:00:00"));

// etiqueta de ronda a partir del round_id que envía /api/matches: jN = jornada
// de grupos; el resto son claves de eliminatoria (r32/r16/qf/sf/p3/f/ko).
const roundName = (rid) =>
  /^j\d+$/.test(rid) ? t("round.group", { n: rid.slice(1) }) : t("round." + rid);

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
  applyPublicMode();
  buildEngineSelect();
  await loadData();
  buildSnapshotSelect();
  renderDocs();
  render();
  // permalink a la matriz de un partido: #match=2026-06-11|Mexico|South Africa
  if (location.hash.startsWith("#match=")) {
    const [date, home, away] = decodeURIComponent(location.hash.slice(7)).split("|");
    activateTab("calendar");
    openMatrix(home, away, date);
  }
}

// Versión pública (WCPRED_PUBLIC en el servidor → meta.public): sin botón de
// actualizar datos ni pestaña de Conectividad.
function applyPublicMode() {
  if (!state.meta || !state.meta.public) return;
  $("#refresh-btn")?.remove();
  document.querySelector('.tab[data-tab="connectivity"]')?.remove();
  $("#tab-connectivity")?.remove();
  if (state.tab === "connectivity") activateTab("champion");
}

function buildEngineSelect() {
  const engines = state.meta.engines || ["dc"];
  const sel = $("#engine-select");
  sel.innerHTML = engines
    .map((e) => `<option value="${e}">${engineLabel(e)}</option>`)
    .join("");
  if (!engines.includes(state.engine)) state.engine = engines[0];
  sel.value = state.engine;
  updateEngineNote();
}

function updateEngineNote() {
  const note = $("#engine-note");
  if (note) note.textContent = engineLabel(state.engine);
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
    ? t("snapshot.predictions", { date: fmtDay(wanted) })
    : t("snapshot.none");
}

// ----------------------------------------------------------- ¿Quién gana?

const SIM_COLS = [
  ["p_win_group", "sim.win_group"],
  ["p_r16", "sim.r16"],
  ["p_qf", "sim.qf"],
  ["p_sf", "sim.sf"],
  ["p_final", "sim.final"],
  ["p_champion", "sim.champion"],
];

function renderChampion() {
  const snap = pickSnapshot(curCache().sims, state.snapshotDate);
  const el = $("#tab-champion");
  if (!snap) { el.innerHTML = `<p class="note">${t("champion.none")}</p>`; return; }
  const rows = [...snap.rows].sort((a, b) => b.p_champion - a.p_champion);

  // lede editorial + gráfica de aspirantes (los 8 primeros por p_champion)
  const top = rows.slice(0, 8);
  const maxP = top[0]?.p_champion || 1;
  const contenders = top.map((r) => `
    <div class="contender" title="${teamName(r.team)}: ${pct(r.p_champion)}">
      <span class="who">${flagImg(r.team)}<span>${teamName(r.team)}</span></span>
      <span class="track"><span class="fill" style="width:${((r.p_champion / maxP) * 100).toFixed(1)}%"></span></span>
      <span class="val">${pct(r.p_champion)}</span>
    </div>`).join("");

  el.innerHTML = `
    <h2 class="section">${t("champion.title")}</h2>
    <p class="lede">${t("champion.lede", {
      team: `<b>${teamName(rows[0].team)}</b>`, pct: pct(rows[0].p_champion),
      team2: teamName(rows[1].team), pct2: pct(rows[1].p_champion),
    })}</p>
    <div class="card">
      <div class="contenders">${contenders}</div>
    </div>
    <p class="note">${t("champion.intro", { date: fmtDay(snap.date), odds: state.approach === "odds" })}</p>
    <div class="card" style="overflow-x:auto">
      <table class="probs">
        <thead><tr><th class="team-col">${t("col.team")}</th>
          ${SIM_COLS.map(([, h]) => `<th>${t(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r, i) => `
          <tr><td class="team-cell"><span class="rank-num">${i + 1}</span>${flagImg(r.team)}${teamName(r.team)}
                <span class="group-chip">${r.group}</span></td>
            ${SIM_COLS.map(([k]) => pcell(r[k])).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

// -------------------------------------------------------------- evolución

const EVO_METRICS = [
  ["p_champion", "evo.m.champion"],
  ["p_final", "evo.m.final"],
  ["p_sf", "evo.m.sf"],
  ["p_qf", "evo.m.qf"],
  ["p_knockout", "evo.m.knockout"],
];
// paleta categórica validada (banda de luminosidad, croma y separación CVD:
// peor par adyacente ΔE 24.2) con el validador del skill de dataviz; el orden
// de los huecos es parte de la garantía — no reordenar sin revalidar
const PALETTE = ["#009490", "#d95926", "#2a78d6", "#eda100",
                 "#008300", "#4a3aa7", "#e34948", "#e87ba4"];
const EVO_DEFAULT_N = 8;         // selección por defecto: una por hueco de la paleta
const EVO_GRAY = "#c8cfcf";      // color de las selecciones de fondo (no resaltadas)

// color estable por equipo resaltado, en el orden (ordenado por métrica) dado
function evoColors(selectedOrdered) {
  const map = {};
  selectedOrdered.forEach((tm, i) => (map[tm] = PALETTE[i % PALETTE.length]));
  return map;
}

// leyenda interactiva: todas las selecciones como chips conmutables (clic para
// resaltar/quitar) + botón para deseleccionar todas
function selectableLegend(teamsOrdered, selected, colorOf) {
  const clear = `<button class="evo-clear" type="button"${selected.size ? "" : " disabled"}>${t("legend.clear")}</button>`;
  const chips = teamsOrdered.map((tm) => {
    const on = selected.has(tm);
    return `<span class="item team-toggle ${on ? "on" : "off"}" data-team="${tm}" title="${on ? t("legend.remove") : t("legend.add")}">
      <span class="swatch" style="background:${on ? colorOf[tm] : EVO_GRAY}"></span>
      ${flagImg(tm)} ${teamName(tm)}</span>`;
  }).join("");
  return `<div class="evo-legend selectable">${clear}${chips}</div>`;
}

// conecta los clics de la leyenda; selKey es "evoSelected" o "rankSelected"
function wireLegend(el, selected, selKey, rerender) {
  el.querySelectorAll(".team-toggle").forEach((n) =>
    n.addEventListener("click", () => {
      const tm = n.dataset.team;
      if (selected.has(tm)) selected.delete(tm); else selected.add(tm);
      state[selKey] = selected;
      rerender();
    }));
  const clear = el.querySelector(".evo-clear");
  if (clear) clear.addEventListener("click", () => { state[selKey] = new Set(); rerender(); });
}

function renderEvolution() {
  const snaps = curCache().sims;
  const el = $("#tab-evolution");
  if (!snaps.length) { el.innerHTML = `<p class="note">${t("evo.none")}</p>`; return; }

  const metric = state.evoMetric;
  const last = snaps[snaps.length - 1];
  const ordered = [...last.rows].sort((a, b) => b[metric] - a[metric]).map((r) => r.team);
  const selected = state.evoSelected || new Set(ordered.slice(0, EVO_DEFAULT_N));
  const colorOf = evoColors(ordered.filter((tm) => selected.has(tm)));
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
    grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e9eded"/>
             <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#4f5a5e">${Math.round(v * 100)}%</text>`;
  }
  // eje X: fechas (máx ~12 etiquetas)
  const every = Math.max(1, Math.ceil(n / 12));
  let xaxis = "";
  snaps.forEach((s, i) => {
    if (i % every === 0 || i === n - 1)
      xaxis += `<text x="${x(i)}" y="${H - mB + 18}" text-anchor="middle" font-size="11" fill="#4f5a5e">${fmtShort(s.date)}</text>`;
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
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
    s.values.forEach((v, i) => {
      if (v != null) lines += `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${s.color}"/>`;
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
    lines += `<text x="${x(n - 1) + 21}" y="${l.ly}" font-size="11.5" font-weight="600" fill="#1f2529">${teamName(l.s.team)} ${pct(l.v)}</text>`;
  });

  const metricLabel = t(EVO_METRICS.find(([k]) => k === metric)[1]);
  el.innerHTML = `
    <h2 class="section">${t("evo.title")}</h2>
    <div class="evo-controls">
      <label>${t("label.metric")}
        <select id="evo-metric">${EVO_METRICS.map(([k, l]) =>
          `<option value="${k}"${k === metric ? " selected" : ""}>${t(l)}</option>`).join("")}</select>
      </label>
      <span class="note">${t("evo.note", {
        total: ordered.length, metric: metricLabel, odds: state.approach === "odds",
        selected: selected.size, oneDay: n === 1,
      })}</span>
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
  if (!snap) { el.innerHTML = `<p class="note">${t("groups.none")}</p>`; return; }
  const byGroup = {};
  snap.rows.forEach((r) => (byGroup[r.group] ||= []).push(r));

  el.innerHTML = `
    <h2 class="section">${t("groups.title")}</h2>
    <p class="note">${t("groups.intro", { date: fmtDay(snap.date) })}</p>
    <div class="groups-grid">${Object.keys(state.meta.groups).map((g) => {
      const rows = (byGroup[g] || []).sort((a, b) => b.xPts - a.xPts);
      return `<div class="card group-card"><h3>${t("label.group", { g })}</h3>
        <table class="gtable">
          <thead><tr><th>${t("col.team")}</th><th>${t("pos.1")}</th><th>${t("pos.2")}</th><th>${t("pos.3")}</th><th>${t("pos.4")}</th>
            <th>${t("col.qualify")}</th><th>xPts</th></tr></thead>
          <tbody>${rows.map((r) => `
            <tr><td class="team-cell">${flagImg(r.team)}${teamName(r.team)}</td>
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
  // Penka/las cuotas liquidan sobre el resultado a los 90', no el de la prórroga
  if (!match.played || !pred) return "";
  const [ph, pa] = pickOf(pred).split("-").map(Number);
  if (ph === match.home_score_90 && pa === match.away_score_90)
    return `<span class="badge exact">${t("badge.exact")}</span>`;
  if (Math.sign(ph - pa) === Math.sign(match.home_score_90 - match.away_score_90))
    return `<span class="badge outcome">${t("badge.outcome")}</span>`;
  return `<span class="badge miss">${t("badge.miss")}</span>`;
}

// "pró."/"pen." junto al resultado real cuando hubo prórroga o penaltis; el
// title recuerda el marcador a los 90', que es sobre lo que puntúa el pick
function etTag(m) {
  if (!m.played) return "";
  const s90 = `${m.home_score_90} – ${m.away_score_90}`;
  if (m.shootout_winner)
    return ` <span class="et-tag" title="${t("match.pens_title", { team: teamName(m.shootout_winner), score: s90 })}">${t("match.pens")}</span>`;
  if (m.home_score !== m.home_score_90 || m.away_score !== m.away_score_90)
    return ` <span class="et-tag" title="${t("match.aet_title", { score: s90 })}">${t("match.aet")}</span>`;
  return "";
}

function matchCard(m) {
  const pred = predictionFor(m);
  const score = m.played
    ? `<span class="score">${m.home_score} – ${m.away_score}${etTag(m)}</span>`
    : `<span class="score future">${t("match.vs")}</span>`;
  // etiqueta según quepa: "1 · 68%" → "68%" → nada (el title siempre la lleva)
  const segLabel = (prefix, p) =>
    p >= 0.17 ? `${prefix} · ${pct(p)}` : p >= 0.09 ? pct(p) : "";
  const seg = (cls, prefix, p) =>
    `<span class="seg ${cls}" style="width:${p * 100}%" title="${prefix}: ${pct(p)}">${segLabel(prefix, p)}</span>`;
  const probBar = pred ? `
    <div class="prob-bar" title="${t("match.prob_title")}">
      ${seg("p1", "1", pred.P_1)}${seg("px", "X", pred.P_X)}${seg("p2", "2", pred.P_2)}
    </div>` : "";
  const predLine = pred ? `
    <div class="pred-line">
      <span class="pick-chip" title="${t("match.strategy_title", { strategy: strategyLabel(state.strategy) })}">${t("match.pred_prefix")} ${pickOf(pred)}</span>
      ${pickBadge(m, pred)}
    </div>` : `<div class="pred-line"><span class="xp">${t("match.no_pred")}</span></div>`;
  const oddsLine = m.odds ? `
    <div class="odds-line">${t("match.odds")}
      <span class="o">1&nbsp;${m.odds[0].toFixed(2)}</span>
      <span class="o">X&nbsp;${m.odds[1].toFixed(2)}</span>
      <span class="o">2&nbsp;${m.odds[2].toFixed(2)}</span>
    </div>` : "";
  return `<div class="match-card" data-home="${m.home}" data-away="${m.away}" data-date="${m.date}"
       title="${t("match.card_title")}">
    <div class="meta"><span>${m.city}${m.group ? ` · ${t("label.group", { g: m.group })}` : ""}</span>
      <span>${fmtShort(m.date)}</span></div>
    <div class="match-row">
      <span class="team">${flagImg(m.home, true)}<span>${teamName(m.home)}</span></span>
      ${score}
      <span class="team away">${flagImg(m.away, true)}<span>${teamName(m.away)}</span></span>
    </div>
    ${predLine}${probBar}${oddsLine}
  </div>`;
}

function renderCalendar() {
  const el = $("#tab-calendar");
  if (!state.matches?.length) { el.innerHTML = `<p class="note">${t("cal.none")}</p>`; return; }

  const byRound = {};
  state.matches.forEach((m) => (byRound[m.round_id] ||= []).push(m));

  el.innerHTML = `
    <h2 class="section">${t("cal.title")}</h2>
    <p class="note">${t("cal.intro")}</p>
    ${[...ROUND_ORDER].reverse().filter((r) => byRound[r]).map((rid) => {
      const ms = byRound[rid];
      const byDay = {};
      ms.forEach((m) => (byDay[m.date] ||= []).push(m));
      return `<div class="round-block"><h2>${roundName(rid)}</h2>
        ${Object.keys(byDay).sort().reverse().map((d) => `
          <div class="day-label">${fmtDay(d)}</div>
          <div class="match-grid">${byDay[d].map(matchCard).join("")}</div>`).join("")}
      </div>`;
    }).join("")}`;
}

// ------------------------------------------------------------ conectividad

// confederaciones: identidades fijas sobre la misma paleta validada
const CONF_COLORS = {
  UEFA: "#2a78d6", CONMEBOL: "#009490", CONCACAF: "#d95926",
  CAF: "#eda100", AFC: "#e34948", OFC: "#4a3aa7",
};
const CONF_UNKNOWN = "#9aa4a4";
// nombre de confederación con su punto de color (el texto queda en tinta: los
// tonos medios de la paleta no dan 4.5:1 como color de texto)
const confLabel = (conf) => conf
  ? `<span class="conf-dot" style="background:${CONF_COLORS[conf] || CONF_UNKNOWN}"></span>${conf}`
  : "–";

async function loadConnectivity() {
  if (state.connLoading) return;
  state.connLoading = true;
  const el = $("#tab-connectivity");
  el.innerHTML = `<p class="note">${t("conn.loading")}</p>`;
  try {
    state.connectivity = await fetchJSON("/api/connectivity");
  } catch (e) {
    el.innerHTML = `<p class="note">${t("conn.error", { msg: e.message })}</p>`;
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
  const xMax = Math.max(...pts.map((tm) => tm.bridge_share)) * 1.1;
  const ys = pts.map((tm) => tm.rating);
  const yMin = Math.min(...ys) - 0.2, yMax = Math.max(...ys) + 0.2;
  const X = (v) => mL + (v / xMax) * (W - mL - mR);
  const Y = (v) => mT + (1 - (v - yMin) / (yMax - yMin)) * (H - mT - mB);

  let grid = "";
  for (let v = 0; v <= xMax; v += 0.1) {
    grid += `<line x1="${X(v)}" y1="${mT}" x2="${X(v)}" y2="${H - mB}" stroke="#e9eded"/>
             <text x="${X(v)}" y="${H - mB + 16}" text-anchor="middle" font-size="11" fill="#4f5a5e">${Math.round(v * 100)}%</text>`;
  }
  for (let v = Math.ceil(yMin * 2) / 2; v <= yMax; v += 0.5) {
    grid += `<line x1="${mL}" y1="${Y(v)}" x2="${W - mR}" y2="${Y(v)}" stroke="#e9eded"/>
             <text x="${mL - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="#4f5a5e">${v.toFixed(1)}</text>`;
  }
  grid += `<text x="${(mL + W - mR) / 2}" y="${H - 6}" text-anchor="middle" font-size="11.5" fill="#4f5a5e">${t("conn.scatter_xaxis")}</text>
           <text transform="rotate(-90)" x="${-(mT + H - mB) / 2}" y="13" text-anchor="middle" font-size="11.5" fill="#4f5a5e">${t("conn.scatter_yaxis")}</text>`;

  let marks = "";
  pts.forEach((tm) => {
    const info = teamInfo(tm.team);
    const cx = X(tm.bridge_share), cy = Y(tm.rating);
    const sel = tm.team === state.connSelected;
    marks += `<g class="conn-pt${sel ? " sel" : ""}" data-team="${tm.team}">
      <circle cx="${cx}" cy="${cy}" r="13" fill="${CONF_COLORS[tm.conf] || CONF_UNKNOWN}" opacity="${sel ? "0.85" : "0.3"}"/>
      ${info.code ? `<image href="/flags/${info.code}.svg" x="${cx - 10}" y="${cy - 7}" width="20" height="14"/>` : ""}
      <title>${teamName(tm.team)} (${tm.conf}) — rating ${tm.rating.toFixed(2)} · ${pct(tm.bridge_share)} · ${tm.opp_rating.toFixed(2)}</title>
    </g>`;
  });
  return `<svg class="evo-svg" viewBox="0 0 ${W} ${H}">${grid}${marks}</svg>`;
}

// desglose del equipo seleccionado: contra qué confederaciones entrena su rating
function connDetail(d) {
  const tm = d.teams.find((x) => x.team === state.connSelected);
  if (!tm) return `<p class="note">${t("conn.detail_prompt")}</p>`;
  const known = Object.values(tm.by_conf).reduce((a, b) => a + b, 0);
  const rest = 1 - known;   // rivales sin confederación inferible en la ventana
  const segs = d.confederations
    .filter((c) => tm.by_conf[c] > 0.001)
    .map((c) => `<span class="seg" style="width:${tm.by_conf[c] * 100}%;background:${CONF_COLORS[c]};color:${inkFor(CONF_COLORS[c])}"
        title="${c}: ${pct(tm.by_conf[c])}">${tm.by_conf[c] >= 0.09 ? c : ""}</span>`)
    .join("");
  return `
    <div class="conn-detail-head">${flagImg(tm.team, true)} <b>${teamName(tm.team)}</b>
      <span class="group-chip">${confLabel(tm.conf)}</span></div>
    <div class="conn-stats">
      <span><b>${tm.rating.toFixed(2)}</b> ${t("conn.stat_rating")}</span>
      <span><b>${tm.matches}</b> ${t("conn.stat_matches")}</span>
      <span><b>${pct(tm.bridge_share)}</b> ${t("conn.stat_bridge")}</span>
      <span><b>${tm.opp_rating.toFixed(2)}</b> ${t("conn.stat_opp")}</span>
    </div>
    <div class="prob-bar conn-bar" title="${t("conn.bar_title")}">
      ${segs}${rest > 0.001 ? `<span class="seg" style="width:${rest * 100}%;background:${CONF_UNKNOWN};color:${inkFor(CONF_UNKNOWN)}"
        title="${t("conn.bar_unknown_title", { pct: pct(rest) })}">${rest >= 0.09 ? "¿?" : ""}</span>` : ""}
    </div>`;
}

// matriz conf x conf con cada fila normalizada por su peso total
function connHeatmap(d) {
  const confs = d.confederations;
  const Wm = d.matrix_weight, C = d.matrix_count;
  const tot = Wm.map((row) => row.reduce((a, b) => a + b, 0));
  return `<table class="probs conn-heat">
    <thead><tr><th class="team-col">${t("conn.heat_conf")}</th>${confs.map((c) => `<th>${c}</th>`).join("")}</tr></thead>
    <tbody>${confs.map((c, i) => `
      <tr><td class="team-cell">${confLabel(c)}</td>
        ${confs.map((c2, j) => {
          const share = tot[i] ? Wm[i][j] / tot[i] : 0;
          const { bg, dark } = shadeCell(Math.min(share * 1.6, 0.92));
          return `<td class="pcell${dark ? " dark" : ""}${i === j ? " diag" : ""}"
              style="background:${bg}"
              title="${c} – ${c2}: ${C[i][j]} · ${Wm[i][j].toFixed(0)} (${pct(share)})">${pct(share)}</td>`;
        }).join("")}</tr>`).join("")}
    </tbody></table>`;
}

function connTable(d) {
  return `<table class="probs">
    <thead><tr><th class="team-col">${t("col.team")}</th><th>${t("col.conf")}</th><th>${t("col.matches")}</th>
      <th>${t("col.bridge")}</th>
      <th>${t("col.opp")}</th>
      <th>${t("col.rating")}</th></tr></thead>
    <tbody>${d.teams.map((tm, i) => `
      <tr class="conn-row${tm.team === state.connSelected ? " sel" : ""}" data-team="${tm.team}">
        <td class="team-cell"><span class="rank-num">${i + 1}</span>${flagImg(tm.team)}${teamName(tm.team)}</td>
        <td>${confLabel(tm.conf)}</td>
        <td>${tm.matches}</td>${pcell(tm.bridge_share)}
        <td>${tm.opp_rating.toFixed(2)}</td>
        <td><b>${tm.rating.toFixed(2)}</b></td></tr>`).join("")}
    </tbody></table>`;
}

function renderConnectivity() {
  if (!state.meta) return;            // aún sin /api/meta: render() repintará
  const el = $("#tab-connectivity");
  if (!el) return;                    // versión pública: la pestaña no existe
  const d = state.connectivity;
  if (!d) { loadConnectivity(); return; }
  el.innerHTML = `
    <h2 class="section">${t("conn.title")}</h2>
    <p class="note">${t("conn.intro", { date: fmtDay(d.as_of) })}</p>
    <div class="card">
      <h3 class="conn-h3">${t("conn.scatter_h3")}</h3>
      <p class="note">${t("conn.scatter_note")}</p>
      ${connScatter(d)}
      <div class="evo-legend">${d.confederations.map((c) => `
        <span class="item"><span class="swatch" style="background:${CONF_COLORS[c]};height:10px;border-radius:5px"></span>${c}</span>`).join("")}
        <span class="item"><span class="swatch" style="background:${CONF_UNKNOWN};height:10px;border-radius:5px"></span>${t("conn.legend_unknown")}</span></div>
    </div>
    <div class="card" id="conn-detail">${connDetail(d)}</div>
    <div class="card">
      <h3 class="conn-h3">${t("conn.matrix_h3")}</h3>
      <p class="note">${t("conn.matrix_note")}</p>
      <div style="overflow-x:auto">${connHeatmap(d)}</div>
    </div>
    <div class="card" style="overflow-x:auto">
      <h3 class="conn-h3">${t("conn.table_h3")}</h3>
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
  el.innerHTML = `<p class="note">${t("rank.loading")}</p>`;
  try {
    const hist = await fetchJSON(`/api/rankings/history?engine=${eng}`);
    let live = null;
    if (!hist.snapshots.length) {
      // sin snapshots fechados todavía: ajuste en vivo a día de hoy
      el.innerHTML = `<p class="note">${t("rank.live_loading")}</p>`;
      live = await fetchJSON(`/api/rankings?engine=${eng}`);
    }
    state.rankings[eng] = { snapshots: hist.snapshots, live };
  } catch (e) {
    el.innerHTML = `<p class="note">${t("rank.error", { msg: e.message })}</p>`;
    return;
  } finally {
    state.rankLoading = false;
  }
  renderRankings();
}

// métricas de la gráfica de evolución (la de Elo solo si el motor la tiene)
function rankMetrics(hasElo) {
  const m = [["rating", "rank.m.rating"]];
  if (hasElo) m.push(["elo", "rank.m.elo"]);
  m.push(["rank", "rank.m.rank"], ["opp_rating", "rank.m.opp"]);
  return m;
}

function renderRankings() {
  if (!state.meta) return;
  const el = $("#tab-rankings");
  const data = state.rankings[state.engine];
  if (!data) { loadRankings(); return; }

  const engLabel = engineLabel(state.engine);
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

  const sortLabel = hasElo ? t("rank.sort_elo") : t("rank.sort_rating");
  const tbody = rows.map((tm, i) => `
    <tr class="conn-row" data-team="${tm.team}">
      <td class="team-cell"><span class="rank-num">${i + 1}</span>${flagImg(tm.team)}${teamName(tm.team)}</td>
      <td>${confLabel(tm.conf)}</td>
      ${hasElo ? `<td><b>${Math.round(tm.elo)}</b></td>` : ""}
      <td>${tm.atk.toFixed(2)}</td>
      <td>${tm.dfn.toFixed(2)}</td>
      <td><b>${tm.rating.toFixed(2)}</b></td>
      <td>${tm.opp_rating != null ? tm.opp_rating.toFixed(2) : "–"}</td>
    </tr>`).join("");

  const source = fromLive
    ? t("rank.source_live", { date: fmtDay(asOf) })
    : t("rank.source_snap", { date: fmtDay(asOf) });

  const evoBlock = snaps.length ? rankEvolutionBlock(snaps, hasElo) : null;

  el.innerHTML = `
    <h2 class="section">${t("rank.title", { engine: engLabel })}</h2>
    <p class="note">${t("rank.intro", { engine: engLabel, sort: sortLabel, source, hasElo })}</p>
    ${evoBlock ? evoBlock.html : ""}
    <div class="card" style="overflow-x:auto">
      <h3 class="conn-h3">${t("rank.class_h3", { live: fromLive, date: fmtShort(asOf) })}</h3>
      <table class="probs">
        <thead><tr><th class="team-col">${t("col.team")}</th><th>${t("col.conf")}</th>
          ${hasElo ? `<th>${t("col.elo")}</th>` : ""}
          <th>${t("col.attack")}</th>
          <th>${t("col.defence")}</th>
          <th>${t("col.rating")}</th>
          <th>${t("col.opp")}</th>
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
    .filter((tm) => state.meta.teams[tm])
    .sort((a, b) => isRank ? (snapRank[lastIdx][a] - snapRank[lastIdx][b])
                           : (valAt(lastIdx, b) - valAt(lastIdx, a)));
  const selected = state.rankSelected || new Set(ordered.slice(0, EVO_DEFAULT_N));
  const colorOf = evoColors(ordered.filter((tm) => selected.has(tm)));
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
      grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e9eded"/>
               <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#4f5a5e">${v}</text>`;
  } else {
    const step = niceStep(hi - lo);
    const dec = step < 0.1 ? 2 : step < 1 ? 1 : 0;
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step)
      grid += `<line x1="${mL}" y1="${y(v)}" x2="${W - mR}" y2="${y(v)}" stroke="#e9eded"/>
               <text x="${mL - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#4f5a5e">${v.toFixed(dec)}</text>`;
  }
  const every = Math.max(1, Math.ceil(n / 12));
  let xaxis = "";
  snaps.forEach((s, i) => {
    if (i % every === 0 || i === n - 1)
      xaxis += `<text x="${x(i)}" y="${H - mB + 18}" text-anchor="middle" font-size="11" fill="#4f5a5e">${fmtShort(s.date)}</text>`;
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
      lines += `<polyline points="${pts.join(" ")}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
    s.values.forEach((v, i) => {
      if (v != null) lines += `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${s.color}"/>`;
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
    lines += `<text x="${x(n - 1) + 21}" y="${l.ly}" font-size="11.5" font-weight="600" fill="#1f2529">${teamName(l.s.team)} ${fmtV(l.v)}</text>`;
  });

  const metricLabel = t(metrics.find(([k]) => k === metric)[1]);
  const html = `
    <div class="card">
      <h3 class="conn-h3">${t("rank.evo_h3")}</h3>
      <div class="evo-controls">
        <label>${t("label.metric")}
          <select id="rank-metric">${metrics.map(([k, l]) =>
            `<option value="${k}"${k === metric ? " selected" : ""}>${t(l)}</option>`).join("")}</select>
        </label>
        <span class="note">${t("rank.evo_note", {
          total: ordered.length, metric: metricLabel, selected: selected.size,
          oneDay: n === 1, n, isRank,
        })}</span>
      </div>
      <svg class="evo-svg" viewBox="0 0 ${W} ${H}">${grid}${xaxis}${lines}</svg>
      ${selectableLegend(ordered, selected, colorOf)}
    </div>`;
  return { html, selected };
}

// ----------------------------------------------------------- documentación

function renderDocs() {
  const el = $("#tab-docs");
  if (el) el.innerHTML = t("docs.html");
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
  box.innerHTML = `<div class="matrix-loading">${t("matrix.loading")}</div>`;
  let d;
  try {
    const q = new URLSearchParams({ home, away, date, approach: state.approach,
                                    engine: state.engine, strategy: state.strategy });
    d = await fetchJSON(`/api/matrix?${q}`);
  } catch (e) {
    box.innerHTML = `<div class="matrix-loading">${t("matrix.error", { msg: e.message })}</div>`;
    return;
  }
  const m = state.matches.find((x) => x.home === home && x.away === away && x.date === date);
  const n = d.matrix.length;
  const maxP = Math.max(...d.matrix.flat());
  const [pickH, pickA] = d.pick.split("-").map(Number);

  const cell = (h, a) => {
    const p = d.matrix[h][a];
    const { bg, dark } = shadeCell(maxP ? Math.min((p / maxP) * 0.92, 0.92) : 0);
    const cls = [
      dark ? "dark" : "",
      h === pickH && a === pickA ? "pick" : "",
      m?.played && h === m.home_score_90 && a === m.away_score_90 ? "real" : "",
    ].join(" ");
    const label = p >= 0.001 ? (p * 100).toFixed(1) : "·";
    return `<td class="${cls}" style="background:${bg}"
                title="${h}-${a}: ${(p * 100).toFixed(2)}%">${label}</td>`;
  };

  const score = m?.played ? `${m.home_score} – ${m.away_score}${etTag(m)}` : t("match.vs");
  box.innerHTML = `
    <div class="matrix-head">${flagImg(home, true)} ${teamName(home)}
      <span style="color:var(--muted)">${score}</span> ${teamName(away)} ${flagImg(away, true)}</div>
    <div class="matrix-sub">${t("matrix.sub", {
      engine: engineLabel(d.engine), date: fmtDay(d.as_of), odds: d.odds_used,
      p1: pct(d.p1), px: pct(d.px), p2: pct(d.p2), pick: d.pick,
    })}</div>
    <table class="matrix">
      <tr><th></th><th class="axis" colspan="${n}">${t("matrix.away_goals", { team: teamName(away) })}</th></tr>
      <tr><th class="axis">${t("matrix.home_goals", { team: teamName(home) })}</th>${[...Array(n)].map((_, a) => `<th>${a}</th>`).join("")}</tr>
      ${[...Array(n)].map((_, h) =>
        `<tr><th>${h}</th>${[...Array(n)].map((_, a) => cell(h, a)).join("")}</tr>`).join("")}
    </table>
    <div class="matrix-legend">
      <span><span class="key" style="outline:2.5px solid var(--hi); outline-offset:-2.5px"></span>${t("matrix.legend_pick")}</span>
      ${m?.played ? `<span><span class="key" style="outline:2.5px solid var(--ink); outline-offset:-2.5px"></span>${t("matrix.legend_real")}</span>` : ""}
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
  log.textContent = st.log.join("\n") || t("refresh.starting");
  log.scrollTop = log.scrollHeight;
  if (st.running) {
    pollTimer = setTimeout(pollRefresh, 2000);
  } else {
    $("#refresh-start").disabled = false;
    if (st.returncode === 0) {
      log.textContent += t("refresh.done");
      await reloadAll();
    } else if (st.returncode != null) {
      log.textContent += t("refresh.failed", { code: st.returncode });
    }
  }
}

function setupRefresh() {
  const btn = $("#refresh-btn");
  if (!btn) return;                   // versión pública: el botón no existe
  const modal = $("#refresh-modal");
  btn.addEventListener("click", () => {
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

// -------------------------------------------------------------------- i18n UI

// recorre los textos estáticos marcados en index.html y los traduce al idioma
// activo (textContent, atributos title y placeholder); marca el botón activo.
function applyStaticI18n() {
  document.documentElement.lang = state.lang;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll("[data-i18n-title]").forEach((n) => { n.title = t(n.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
  document.querySelectorAll(".lang-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.lang === state.lang));
}

function setLanguage(lang) {
  if (lang !== "es" && lang !== "en") return;
  state.lang = lang;
  try { localStorage.setItem("wcpred_lang", lang); } catch (e) { /* modo privado */ }
  applyStaticI18n();
  if (state.meta) { buildEngineSelect(); buildSnapshotSelect(); renderDocs(); render(); }
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
  applyStaticI18n();
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      activateTab(btn.dataset.tab);
      history.replaceState(null, "", `#${btn.dataset.tab}`);
    }));
  if (location.hash) activateTab(location.hash.slice(1));

  document.querySelectorAll(".lang-btn").forEach((b) =>
    b.addEventListener("click", () => setLanguage(b.dataset.lang)));

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
    $("#snapshot-note").textContent = t("snapshot.predictions", { date: fmtDay(e.target.value) });
    render();
  });

  setupMatrix();
  setupRefresh();
}

setupUI();
reloadAll().catch((e) => {
  document.querySelector("main").innerHTML =
    `<p class="note">${t("init.error", { msg: e.message })}</p>`;
});
