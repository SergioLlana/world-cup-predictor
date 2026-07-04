# Plan: migración a AWS (web estática en S3+CloudFront + pipeline programado en Fargate)

## Objetivos (entrevista 2026-07-04)

1. **Quitar mi máquina del flujo**: el pipeline diario (update-data + generadores
   + MCMC + export) corre programado en AWS.
2. **Sacar los datos de git**: los CSVs diarios dejan de commitearse; S3 pasa a
   ser la fuente de verdad (el histórico pre-migración queda en el historial git).
3. **Web pública siempre disponible y compartible** (Twitter/X): sin el dyno
   free de Render que duerme a los ~15 min.

Decisiones: web **100% estática** (S3 + CloudFront, sin servidor), pipeline en
**EventBridge Scheduler → ECS Fargate**, infraestructura con **scripts AWS CLI**
idempotentes en `scripts/aws/`.

## Por qué estática (y alternativas descartadas)

El modo público (`WCPRED_PUBLIC=1`) ya es **solo lectura**: refresh bloqueado,
Conectividad oculta, bayes servido desde CSVs precalculados. Los únicos fits en
vivo que quedan (matrices dc/elo, fallback de rankings) son deterministas por
snapshot → se pueden exportar a ficheros. Sin servidor no hay cold starts, no
hay dependencias que parchear y un pico de tráfico desde X lo absorbe CloudFront
por céntimos.

- **Lambda + API Gateway (Mangum)** — descartada: FastAPI casi sin cambios, pero
  añade cold starts (1-2 s), caché de lecturas S3 y más superficie operativa que
  un export a ficheros.
- **App Runner / Lightsail (contenedor)** — descartada: es replicar Render en
  AWS (~5-7 $/mes por un servidor siempre encendido que solo lee CSVs).

El **modo local completo no cambia**: FastAPI + `data/` en disco (traído de S3
con `pull_data.sh`), con fits en vivo y refresh como hoy.

## Arquitectura objetivo

```
                    (diario, cron Europe/Madrid)
EventBridge Scheduler ──▶ ECS Fargate (imagen wcpred-pipeline, con CmdStan)
                             │ 1. s3 sync  s3://wcpred-data → data/
                             │ 2. update_data.sh --skip-xg   (ODDS_API_KEY ← SSM)
                             │ 3. generate_predictions.sh × odds,history × dc,elo,bayes
                             │ 4. generate_rankings.sh
                             │ 5. export_static.py  →  build/site/
                             │ 6. s3 sync data/ ↑  +  s3 sync site ↑  + invalidación
                             ▼
        s3://wcpred-data (privado, versionado)     s3://wcpred-site (privado)
              fuente de verdad de data/                    │ OAC
                                                           ▼
                                                      CloudFront ──▶ público
                                                 (frontend + api/*.json)
```

## Fase 0 — Base de cuenta

- Cuenta AWS, región **eu-south-2 (Madrid)** (fallback eu-west-1 si faltara
  algún servicio); CloudFront es global.
- Perfil CLI `wcpred`; usuario/rol de administración solo para los scripts de setup.
- **Alarma de presupuesto (Budgets) a 5 $/mes** — la red de seguridad de todo el plan.
- `scripts/aws/00_setup.sh`: crea buckets (`wcpred-data-<account>`,
  `wcpred-site-<account>`, privados, versioning en el de datos), parámetro SSM
  SecureString `/wcpred/odds-api-key`, y el log group.

## Fase 1 — Datos en S3 (publicación aún desde local)

- `scripts/aws/push_data.sh`: `aws s3 sync data/ s3://wcpred-data/...`
  (incluye `input/` con los snapshots de odds y `models/` — la caché de
  posteriores bayes, con regla de lifecycle p. ej. 60 días).
- `scripts/aws/pull_data.sh`: lo inverso, para desarrollo y para el contenedor.
- A partir de aquí el pipeline local publica a S3 tras cada run; los commits de
  datos a git se mantienen **en paralelo** hasta la fase 5 (transición segura).

## Fase 2 — Web estática (S3 + CloudFront)

1. **`scripts/export_static.py`**: levanta la app en modo público con el
   `TestClient` de FastAPI y vuelca cada respuesta a `build/site/api/` (gitignored):
   - `meta.json`, `matches.json`
   - `picks|groups|sims_<approach>_<engine>.json` (2×3 combinaciones cada uno)
   - `rankings_history_<engine>.json` y `rankings_<engine>.json` (3 + 3)
   - `matrix/<fecha>_<slug-home>_<slug-away>_<approach>_<engine>.json` por
     partido del calendario (~104 × 2 × 3 ficheros pequeños), con **los picks de
     ambas estrategias en el mismo JSON** (evita duplicar por estrategia).
   - Checklist de cobertura: todo `fetchJSON()` de `app.js` debe tener fichero
     (connectivity y refresh no aplican en público).
2. **Frontend**: shim en `fetchJSON` — si el site es estático (flag en el
   `index.html` desplegado o en `meta.json`), mapear `/api/x?a=1&b=2` → ruta de
   fichero. El slug de equipos (minúsculas, espacios→`-`, sin diacríticos:
   `Curaçao`→`curacao`) se comparte entre exportador y frontend.
