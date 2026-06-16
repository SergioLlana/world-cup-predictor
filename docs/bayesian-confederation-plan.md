# Plan: Dixon-Coles bayesiano en Stan con prior jerárquico de confederación

## Context

La limitación central del modelo (`docs/known-limitations.md`,
`docs/connectivity.md`) es que los **offsets de fuerza entre confederaciones
están débilmente identificados**: solo los escasos partidos "puente" conectan
los bloques, y con ellos AFC/CAF derivan (Australia por encima de USA) y las
comparaciones de élite cross-bloc (Argentina vs España) cargan más
incertidumbre de la que sugieren los ratings puntuales. El plan de robustez
(`docs/model-robustness-plan.md`, fases 0-3) probó y rechazó 5 mitigaciones
sobre el modelo MLE actual; todas fallaron porque eran intervenciones globales
post-hoc o anclas externas con el mismo sesgo regional.

La guía del usuario apunta a algo estructuralmente distinto: un **Dixon-Coles
bayesiano** con un **offset de confederación dentro del prior**. La propiedad
clave: si cada selección sudamericana se desplaza igual respecto a Europa en el
prior, los partidos *intra*-confederación no pueden deshacer ese desplazamiento
(solo informan diferencias relativas dentro del bloque); **únicamente los
puentes, más raros, ajustan el offset**. Eso es exactamente lo que el modelo
MLE no logra. Además el usuario señala que el mayor retorno está en **tratar
mejor el tiempo** (ratings dinámicos en vez de pesos por decaimiento).

Decisiones tomadas en la entrevista:
- **Tiempo: por fases.** Fase A = prior jerárquico de confederación con el
  decaimiento exponencial actual como verosimilitud ponderada. Fase B (misma
  rama, solo si A convence) = fuerzas dinámicas random-walk.
- **Posterior: media ahora, propagación luego.** Empezar fijando atk/dfn/home/
  rho a la media posterior (drop-in transparente); propagación posterior
  completa como mejora posterior.
- **Validación: fit estático por torneo** (un muestreo MCMC pre-torneo por
  torneo, como `--static`), no re-fit rodante por jornada.

Restricción dura (heredada del plan de robustez, sigue vigente): **el modelo
MLE actual debe seguir siendo el default y totalmente regenerable**. El motor
bayesiano es opt-in, default off; no se regeneran snapshots pasados; outputs de
experimento fuera de `data/predictions|groups|simulations`.

## Enfoque (Fase A — esta iteración)

Un nuevo motor bayesiano que **reutiliza toda la interfaz del modelo actual**
para encajar sin tocar el pipeline aguas abajo.

### 1. Dependencia Stan

- `pyproject.toml`: nuevo extra `bayes = ["cmdstanpy>=1.2"]`. Documentar que
  requiere CmdStan (`install_cmdstan`) y toolchain C++.
- `pyproject.toml` `[tool.setuptools]`: añadir `package-data` para incluir el
  `.stan` en el paquete (p. ej. `wcpred = ["stan/*.stan"]`) y `include-package-data`.

### 2. Modelo Stan — `wcpred/stan/dixon_coles.stan`

Verosimilitud Dixon-Coles ponderada (igual que `model.py`): por partido,
`target += w * (poisson_lpmf(hg | lam) + poisson_lpmf(ag | mu) + log(tau))`,
con `lam = exp(atk[h] + dfn[a] + home*hadv)`, `mu = exp(atk[a] + dfn[h])` y
`tau(x,y; lam, mu, rho)` la corrección de marcadores bajos de DC (mismas 4
celdas que `DixonColes._tau`).

Parámetros y prior jerárquico (no centrado):
- `atk[i] = atk_conf[c(i)] + sigma_atk * atk_raw[i]`, con
  `atk_raw ~ student_t(nu, 0, 1)` (la t robusta evita aplastar outliers
  legítimos como Argentina — el riesgo que hizo descartar el diseño 2a).
  Igual para `dfn`.
