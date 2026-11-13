# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Setup local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`.env` mínimo requerido:
```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
YOUTUBE_CLIENT_SECRETS=...   # path a client_secrets.json
```
Archivos de sesión en `assets/.browser_profiles/` (git-excluidos): `instagrapi_session.json`, `tiktok_cookies.json`.

## Comandos de desarrollo

```bash
# Tests (suite completa — deben pasar al 100% antes de cualquier commit)
python -m unittest discover -s tests

# Test de un archivo concreto
python -m unittest tests/test_ai_selector.py

# Pipeline manual con URL individual (sin subir)
python main.py --url "https://youtube.com/..." --mode subs

# Pipeline manual + subida a YouTube
python main.py --url "https://youtube.com/..." --mode subs --upload --publish-all

# Modo autónomo (escanea canales + selección IA + Co-Pilot)
python main.py --auto

# Bot Telegram en primer plano (logs directos en terminal)
python main.py --telegram

# Radar viral (imprime leaderboard sin procesar nada)
python main.py --radar

# Limpiar temp/ y forzar límites de disco
python main.py --clean

# Panel de estado (temp/, output/, cuotas diarias)
python main.py --status
```

## Arquitectura del pipeline

El flujo completo de un vídeo pasa por estas etapas en `src/pipeline.py:process_single_video`:

```
1. Validación GTA 6 exclusiva   → src/channels.py:is_strictly_gta6
2. Descarga 1080p               → src/downloader.py  (yt-dlp, segmento heatmap)
3. Traducción / subtítulos       → src/translator.py  (Gemini 2.5 Flash)
4. Generación de metadatos       → src/translator.py:generate_video_metadata
5. Renderizado FFmpeg            → src/video_editor.py:render_final_video
     ├── Formato D (Pro-Cinema 83.3%) o C (4:5) según archetype
     ├── Subtítulos Karaoke Glow (Pillow)
     └── h264_videotoolbox  SIEMPRE (nunca libx264)
6. Miniatura                     → src/thumbnail_generator.py
7. Co-Pilot gate                 → src/copilot.py  (Telegram approve/reject)
8. Subida multiplataforma        → src/uploader.py (YouTube) + src/social_publisher.py (TikTok/Instagram)
9. Limpieza temp/                → src/cleaner.py
```

**Modo autónomo** (`--auto`): `src/channels.py:fetch_channel_candidates` → `src/ai_selector.py:select_best_candidate_ai` → loop `process_single_video`.

**Bot Telegram** (`--telegram`): `src/telegram_bot.py:start_telegram_bot_daemon` gestiona comandos, inline buttons y el flujo Co-Pilot completo vía `src/copilot.py`.

## Módulos clave de `src/`

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Fuente única de rutas, vars de entorno y `is_quant_busy()` |
| `channels.py` | Scraping de candidatos, `is_strictly_gta6`, dedup, `mark_video_processed` |
| `ai_selector.py` | Selección editorial con Gemini (scoring velocity-first) |
| `viral_discovery.py` | Radar viral — queries ytsearch15, scoring 0-100, dedup cross-source |
| `downloader.py` | yt-dlp, segmentación por heatmap, prefer 1080p avc1 |
| `translator.py` | SRT translate + generate_video_metadata vía Gemini |
| `video_editor.py` | FFmpeg render, formatos D/C/SPLIT/FIT, karaoke glow subtitles |
| `copilot.py` | Estado pendiente, approve/reject, auto-expiración |
| `social_publisher.py` | TikTok (Playwright) + Instagram (instagrapi) publish |
| `performance_tracker.py` | Registra vídeos publicados, actualiza métricas 23h después |
| `learning_engine.py` | Ciclo de aprendizaje; inyecta top/bottom performers en prompts |
| `traffic_sentinel.py` | YouTube Suggest + Google News para keywords en tiempo real |

## Infraestructura y despliegue

- **Host producción:** MacBook Pro Intel Haswell, macOS Big Sur — `100.108.212.124` (Tailscale)
- **Convive con GaTDSEQ:** nice 15, FFmpeg máx. 2 hilos; reducir a 1 si `is_quant_busy()` es True
- **Watchdog:** cron `*/5 * * * *` en el Mac remoto — resucita `main.py --telegram` si cae

```bash
# Sincronizar al Mac remoto
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='.env' \
  ./ gabrieltrujillovallejo@100.108.212.124:~/GTAVIHub/

# Reiniciar bot Telegram
ssh gabrieltrujillovallejo@100.108.212.124 \
  "pkill -f 'main.py --telegram' ; sleep 2 ; \
   cd ~/GTAVIHub && nohup python -u main.py --telegram >> logs/telegram.log 2>&1 &"

# Verificar salud post-despliegue
ssh gabrieltrujillovallejo@100.108.212.124 "tail -20 ~/GTAVIHub/logs/telegram.log"
```

## Protocolo antes de cada commit

1. `python -m unittest discover -s tests` — 100% verde
2. `ls temp/` — sin `.mp4` huérfanos
3. `git status` — `.env`, `token.json`, `client_secrets.json`, `data/processed.json`, `data/copilot_state.json` NO deben aparecer

## Macro "auditoria"

Si el usuario escribe **"auditoria"**, ejecutar secuencialmente:
1. Revisar logs en Mac remoto (`~/GTAVIHub/logs/`)
2. Verificar `temp/` y `output/` (limpiar si hay `.mp4` huérfanos)
3. Comprobar que el watchdog cron esté activo (`crontab -l`)
4. Reportar estado del proceso `main.py --telegram`

## Restricciones críticas

- **Jamás** `libx264` — siempre `h264_videotoolbox` en Mac
- `data/processed.json` y `data/copilot_state.json` NUNCA al repo
- Máx. 2-3 vídeos/día por plataforma con jitter 10-15 min
- Co-Pilot: aprobación táctil en Telegram obligatoria antes de publicar (bypass solo con `--no-copilot`)
- Exploración de código: usar `codegraph_explore` ANTES de grep/Read (`.codegraph/` indexado)
