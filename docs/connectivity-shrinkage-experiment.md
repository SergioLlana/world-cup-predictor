# Experimento: encogimiento por conectividad para la inflación de la AFC

*2026-06-16. Compañero de proceso de la **Fase C** de
[bayesian-confederation-plan.md](bayesian-confederation-plan.md) y del problema
de inflación por calendario de [known-limitations.md](known-limitations.md) /
[connectivity.md](connectivity.md). Documenta una hipótesis probada y
**rechazada**, y por qué — para no volver a intentarla por el mismo camino.*

## Punto de partida

Observación: el motor `elo` coloca a **Australia demasiado arriba** en el
ranking de la web (#13 por Elo bruto). Es la inflación por calendario ya
documentada (`known-limitations.md` usa a Australia como ejemplo canónico): las
selecciones de confederaciones poco conectadas (AFC sobre todo) tienen ratings
inflados porque su escala está mal anclada a la global.

Diagnóstico inicial comparando motores (`as-of 2026-06-15`):

| equipo | `dc` | `elo` | `bayes` |
|---|---|---|---|
| Australia | #24 | **#13** | #28 |
| Corea | #36 | #19 | #40 |
| Irán | #28 | #17 | #30 |
| Japón | #12 | #8 | #16 |

El `elo` infla más que `dc` (actualización secuencial y local: la información de
los pocos puentes se propaga muy despacio). El `bayes`, con su offset jerárquico
de confederación, ya trata mejor a Australia (#28). La pregunta del experimento:
**¿se puede mejorar aún más el `bayes`?**

## Por qué el offset uniforme no basta (lo que ya sabíamos)

El `bayes` modela `fuerza = offset_de_confederación + desviación_individual`. El
offset es **un único número por bloque**, estimado casi por completo por los
partidos puente de la **élite** (sólo Japón/Australia/Corea/Arabia juegan fuera
de la AFC; los minnows, 0–10 % de puentes) y aplicado por igual a todos. Bajar
el prior del offset de la AFC —lo que el usuario ya había probado— apenas mueve
a Australia, porque:

1. los datos puente de la élite sostienen el posterior del offset contra el
   prior, y
2. un offset uniforme **traslada** el bloque entero; no puede **comprimir** su
   dispersión interna, que es donde vive la ventaja de Australia sobre los
   minnows.

Esto sí ayuda con **Argentina** (su caso es de *nivel de bloque* puro: CONMEBOL
son 10 equipos fuertes y bien conectados), pero no con Australia.

## La hipótesis del experimento (Fase C)

Ponderar lo que cada equipo hereda de su bloque por su **bridge share** (cuota
de peso de partidos inter-confederación; `confederations.bridge_share`, los
mismos pesos `w` que ajusta el modelo). Mapeo
`c = min(1, bridge_share / BAYES_CONNECT_REF)` con `ref = 0.4`. Dos
formulaciones (ambas `--bayes-connect`, estáticas, default-off, `.stan` aparte
para no tocar el modelo de producción; `--bayes-connect-mode`):

- **A — `offset`** (`stan/dixon_coles_connect.stan`):
  `atk[t] = c[t]·atk_conf + σ·atk_raw`. Atenúa el offset del bloque para los
  equipos aislados → se anclan a la **escala global** (0).
- **B — `deviation`** (`stan/dixon_coles_connect_dev.stan`):
  `atk[t] = atk_conf + σ·c[t]·atk_raw`. Partial pooling clásico: encoge la
  desviación del equipo aislado hacia la **media de su bloque**.

Con `c = 1` para todos, ambas se reducen exactamente a `dixon_coles.stan`.

## Resultados

**Rankings (`ratings --engine bayes --as-of 2026-06-15`):**

| | Australia | España | UEFA media | AFC media |
|---|---|---|---|---|
| base bayes | #28 | #2 | +0.78 | −0.54 |
| A (`offset`) | **#20** ⬆ | #3 ⬇ | +0.55 ⬇ | −0.34 ⬆ |
| B (`deviation`) | **#21** ⬆ | #2 ✓ | +0.82 ✓ | −0.57 ✓ |

**Backtest (`backtest --tournament all --static --engine bayes`, 290 partidos):**

| config | puntos Penka | RPS | log-loss |
|---|---|---|---|
| base bayes | **605** | **0.1905** | **2.7732** |
| B (`deviation`) | 581 | 0.1932 | 2.7950 |

(El base 605 confirma de paso la regenerabilidad: con el knob off se usa el path
estático intacto.)

### A es contraproducente

El offset de un bloque **débil es negativo** (AFC ≈ −0.54). Atenuarlo hacia 0 no
es "conservador": **sube** a la AFC (Australia #20, Japón #9, Irán #18). Y en los
bloques fuertes (UEFA, offset positivo) atenuar **baja** a outliers legítimos
poco puenteados (España #3, Inglaterra). Justo al revés del objetivo. La premisa
"tirar hacia la escala global = hacia 0" estaba equivocada: 0 sólo es
conservador para un bloque fuerte.

### B es limpia pero no cumple el objetivo

Preserva los outliers (España #2, UEFA no baja) y hace el partial pooling
esperado en los minnows (Laos #231→#198, Bhutan #241→#230), pero **tampoco baja
a Australia** y empeora las tres métricas de backtest, con el daño concentrado
en **wc2022** (102→88 pts) — el torneo más cargado de AFC, justo el bloque que
distorsiona.

## Hallazgo raíz: el bridge share es el predictor equivocado

La razón de fondo de que ninguna formulación funcione:

> **Australia no es un equipo poco conectado.** Su bridge share es **0.47**, de
> los más altos de la AFC (Japón 0.49, Corea 0.47).

Mide la conectividad por equipo y la élite asiática juega 35–50 % de partidos
fuera del bloque; los minnows, 0–10 %. Lo que infla a Australia **no es la
cantidad de puentes sino su dificultad**: sus puentes son Nueva Zelanda ×5
(OFC), Curaçao 5-1, Canadá, Camerún, Túnez… y sólo pierde con los muy top (3-7-2
vs UEFA/CONMEBOL fuertes). Por eso ningún encogimiento por bridge share la toca,
y A incluso la **premia** por su alta conectividad.

El predictor que sí la separa es la **dificultad media de rivales**
(`opp_rating`, donde la AFC sale plana y baja), no la conectividad.

## Qué queda por probar (Fase C')

La línea de "encoger a los poco anclados" **sigue viva**, pero con el predictor
correcto. Pendiente:

1. **Encogimiento por `opp_rating`** en lugar de bridge share: gatear la
   desviación (estilo B, que no daña outliers) por la dificultad de calendario,
   no por la cantidad de puentes. Hipótesis: baja a quien acumuló rating contra
   rivales débiles (Australia) sin castigar a quien juega calendarios duros.
2. **Compresión de la escala intra-bloque** de las confederaciones con
   `opp_rating` bajo (un `sigma_atk` por bloque, no global), atacando la
   dispersión interna que el offset uniforme no puede tocar.
3. Validar siempre con `--bridge-audit` (tabla de calibración inter-bloque) y el
   backtest de 6 torneos, vigilando wc2022 (el más sensible a la AFC).

Cuidado: el motor `elo` (el del ranking de la web, #13) es un mecanismo distinto
del `bayes` y no tiene estructura de offset; cualquier mitigación ahí pasa por
`ELO_CONF_K` (`wcpred tune --elo-engine`), no por esto.

## Reproducir

```bash
# Rankings con cada formulación (default-off; sólo --engine bayes)
wcpred ratings --engine bayes --as-of 2026-06-15                              # base
wcpred ratings --engine bayes --as-of 2026-06-15 --bayes-connect              # A (offset)
wcpred ratings --engine bayes --as-of 2026-06-15 --bayes-connect \
               --bayes-connect-mode deviation                                  # B

# Backtest comparativo
wcpred backtest --tournament all --static --engine bayes                       # base
wcpred backtest --tournament all --static --engine bayes --bayes-connect \
               --bayes-connect-mode deviation                                  # B
```

Knobs: `BAYES_CONNECT_SHRINK` / `BAYES_CONNECT_REF` / `BAYES_CONNECT_MODE`
(`config.py`). Helper: `confederations.bridge_share`. **No regenerar snapshots
pasados con estos knobs** (regla de regenerabilidad): son experimentos
default-off.
