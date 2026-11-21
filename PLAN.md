# PLAN.md — Auditoria Profunda y Arquitectura de Mejoras (El Alfa)

**Proyecto:** GTA VI Hub Spain (`@gtavihubextra`)
**Fecha:** 2026-11-21
**Estado:** FASE 1 COMPLETADA (Solo lectura) — Esperando confirmacion para Fase 2

---

## FASE 1: AUDITORIA PROFUNDA

### 1. Mapa de Arquitectura Actual

#### 1.1 Flujo de Datos Completo (End-to-End)

```
INGESTA                  SELECCION              EDICION                METADATOS             SUBIDA                FEEDBACK
+-----------------+     +----------------+     +----------------+    +----------------+    +----------------+    +----------------+
| fetch_channel   |     | ai_selector    |     | downloader     |    | translator     |    | copilot        |    | learning_engine|
| _candidates()   |---->| select_best    |---->| download_video |    | generate_video |    | stage_pending  |    | run_self       |
| (channels.py)   |     | _candidate_ai()|     | _and_subtitles |    | _metadata()    |    | _video()       |    | _learning_cycle|
|                 |     |                |     | (downloader.py)|    | (translator.py)|    | (copilot.py)   |    | (learning      |
| viral_discovery |     | Gemini LLM +   |     |   |            |    |   |            |    |   |            |    |  _engine.py)   |
| scan_viral_radar|     | playbook       |     |   v            |    |   v            |    |   v            |    |   |            |
| (viral_disc.py) |     | heuristics     |     | video_editor   |    | ai_selector    |    | Telegram Bot   |    |   v            |
|                 |     |                |     | render_final   |    | hook/copy gen  |    | Approve/Reject |    | performance    |
| x_scout         |     | anti-mono      |     | _video()       |    |                |    |   |            |    | _tracker       |
| scan_x_timeline |     | cultura +      |     | (video_editor  |    |                |    |   v            |    | sync_live      |
| (x_scout.py)    |     | angle rotation |     |  .py)          |    |                |    | social_publisher    | _channel       |
|                 |     |                |     |   |            |    |                |    | publish_all()  |    | _metrics()     |
| traffic_sentinel|     |                |     |   v            |    |                |    | YT+TT+IG+Stagger   |                |
| scan_realtime   |     |                |     | thumbnail      |    |                |    | (social_pub.py)|    | channel_sentinel
| _traffic()      |     |                |     | _generator     |    |                |    |                |    | evaluate_and   |
| (traffic_sent.) |     |                |     | (thumbnail_gen)|    |                |    |                |    | _heal_channels |
+-----------------+     +----------------+     +----------------+    +----------------+    +----------------+    +----------------+
```

#### 1.2 Orquestador Central: `process_single_video()` (src/pipeline.py:226)

Funcion monolitica (~220 lineas) que ejecuta 7 etapas secuenciales:

| Etapa | Modulo | Descripcion |
|-------|--------|-------------|
| 0. Validacion GTA6 | `channels.is_strictly_gta6()` | Bloqueo innegociable: solo GTA 6 |
| 1. Descarga | `downloader.download_video_and_subtitles()` | yt-dlp con 4K VP9 / 1080p AVC1, heatmap slicing para largos |
| 2. Traduccion SRT | `translator.translate_srt()` / `transcribe_and_translate_audio_gemini()` | Gemini 4 Hydrogen con fallback chain |
| 3. Metadatos | `translator.generate_video_metadata()` | Titulo viral, descripcion Fair Use, tags SEO |
| 4. Render FFmpeg | `video_editor.render_final_video()` | 2160x3840 @18000k, h264_videotoolbox, Pop Karaoke, hook card |
| 5. Thumbnail | `thumbnail_generator.generate_thumbnail()` | 1080x1920 con texto impactante |
| 6. Subida/Co-Pilot | `copilot.stage_pending_video()` -> Telegram -> `social_publisher.publish_all()` | YT + TT + IG escalonado |
| 7. Limpieza | `cleaner.clean_temp_directory()` | Regla 0 bytes en temp/ |

#### 1.3 Modulos por Dominio (38 archivos .py en src/)

