#!/usr/bin/env bash
# Despliegue de GTA VI Hub al MacBook Pro de producción (vía Tailscale + scp).
# Uso:  ./scripts/deploy.sh            -> sube código y reinicia el bot
#       ./scripts/deploy.sh --no-restart -> solo sube código
# NO sube secretos (.env, token.json, client_secrets.json, data/).
set -euo pipefail

HOST="${GTA_HOST:-gabrieltrujillovallejo@100.108.212.124}"
REMOTE="${GTA_REMOTE_DIR:-~/GTAVIHub}"
cd "$(dirname "$0")/.."

echo "→ Comprobando conexión con $HOST ..."
ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST" 'echo "   conectado: $(hostname)"' \
  || { echo "✗ Sin conexión. ¿Tailscale activo en este Mac?"; exit 1; }

echo "→ Subiendo código ..."
scp -q main.py requirements.txt .env.example .gitignore "$HOST:$REMOTE/"
scp -q src/*.py "$HOST:$REMOTE/src/"
scp -q docs/*.md "$HOST:$REMOTE/docs/"
scp -q scripts/*.py scripts/*.sh "$HOST:$REMOTE/scripts/" 2>/dev/null || true
echo "   código subido."

if [[ "${1:-}" == "--no-restart" ]]; then
  echo "✓ Hecho (sin reiniciar). El cambio se aplicará en el próximo reinicio."
  exit 0
fi

echo "→ Reiniciando bot (el watchdog lo revive) ..."
ssh "$HOST" "pkill -f 'main.py --telegram' || true; sleep 5; \
  bash $REMOTE/deploy/launchd/watchdog.sh >/dev/null 2>&1 || true; sleep 5; \
  pgrep -fl 'main.py --telegram' || echo '   aún no visible; el cron lo levantará en <5 min'"
echo "✓ Despliegue completado."