- **`atk_conf[C]`, `dfn_conf[C]`: los offsets de confederación** —
  `~ normal(0, sigma_conf)`. Son la pieza nueva: identificados casi solo por
  partidos puente; con `sigma_conf` moderado los bloques no derivan sin
  evidencia de puentes. Equipos sin confederación inferida → offset fijo 0.
- `home` (ventaja de local), `rho` (con prior y restricción `tau > 0` vía
  rechazo suave, o muestreado en `[-0.2, 0.2]` como el grid actual).
- Identificabilidad: suma-cero global sobre `atk` (replica el penalti
  `atk.mean()=0` del MLE) y suma-cero sobre los offsets de confederación.
- Hiperparámetros con priors débiles: `sigma_atk, sigma_dfn, sigma_conf` (half-
  normal), `nu` (gamma).

### 3. Clase de modelo — `wcpred/model_bayes.py`

`BayesianDixonColes(DixonColes)`: **subclase** para heredar `rates`,
`matrix_from_rates`, `_tau`, `score_matrix` sin duplicar nada. Solo sobrescribe
`fit(m, ...)`:
1. Construye `idx`, índices home/away, goles, pesos `w`, `hadv` (idéntico a
   `DixonColes.fit`).
2. Infiere confederaciones con `confederations.infer_confederations(m)` y mapea
   cada equipo a un índice de bloque (los desconocidos a un bloque "sin offset").
3. Compila (cacheado) y muestrea el `.stan` con cmdstanpy.
4. Fija `self.atk/self.dfn` = media posterior de las fuerzas compuestas por
   equipo, `self.home`/`self.rho` = media posterior. Resultado: drop-in.
- Guardar el `CmdStanModel` compilado en caché de módulo para no recompilar
  entre fits del backtest.

### 4. Integración CLI — `wcpred/cli.py`

- `common(sp)`: nuevo `--engine {dc,bayes}` (default `dc`).
- `build_model`: si `args.engine == "bayes"`, usar `BayesianDixonColes` (las
  ramas Elo/anchor son específicas del MLE; con `bayes` se ignoran o se sale
  con mensaje claro). El resto (`prepare_training`, fixtures, guardas de equipos
  faltantes) no cambia.
- `backtest.backtest`: parámetro `engine="dc"`; cuando `bayes`, instanciar
  `BayesianDixonColes` en lugar de `DixonColes`. La ruta de `--bridge-audit` ya
  usa `model.score_matrix`, así que funciona igual con la subclase.
- `cmd_backtest`/`cmd_predict`/etc.: pasar `engine=args.engine`. El motor bayes
  **solo se valida en estático** (`--static`); avisar si se pide rodante.

### 5. Validación (gate)

Comparar **bayes estático vs MLE estático** sobre los 6 torneos
(`backtest --static`), métricas: RPS, log-loss, puntos Penka y la tabla
`--bridge-audit`. Criterio de adopción (mismo espíritu que el plan): RPS/
log-loss no empeoran **y** las dos sesgos diagnosticados encogen
(`bias_a(CONMEBOL–UEFA)` +0.088, `bias_a(CONCACAF–UEFA)` +0.113), o al menos la
incertidumbre cross-bloc queda mejor reflejada. Canarios: gap AUS−USA y
ARG−ESP, top-20 sensato.

### 6. Documentación / trazabilidad

- Reabrir `docs/model-robustness-plan.md` con una **Fase 4 — prior jerárquico
  de confederación bayesiano (Stan)**: hipótesis, diseño, gate, y registrar
  resultado en el Decision/Results log en la misma sesión (regla viva del doc).
- Actualizar `CLAUDE.md` (arquitectura: `model_bayes.py`, `stan/`, `--engine`)
  y `MEMORY.md` si procede.

## Regenerabilidad (verificar)

- `--engine dc` reproduce el modelo actual **byte a byte**: confirmar con un
  `backtest --tournament all --static` antes/después (números idénticos).
- Snapshots en `data/predictions|groups|simulations` se siguen generando con
  `dc` (default). Outputs de experimento bayes → árbol aparte
  (`data/experiments/bayes/...`) o sufijo de variante.