**Nucleo del Pipeline (criticos — NO TOCAR sin tests):**
- `config.py` — Constantes, feature flags, coexistencia GaTDSEQ
- `pipeline.py` — Orquestador central `process_single_video()`
- `downloader.py` — yt-dlp + heatmap slicing + SRT sync
- `video_editor.py` — FFmpeg render 4K, Pop Karaoke, hooks, badges
- `translator.py` — Gemini client, traduccion SRT, metadata generation
- `uploader.py` — YouTube Data API v3 upload con cooldowns
- `social_publisher.py` — Multi-plataforma (YT + TikTok Playwright + IG instagrapi)
- `copilot.py` — Co-Pilot con POSIX lock, staging, auto-approve timer

**Inteligencia y Seleccion:**
- `ai_selector.py` — Seleccion IA con Gemini + heuristicos + anti-monocultura
- `channels.py` — Gestion de canales, `is_strictly_gta6()`, filtro anti-repeticion
- `viral_discovery.py` — Radar viral con yt-dlp parallel queries
- `x_scout.py` — Scout de X/Twitter con GraphQL intercept + DOM
- `traffic_sentinel.py` — YouTube Suggest API + Google News scraping
- `learning_engine.py` — Self-learning cycle con Gemini, playbook persistence
- `performance_tracker.py` — Metricas reales 24h, clasificacion de angulos
- `channel_sentinel.py` — Deteccion de shadowban, auto-healing, quarantine

**Edicion y Assets:**
- `audio_shield.py` — Validacion de audio (volumedetect, speech density)
- `dubber.py` — Doblaje neural con Edge-TTS + ducking
- `emoji_renderer.py` — Renderizado de emojis Apple Color Emoji anti-tofu
- `thumbnail_generator.py` — Miniaturas de alto impacto
- `ocr_extractor.py` — Extraccion OCR de texto en frames

**Distribucion y Engagement:**
- `telegram_bot.py` — Centro de control movil (bot Telegram, ~1900 lineas)
- `community_manager.py` — Auto-respuestas en YT/IG con Gemini
- `adaptive_scheduler.py` — 4 ventanas de publicacion con jitter
- `knowledge_recycler.py` — Fases editoriales (pre/launch/post)
- `story_generator.py` / `story_scheduler.py` — IG Stories con ofertas

**Utilidades:**
- `cleaner.py` — Limpieza estricta temp/output
- `monitor.py` — Dashboard de estado
- `telemetry.py` — Host telemetry (CPU, RAM, disco, GaTDSEQ)
- `compliance_auditor.py` — Scorecard de politicas
- `affiliates.py` / `deal_scanner.py` — Monetizacion Amazon

#### 1.4 Archivos de Estado Persistente (data/)

| Archivo | Funcion | Critico |
|---------|---------|---------|
| `processed.json` | IDs ya procesados (anti-duplicacion) | **SI** |
| `copilot_state.json` | Estado del Co-Pilot | **SI** |
| `viral_playbook.json` | Heuristicos del learning engine | SI |
| `traffic_radar.json` | Queries dinamicas de busqueda | SI |
| `x_taste_profile.json` | Perfil de gustos desde X likes | SI |
| `curated_queue.json` | Cola curada desde X Scout | SI |
| `performance_records.json` | Metricas reales post-publicacion | SI |
| `adaptive_schedule.json` | Horarios con jitter para hoy | Medio |
| `sentinel_channel_state.json` | Estado de salud de canales | Medio |
| `channel_analytics_history.json` | Historial de metricas | Medio |
| `discovered_channels.json` | Canales descubiertos automaticamente | Bajo |
| `scheduler_slots_state.json` | Slots del scheduler adaptativo | Bajo |
| `deals_state.json` / `stories_state.json` | Estado de ofertas/stories | Bajo |

#### 1.5 Infraestructura de Deploy

- **Watchdog:** `deploy/launchd/watchdog.sh` cada 5 min via cron, heartbeat check (600s timeout)
- **Proceso principal:** `main.py --telegram` con nice 15 en background
- **Scheduler:** 4 slots cron (10:45, 14:15, 17:45, 20:45 CET)
- **FFmpeg:** Siempre `h264_videotoolbox`, 2 threads (1 si GaTDSEQ activo)

