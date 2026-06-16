# Fase B (B1) del modelo bayesiano: fuerzas dinámicas random-walk

## Context

El motor bayesiano (`--engine bayes`, `wcpred/model_bayes.py` + `stan/dixon_coles.stan`)
implementa la **Fase A** del plan (`docs/bayesian-confederation-plan.md`): prior
jerárquico de offset de confederación, plug-in de **medias** posteriores
(«plug-in» = sustituir cada parámetro por su media posterior y usar esa única
estimación, en vez de promediar sobre las muestras del posterior), y el
**tiempo entra como los pesos de decaimiento exponencial** del MLE. La Fase A fue
rechazada como default (codifica el sesgo regional vía los puentes), pero el
usuario señaló desde la entrevista que **el parámetro con más efecto es tratar mejor el
tiempo**: sustituir el decaimiento por ratings dinámicos. Eso es la Fase B.

La Fase B del plan tiene dos partes separables. **Esta iteración implementa solo
B1** (fuerzas dinámicas random-walk); B2 (propagación posterior completa) queda
diferida. Decisión del usuario: **mantener intacta la implementación actual**
(Fase A estática) y que lo dinámico sea **una opción activable por argumentos**.
Granularidad temporal por defecto: **semestral** (~23 bloques sobre 2015–2026),
configurable.

Hipótesis: reemplazar el peso `exp(-ln2/HL·edad)` por una evolución latente
explícita `atk[i,t] ~ normal(atk[i,t-1], σ_rw)` sobre bloques temporales, y
predecir con el **estado más reciente**, captura forma/tendencia mejor que un
decaimiento isótropo. El offset de confederación se conserva (es la identidad del
motor); lo nuevo es la dinámica temporal de la desviación de cada equipo.

Restricción dura (regla viva del plan, sigue vigente): `--engine dc` y
`--engine bayes` (no-dinámico) deben quedar **byte a byte** idénticos; lo nuevo es
opt-in, default off; outputs de experimento fuera de
`data/predictions|groups|simulations`; no se regenera ningún snapshot pasado.

## Enfoque (B1)

Un segundo modelo Stan dinámico, activable con `--bayes-dynamic`, que reutiliza
toda la interfaz del modelo (subclase ya existente). La adopción sigue siendo
plug-in de medias (Fase A); lo único que cambia es **cómo entra el tiempo**.

### 1. Modelo Stan — NUEVO `wcpred/stan/dixon_coles_dynamic.stan`

Parte de `stan/dixon_coles.stan` (misma `dc_tau`, mismo offset de confederación,
mismos `home`/`rho`/`nu`/`sigma_*`/gauge de offsets). Cambios:

- `data`: añade `int<lower=1> B;` (nº de bloques) y
  `array[N] int<lower=1,upper=B> tb;` (bloque de cada partido).
- Random-walk **no centrado** por equipo sobre los `B` bloques:
  - `parameters`: `matrix[T,B] atk_z; matrix[T,B] dfn_z;` (innovaciones) +
    `real<lower=1e-3> sigma_rw_atk; real<lower=1e-3> sigma_rw_dfn;` (escala del
    paso, half-normal).
  - `transformed parameters` construye `matrix[T,B] atk, dfn`:
    `u[t,1] = sigma_atk * atk_z[t,1]`;
    `u[t,b] = u[t,b-1] + sigma_rw_atk * atk_z[t,b]` (b>1);
    `atk[t,b] = (conf[t]>0 ? atk_conf[conf[t]] : 0) + u[t,b]`. Igual para `dfn`.
  - `model` (priors): columna inicial robusta — `atk_z[,1] ~ student_t(nu,0,1)`
    (conserva la t de Fase A que evita aplastar outliers como Argentina);
    pasos `to_vector(atk_z[,2:B]) ~ std_normal();`. `sigma_rw_* ~ normal(0,0.2)`
    (half-normal: evolución suave por defecto — la mayoría de la señal temporal
    es lenta). Igual para `dfn`.
- Gauge: además de `sum(atk_conf)`/`sum(dfn_conf)` a 0 (heredado), pin suave
  **por bloque** de la parte de desviación de equipo `sum_t u_atk[,b] ~
  normal(0, 0.01*T)` (la degeneración de shift atk+c/dfn−c es por bloque).
- Likelihood: idéntica a la estática pero indexando por bloque,
  `log_lam = atk[hi,tb] + dfn[ai,tb] + home*hadv`, etc. Mantiene `w` (se pasará
  `w=1`; ver §2).

### 2. Clase de modelo — `wcpred/model_bayes.py`

Sin tocar el path estático (Fase A) — queda idéntico. Añadir:

- `_compiled_model(stan_file)` cacheado **por archivo** (dict de módulo en vez de
  un único `_COMPILED`), para no recompilar entre fits del backtest y soportar
  los dos `.stan`.
- `BayesianDixonColes.fit(..., dynamic=None, time_block=None)`:
  - Resuelve `dynamic`/`time_block` desde `config.BAYES_DYNAMIC` /
    `config.BAYES_TIME_BLOCK` cuando llegan `None`.
  - `dynamic` falso → **exactamente el código actual** (regenerabilidad).
  - `dynamic` verdadero:
    1. Igual prólogo (idx, hi/ai, goles enteros, conf). **Pesos**: el random-walk
       *es* el modelo de tiempo, así que se pasa `w = np.ones(N)` (el decaimiento
       desaparece; los multiplicadores friendly/cross-conf están off por defecto
       — documentar que el motor dinámico los ignora).
    2. Bloques: `period = m["date"].dt.to_period(freq)` con
       `freq ∈ {"A","2Q"/"6M","Q"}` según `time_block`; mapear los periodos
       únicos ordenados → `tb ∈ 1..B`. El bloque máximo = `B` = **estado más
       reciente**.
    3. Muestrear `dixon_coles_dynamic.stan`. Adoptar el **último bloque**:
       `atk = mcmc.stan_variable("atk")[:, :, B-1].mean(axis=0)` (shape
       draws×T×B), `dfn` igual; `home`/`rho` medias. Guardar `self.blocks`,
       `self._mcmc`. Drop-in: hereda `rates`/`score_matrix`.

