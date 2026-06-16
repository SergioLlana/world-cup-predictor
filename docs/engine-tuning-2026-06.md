# Tuning de los tres motores (dc / elo / bayes) — junio 2026

Búsqueda de la mejor combinación de hiperparámetros para cada motor
(`--engine dc|elo|bayes`), con evaluación adicional de **cómo cada motor trata
las confederaciones**. Documento generado de forma incremental (una sección por
motor a medida que termina), reanudable: las tablas crudas se persisten fila a
fila en `data/tuning/`.

## Método

- **Conjunto de validación:** los seis torneos de `backtest.TOURNAMENTS`
  (wc2018, euro2021, copa2021, wc2022, euro2024, copa2024 — 290 partidos).
- **Métrica:** se optimiza por **RPS agrupado** (1X2, baja varianza) y se
  desempata por **puntos Penka**; se reporta también el log-loss del marcador
  exacto. Es el protocolo del repo (los puntos solos son demasiado ruidosos en
  ~290 partidos).
- **Sin xG** (cobertura incompleta de FotMob).
- **Dos formas de entrenar, en fases:**
  1. **Estático** — se entrena **una sola vez, en la víspera de cada torneo**
     (`--as-of` en el corte previo) y con ese ajuste se predicen sus partidos.
     Barato → se usa para **barrer la rejilla** de combinaciones.
  2. **Rolling** — se **reentrena antes de cada jornada** (el corte avanza
     partido a partido; cada ajuste solo ve resultados anteriores, como en
     vivo). Fiable pero caro → se usa **solo para re-validar el ganador** de
     cada motor.
- **Excepción `bayes`:** es **estático-only** (un reajuste MCMC por jornada en
  seis torneos es inviable; `backtest()` lo prohíbe). Su ganador se re-confirma
  con otra corrida estática y se compara contra el número rolling de `dc` como
  referencia.

> **Nota:** este documento **solo informa**; no se cambia `config.py`. Los
> defaults se mantienen salvo que el usuario decida adoptar un ganador (regla de
> regenerabilidad: los defaults solo cambian si el rolling supera con claridad).

---

## Motor `dc` (Dixon-Coles MLE)

Tiempos: rejilla base 108 configs = **103 s**; barridos de robustez 20 configs =
**22 s**; re-validación rolling (2 configs) = **46 s**. **Total ~3 min.**

### Paso 1 — rejilla base (estático), top por RPS

`gd_cap × half_life × friendly_w × cross_conf_w` (108 combinaciones).
Tabla cruda: `data/tuning/dc_base.csv`.

| gd_cap | half_life | friendly_w | cross_conf_w | points | rps | log_loss |
|---:|---:|---:|---:|---:|---:|---:|
| None | 1095 | 1.00 | 2.0 | 607 | 0.18840 | 2.7672 |
| None | 730 | 1.00 | 2.0 | 603 | 0.18840 | 2.7687 |
| None | 730 | 1.00 | 1.5 | 609 | 0.18850 | 2.7678 |
| None | 1095 | 1.00 | 1.5 | 596 | 0.18857 | 2.7670 |
| … | | | | | | |
| None | 730 | 1.00 | **1.0** (default) | 601 | 0.18872 | 2.7679 |

Lecturas: el `gd_cap` (tope de goleada) **nunca** ayuda (None gana siempre); una
vida media más larga (1095 d) y, sobre todo, **doblar el peso de los partidos
inter-confederación (`cross_conf_w=2.0`)** mejoran marginalmente el RPS. Todo
dentro de una banda muy estrecha (0.1884–0.1889).

### Paso 2 — variables antes descartadas (barrido desde la mejor base)

Partiendo de `gd_cap=None, half_life=1095, friendly_w=1.0, cross_conf_w=2.0`.
Tabla cruda: `data/tuning/dc_robustness.csv`.

| variable | mejor valor | rps | vs base (0.18840) |
|---|---|---:|---|
| **shrinkage** (phantom/pseudo × 0.25–2.0) | ninguno | 0.18840 | sin mejora (todo lo empeora) |
| **anchor_beta** (re-anclaje de confederación) | **1.0** | **0.18820** | **mejora** (610 pts) |
| **elo_tau** (prior Elo externo) | 0.0 | 0.18840 | sin mejora (todo lo empeora) |