#### 1.6 Stack de Dependencias

| Dependencia | Uso | Version |
|-------------|-----|---------|
| yt-dlp | Descarga + metadata | >=2026.8.19 |
| google-genai | Gemini API (traduccion, metadatos, learning) | >=2.31.0 |
| edge-tts | Doblaje neural | >=7.3.1 |
| Pillow | Render subtitulos, thumbnails, emojis | >=13.0.0 |
| playwright | TikTok upload + X Scout | ==1.37.0 (Big Sur limit) |
| instagrapi | Instagram Reels/Stories API | >=3.1.0 |
| google-api-python-client | YouTube Data API v3 | >=2.201.0 |
| FFmpeg (sistema) | Render video, audio analysis | h264_videotoolbox |

#### 1.7 Tests Existentes (27 archivos en tests/)

Cobertura por modulo critico:
- `test_config.py`, `test_sanity.py` — Configuracion y sanity checks
- `test_exhaustive_pipeline.py`, `test_phase1_fixes.py` — Pipeline end-to-end
- `test_ai_selector.py` — Seleccion IA y anti-monocultura
- `test_compliance.py`, `test_audit_fixes.py` — Politicas y compliance
- `test_viral_discovery.py` — Scoring de viralidad
- `test_emoji_and_framing.py` — Renderizado visual
- `test_audio_shield.py` — Validacion de audio
- `test_learning_engine.py` — Motor de aprendizaje
- `test_channel_sentinel.py` — Deteccion de anomalias

---

### 2. Puntos Criticos a Proteger (NO TOCAR)

| ID | Recurso | Razon | Riesgo si se toca |
|----|---------|-------|-------------------|
| P1 | `data/processed.json` | Registro maestro anti-duplicacion | Resubida masiva de clips ya publicados |
| P2 | `data/copilot_state.json` | Estado de aprobaciones pendientes | Publicaciones duplicadas o perdidas |
| P3 | `.browser_profiles/` | Sesiones de Playwright (TikTok, IG, X) | Logout masivo, re-login manual necesario |
| P4 | `token.json` / `client_secrets.json` | OAuth2 YouTube API | Perdida de acceso a subida |
| P5 | `.env` | API keys (Gemini, Telegram, Groq) | Pipeline muerto |
| P6 | `config/channels.json` | 22+ fuentes monitorizadas activas | Perdida de ingesta |
| P7 | `src/config.py:65` | `FFMPEG_VIDEO_CODEC = "h264_videotoolbox"` | CPU 100% con libx264 en Mac |
| P8 | `deploy/launchd/watchdog.sh` + crontab | Auto-healing del bot 24/7 | Bot muere sin resurrecion |
| P9 | `src/copilot.py` POSIX lock (`fcntl.flock`) | Impide doble publicacion | Race condition -> doble subida |
| P10 | `src/pipeline.py:280` filtro `is_strictly_gta6` | Gate obligatorio pre-descarga | Contenido no-GTA6 en el canal |
| P11 | Sesion Playwright (`==1.37.0`) | Big Sur no soporta >1.37 | Crash de TikTok upload |
| P12 | `data/viral_playbook.json` | Heuristicos calibrados con datos reales | Regresion en calidad de seleccion |

---

### 3. Deteccion de Conflictos entre Mejoras de Fase 2

#### Conflicto C1: Demucs (Stem Separation) vs Tiempos de Render + Cron

**Problema:** Demucs en CPU (Intel Haswell sin CUDA) tarda ~2-5 min por clip de 30s. Sumado al render 4K FFmpeg (~1-3 min), el pipeline pasaria de ~4 min a ~7-9 min por video. Las ventanas cron de 50 min (ej. 10:45-11:35) podrian quedarse cortas si hay 2+ clips en cola.

**Resolucion:** Ejecutar Demucs SOLO cuando `is_quant_busy()` retorne False (GaTDSEQ inactivo). Si GaTDSEQ esta activo, skip Demucs y usar el audio original con atenuacion FFmpeg simple (`lowpass=f=200,volume=0.3` sobre la banda de frecuencias musicales). Feature flag `ENABLE_STEM_SEPARATION=true|false` en `.env`.

