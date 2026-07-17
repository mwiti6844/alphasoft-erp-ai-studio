#!/usr/bin/env bash
# Post-deploy on VPS: build and start AI runtime container.
# Run as deploy (no sudo). Requires Docker + docker compose plugin.
set -euo pipefail

APP_PATH="${APP_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
cd "$APP_PATH"

echo "==> Deploying AI Studio in ${APP_PATH} as $(whoami)"

if [[ ! -f runtime/.env ]]; then
    echo "ERROR: runtime/.env not found."
    echo "       cp runtime/.env.example runtime/.env && edit secrets before deploying."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not installed. Run servers/alpasoft/scripts/setup-docker-ai.sh on the VPS first."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: docker compose plugin not found."
    exit 1
fi

# Old systemd unit binds :8000 — must be stopped before Docker takes the port.
if systemctl is-active --quiet alphasoft-ai 2>/dev/null; then
    echo "WARNING: alphasoft-ai.service is still active (uses port 8000)."
    echo "         Stop it once with sudo: systemctl stop alphasoft-ai && systemctl disable alphasoft-ai"
    if ss -lptn 2>/dev/null | grep -q ':8000 '; then
        echo "ERROR: port 8000 is in use. Stop alphasoft-ai.service first."
        exit 1
    fi
fi

echo "==> Building image"
docker compose -f "$COMPOSE_FILE" build

echo "==> Starting container"
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo "==> Waiting for health"
for _ in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
        echo "==> Health OK"
        docker compose -f "$COMPOSE_FILE" ps
        exit 0
    fi
    sleep 2
done

echo "ERROR: health check failed on http://127.0.0.1:8000/api/health"
docker compose -f "$COMPOSE_FILE" logs --tail=50
exit 1