De las tres variables que el plan de robustez había rechazado, solo el
**re-anclaje de confederación pleno (`anchor_beta=1.0`)** vuelve a dar una mejora
(pequeña) al combinarse con `cross_conf_w=2.0`. Shrinkage y prior Elo externo
siguen sin aportar.

### Ganador `dc` y re-validación rolling

Ganador estático: **`gd_cap=None, half_life=1095, friendly_w=1.0,
cross_conf_w=2.0, anchor_beta=1.0`** (rps estático 0.18820, 610 pts).

| config (rolling, gold standard) | points | pts/match | rps | log_loss |
|---|---:|---:|---:|---:|
| default (hl=730, ccw=1.0, anchor=0) | 594 | 2.048 | 0.1890 | 2.7702 |
| **ganador (hl=1095, ccw=2.0, anchor=1.0)** | **602** | **2.076** | **0.1885** | **2.7692** |

El ganador también supera al default en rolling (rps 0.1885 vs 0.1890, +8 pts),
de forma **consistente pero marginal**. Las tres mejoras apuntan en la misma
dirección — dar más peso a los partidos cruzados y re-anclar las confederaciones
a la escala de ventana larga — lo que es coherente con el sesgo
inter-confederación documentado en `docs/known-limitations.md`.

---

## Motor `elo` (Elo)

Tiempos: `wcpred tune --elo-engine` completo (rejilla escalar 20 + descenso por
coordenadas 36 + re-validación rolling de 2 configs) = **41 s**. Salida cruda:
`data/tuning/elo_run.txt`.

### Paso 1 — rejilla escalar (conf-K = 1.0), top por RPS

`longterm_years ∈ {5,8,10,12,15} × ha ∈ {50,75,100,125}`.

| longterm_years | ha | points | rps | log_loss |
|---:|---:|---:|---:|---:|
| **15** | **50** | 609 | **0.19277** | 2.7966 |
| 12 | 50 | 609 | 0.19285 | 2.7971 |
| 10 | 50 | 599 | 0.19296 | 2.7974 |
| 8 | 50 | 591 | 0.19308 | 2.7979 |

Igual que en el tuning previo (`docs/elo-engine-tuning.md`): **ventaja de campo
baja (HA=50)** y **ventana larga (15 años)** ayudan algo.

### Paso 2 — K por confederación (descenso por coordenadas, desde 15y/HA=50)

Partiendo de HA=50/15y, se barre la K de cada confederación
`{0.5,0.75,1.0,1.25,1.5,2.0}` una a una. Config ganadora:

```
conf_k = {UEFA: 2.0, CONMEBOL: 1.5, CONCACAF: 0.5, CAF: 2.0, AFC: 2.0, OFC: 2.0}
```

rps estático 0.1896. **Lectura sobre confederaciones:** el descenso sube la K de
casi todos los bloques (UEFA/CAF/AFC/OFC = 2.0; los resultados mueven más rápido
su rating) y **baja la de CONCACAF a 0.5** (sus resultados mueven poco su
rating). Romper la propiedad de suma cero del Elo (K≠1 por bloque) es el efecto
buscado: es un parámetro directo sobre el sesgo de conectividad débil.

### Ganador `elo` y re-validación rolling

| config (rolling, gold standard) | points | pts/match | rps | log_loss |
|---|---:|---:|---:|---:|
| default (10y, HA=100, K=1.0) | 587 | 2.024 | 0.1950 | 2.8089 |
| **ganador (15y, HA=50, conf-K↑)** | **607** | **2.093** | **0.1934** | **2.7915** |

El ganador mejora el rolling de forma más clara que `dc` (rps 0.1934 vs 0.1950,
+20 pts). Aun así, sigue por **detrás del `dc` default** en rolling (rps 0.1885
del ganador dc / 0.1890 default dc): el motor Elo tuneado se acerca pero no
supera al Dixon-Coles MLE.

---

## Motor `bayes` (Dixon-Coles bayesiano, Stan)

Variables barridas: `dynamic ∈ {False,True}` × `time_block ∈ {year,halfyear,
quarter}` (solo si dinámico) × `sigma_conf_scale ∈ {0.1,0.25,0.5,1.0}` ×
`propagate ∈ {False,True}`. **Estático-only** (un reajuste MCMC por jornada en 6
torneos es inviable), así que su ganador NO tiene re-validación rolling; se
compara contra el `dc` estático. Tabla cruda: `data/tuning/bayes.csv`.