#### Conflicto C2: Seamless Loop vs Sincronizacion de Subtitulos

**Problema:** El Seamless Loop ajusta el punto de corte final para terminar en tension. Si se corta a mitad de frase, el ultimo bloque de subtitulos SRT quedaria truncado o desincronizado con el audio.

**Resolucion:** El modulo de Seamless Loop debe operar DESPUES de `parse_srt_file()` y recalcular los timestamps del ultimo bloque SRT. Cortar siempre en un silencio o entre bloques SRT (nunca a mitad de palabra), usando el timing de `calculate_word_timing()` existente como guia. El corte ideal es 0.15s despues del ultimo `end` timestamp del SRT.

#### Conflicto C3: Quality Gate vs Co-Pilot Flow

**Problema:** El Quality Gate pre-subida debe ejecutarse ANTES de `stage_pending_video()`, pero el flujo actual llama a `stage_pending_video()` justo despues del render y ANTES de que el usuario apruebe en Telegram. Si el Quality Gate rechaza un video que ya fue staged, habria un archivo huerfano en `data/pending/`.

**Resolucion:** Insertar el Quality Gate como paso 5.5 en `process_single_video()`, entre el render (paso 4) y el staging Co-Pilot (paso 6). Si el video no pasa, se mueve a `/quarantine` con logs y se retorna `None` sin llegar nunca al Co-Pilot. El flujo queda: Render -> Quality Gate -> (pasa?) -> Stage Co-Pilot -> Telegram.

#### Conflicto C4: Metadata Multi-Plataforma vs Script de Subida Actual

**Problema:** Actualmente `generate_video_metadata()` genera UN set de metadatos. Las mejoras proponen payloads diferenciados por red (TikTok: hook + comment fijado; YouTube: SEO; IG: copy DM-oriented). Esto requiere que el retorno de `generate_video_metadata()` sea un dict con claves por plataforma.

**Resolucion:** Extender el dict de metadata actual (sin romper la firma) anadiendo claves opcionales: `tiktok_caption`, `tiktok_pinned_comment`, `ig_caption`, `yt_description_override`. El `social_publisher.py` ya tiene `_build_tiktok_caption()` que puede consumir estos campos. Cambio retrocompatible: si las claves no existen, se usa el copy generico actual.

#### Conflicto C5: Scoring Engine Externo (Reddit/X) vs Rate Limits

**Problema:** Anadir scraping de Reddit y monitoreo continuo de X consume requests y CPU. El host ya ejecuta yt-dlp parallel queries (viral_discovery) + X Scout (Playwright) + traffic_sentinel (YouTube Suggest + Google News). Sumar mas scrapers podria saturar la conexion o disparar bans.

**Resolucion:** Reutilizar la infraestructura existente: `x_scout.py` ya intercepta GraphQL y `traffic_sentinel.py` ya scrapea noticias. Anadir Reddit como UNA query mas en `viral_discovery.py` (via `yt-dlp` con `redditsearch:` o requests simple al JSON API publico). Frecuencia: 1 vez cada ciclo cron (cada ~4h), no polling continuo. Feature flag `ENABLE_REDDIT_SCOUT=true|false`.

#### Conflicto C6: Feedback Loop vs YouTube API Quota

**Problema:** YouTube Data API v3 tiene quota de 10,000 unidades/dia. `fetch_recent_videos()` ya consume ~100 unidades por llamada. Si el feedback loop consulta metricas cada hora para 12 videos, sumaria ~2,400 unidades/dia, dejando margen estrecho para las 4 subidas diarias (~1,600 unidades cada una).

**Resolucion:** El feedback loop usa yt-dlp como fallback (ya implementado en `fetch_own_channel_insights()`). Consultar YouTube API solo 2 veces/dia (en el ciclo de learning_engine) y usar yt-dlp para el resto. `performance_tracker.sync_live_channel_metrics()` ya tiene este patron.

---

## FASE 2: ARQUITECTURA DE MEJORAS (EL ALFA)

### Orden de Implementacion (menor a mayor riesgo)

