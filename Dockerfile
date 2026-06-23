# Container image for the public wcpred dashboard. Optional fallback for hosts
# that build from a Dockerfile instead of the render.yaml native Python runtime
# (Fly.io, Railway with Docker, etc.). Render uses render.yaml by default.
FROM python:3.11-slim

WORKDIR /app
COPY . .

# Only the web extra: serves the date-stamped CSVs + live dc/elo re-fits. The
# bayes engine (CmdStan) is intentionally left out of the public deploy.
RUN pip install --no-cache-dir -e ".[web]"

# Lock the image into public mode (no refresh, no Connectivity, no bayes).
ENV WCPRED_PUBLIC=1
ENV PORT=8026
EXPOSE 8026

# Honour $PORT when the platform injects one (Render/Railway), default 8026.
CMD ["sh", "-c", "uvicorn webapp.server:app --host 0.0.0.0 --port ${PORT:-8026}"]
