@AGENTS.md

# Instrucciones específicas para Claude Code

## Contexto de infraestructura
- **Host producción GTA6Channel:** MacBook Pro Intel Haswell, macOS Big Sur 11.7.11
- **IP Tailscale:** `100.108.212.124` (alias MagicDNS: `gtrujillo-macbook-pro`)
- **Acceso:** SSH exclusivamente por Tailscale — `ssh gabrieltrujillovallejo@100.108.212.124`
- **Convive con GaTDSEQ Worker** en el mismo Mac — respetar siempre prioridad de CPU (nice 15)

## Herramientas y flujo de trabajo

### Módulos clave recientes
- `src/x_scout.py` — Scout persistente de X (Twitter): extrae clips nativos y enlaces desde tus Likes (`/likes`) y Timeline, actualizando `data/x_taste_profile.json` y alimentando la cola `data/curated_queue.json`.
- `src/community_manager.py` — Interacción comunitaria autónoma: auto-respuestas inteligentes con Gemini/0-API en comentarios de YouTube e Instagram Reels, filtrando spam y con límite de tasa.
- `src/social_publisher.py` — Constructor de descripciones estéticas en TikTok (`_build_tiktok_caption`) con debate, SEO y hasta 900 caracteres.
- `src/uploader.py` — Sistema de enfriamiento temporal (`youtube_cooldown_until.txt`), tope diario de 3 Shorts/24h y espaciado de >=4h en YouTube.

### Exploración del código
- El proyecto tiene `.codegraph/` indexado. Usar `codegraph_explore` ANTES de grep/Read para localizar símbolos.
- Para leer archivos grandes de `src/` usar Read con offset/limit.

### Despliegue en producción
```bash
# Sincronizar al Mac remoto (NUNCA git push sin confirmar primero)
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='.env' \
  ./ gabrieltrujillovallejo@100.108.212.124:~/GTAVIHub/

# Reiniciar bot Telegram (si se tocó telegram_bot.py o main.py)
ssh gabrieltrujillovallejo@100.108.212.124 \
  "pkill -f 'main.py --telegram' ; sleep 2 ; \
   ~/GTAVIHub/deploy/launchd/watchdog.sh"
```

### Verificación de salud post-despliegue
```bash
ssh gabrieltrujillovallejo@100.108.212.124 "tail -20 ~/GTAVIHub/logs/telegram.log"
```

## Convenciones de commits (Conventional Commits)
- `feat:` — nueva funcionalidad
- `fix:` — corrección de bug
- `refactor:` — reestructuración sin cambio de comportamiento
- `docs:` — solo documentación
- `chore:` — limpieza, dependencias, CI

## Protocolo antes de cada commit
1. `python -m unittest discover -s tests` — deben pasar al 100%
2. Verificar `temp/` vacío: `ls temp/` no debe mostrar `.mp4`
3. `git status` — confirmar que `.env`, `token.json`, `client_secrets.json` NO aparecen

## Macro "auditoria"
Si el usuario escribe **"auditoria"**, ejecutar secuencialmente:
1. Revisar logs en Mac remoto (`~/GTAVIHub/logs/`)
2. Verificar `temp/` y `output/` (limpiar si hay `.mp4` huérfanos)
3. Comprobar que el watchdog cron esté activo (`crontab -l`)
4. Reportar estado del proceso `main.py --telegram`

## Recordatorios clave
- **Jamás** usar `libx264`; siempre `h264_videotoolbox` en Mac
- Máximo 2-3 vídeos/día por plataforma con jitter de 10-15 min
- El modo Co-Pilot requiere aprobación táctil en Telegram antes de publicar
- `data/processed.json` y `data/copilot_state.json` NUNCA al repo