| Prioridad | Mejora | Riesgo | Dependencias | Tiempo Est. |
|-----------|--------|--------|--------------|-------------|
| 1 | Quality Gate Pre-Subida | BAJO | Ninguna (nuevo modulo aislado) | — |
| 2 | Generador de Copy Multi-Plataforma | BAJO | Extiende translator.py + social_publisher.py | — |
| 3 | Clasificador de Series Numeradas | BAJO | Nuevo JSON state + video_editor.py | — |
| 4 | Higiene de Metadatos EXIF | MUY BAJO | Comando FFmpeg adicional post-render | — |
| 5 | Motor de Arbitraje Cross-Border (Reddit) | MEDIO | viral_discovery.py + nuevo modulo | — |
| 6 | Seamless Loop | MEDIO | downloader.py + video_editor.py | — |
| 7 | Blindaje Audio (Stem Separation) | ALTO | Demucs install + pipeline.py | — |
| 8 | Bucle de Feedback Autonomo | MEDIO | learning_engine.py + performance_tracker.py | — |

---

### Mejora 1: Quality Gate Pre-Subida (`src/quality_gate.py`)

**Objetivo:** Filtro obligatorio "anti-mierda" entre render y subida.

**Diseno:**
```python
# src/quality_gate.py

def run_quality_gate(
    video_path: Path,
    metadata: Dict,
    candidate_score: int = 0,
    source_title: str = "",
    dry_run: bool = False
) -> Tuple[bool, str, Dict]:
    """
    Retorna (approved: bool, reason: str, diagnostics: dict).
    Si approved=False, el video se mueve a quarantine/.
    """
```

**Validacion Tecnica (FFprobe/Python):**
- Resolucion: exactamente 9:16 (tolerancia +-2px)
- Duracion: entre SHORT_MIN_DURATION y SHORT_MAX_DURATION (config.py)
- Frames negros: scan de primeros y ultimos 5 frames (< 15 luma = negro)
- Audio: reutiliza `audio_shield.validate_audio_and_speech_vitality()`
- Subtitulos: verifica que existen PNGs de karaoke en temp/ si mode=subs/dub
- Archivo integro: ffprobe exit code 0, duracion > 0

**Validacion de Potencial Viral (LLM Scoring):**
- Evalua hook de primeros 3s (titulo del hook card), claridad sin contexto previo, potencia del titulo
- Input: metadata + candidate_score + source_title
- Usa Gemini con prompt ligero (flash-lite, ~200 tokens)
- Umbral configurable: `MIN_VIRAL_SCORE` en .env (default: 7.0/10)
- Si Gemini falla, fallback a heuristico basado en candidate_score >= 55

**Quarantine:**
- Videos rechazados se mueven a `output/quarantine/` con un JSON de diagnostico
- Log en Telegram: "Video X rechazado por Quality Gate: [razon]"
- `quarantine/` se limpia automaticamente tras 48h por `cleaner.py`

**Integracion en pipeline.py:**
```
Paso 4 (Render) -> Paso 5 (Quality Gate) -> Paso 6 (Co-Pilot stage)
                                           |
                                           v (si falla)
                                     quarantine/ + return None
```

**Feature flag:** `ENABLE_QUALITY_GATE=true` (default: true)

---

### Mejora 2: Generador de Copy Multi-Plataforma

**Objetivo:** Payloads diferenciados por red social.

**Diseno:** Extender `generate_video_metadata()` en `translator.py` para que el prompt de Gemini genere campos adicionales:

```json
{
  "title": "...",
  "description": "...",
  "tags": [...],
  "tiktok_caption": "Hook corto <= 54 chars sentence-case",
  "tiktok_pinned_comment": "Pregunta polemica para disparar comentarios",
  "ig_caption": "Copy orientado a envios por DM (Mandaselo al que...)",
  "yt_seo_title": "Titulo optimizado con keywords exactas"
}
```

**Consumo:**
- `social_publisher._build_tiktok_caption()` ya existe: se alimenta de `tiktok_caption`
- `publish_to_youtube()` recibe `yt_seo_title` como override opcional
- IG: caption override en `publish_to_instagram_reels()`

**Riesgo:** BAJO — cambios retrocompatibles (claves nuevas opcionales)

---

### Mejora 3: Clasificador de Series Numeradas

**Objetivo:** Detectar si un clip encaja en una serie recurrente y estampar numero de episodio.