3. **CloudFront**: OAC contra `wcpred-site` (bucket privado), root
   `index.html`, TTL corto para `api/` (60-300 s); la publicación termina con
   `create-invalidation '/*'` (cuenta como 1 path, free tier 1000/mes).
4. `scripts/aws/publish_site.sh`: export + sync + invalidación.
5. Extras para compartir en X: metatags OG/Twitter Card en `index.html`
   (título, descripción, imagen estática). Dominio propio opcional
   (Route 53 + certificado ACM en us-east-1) — se puede añadir después sin tocar nada.

**Verificación**: la URL de CloudFront reproduce el modo público actual pestaña
a pestaña (picos, grupos, calendario con matrices de los 3 motores, rankings,
EN/ES), comparando algunos JSON contra el API local en modo público.

## Fase 3 — Imagen del pipeline

- **`Dockerfile.pipeline`** (el `Dockerfile` actual queda para la web y morirá
  con Render): `python:3.11-slim` + toolchain C++ (`g++ make`) +
  `pip install -e ".[web,bayes]"` + `install_cmdstan` + **precompilar los
  `.stan` en el build** (que el run diario no recompile). `TZ=Europe/Madrid`
  (el cron y `ODDS_CUTOVER` 17:00 son hora local). `.[web]` hace falta para el
  `TestClient` del exportador.
- Arquitectura **ARM64** (Fargate Graviton, ~20 % más barato) — se construye
  nativo desde el portátil Apple Silicon sin emulación.
- Entrypoint **`scripts/daily_publish.sh`** = pasos 1-6 del diagrama. Los pasos
  2-4 son los mismos que lanza hoy `POST /api/refresh`; el 5-6 son nuevos.
- Probar **primero en local**: `docker run` con credenciales de solo-S3 debe
  dejar la web pública actualizada de punta a punta. La caché de posteriores en
  S3 hace el MCMC incremental (~2 min solo el primer fit del día).
- ECR: repo `wcpred-pipeline` + `scripts/aws/push_image.sh`.

## Fase 4 — Programación y alertas

- Cluster ECS (solo Fargate, sin instancias), task definition **2 vCPU / 8 GB**
  (holgura para las 4 cadenas MCMC; el run diario completo se estima en
  15-25 min).
- **EventBridge Scheduler**: `cron(0 8 * * ? *)` zona Europe/Madrid → RunTask.
  Misma franja matinal que el hábito actual, coherente con los snapshots de odds.
- IAM mínimo: task role = S3 rw en los 2 buckets + `cloudfront:CreateInvalidation`
  + lectura del parámetro SSM; execution role = ECR pull + CloudWatch Logs.
- **Alerta de fallo**: regla EventBridge sobre "ECS Task State Change" con
  `exitCode != 0` → SNS → email. Sin ella un pipeline roto pasa desapercibido
  hasta ver la web desactualizada.
- `scripts/aws/30_schedule.sh` crea/actualiza todo; el schedule se puede
  desactivar con un flag cuando acabe el Mundial (19-07).

## Fase 5 — Retirada de Render y salida de datos de git

Solo cuando la fase 4 lleve unos días verificada:

1. Suspender el servicio de Render (dejarlo unos días como fallback, luego borrar).
2. Dejar de commitear `data/predictions|groups|simulations|rankings|matrices`:
   añadirlos a `.gitignore`; **el historial git conserva todo lo anterior** y el
   versioning de S3 asume el registro histórico en adelante (la regla de
   regenerabilidad de CLAUDE.md pasa a apoyarse en S3 y se actualiza ahí).
3. README y CLAUDE.md: nueva URL pública, `pull_data.sh` para desarrollo,
   sección de operación del pipeline (logs en CloudWatch, re-run manual con
   `aws ecs run-task`).

## Costes estimados (mensual)

| Concepto | Estimación |
|---|---|
| S3 (datos + site + versioning, pocos GB) | ~0,20 $ |
| CloudFront (free tier 1 TB/mes) | ~0 $ |
| Fargate ARM 2 vCPU/8 GB × ~25 min/día | ~1,00 $ |
| ECR (~2 GB imagen) | ~0,20 $ |
| SSM, EventBridge, SNS, Logs | ~0 $ |
| **Total durante el Mundial** | **~1-2 $/mes** |
| Después (schedule off, solo servir la web) | ~0,50 $/mes |

## Riesgos y mitigaciones

- **Export incompleto** (una llamada del frontend sin fichero): checklist
  contra `app.js` en fase 2 + probar cada pestaña/idioma en la URL de CloudFront.
- **Deriva local↔contenedor** (versiones de numpy/scipy cambian bytes): el
  contenedor pasa a ser el entorno canónico de generación; `uv.lock`/pins en la
  imagen. El desarrollo local sigue valiendo para todo lo demás.
- **The Odds API falla o agota cuota**: `update_data.sh` ya degrada (genera con
  lo que hay); la alerta SNS avisa si el task sale con error.
- **Coste desbocado** (bucle de invalidaciones, tráfico): alarma de Budgets de
  la fase 0 + TTLs cortos solo en `api/`.
- **Orden de fases**: cada fase deja algo útil y reversible; Render no se toca
  hasta el final.
