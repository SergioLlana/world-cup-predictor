# Tiempos de ejecución de los engines

Cuánto tarda cada opción de `scripts/generate_predictions.sh --engines …`, por
motor (`dc` / `elo` / `bayes`) y por sub-comando (`predict` / `groups` /
`simulate`). Sirve para dimensionar el run diario y el backfill de la web.

## Método

Medido en la máquina de desarrollo, un par approach/fecha real
(`--approach odds --as-of 2026-06-12`), con los valores por defecto de Monte
Carlo (`groups` 1.000.000 sims, `simulate` 100.000 sims). Cada celda es una sola
corrida cronometrada con `date`, aislada (sin otros procesos compitiendo por
CPU). Reproducir:

```bash
scripts/generate_predictions.sh --approach odds --as-of 2026-06-12 \
  --engines bayes --groups-only      # etc., variando --engines y --*-only
```

## Resultados (segundos)

| sub-comando | dc | elo | bayes |
|---|---:|---:|---:|
| `predict`  | 3 | 3 | 152 |
| `groups`   | 9 | 8 | 156 |
| `simulate` | 3 | 3 | 147 |
| **total (3 salidas)** | **15** | **14** | **455 (~7,6 min)** |

Coste de un **par completo** (un approach + una fecha) según los motores que pidas:

| `--engines` | tiempo aprox. |
|---|---:|
| `dc`            | ~15 s |
| `elo`           | ~14 s |
| `bayes`         | ~7,6 min |
| `dc,elo`        | ~30 s |
| `elo,bayes`     | ~8 min (medido: 492 s) |
| `dc,elo,bayes`  | ~8 min |

## Lectura

- **`dc` y `elo` cuestan lo mismo** (segundos). El sub-comando más caro de los
  dos es `groups`, por el Monte Carlo de 1M de simulaciones; el fit del modelo
  es instantáneo en ambos.
- **`bayes` domina el reloj**: ~150 s por sub-comando. El coste **no** es el
  Monte Carlo sino el **fit MCMC** (4 cadenas, vía CmdStan), que se rehace en
  cada sub-comando de forma independiente (`predict`, `groups` y `simulate` no
  comparten el ajuste). Por eso `bayes` solo escala bien si lo limitas a las
  salidas que necesitas (p. ej. `--predict-only`). Requiere el extra `.[bayes]`
  + CmdStan.
- **Añadir `dc` a `elo,bayes` es gratis** en la práctica (+15 s sobre ~8 min).

## Implicaciones prácticas

- **Run diario** con `--engines dc,elo,bayes` y las tres salidas: ~8 min por
  par approach/fecha. Si corres `odds` e `history`, ~16 min.
- **Backfill** de los 7 pares con snapshot `dc` (odds 06-11..06-14 + history
  06-11/06-12/06-14) en `elo` y `bayes`, tres salidas: **~57 min**, dominado por
  los fits MCMC de `bayes`.
- Para iterar rápido (solo comparar picks), usa `--predict-only`: baja a ~150 s
  por par con `bayes`, segundos con `dc`/`elo`.
