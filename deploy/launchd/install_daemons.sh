#!/usr/bin/env bash
# ==============================================================================
# GTA VI Hub Spain - macOS launchd Daemon Installer
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$DIR/logs"

echo "[*] Instalando servicios launchd desde: $DIR"

for plist in com.gtavihub.telegrambot.plist com.gtavihub.automation.plist; do
    SRC="$DIR/deploy/launchd/$plist"
    DEST="$LAUNCH_AGENTS_DIR/$plist"
    
    if [ -f "$SRC" ]; then
        echo "[*] Configurando $plist..."
        sed "s|/Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/GTA6Channel|$DIR|g" "$SRC" > "$DEST"
        
        launchctl unload "$DEST" 2>/dev/null || true
        launchctl load -w "$DEST"
        echo "[✓] $plist cargado con éxito."
    fi
done

echo ""
echo "=== Estado de Demonios Activos ==="
launchctl list | grep gtavihub || echo "[!] Ningún demonio detectado."
