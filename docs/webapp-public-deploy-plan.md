# Plan: webapp bilingüe + despliegue público en Render

## Contexto

La webapp (`webapp/`, FastAPI + JS vanilla) hoy solo existe en local, está
íntegramente en español y permite refrescar datos (`POST /api/refresh` lanza los
scripts de generación). Queremos:

1. **Bilingüe EN/ES, por defecto inglés**, con conmutador de idioma.
2. **Desplegarla públicamente** (accesible desde cualquier sitio) en **Render**
   (servicio Python persistente).
3. La **versión pública no puede actualizar datos** (los genero yo en local con
   los scripts) → ocultar y bloquear el refresh.
4. La versión pública **no muestra la pestaña Conectividad**.
5. Añadir una **pestaña de Documentación** breve y poco técnica que explique el
   proceso completo: cómo encajan los motores intercambiables (Dixon-Coles /
   Elo / Bayesiano) y las cuotas. Basada en `docs/models-explained.md`.

Decisión de despliegue (tras research): Render mantiene **todas** las funciones
de visualización, incluida la matriz de marcadores al pulsar un pick y el
fallback de rankings en vivo (recálculo `dc`/`elo`, rápido y cacheado). Los
datos viajan en git (`data/`, 5.4 MB ya versionado), así que desplegar = `git
push` con auto-deploy. Una sola base de código sirve los dos modos vía la
variable de entorno `WCPRED_PUBLIC` (local sin ella = completo; Render con ella
= público).

## Parte A — Modo público vía `WCPRED_PUBLIC` (`webapp/server.py`)

Leer `PUBLIC = bool(os.getenv("WCPRED_PUBLIC"))` al inicio. Efectos:

- **Motores**: si `PUBLIC`, `ENGINES = ("dc", "elo")` (sin `bayes`, que necesita
  CmdStan y no estará instalado). `DEFAULT_ENGINE` sigue `"elo"`.
- **`POST /api/refresh`**: al principio del handler,
  `if PUBLIC: raise HTTPException(403, "deshabilitado en la versión pública")`.
  `GET /api/refresh/status` puede quedarse (devuelve idle).
- **`GET /api/connectivity`**: `if PUBLIC: raise HTTPException(404)`.
- **`/api/meta`**: añadir `"public": PUBLIC` para que el frontend oculte el
  botón de refresh y la pestaña Conectividad.

`/api/matrix` y `/api/rankings` (recálculo en vivo) se mantienen: solo usan
`dc`/`elo`, que dependen de `pandas/numpy/scipy` ya presentes; `bayes` nunca se
importa porque el picker no lo ofrece. No se necesita el extra `.[bayes]` ni
secretos en producción.

## Parte B — i18n EN/ES (por defecto EN)

Nuevo fichero **`webapp/static/i18n.js`** (cargado antes de `app.js` en
`index.html`): un diccionario `I18N = { en: {...}, es: {...} }` y un helper
`t(key)` que lee de `state.lang`. `state.lang` por defecto `"en"`, persistido en
`localStorage`.

- **`index.html`**: marcar los textos estáticos con `data-i18n="clave"` (y
  `data-i18n-title` para tooltips): título/subtítulo, etiquetas de los toggles
  (Cuotas de mercado, Marcador más probable), "Motor", "Día", botón refresh,
  botones de tabs, modales. Añadir un **conmutador de idioma EN/ES** en
  `.controls` del header. Un `applyStaticI18n()` recorre `[data-i18n]` al cargar
  y al cambiar idioma; actualiza también `<html lang>` y `<title>`.
- **`app.js`**: sustituir los literales en español de las funciones `render*`
  por `t(...)`. Afecta a las constantes `ENGINE_LABELS`, `STRATEGY_LABELS`,
  `SIM_COLS`, `EVO_METRICS` (pasan a derivarse de `t()`), y a las
  notas/encabezados generados (¿Quién gana?, Evolución, Grupos, Calendario,
  Rankings, modal de matriz, mensaje de error). El conmutador llama
  `applyStaticI18n()` + `render()` (sin recarga de datos).
- **Nombres de equipo**: helper `teamName(name)` → `lang==="es" ?
  teams[name].es : name` (la clave del dict `TEAMS` ya es el nombre en inglés de
  martj42). Reemplaza los usos directos del nombre en todas las tablas/gráficos.