### 3. Config — `wcpred/config.py`

```python
BAYES_DYNAMIC = False          # Fase B1: random-walk temporal en vez del
                               # decaimiento (docs/bayesian-confederation-plan.md).
                               # False = Fase A estática (default del motor bayes).
BAYES_TIME_BLOCK = "halfyear"  # granularidad del random-walk: year|halfyear|quarter
```

### 4. CLI — `wcpred/cli.py`

- `common(sp)`: `--bayes-dynamic` (store_true, default `BAYES_DYNAMIC`) y
  `--bayes-block {year,halfyear,quarter}` (default `BAYES_TIME_BLOCK`).
- `build_model`: si `args.bayes_dynamic` y `engine != "bayes"` → `sys.exit` con
  mensaje claro. Pasar `dynamic=args.bayes_dynamic, time_block=args.bayes_block`
  a `BayesianDixonColes().fit`. Mensaje de log con "(dynamic, block=…)".

### 5. Backtest — `wcpred/backtest.py`

- `backtest(..., dynamic=False, time_block=None)`; guard: `dynamic` exige
  `engine="bayes"` y `rolling=False` (MCMC por jornada inviable, como Fase A).
  Pasar a `BayesianDixonColes().fit`.
- `cmd_backtest` pasa `dynamic=args.bayes_dynamic, time_block=args.bayes_block`.

### 6. Validación y trazabilidad

- Instalar el extra: `.venv/bin/python -m pip install -e ".[bayes]"` (el
  toolchain CmdStan 2.39 ya está en `~/.cmdstan`).
- Extender `scripts/compare_bayes.py` para añadir una tercera variante
  **bayes-dinámico** (estático, 6 torneos): RPS / log-loss / puntos Penka +
  `bridge_audit`. Extender `scripts/bayes_control_cases.py` para fittear también el
  dinámico y reportar AUS−USA, ARG−ESP, top-10 y `sigma_rw_*`.
- Criterio de validación (mismo espíritu que todas las fases): adoptar como default solo si
  RPS/log-loss no empeoran **y** encogen los sesgos diagnosticados
  (CONMEBOL–UEFA +0.103, CONCACAF–UEFA +0.120 en el baseline estático). Si no
  (lo esperable dado el patrón), **queda disponible pero off**.
- Docs en la **misma sesión** (regla viva): marcar B1 en
  `docs/bayesian-confederation-plan.md`; añadir a `docs/model-robustness-plan.md`
  la sub-fase "Phase 4 — B1" con números en Results log + fila en Decision log;
  actualizar `CLAUDE.md` (motor dinámico + flags) y `MEMORY.md`.

## Archivos críticos

- **NUEVO** `wcpred/stan/dixon_coles_dynamic.stan` — DC ponderado + offset de
  confederación + random-walk no centrado por equipo y bloque.
- `wcpred/model_bayes.py` — caché por archivo + rama dinámica en `fit`
  (path estático intacto).
- `wcpred/config.py` — `BAYES_DYNAMIC`, `BAYES_TIME_BLOCK`.
- `wcpred/cli.py` — `--bayes-dynamic`/`--bayes-block` + guard + threading.
- `wcpred/backtest.py` — params `dynamic`/`time_block` + guard.
- `scripts/compare_bayes.py`, `scripts/bayes_control_cases.py` — variante dinámica.
- `docs/bayesian-confederation-plan.md`, `docs/model-robustness-plan.md`,
  `CLAUDE.md`, `MEMORY.md` — trazabilidad.
- `pyproject.toml` — sin cambios: `package-data = wcpred/stan/*.stan` ya incluye
  el nuevo `.stan` (verificar, no editar).

## Verificación end-to-end

```bash
.venv/bin/python -m pip install -e ".[bayes]"     # cmdstanpy (CmdStan ya presente)
# 1. Regenerabilidad: dc y bayes-estático idénticos antes/después
wcpred backtest --tournament wc2022 --static                      # dc baseline
wcpred backtest --tournament wc2022 --static --engine bayes       # Fase A intacta
# 2. Smoke test dinámico en un torneo
wcpred backtest --tournament wc2022 --static --engine bayes \
       --bayes-dynamic --bridge-audit
# 3. Criterio de validación: 6 torneos, dc-static vs bayes-static vs bayes-dyn
.venv/bin/python scripts/compare_bayes.py        # (extendido con la 3ª variante)
# 4. Casos de control + diagnósticos del random-walk (as-of 2026-06-13)
.venv/bin/python scripts/bayes_control_cases.py
# 5. Predicción puntual con el motor dinámico
wcpred ratings --top 20 --engine bayes --bayes-dynamic --as-of 2026-06-13
```

Criterio de convergencia (workflow bayesiano): revisar `mcmc.diagnose()`
(R-hat<1.01, ESS, divergencias, E-BFMI) en los casos de control antes de emitir
veredicto; si el random-walk diverge, subir `adapt_delta` y/o suavizar
`sigma_rw_*`. Registrar el veredicto numérico en el doc vivo.