- No se regenera ningún snapshot pasado con el modelo nuevo.

## Fase B (misma rama)

- **B1 — Fuerzas dinámicas: IMPLEMENTADO (2026-06-13, opt-in `--bayes-dynamic`).**
  `atk[i,t] ~ normal(atk[i,t-1], sigma_rw)` sobre bloques temporales (default
  **semestral**; `--bayes-block year|halfyear|quarter`), prediciendo con el
  estado más reciente. Sustituye el decaimiento exponencial por evolución
  latente explícita (el random-walk *es* el modelo de tiempo, así que los
  partidos entran sin ponderar). Modelo `stan/dixon_coles_dynamic.stan`
  (random-walk no centrado por equipo, columna inicial Student-t robusta,
  gauge suma-cero por bloque); el offset de confederación de Fase A se conserva.
  Plan de implementación y veredicto: `docs/bayesian-phase-b-plan.md` y la
  sub-fase B1 en `docs/model-robustness-plan.md`.
- **B2 — Propagación posterior completa: IMPLEMENTADO (2026-06-13, opt-in
  `--bayes-propagate`).** `BayesianDixonColes` guarda los draws posteriores
  (`atk_draws`/`dfn_draws`/`home_draws`/`rho_draws`; en dinámico, el último
  bloque) y sobrescribe `score_matrix` para devolver la **media de las matrices
  Dixon-Coles por draw** en vez de una matriz construida con las medias
  posteriores (plug-in de Fase A/B1). Promediar sobre el posterior arrastra la
  incertidumbre de ratings — máxima en los puentes cross-bloc débilmente
  identificados — hasta los marcadores, ensanchando la distribución. Opt-in
  `--bayes-propagate` / `BAYES_PROPAGATE` (default off; con off, `score_matrix`
  cae al path heredado, byte a byte idéntico). Componible con A o B1. Veredicto
  en la sub-fase B2 de `docs/model-robustness-plan.md`.

## Fase C — encogimiento por conectividad (RECHAZADA, 2026-06-16)

*Proceso completo (diagnóstico, formulaciones, resultados, qué queda por
probar): [connectivity-shrinkage-experiment.md](connectivity-shrinkage-experiment.md).*


Motivación (caso Australia, `docs/known-limitations.md`): el offset uniforme de
confederación de la Fase A está fijado casi por completo por los partidos puente
de la **élite** del bloque (sólo Japón/Australia/Corea juegan fuera de la AFC) y
se aplica por igual a los minnows aislados. La hipótesis: ponderar lo que cada
equipo hereda de su bloque por su **bridge share** (cuota de peso de partidos
inter-confederación; `confederations.bridge_share`, los mismos pesos `w` que
ajusta el modelo) — un equipo bien conectado libre, uno aislado anclado. Mapeo
`c = min(1, bridge_share / BAYES_CONNECT_REF)` (ref=0.4). Dos formulaciones,
ambas opt-in `--bayes-connect` (estáticas, default-off, archivo `.stan` aparte
para no tocar el modelo de producción; `--bayes-connect-mode`):