Coste real: configs estáticas ~12 min cada una; dinámicas mucho más (`year` ~31
min, `halfyear` ~39, `quarter` ~50) por los parámetros del random-walk. La
rejilla completa de 32 serían ~10 h. **Se recortó con criterio** (ver abajo) a 18
configs efectivas.

### Estáticas — `sigma_conf` y `propagate` son planos

Las 8 configs estáticas (sigma × propagate) quedan **todas en rps 0.1905–0.1907**.
Ni el prior de confederación (`sigma_conf` 0.1→1.0) ni la propagación posterior
mueven la métrica. Mejor estática ≈ 0.1905.

### Dinámicas — el tiempo como random-walk es lo que mejora

Las 8 configs dinámicas `year` (sigma × propagate) quedan **todas en
0.1887–0.1890** — de nuevo `sigma_conf`/`propagate` planos, pero el tratamiento
dinámico del tiempo baja el RPS ~0.0017 frente a estático. Confirmado eso, las
dos granularidades restantes se corrieron solo al sigma/propagate representativos
(0.5 / False) en vez de las 16 combinaciones (ahorro de ~8 h sin perder
información, ya que sigma/prop son ruido):

| time_block (sigma 0.5, prop False) | points | rps | log_loss |
|---|---:|---:|---:|
| year | 598 | 0.18875 | 2.7680 |
| halfyear | 604 | 0.18842 | 2.7683 |
| **quarter** | 613 | **0.18839** | 2.7683 |

La granularidad más fina ayuda con **rendimientos decrecientes** (year→halfyear
−0.00033, halfyear→quarter −0.00003, ya ruido).

### Ganador `bayes`

**Dinámico, `time_block=halfyear`, sigma_conf 0.5, propagate off** — rps 0.18842,
604 pts. (Se elige `halfyear` sobre `quarter`: empatados en RPS, pero es el
default, con ventana de predicción más estable y la mitad de coste.) **Bayes
queda prácticamente empatado con el `dc`** (dc estático ganador 0.18820; bayes,
estático-only, 0.18842): el modo dinámico es lo mejor del lado bayesiano e iguala
al Dixon-Coles, sin superarlo.

> Nota operativa: una config `quarter` falló por **disco lleno** (los temporales
> de CmdStan saturaron `/var/folders`), no por el modelo; se liberó espacio y se
> añadió reintento de semilla (`backtest(bayes_seed=…)`).

---

## Trato de las confederaciones

Para el ganador de cada motor: (a) los casos cara a cara en **venue neutral a
2026-06-15**, y (b) la tabla de sesgo inter-confederación del `--bridge-audit`
rolling sobre los 6 torneos (`bias_a` > 0 ⇒ el motor **sobrevalora** al bloque
`conf_a` en partidos cruzados). Tablas crudas: `data/tuning/bridge_*.csv`.

### Casos cara a cara (1X2 neutral, marcador más probable, xG)

| par | motor | 1 | X | 2 | pick | xG |
|---|---|---:|---:|---:|---:|---|
| **Argentina vs España** | dc-winner | **37.8%** | 31.4% | 30.8% | 1-0 | 1.11–0.97 |
| (CONMEBOL vs UEFA) | elo-winner | 29.7% | 30.4% | **40.0%** | 0-1 | 1.01–1.21 |
| | bayes-winner | **36.3%** | 32.0% | 31.7% | 0-0 | 1.04–0.95 |
| **Australia vs EE. UU.** | dc-winner | **39.3%** | 30.2% | 30.5% | 1-0 | 1.20–1.02 |
| (AFC vs CONCACAF) | elo-winner | **47.5%** | 29.1% | 23.5% | 1-0 | 1.38–0.89 |
| | bayes-winner | **40.0%** | 30.0% | 29.9% | 1-0 | 1.20–1.00 |

Lecturas:

- **Argentina vs España:** `dc` y `bayes` **mantienen a Argentina por encima**
  (el caso de estudio de `docs/connectivity.md` sigue vivo pese al
  `cross_conf_w=2.0` y el re-anclaje del dc). El **`elo` ganador es el único que
  lo invierte**: pone a España por delante (40% vs 30%). La K alta de UEFA (2.0)
  frente a la baja de CONCACAF y la ventana larga reordenan el cruce.
- **Australia vs EE. UU.:** **ningún motor lo corrige**; el `elo` ganador
  incluso lo **agrava** (47.5% vs 23.5%), porque sube la K de la AFC a 2.0 y baja
  la de CONCACAF a 0.5 — EE. UU. mueve poco su rating. Es el mecanismo de
  `docs/known-limitations.md` amplificado. `dc` y `bayes` lo dejan en ~40/30.

