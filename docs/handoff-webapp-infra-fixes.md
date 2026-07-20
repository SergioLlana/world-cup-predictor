# Handoff: arreglos de la revisión de la web e infraestructura (2026-07-07)

Documento de traspaso para el agente que aplique los arreglos. Sale de una
revisión `/code-review high` sobre la web (`webapp/`) y su infraestructura
(`scripts/aws/`, `Dockerfile.pipeline`, `scripts/export_static.py`,
`scripts/daily_publish.sh`). Los 10 hallazgos ya fueron verificados (leyendo
el código y, donde fue posible, probando); no hace falta re-auditar, solo
arreglar. Los números de línea son del commit `146ddea`.

## Contexto mínimo del sistema

- **Dos despliegues del mismo frontend.** En local, `webapp/server.py`
  (FastAPI, puerto 8026, `scripts/run_webapp.sh`) sirve la API en vivo. En
  público (<https://wc-pred.com>), `scripts/export_static.py` congela cada
  respuesta de la API a JSON estático (`build/site/api/*.json`) y
  `scripts/aws/publish_site.sh` lo sube a S3 detrás de CloudFront. El frontend
  (`webapp/static/app.js`) reescribe sus `/api/...` a esos ficheros cuando
  `window.__WCPRED_STATIC__` está inyectado (función `staticPath`).
- **El pipeline diario** corre en ECS Fargate (`scripts/daily_publish.sh` es
  el entrypoint del contenedor, imagen `Dockerfile.pipeline`). Se dispara a
  mano con `scripts/aws/run_pipeline.sh`. Un exit code ≠ 0 dispara una alerta
  SNS por email; exit 0 no avisa de nada.
- **No hay suite de tests.** La verificación de la web es manual (levantar el
  servidor y hacer clic); `scripts/smoke.sh` solo aplica si tocas
  `cli.py`/`backtest.py`/los motores (aquí no).
- **Reglas del repo (CLAUDE.md)**: no tocar el modelo `dc` ni regenerar
  snapshots pasados; los directorios de snapshots bajo `data/` están
  gitignorados (S3 es la fuente de verdad); ficheros generados nunca en la
  raíz del proyecto.
- **No ejecutes comandos AWS con efectos** (sync, invalidations, run-task):
  los arreglos de infra son ediciones de scripts; el usuario los desplegará.
- Commits: mensajes en español con prefijo de área (`webapp:`, `aws:`,
  `docker:`), autor `sergio.llanaperez@gmail.com`.

## Arreglos, por prioridad

### 1. `webapp/static/app.js` — recursión infinita `loadRankings` ↔ `renderRankings` (bug, alta)

- `loadRankings()` (~línea 817): `if (state.rankLoading || state.rankings[eng]) { renderRankings(); return; }`
- `renderRankings()` (~línea 843): `if (!data) { loadRankings(); return; }`
- Si `state.rankLoading` es `true` y el motor activo aún no tiene datos, las
  dos funciones se llaman mutuamente de forma síncrona → `RangeError` (stack
  overflow). Disparo realista: pestaña Rankings con la carga lenta en vuelo
  (el ajuste en vivo de bayes tarda minutos) y el usuario cambia de motor,
  de idioma o el toggle odds/history — cualquier cosa que llame a `render()`.
- **Arreglo**: en `loadRankings`, cuando `state.rankLoading` sea `true`,
  `return` sin llamar a `renderRankings` (al terminar el fetch en curso ya se
  llama a `renderRankings`, que re-disparará la carga del motor que toque).
  El patrón correcto ya existe en `loadConnectivity()` (~línea 651): `if
  (state.connLoading) return;`. Ojo: `rankLoading` es global, no por motor —
  con el `return` temprano basta; no hace falta hacerlo por motor.
- **Verificar**: en local, pestaña Rankings con motor bayes sin snapshots (o
  simular latencia), cambiar de motor/idioma durante la carga → no debe
  petar la consola y al terminar deben pintarse los rankings correctos.

### 2. `webapp/server.py` — NaN en cuotas tumba `/api/matches` (bug, alta)

- `_odds_pairs()` (líneas 228–236) lee el CSV de cuotas con `pd.read_csv`
  crudo y `matches()` devuelve esa lista tal cual (`"odds": odds`, línea
  308), sin pasar por la guarda anti-NaN `_records()` que el resto de
  endpoints sí usa (ver su docstring, líneas 175–180: el codificador de
  Starlette usa `allow_nan=False`).
- Una celda `odds_1/odds_X/odds_2` vacía (README documenta la edición manual
  de `data/input/odds.csv`; los snapshots congelados en `data/input/odds/`
  también entran aquí vía `resolve_odds_path`) → NaN → 500 en todo
  `/api/matches` → `reloadAll()` en app.js falla y sustituye el `<main>` por
  el mensaje de error: la app local no carga.
- **Arreglo**: en `_odds_pairs`, descartar (no emitir) los pares con algún
  valor no finito — p. ej. `if any(pd.isna(v) for v in vals): continue`. El
  frontend ya tolera `odds: null` por partido (`matchCard` solo pinta la
  línea de cuotas si `m.odds` es truthy).
- Nota relacionada (opcional, decidir con criterio): `_odds_pairs` no
  reutiliza `wcpred.data.load_odds`, que lee las cuotas como `str` porque el
  formato puede ser americano (−235/+375) además de decimal.
  `scripts/fetch_odds.py` pide `oddsFormat=decimal`, así que hoy solo llega
  decimal; si se quiere cubrir cuotas americanas metidas a mano habría que
  convertirlas (la conversión vive en `wcpred/odds.py`). Como mínimo, el
  filtro de NaN; la conversión es mejora aparte.
- **Verificar**: vaciar temporalmente una celda de `data/input/odds.csv`
  (¡restaurarla después, está modificado en el working tree!), levantar el
  servidor y comprobar que `/api/matches` responde 200 y ese partido sale
  sin línea de cuotas. `scripts/export_static.py` tiene su propia detección
  (`allow_nan=False` en `write_json`), no hace falta tocarlo.

### 3. `scripts/aws/publish_site.sh` — el sitio público pierde el `no-cache` del bundle (bug de despliegue, alta)

- En local, `NoCacheStaticFiles` (webapp/server.py:692) sirve
  `index.html/app.js/i18n.js/style.css` con `Cache-Control: no-cache`
  precisamente porque hubo un incidente de bundle rancio (lo cuenta su
  docstring). El despliegue estático no reproduce ese invariante: el
  `aws s3 sync` (línea ~36) no fija `--cache-control`, y la distribución
  CloudFront (creada por `20_site.sh`) usa `CachingOptimized` por defecto
  para todo lo que no es `api/*`. Sin `Cache-Control` del origen, los
  navegadores aplican frescura heurística (~10 % de la antigüedad del
  `Last-Modified`); como `sync` solo resube lo que cambia, un `app.js`
  estable acumula días de antigüedad → visitantes recurrentes pueden quedarse
  con un bundle viejo desincronizado del JSON (la invalidación de CloudFront
  no llega a las cachés de los navegadores).
- **Arreglo** (editar el script, no ejecutarlo): subir el "shell" de la app
  con `Cache-Control: no-cache` y dejar los assets pesados cacheables.
  Un enfoque en dos pasos dentro de `publish_site.sh`:
  1. `aws s3 sync` como ahora para todo (los `api/*.json` van por la
     behaviour `CachingDisabled` de CloudFront, no necesitan cabecera).
  2. Después, forzar metadatos en los ficheros del bundle:
     `aws s3 cp` de `index.html`, `app.js`, `i18n.js`, `style.css` con
     `--cache-control "no-cache" --content-type` adecuado (o `cp --recursive
     --exclude "*" --include ...` con `--metadata-directive REPLACE`).
     Cuidado: cambiar solo metadatos exige re-subir el objeto; `sync` no lo
     hace por ti.
  - Alternativa más limpia si se prefiere: banderas/og/fuentes con
    `--cache-control "public,max-age=604800"` y el resto `no-cache`.
    Respetar `--dry-run` (variable `$DRY`) en los pasos nuevos.
- **Verificar**: solo se puede de verdad tras un despliegue del usuario:
  `curl -sI https://wc-pred.com/app.js | grep -i cache-control`. En la PR,
  basta razonar el script y probar la sintaxis con `--dryrun` si hay perfil
  (`wcpred`) configurado — si no hay credenciales, no intentes ejecutarlo.

### 4. `scripts/daily_publish.sh:29` — `export VAR="$(aws ssm …)"` enmascara el fallo (bug de pipeline, media)

- `export ODDS_API_KEY="$(aws ssm get-parameter …)"`: el exit code del
  builtin `export` es 0 aunque la sustitución falle (SC2155), así que con
  `set -e` un fallo de SSM (parámetro borrado, permiso perdido) no aborta;
  la clave queda vacía, `update_data.sh` falla al refrescar cuotas, el
  `|| echo "continuing"` de la línea 32 lo traga, y el pipeline publica el
  sitio con cuotas del último día bueno **saliendo con exit 0** — la alerta
  SNS nunca salta y la degradación es invisible.
- **Arreglo**: separar asignación y export para que `set -e` actúe:
  ```bash
  ODDS_API_KEY="$(aws ssm get-parameter --name "$ODDS_KEY_PARAM" \
    --with-decryption --query Parameter.Value --output text)"
  export ODDS_API_KEY
  ```
  **Decisión de diseño ya tomada en la revisión**: un fallo de SSM es una
  misconfiguración (distinto de un fallo transitorio de la fuente de datos,
  que sí degrada con gracia en la línea 32), así que **abortar es lo
  correcto** — el exit ≠ 0 dispara la alerta SNS existente. No añadir otro
  `|| echo`.
- **Verificar**: `bash -n scripts/daily_publish.sh` y revisar a ojo; no se
  puede ejecutar el pipeline localmente sin credenciales/S3.

### 5. `Dockerfile.pipeline` — `COPY . .` invalida las capas caras (eficiencia, media)

- Orden actual: capa CmdStan (cacheada bien) → `COPY . .` (línea ~32) →
  `pip install -e ".[web,bayes]" awscli` → precompilación de
  `wcpred/stan/*.stan`. Cualquier cambio de código invalida la instalación
  completa del árbol científico (pandas/scipy/cmdstanpy/awscli) **y** la
  recompilación C++ de los modelos Stan (minutos, y capas grandes a ECR).
- **Arreglo** (estrategia; los detalles dependen de `pyproject.toml`, léelo):
  1. `COPY pyproject.toml .` (+ lo que exija el build backend, p. ej.
     `README.md`) y instalar **solo las dependencias** de los extras
     `web`+`bayes` más `awscli` en su propia capa (p. ej. extrayéndolas con
     un `python -c "import tomllib; ..."` | `pip install -r /dev/stdin`).
  2. `COPY wcpred/stan/ wcpred/stan/` y la precompilación Stan en su capa
     (solo se invalida si cambia un `.stan`).
  3. `COPY . .` al final + `pip install -e . --no-deps`.
  - Mantener intactos: el orden CmdStan-antes-de-todo, el `assert` de
    `install_cmdstan`, `cores=1`, `compile="force"`, `ENV
    WCPRED_AWS_PROFILE=""` y el `ENTRYPOINT`. El `.dockerignore` ya excluye
    `data/`, `build/` y los binarios Stan compilados — no lo toques.
- **Verificar**: `docker build --platform linux/arm64 -f Dockerfile.pipeline .`
  si hay Docker disponible; después tocar un fichero JS y re-build para
  comprobar que las capas de deps y Stan salen de caché. Si no hay Docker,
  dejarlo señalizado en la PR para que el usuario lo pruebe con
  `scripts/aws/push_image.sh`.

### 6. `webapp/server.py:183-189` — `_read_snapshots` re-parsea todos los CSV en cada petición (eficiencia, media)

- `/api/picks`, `/api/groups` y `/api/sims` re-leen y re-parsean ~26
  snapshots inmutables cada uno por petición (`pd.read_csv` + `astype(object)`
  + `to_dict`), creciendo un fichero por día de torneo. El propio fichero ya
  tiene el patrón correcto: `_odds_pairs` (línea 228) y `_matrices_rows`
  (línea 333) son `lru_cache` con clave `(path, mtime)`.
- **Arreglo**: extraer un helper cacheado, p. ej.
  ```python
  @lru_cache(maxsize=512)
  def _snapshot_rows(path, mtime):
      return _records(pd.read_csv(path))
  ```
  y que `_read_snapshots` (y `rankings_history`, línea 612, que tiene el
  mismo patrón) lo usen pasando `os.path.getmtime(path)`. La clave con mtime
  conserva la semántica de "un refresco se ve en la siguiente carga" que
  promete el docstring de cabecera del módulo (líneas 9-10) — **actualiza ese
  docstring**, que dice "The API never caches".
- Las estructuras cacheadas se comparten entre peticiones: son de solo
  lectura en todos los usos actuales; no mutar las filas en el futuro.
- **Verificar**: levantar la web, cargar, lanzar un refresh local (botón) y
  comprobar que los datos nuevos aparecen al recargar.

### 7. `webapp/server.py:315` — `_model_for` sin single-flight (eficiencia, media)

- `lru_cache` no deduplica cómputos en vuelo: mientras un ajuste para
  `(as_of, engine)` corre (segundos en dc/elo, minutos si bayes muestrea),
  cada petición concurrente idéntica lanza el suyo en otro hilo del
  threadpool de Starlette (los handlers son `def` síncronos).
- **Arreglo**: candado por clave alrededor del ajuste. Esquema simple:
  ```python
  _fit_locks = {}
  _fit_locks_guard = threading.Lock()

  def _fit_lock(key):
      with _fit_locks_guard:
          return _fit_locks.setdefault(key, threading.Lock())
  ```
  y en el camino que llama a `_model_for` (o envolviéndolo), tomar el lock de
  `(as_of, engine)` antes de invocar la función cacheada: el primero ajusta,
  los demás esperan y encuentran el resultado en el `lru_cache`. Cuidado con
  no bloquear dentro del `lru_cache` mismo de forma que se serialicen claves
  distintas.
- **Verificar**: abrir varias matrices del mismo día seguidas en el
  calendario; con un `print`/log temporal, comprobar que solo hay un fit.

### 8. `webapp/static/app.js:909` — `render()` reconstruye las cuatro pestañas (eficiencia, media)

- Cada cambio de estado (selector «Día», toggle de estrategia, idioma…)
  regenera campeón + evolución (SVG completo) + grupos + calendario (104
  tarjetas, cada una con el escaneo lineal `predictionFor`), aunque solo una
  pestaña es visible.
- **Arreglo**: render perezoso — `render()` pinta solo la pestaña activa y
  marca las demás como sucias (p. ej. `state.dirty = new Set([...])`);
  `activateTab()` (línea ~1070) re-pinta si su pestaña está sucia. Puntos a
  cubrir: `reloadAll()` (incluido el camino del permalink `#match=`, que
  activa `calendar`), `pollRefresh` → `reloadAll`, `setLanguage` (ensucia
  todas), y los handlers de `setupUI`. Conectividad y rankings ya funcionan
  así — usar su patrón.
- Es el arreglo más invasivo del lote: si el presupuesto es corto, hacerlo
  el último y con calma, probando todas las pestañas y toggles.
- **Verificar**: clic por todas las pestañas, cambiar día/estrategia/idioma/
  motor/approach en cada una, permalink `#match=...`, refresh completo.

### 9. `webapp/static/app.js:411` — serie de evolución O(equipos × snapshots × filas) (eficiencia, baja)

- `renderEvolution` hace `snaps.map(s => s.rows.find(r => r.team === team))`
  dentro del map de 48 equipos: ~60k comparaciones por render, repetidas en
  cada clic de la leyenda.
- **Arreglo**: construir una vez `const byTeam = snaps.map(s => new
  Map(s.rows.map(r => [r.team, r])))` y usar `byTeam[i].get(team)`.
- **Verificar**: la gráfica de evolución se ve igual y los chips de la
  leyenda responden fluido.

### 10. `webapp/static/app.js:311` — TypeError si se toca un control antes de la carga inicial (bug menor, baja)

- Con red lenta, tocar el toggle ev/outcome o el selector de día antes de que
  `reloadAll()` termine llama a `render()` con `curCache().sims` aún
  `undefined` → `pickSnapshot(undefined)` hace `undefined.length` →
  TypeError (el render de ese evento muere en silencio).
- **Arreglo**: guarda temprana al inicio de `render()`:
  `if (!state.meta || !curCache().sims) return;` (reloadAll siempre llama a
  `render()` al terminar, así que no se pierde ningún repintado).
- **Verificar**: con throttling de red en el navegador, aporrear los toggles
  durante la carga → sin errores en consola.

## Descartado en la revisión (no perseguir)

- **Coma final en la lista de subnets** de `scripts/aws/run_pipeline.sh`
  (`SUBNETS_CSV` acaba en `,`): probado contra el parser shorthand de la AWS
  CLI — la tolera y produce la lista limpia. No es un bug.
- **Claves i18n ausentes** (`pos.*`, `ms.*`): están todas definidas en
  `webapp/static/i18n.js` (varias por línea; un grep ingenuo las pierde).
- **Los `wc-*.png` de la raíz** del working tree: capturas de pantalla del
  usuario (07-07 08:45), no salida del pipeline. No tocar, no borrar.
- El `slug()` de app.js y `team_slug()` de export_static.py están
  verificados como equivalentes para los 48 nombres actuales.

## Sugerencia de orden de trabajo

Commits pequeños y separados por hallazgo (o por pareja afín), en este orden:
1–2 (bugs de frontend/servidor, rápidos), 4 (una línea), 3 (script de
publish), 6–7 (caché del servidor), 9–10 (frontend menores), 5 (Docker),
8 (refactor de render, el último). Tras los cambios de webapp, levantar
`scripts/run_webapp.sh` y hacer una pasada manual completa; tras cualquier
cambio que afecte al export, correr `python scripts/export_static.py --out
/tmp/site-test` y comprobar que termina sin errores (usa los datos locales de
`data/`; si faltan, `scripts/aws/pull_data.sh` — pero requiere credenciales,
en ese caso pedírselo al usuario).
