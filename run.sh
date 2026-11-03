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
    if [ -f "scripts/auth_youtube.py" ]; then
        python3 scripts/auth_youtube.py
    else
        python3 auth_youtube.py
    fi
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

# Comando especial para iniciar sesión persistente en TikTok e Instagram
if [ "$1" == "login-social" ] || [ "$1" == "--login-social" ] || [ "$1" == "login" ]; then
    python3 main.py --login-social
    exit 0
fi

# Comando especial para iniciar el bot de control remoto de Telegram
if [ "$1" == "telegram" ] || [ "$1" == "--telegram" ] || [ "$1" == "bot" ]; then
    python3 main.py --telegram
    exit 0
fi

# Comando especial para escanear el Radar Viral de engagement
if [ "$1" == "radar" ] || [ "$1" == "--radar" ] || [ "$1" == "viral" ]; then
    python3 main.py --radar
    exit 0
fi

# Comando especial para el Centinela de Tráfico en Tiempo Real
if [ "$1" == "traffic" ] || [ "$1" == "--traffic" ] || [ "$1" == "sentinel" ]; then
    python3 src/traffic_sentinel.py
    exit 0
fi

# Comando especial para el Reciclador Dinámico de Conocimiento
if [ "$1" == "recycle" ] || [ "$1" == "--recycle" ] || [ "$1" == "fase" ]; then
    python3 src/knowledge_recycler.py
    exit 0
fi

# Comando especial para el Laboratorio de Clips y prueba de formatos (sin subidas)
if [ "$1" == "lab" ] || [ "$1" == "--lab" ]; then
    shift
    if [ "$1" == "--loop" ] || [ "$1" == "loop" ]; then
        shift
        python3 scripts/recursive_lab_session.py "$@"
    else
        python3 scripts/clip_lab.py "$@"
    fi
    exit 0
fi

# Ejecutar con argumentos pasados o por defecto --auto
if [ $# -eq 0 ]; then
    echo "[*] Ejecutando escaneo autónomo estándar..."
    python3 main.py --auto
else
    python3 main.py "$@"
fi