- **Etiquetas de ronda**: derivarlas en el frontend desde `round_id` que ya
  envía `/api/matches` (`r32/r16/qf/sf/p3/f` y `j1/j2/j3` → "Group stage ·
  Matchday N" / "Fase de grupos · Jornada N"), en vez de usar `round_name`
  (español) del servidor. Sin cambios en el backend.
- **Formato de fechas**: `fmtDay`/`fmtShort` usan locale según `state.lang`
  (`en-GB`/`es-ES`).

## Parte C — Pestaña de Documentación (ambos modos)

- **`index.html`**: añadir `<button class="tab" data-tab="docs" data-i18n="...">`
  y `<section id="tab-docs" class="panel">`.
- **`app.js`**: `renderDocs()` que pinta HTML estático (bilingüe vía `t()`)
  resumiendo `docs/models-explained.md` de forma breve y poco técnica:
  1. El flujo: **resultados** entrenan el modelo → (opcional **xG** mezclado) →
     el **motor** produce una matriz de probabilidad de marcadores → las
     **cuotas** se mezclan al predecir (1X2 del mercado, forma del modelo) → se
     elige el marcador que **maximiza los puntos Penka esperados** (no el más
     probable) → **Monte Carlo** para grupos y cuadro.
  2. Los tres **motores intercambiables**, 2-3 frases cada uno: Dixon-Coles
     (Poisson ponderado, modelo de producción), Elo (puntos por resultado),
     Bayesiano (DC con incertidumbre; nota de que solo está en la versión
     local).
  3. Un diagrama de flujo simplificado (texto/HTML, como el de
     `models-explained.md`).
  El texto vive en `i18n.js` (claves `en`/`es`). Activar carga perezosa en
  `activateTab` como ya se hace con Conectividad/Rankings (no necesita fetch).

## Parte D — Ocultar refresh y Conectividad en público (`app.js` + `index.html`)

En el init de `app.js`, tras cargar `/api/meta`, si `meta.public`:
- ocultar `#refresh-btn` (y no cablear su handler / modal);
- ocultar el botón de tab `[data-tab="connectivity"]` y su `<section>`; si la URL
  trae `#connectivity`, redirigir a la tab por defecto.
El picker de motor ya solo listará `meta.engines` (`dc`/`elo`).

## Parte E — Despliegue en Render

- Nuevo **`render.yaml`** (Blueprint, runtime Python nativo):
  - `buildCommand: pip install -e ".[web]"`
  - `startCommand: uvicorn webapp.server:app --host 0.0.0.0 --port $PORT`
  - `envVars: WCPRED_PUBLIC=1` (+ fijar versión de Python).
- Alternativa equivalente si el runtime nativo da problemas: un `Dockerfile`
  (`python:3.11-slim`, `pip install -e ".[web]"`, `CMD uvicorn ... --port
  $PORT`).
- `data/` viaja en git → sin paso extra de subida de datos. Para actualizar la
  web pública: generar en local con los scripts, commit de los CSV y `git push`
  (auto-deploy).
- **`README.md`**: sección de despliegue (Render + `WCPRED_PUBLIC`) y nota del
  conmutador de idioma.

## Ficheros a tocar

- `webapp/server.py` — gating `WCPRED_PUBLIC` (ENGINES, refresh/connectivity
  403, `meta.public`).
- `webapp/static/index.html` — `data-i18n`, conmutador de idioma, tab Docs,
  carga de `i18n.js`.
- `webapp/static/app.js` — integración i18n en `render*`, `teamName`, etiquetas
  de ronda desde `round_id`, `renderDocs`, ocultado público.
- `webapp/static/i18n.js` *(nuevo)* — diccionario EN/ES + `t()` + textos de Docs.
- `webapp/static/style.css` — estilos del conmutador de idioma y la pestaña Docs.
- `render.yaml` *(nuevo)* (y opcional `Dockerfile`).
- `README.md` — despliegue + idioma.

## Verificación

1. **Local modo completo** (`scripts/run_webapp.sh`, sin `WCPRED_PUBLIC`):
   - Conmutador EN/ES cambia toda la UI (chrome, notas, equipos, rondas, fechas)
     sin recargar; arranca en EN; recuerda elección al recargar.
   - Siguen visibles: botón Actualizar, pestaña Conectividad, motor `bayes`.
   - Nueva pestaña Docs se ve y lee bien en ambos idiomas.
   - La matriz de marcadores (pulsar un pick) sigue funcionando.
2. **Local modo público** (`WCPRED_PUBLIC=1 uvicorn webapp.server:app --port
   8027`):
   - Sin botón Actualizar ni pestaña Conectividad; motor solo `dc`/`elo`.
   - `POST /api/refresh` → 403; `GET /api/connectivity` → 404; `/api/meta` trae
     `"public": true`.
   - Matriz de marcadores y Rankings siguen funcionando (`dc`/`elo`).
3. **Render**: desplegar con el Blueprint, abrir la URL pública y repetir las
   comprobaciones del modo público; verificar arranque en inglés.
