#!/usr/bin/env bash
# ==============================================================================
# GTA6Channel Automation Runner (Optimized for Apple Silicon M4)
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Activar entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "[!] No se encontró .venv en $DIR"
    exit 1
fi

# Comando especial para autenticar YouTube
if [ "$1" == "auth" ] || [ "$1" == "--auth" ]; then
    python3 auth_youtube.py
    exit 0
fi

# Comando especial para ver estado y monitorización
if [ "$1" == "status" ] || [ "$1" == "--status" ]; then
    python3 main.py --status
    exit 0
fi

# Comando especial para auditar directrices y políticas anti-strike
if [ "$1" == "audit" ] || [ "$1" == "--audit" ]; then
    python3 main.py --audit
    exit 0
fi

# Ejecutar con argumentos pasados o por defecto --auto
if [ $# -eq 0 ]; then
    echo "[*] Ejecutando escaneo autónomo estándar..."
    python3 main.py --auto
else
    python3 main.py "$@"
fi