**Diseno:**
```python
# src/series_classifier.py
SERIES_STATE_FILE = DATA_DIR / "series_state.json"

SERIES_PATTERNS = {
    "detalles_enfermizos": ["detalle", "detalles", "enfermizo", "oculto"],
    "mitos_a_prueba": ["mito", "mitos", "verdad", "falso", "prueba"],
    "fisicas_locas": ["fisica", "fisicas", "motor", "ragdoll", "bug"],
    "secretos_leonida": ["secreto", "secretos", "easter egg", "hidden"],
    "armas_legendarias": ["arma", "legendaria", "oculta", "weapon"],
}

def classify_and_number(title: str, metadata: Dict) -> Optional[Dict]:
    """Retorna {"series_id": "detalles_enfermizos", "episode": 14, "stamp_text": "DETALLES ENFERMIZOS #14"}"""
```

**Integracion:**
- Se llama desde `pipeline.py` justo despues de generar metadatos (paso 3.5)
- Si detecta serie, inyecta `stamp_text` en el hook card de `render_top_hook_headline()`
- El numero de episodio se persiste en `data/series_state.json`

**Riesgo:** BAJO — nuevo modulo aislado, solo toca pipeline.py en un punto

---

### Mejora 4: Higiene de Metadatos EXIF

**Objetivo:** Limpiar metadata EXIF y aplicar micro-variaciones para evitar deteccion de duplicados cross-plataforma.

**Diseno:** Paso adicional post-render en `video_editor.py`:
```bash
ffmpeg -i input.mp4 -map_metadata -1 -c copy -movflags +faststart output_clean.mp4
```
Mas micro-variaciones:
- Crop aleatorio de 1-2px por lado (imperceptible)
- Offset de brightness +/- 0.5% por plataforma
- Variacion de bitrate: +/- 2% entre versiones YT/TT/IG

**Riesgo:** MUY BAJO — operacion de copia sin re-encode

---

### Mejora 5: Motor de Arbitraje Cross-Border

**Objetivo:** Detectar picos de traccion temprana en Reddit, X y fuentes anglosajonas.

**Diseno:**
```python
# src/cross_border_scout.py

def scan_reddit_gta6(subreddits: List[str] = ["GTA6", "GTA", "gaming"],
                     min_upvote_velocity: float = 50.0) -> List[Dict]:
    """Escanea posts recientes con velocidad de upvotes alta."""

def calculate_emotion_score(title: str, comments_sample: List[str]) -> float:
    """Puntua 'emocion pura' (bugs, fisicas, secretos) vs gameplay generico."""
```

**Integracion:**
- Se invoca desde `viral_discovery.scan_viral_radar()` como fuente adicional
- Los candidatos de Reddit se mergean con los de YouTube en el pool de `ai_selector`
- Frecuencia: 1 vez por ciclo cron (~4h)
- Reddit JSON API publico (`.json` suffix, sin auth necesaria para lectura)

**Feature flag:** `ENABLE_REDDIT_SCOUT=true`

---

### Mejora 6: Seamless Loop

**Objetivo:** Corte final en tension para fomentar re-view automatico.

**Diseno:**
- Analizar los ultimos 3s del audio buscando un punto de silencio o entre-frases
- Si hay SRT: cortar 0.15s despues del ultimo `end` timestamp del ultimo bloque completo
- Si no hay SRT (modo gameplay): cortar en un pico de accion (deteccion de cambio de escena)
- El segundo 0 del video debe tener coherencia visual con el final (mismo plano o transicion natural)

**Integracion en downloader.py:**
- Nueva funcion `find_seamless_cut_point(srt_blocks, audio_path, target_duration)`
- Se ejecuta DESPUES de `slice_srt_file()` para mantener sincronizacion

**Riesgo:** MEDIO — toca downloader.py (modulo critico), requiere tests exhaustivos

---

### Mejora 7: Blindaje Audio (Stem Separation)

**Objetivo:** Separar y atenuar musica de radio GTA 6 para evitar Content ID.

