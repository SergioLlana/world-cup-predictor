# Estrategia de selección del marcador (`--pick-strategy`)

El modelo produce una **matriz de probabilidad** `P[goles_local, goles_visitante]`
por partido. Convertir esa matriz en **un marcador** que apostar es un paso
aparte —`scoring.select_prediction`— independiente del modelo y del tuning. Hay
dos estrategias:

- **`ev`** (default, regenerable): el marcador que **maximiza los puntos Penka
  esperados** (`scoring.best_prediction`, `argmax E[pts]`). Es óptimo en
  aislamiento pero **demasiado conservador**: tiende a poner 1-0 al favorito.
- **`outcome`** (estrategia C): el **resultado 1X2 más probable** (1/X/2) y, dentro
  de él, el **marcador más probable** (`scoring.best_prediction_outcome`).

## Por qué `outcome` rinde más

Comparación sobre los seis torneos del backtest (rolling, motor `dc`, Penka):

| estrategia | puntos | pts/partido |
|---|---:|---:|
| **`outcome` (C)** | **643** | **2.217** |
| `ev` (default) | 594 | 2.048 |

**+8% de puntos Penka.** Y sobre los 28 partidos ya jugados del Mundial 2026
(odds/dc reconstruido): **45 pts (C) vs 38 pts (ev)**, +18%.

El hallazgo clave: C **no gana prediciendo más empates** (predice casi ninguno,
igual que `ev`). Gana eligiendo **mejores marcadores de victoria**. El optimizador
de valor esperado es demasiado conservador y por defecto pone 1-0; C pone el
marcador de victoria *más probable* del favorito (2-0, 2-1…), que engancha más
exactos (5 pts) y diferencias (3 pts) donde `ev` se quedaba en "solo ganador"
(2 pts).

Lo que **no** funciona (medido y descartado): forzar empates cuando `P_X` supera
un umbral. El modelo casi nunca asigna >30% a un empate —ni siquiera en este
Mundial tan empatado—, así que la regla apenas se dispara. Es un límite de
**calibración** de las probabilidades, no del paso de selección: no puedes
"elegir" empates que el modelo no te da.

## En los CSV y en la web

Cada fila de `data/predictions/picks_*.csv` lleva **las dos** predicciones
(`predict.predict_fixtures` las calcula siempre desde la misma matriz):

- `pick` / `expected_points` → estrategia `ev`.
- `pick_outcome` / `expected_points_outcome` → estrategia C.

La web (`webapp/`) trae por defecto **motor Elo + estrategia C** y un toggle
("Marcador más probable") que cambia qué columna se muestra — sin recargar datos,
porque ambas viajan en el mismo CSV. Los snapshots antiguos (solo `ev`) caen a
`pick` (`app.js:pickOf`). El script `scripts/enrich_picks_outcome.py` añade la
columna `pick_outcome` a snapshots viejos **sin tocar** las columnas `ev`.

## Regla de regenerabilidad

La estrategia de producción para análisis (CLI/backtest) se queda en **`ev`** a
propósito: los snapshots `data/predictions/` se reproducen idénticos en sus
columnas `ev`. `outcome` es opt-in en la CLI:

```bash
wcpred predict --approach odds --odds data/input/odds.csv --pick-strategy outcome
scripts/generate_predictions.sh --pick-strategy outcome   # flujo en directo
wcpred backtest --tournament all --pick-strategy outcome   # re-validar
```

No se regeneran los snapshots pasados con `outcome`: los partidos ya jugados se
apostaron con `ev`, y reescribir el histórico rompería la regla de
regenerabilidad. C se usa **de hoy en adelante**.