- **A — `offset` (`stan/dixon_coles_connect.stan`):**
  `atk[t] = c[t]·atk_conf + σ_atk·atk_raw` — atenúa el offset hacia la escala
  global (0). **RECHAZADA, contraproducente.** El offset de un bloque débil es
  **negativo** (AFC ≈ −0.54), así que atenuarlo hacia 0 *sube* al bloque:
  Australia #28→#20, Japón #16→#9, Irán #30→#18, AFC media −0.54→−0.34; y en los
  bloques fuertes (UEFA, offset positivo) *baja* a outliers legítimos poco
  puenteados (España #2→#3, Inglaterra). Exactamente al revés del objetivo.
- **B — `deviation` (`stan/dixon_coles_connect_dev.stan`):**
  `atk[t] = atk_conf + σ_atk·c[t]·atk_raw` — partial pooling clásico: encoge la
  desviación del equipo aislado hacia la **media de su bloque** (no hacia 0),
  preservando el offset. **RECHAZADA, no cumple el objetivo.** Más limpia que A
  (preserva outliers: España #2, UEFA +0.78→+0.82; los minnows AFC sí van hacia
  su media: Laos #231→#198, Bhutan #241→#230), pero **tampoco baja a Australia**
  (#28→#21).

**Diagnóstico raíz (por qué el bridge share es el predictor equivocado):**
Australia **no es un equipo poco conectado** — su bridge share es **0.47**, de
los más altos de la AFC (Japón 0.49, Corea 0.47). Lo que la infla no es la
*cantidad* de puentes sino su *dificultad*: sus puentes son Nueva Zelanda ×5
(OFC), Curaçao 5-1, Canadá, Camerún, Túnez, y sólo pierde con los muy top (3-7-2
vs UEFA/CONMEBOL fuertes). Por eso **ningún** encogimiento por bridge share —ni
A ni B— la toca; A incluso la premia por su alta conectividad. El predictor que
sí la separa es la **dificultad media de rivales** (`opp_rating`, la AFC sale
plana y baja), no la conectividad. Una Fase C' tendría que escalar por
`opp_rating` (o comprimir la escala intra-bloque), no por bridge share.

Métricas backtest (6 torneos, 290 partidos, `--static --engine bayes`):

| config | puntos Penka | RPS | log-loss |
|---|---|---|---|
| base bayes | **605** | **0.1905** | **2.7732** |
| B (`deviation`) | 581 | 0.1932 | 2.7950 |

B es **peor en las tres** métricas, con el daño concentrado en **wc2022**
(102→88 pts, RPS 0.2139→0.2229) — el torneo más cargado de AFC, justo el bloque
que B distorsiona. (A no se backtestea: los rankings ya la muestran
contraproducente y además daña outliers UEFA.) El base 605 confirma de paso la
regenerabilidad: con el knob off se usa el path estático intacto.

Knobs (todos default-off; el bayes de producción se regenera idéntico — usa el
path estático sin `conf_w`): `BAYES_CONNECT_SHRINK`, `BAYES_CONNECT_REF`,
`BAYES_CONNECT_MODE` (`config.py`); `--bayes-connect` / `--bayes-connect-ref` /
`--bayes-connect-mode` (`cli.py`). Helper `confederations.bridge_share`.

## Verificación end-to-end

```bash
pip install -e ".[bayes]"          # + install_cmdstan una vez
# 1. Regenerabilidad: dc idéntico antes/después
wcpred backtest --tournament all --static            # baseline MLE
# 2. Motor bayes (estático) en un torneo, smoke test
wcpred backtest --tournament wc2022 --static --engine bayes --bridge-audit
# 3. Gate completo: 6 torneos, comparar RPS/log-loss/puntos/bridge-audit
wcpred backtest --tournament all --static --engine bayes --bridge-audit
# 4. Ratings y predicción puntual con el motor bayes
wcpred ratings --top 20 --engine bayes --as-of 2026-06-13
wcpred predict --approach odds --odds data/input/odds.csv --days 3 --engine bayes
```

## Archivos críticos

- **Nuevo** `wcpred/stan/dixon_coles.stan` — modelo Stan (DC ponderado + prior
  jerárquico de confederación).
- **Nuevo** `wcpred/model_bayes.py` — `BayesianDixonColes(DixonColes)`.
- `wcpred/model.py` — referencia de la interfaz a heredar (`_tau`, `rates`,
  `matrix_from_rates`, `score_matrix`); sin cambios.
- `wcpred/confederations.py` — `infer_confederations` para el mapa equipo→bloque
  (reutilizado, sin cambios).
- `wcpred/cli.py` — flag `--engine`, branch en `build_model`.
- `wcpred/backtest.py` — parámetro `engine` en `backtest`.
- `pyproject.toml` — extra `bayes`, package-data del `.stan`.
- `docs/model-robustness-plan.md`, `CLAUDE.md` — trazabilidad.