**Diseno:**
```python
# src/stem_separator.py

def separate_stems(audio_path: Path, model: str = "htdemucs_ft") -> Dict[str, Path]:
    """Separa vocals, drums, bass, other. Retorna paths a stems."""

def remix_safe_audio(stems: Dict[str, Path], music_attenuation_db: float = -18.0,
                     replacement_beat_path: Optional[Path] = None) -> Path:
    """Mezcla stems preservando vocals+sfx, atenuando musica, inyectando beat libre."""
```

**Requisitos hardware:**
- Demucs `htdemucs_ft` en CPU: ~3-5 min por clip de 30s en Intel Haswell
- RAM: ~2GB adicionales durante separacion
- Solo se ejecuta si `is_quant_busy() == False`

**Integracion:**
- Nuevo paso 1.5 en pipeline.py entre descarga y traduccion
- Si `ENABLE_STEM_SEPARATION=false` o GaTDSEQ activo: fallback a filtro FFmpeg simple
  (`highpass=f=300,lowpass=f=3000,volume=0.4` para atenuar bandas musicales)

**Feature flag:** `ENABLE_STEM_SEPARATION=false` (default: desactivado hasta validacion)

**Dependencia nueva:** `pip install demucs` (~200MB de modelos)

**Riesgo:** ALTO — nueva dependencia pesada, tiempo de procesamiento significativo, toca pipeline.py

---

### Mejora 8: Bucle de Feedback Autonomo

**Objetivo:** Registrar rendimiento real y recalibrar scoring automaticamente.

**Diseno:** Extiende `performance_tracker.py` y `learning_engine.py`:

```python
# En performance_tracker.py
def detect_outliers(threshold_multiplier: float = 3.0) -> List[Dict]:
    """Identifica videos con >3x la media del canal en vistas 24h."""

def recalibrate_scoring_weights(outliers: List[Dict]) -> Dict:
    """Ajusta pesos de ai_selector basandose en patrones de outliers."""
```

**Flujo:**
1. `sync_live_channel_metrics()` obtiene vistas/likes reales (ya existe)
2. `detect_outliers()` etiqueta los que superan 3x media
3. `recalibrate_scoring_weights()` analiza que tenian en comun los outliers
4. Inyecta ajustes en `viral_playbook.json` -> siguiente ciclo de ai_selector los consume

**Frecuencia:** 1 vez/dia en el ciclo de `run_self_learning_cycle()` (ya se ejecuta via Telegram)

**Riesgo:** MEDIO — modifica pesos que afectan a toda la seleccion de contenido

---

## Plan de Pruebas

Cada mejora debe cumplir ANTES de merge:

1. **Unit tests** en `tests/test_<modulo>.py` con mocks de FFmpeg/Gemini/yt-dlp
2. **Dry-run end-to-end:** `python main.py --auto --dry-run` completa sin errores
3. **Validacion de no-regresion:** `python -m unittest discover -s tests` al 100%
4. **Verificacion temp/:** `ls temp/` vacio tras cada ejecucion
5. **Feature flag OFF:** Verificar que el pipeline funciona identico con la mejora desactivada

---

## Matriz de Conflictos Resueltos

| Conflicto | Mejoras Involucradas | Resolucion | Verificacion |
|-----------|---------------------|------------|-------------|
| C1 | Demucs vs Cron/CPU | Feature flag + is_quant_busy() guard + fallback FFmpeg | Test con GaTDSEQ mock activo |
| C2 | Seamless Loop vs SRT | Cortar entre bloques SRT, no a mitad de palabra | Test con SRT de 10 bloques |
| C3 | Quality Gate vs Co-Pilot | QG antes de stage_pending, return None si falla | Test pipeline con video rechazado |
| C4 | Multi-Platform Copy vs Metadata | Claves opcionales retrocompatibles en dict | Test metadata sin claves nuevas |
| C5 | Reddit Scout vs Rate Limits | 1 request/4h via JSON API, merge en pool existente | Test con mock de Reddit response |
| C6 | Feedback Loop vs YT API Quota | yt-dlp fallback, API solo 2 veces/dia | Test quota tracking |

---

**ACCION REQUERIDA:** Revisa este plan y confirma explicitamente antes de que se edite cualquier archivo del repositorio. Puedes aprobar todo, seleccionar mejoras individuales o solicitar cambios en la arquitectura propuesta.