### Sesgo inter-confederación (bridge-audit)

Cruce más sensible, **CONMEBOL vs UEFA** (`bias_a` sobre CONMEBOL; rolling en
dc/elo, estático en bayes):

| motor | n | exp_share CONMEBOL | real | bias |
|---|---:|---:|---:|---:|
| dc-winner | 22 | 0.612 | 0.523 | **+0.089** |
| elo-winner | 22 | 0.575 | 0.523 | **+0.053** |
| bayes-winner | 22 | 0.618 | 0.523 | **+0.095** |

Los tres motores **sobrevaloran a CONMEBOL frente a UEFA** en partidos cruzados;
el **`elo` ganador es el único que reduce el sesgo** (+0.053 vs +0.089/+0.095) —
coherente con que invierta el cara a cara Argentina/España. El resto de cruces
densos quedan casi neutros; las celdas AFC–CONCACAF / CAF–CONCACAF tienen n=2–4 y
son ruido.

**Conclusión sobre confederaciones:** el tuning del Elo (K por bloque) es la
único parámetro de los probados que **mueve de verdad** las comparaciones
cruzadas: reduce el sesgo CONMEBOL→UEFA, pero a costa de empeorar AFC→CONCACAF
(Australia). El `dc` (aun con `cross_conf_w=2.0` + `anchor_beta=1.0`) y el `bayes`
(aun con el prior informativo de bloque del experimento anterior) apenas mueven
los cruces, porque su sesgo dominante —Australia— vive a **nivel de equipo**, no
de bloque (ver el experimento de prior informativo).

---

## Experimento: prior de confederación informativo (no media-cero)

Hipótesis del usuario: si en vez del prior de bloque **media-cero** del bayes
("ningún bloque es más fuerte sin evidencia de puentes") imponemos un prior
**informativo** que fuerce un orden OFC ≪ CONCACAF/CAF ≪ UEFA, quizá venzamos la
inflación de Australia (AFC), que tiene pocos puentes.

**Implementación (opt-in, default = modelo actual intacto y regenerable):** las
medias del offset por bloque pasan de 0 a un valor empírico. Cambios en
`stan/dixon_coles.stan` (+ dinámico), `model_bayes.fit(conf_strength=…)` y
`backtest(informed_conf=…)` + helper `backtest.elo_conf_strength`.

**Cómo se fijan las medias (empírico, β auto-calibrada):** se ajusta un
Dixon-Coles, se toma la fuerza de cada equipo (atk−dfn) y se regresa sobre su
**Elo** (globalmente conectado) → pendiente β; la media de cada bloque
es `β·(Elo medio del bloque − Elo medio global)`, repartida ±s/2 en
ataque/defensa. El orden sale correcto para los bloques débiles (OFC −0.75, AFC
−0.59, CONCACAF −0.56, CAF −0.16 < UEFA +0.31) **pero CONMEBOL se dispara a
+1.9** — artefacto de composición: sus 10 equipos son todos fuertes y la media
global está arrastrada por cientos de minnows. Por eso se probaron dos
correcciones: **capped** (winsorizar a ±0.4) y **weak** (aplicar offset solo a
AFC/OFC/CONCACAF/CAF, dejando UEFA/CONMEBOL data-driven).

### Validación (estático, 6 torneos) — neutro

| config (sigma_conf=0.1) | points | rps | log_loss |
|---|---:|---:|---:|
| baseline (media 0) | 610 | 0.1905 | 2.7742 |
| capped (±0.4) | 605 | 0.1903 | 2.7729 |
| weak (solo bloques finos) | 598 | 0.1903 | 2.7736 |

El prior informativo **no mejora el RPS** (diferencias en el 4º decimal, ruido).
Tabla cruda: `data/tuning/bayes_informed.csv`.

### Cara a cara (sigma_conf=0.1) — el prior NO mueve el sesgo

| par | baseline | capped | weak |
|---|---|---|---|
| Argentina vs España (1) | 39.1% | 38.6% | 38.8% |
| **Australia vs EE. UU. (1)** | **42.7%** | **42.5%** | **42.6%** |

Australia sigue clarísimo favorito; el prior informativo lo mueve <0.3 pp.

### Por qué no funciona (mecanismo)

Offsets de bloque **ajustados** (neto atk_conf−dfn_conf) y fuerza **total** de los
dos equipos:

| | AFC | CONCACAF | OFC | Australia (total) | EE. UU. (total) |
|---|---:|---:|---:|---:|---:|
| baseline | −0.45 | −0.76 | −1.16 | **+1.24** | +0.97 |
| weak | −0.45 | −0.75 | −1.20 | **+1.24** | +0.98 |

Dos hechos lo explican:

1. **El baseline ya coloca AFC y CONCACAF bajos** (−0.45 / −0.76) — y casi al
   mismo nivel de Elo (1422 vs 1427), así que cualquier prior los baja **por
   igual** y su comparación relativa no cambia.
2. **El sesgo de Australia no vive en el offset de bloque, sino en su desviación
   individual.** Australia acaba en +1.24 de fuerza total = offset AFC (−0.45) +
   **desviación individual ≈ +1.7**. Esa desviación (`atk_raw`, Student-t de
   colas pesadas) recoge que Australia golea a rivales débiles de la AFC, y el
   prior de confederación **no la toca**: solo mueve el centro del bloque, que ya
   estaba bajo. Entre baseline y weak el offset AFC se mueve 0.005 y la fuerza de
   Australia 0.003.

**Conclusión del experimento:** el prior de confederación informativo es la
herramienta equivocada para el sesgo de Australia. El problema es **a nivel de
equipo** (calendario flojo inflando `atk_raw`), no a nivel de bloque. Domarlo
exigiría un prior **por equipo** (tirar de cada selección hacia su Elo — la idea
del `--elo-tau`, ya probada y rechazada por compartir el mismo sesgo), no uno por
confederación. Se deja como parameter opt-in, default-off (modelo regenerable intacto).

---

## Conclusión

### Resumen por motor

| motor | ganador | rps | nota |
|---|---|---:|---|
| **dc** | hl=1095, cross_conf_w=2.0, anchor_beta=1.0 | **0.1885** (rolling) | el mejor; +8 pts y −0.0005 rps sobre el default |
| **bayes** | dinámico, halfyear | 0.18842 (estático) | empata con el dc estático (0.18820); no lo supera |
| **elo** | 15y, HA=50, conf-K↑ | 0.1934 (rolling) | mejora +20 pts sobre su default pero por detrás de dc/bayes |

Tiempos de tuning: **dc ~3 min**, **elo ~110 s**, **bayes ~varias horas** (18
configs efectivas; estáticas ~12 min, dinámicas 31–50 min cada una).

### Lecturas

1. **El `dc` por defecto sigue siendo difícil de batir.** Su ganador tuneado lo
   mejora de forma **consistente pero marginal** (rps 0.1890→0.1885). El `bayes`
   dinámico lo iguala pero no lo supera, a un coste de cómputo enorme; el `elo`
   tuneado se queda claramente por detrás.
2. **De las variables antes descartadas, solo el re-anclaje de confederación
   (`anchor_beta`) reaparece** con una mejora marginal en `dc`, combinado con
   `cross_conf_w=2.0`. Shrinkage, prior Elo externo, `gd_cap`, y —en bayes—
   `sigma_conf` y `propagate` siguen siendo neutros o negativos.
3. **El sesgo de confederación no se resuelve con ninguno.** La K por bloque del
   Elo es el único parámetro que mueve los cruces, pero cambia un sesgo por otro
   (corrige CONMEBOL→UEFA, agrava Australia→EE. UU.). El experimento del prior de
   confederación informativo (no media-cero) mostró por qué el caso Australia no
   cede: **es un sesgo a nivel de equipo** (calendario flojo inflando la
   desviación individual), no de bloque, y exigiría un prior por equipo.

### Recomendación

**No cambiar `config.py`** (además de ser lo acordado): las mejoras de los
ganadores sobre los defaults actuales son marginales y dentro de la banda de
ruido del RPS, y la regla de regenerabilidad pide que los defaults solo cambien
ante una mejora clara y rolling-validada. Si en algún momento se quisiera adoptar
algo, el candidato con mejor relación coste/beneficio es el `dc` ganador
(`HALF_LIFE_DAYS=1095`, `CROSS_CONF_WEIGHT=2.0`, `CONF_ANCHOR_BETA=1.0`), que es
barato, rolling-validado y empíricamente la mejor combinación — pero la mejora es
pequeña. Todos los parameters nuevos del experimento de prior informativo quedan
opt-in y default-off (modelo regenerable intacto).

_(pendiente)_
