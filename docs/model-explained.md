# Cómo funciona el modelo

Recorrido de principio a fin de `wcpred`, con las tres fuentes de datos
(resultados, xG, odds) integradas en distintos puntos del pipeline.

## El núcleo: modelo Dixon-Coles (`model.py`)

Es un modelo de Poisson bivariante ponderado. Cada selección tiene dos
parámetros latentes:

- **`atk[i]`** — fuerza ofensiva
- **`dfn[i]`** — debilidad defensiva (más alto = encaja más)

Más un término global **`home`** de ventaja local. Los goles esperados de un
partido son:

```
λ (local)     = exp(atk_local + dfn_visitante + home·hadv)
μ (visitante) = exp(atk_visitante + dfn_local)
```

El ajuste (`fit`) maximiza la log-verosimilitud Poisson ponderada vía L-BFGS-B
(con gradiente analítico y una penalización de identificabilidad para fijar la
media de `atk`). Después estima **`rho`** por *grid search*: la corrección
Dixon-Coles que reajusta las probabilidades de los marcadores bajos
(0-0, 1-0, 0-1, 1-1), donde el Poisson puro falla. La función `_tau` aplica esa
corrección.

El resultado final de un partido es una **matriz de marcador**
`P[goles_local, goles_visitante]` sobre la rejilla `0..8`
(`score_matrix` / `matrix_from_rates`).

## Cómo entran las cuatro fuentes

### 1. Resultados — entrenan el modelo (`data.prepare_training`)

Es la única fuente que **entrena**. Se descargan de martj42 (`update-data`) y
se filtran a partidos jugados entre `TRAIN_START` (2015) y el corte `as_of`.
Cada partido recibe un peso `w`:

- **Decaimiento temporal**: `w = exp(-ln2/730 · días)` → el peso se reduce a la
  mitad cada 2 años (`HALF_LIFE_DAYS`).
- **Amistosos al 50%**: `w *= FRIENDLY_WEIGHT` (0.5).
- Se descartan selecciones con menos de `MIN_MATCHES` (10) partidos.

Ese `w` es el que multiplica la verosimilitud en `fit`.

### 2. xG — se mezcla *dentro* del entrenamiento (`prepare_training`, opcional)

Si pasas `--xg`, antes de ajustar se reemplazan los goles por **goles
efectivos**:

```
g_eff = α·goles + (1-α)·xG     con α = XG_ALPHA = 0.6
```

Es decir, 60% goles reales / 40% xG, solo en los partidos que tienen xG
disponible (`how="left"`, los que no tienen quedan con sus goles reales). Esto
suaviza la varianza de finalización. Sigue alimentando el mismo `fit` Poisson —
el modelo **nunca ve xG como variable aparte**, solo unos goles "corregidos".

### 3. Odds — blend en *tiempo de predicción*, no entrenan (`odds.py` + `predict.predict_match`)

Las cuotas no tocan el modelo entrenado; se combinan al predecir cada partido:

1. `to_prob` convierte cuotas americanas o decimales (autodetectadas por
   `|valor|≥100`) a probabilidad implícita.
2. `devig` quita el margen de la casa normalizando 1X2 para que sumen 1.
3. `market_matrix` **recalibra `λ` y `μ`**: parte de las tasas del modelo y las
   optimiza (Nelder-Mead) hasta que la matriz Dixon-Coles reproduce las
   probabilidades 1X2 del mercado. Clave: hereda la *forma* (rho, distribución
   de marcadores) del modelo pero el *resultado* del mercado.
4. Se mezclan las dos matrices:

   ```python
   P = 1.0·P_mercado + 0.0·P_modelo     # ODDS_WEIGHT = 1.0 (por defecto)
   ```

Por defecto los marginales 1X2 son **100% del mercado**, porque las cuotas
incorporan información que el modelo no tiene (lesiones, suspensiones y
rotaciones, que se precian en minutos). El modelo solo aporta la *forma* de la
distribución de marcadores dentro de cada resultado (las cuotas no contienen
marcadores). Con `--odds-weight < 1.0` se reintroduce el 1X2 del modelo (p. ej.
`0.80` ⇒ `0.80·mercado + 0.20·modelo`).

## El paso final: la elección óptima (`scoring.best_prediction`)

Aquí está lo no obvio del proyecto. Teniendo la matriz `P`, **no se elige el
marcador más probable**, sino el que **maximiza los puntos esperados de
Superbru**:

```
EP(marcador) = Σ  P[th,ta] · puntos(marcador, (th,ta))
```

Con el baremo: 3 exacto / 1.5 acierto-de-signo-y-cerca / 1 acierto-de-signo / 0.
La "cercanía" se mide con el *Closeness Index*
(`|Δdif_goles| + |Δgoles_totales|/2 ≤ 1.5`). Por eso el pick óptimo tiende a
marcadores "seguros" tipo 1-0 o 2-1: cubren mejor el espacio de resultados
cercanos aunque individualmente no sean el más probable.

`best_prediction` está vectorizado: la matriz de puntos del baremo se construye
una sola vez (`points_matrix`, cacheada por tamaño de rejilla) y el cálculo se
reduce a `puntos · P` para todos los partidos.

## Opcional: prórroga y penaltis (eliminatorias)

Superbru puntúa el resultado a los 90', así que **por defecto** el modelo
ignora la prórroga. Para porras que puntúen el resultado *final* de la
eliminatoria existen dos opciones (ambas desactivadas por defecto):

- `--extra-time` (`scoring.resolve_extra_time`): cada empate de la fase
  reglamentaria se reparte según la distribución de goles de la prórroga, una
  matriz Dixon-Coles con las tasas a `EXTRA_TIME_FRACTION = 1/3` (30' vs 90').
- `--shootout` (`scoring.resolve_shootout`, implica `--extra-time`): la masa que
  sigue empatada tras la prórroga se resuelve como tanda de penaltis,
  convirtiéndola en una victoria por un gol (50/50 local/visitante).

Es la idea portada de `etel-euros`; no usarla con el baremo Superbru.

## Resumen del flujo

```
results.csv ─┐
xG (α blend)─┴─→ prepare_training ──→ DixonColes.fit ──→ matriz P_modelo
                                                              │
odds ──→ devig ──→ market_matrix ──→ P_mercado ──┐            │
                                                 └─ 1.0·mkt (def.; --odds-weight)
                                                              │
                                                  best_prediction (max EP Superbru)
                                                              │
                                                          pick + EP
```
