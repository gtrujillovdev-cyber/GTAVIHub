# 🎮 GTA VI Hub Spain — Reglas Operativas y Protocolos del Proyecto

Este documento establece las normas obligatorias de desarrollo, arquitectura, coexistencia de hardware y despliegue headless para **GTA VI Hub Spain**. Todo asistente o agente que trabaje en esta base de código debe acatar estrictamente estas pautas.

---

## 1. 🏛️ Estructura del Repositorio y Arquitectura Limpia

El proyecto sigue una estructura modular estricta. Queda terminantemente prohibido desordenar la raíz del repositorio:

* `config/`: Archivos de configuración de entrada (`channels.json`).
* `data/`: Estado persistente en tiempo de ejecución (`processed.json`, `.policy_audit.json`).
* `docs/`: Guías operativas y normativas (`GUIA_DE_USO.md`, `DIRECTRICES.md`).
* `deploy/launchd/`: Manifiestos de servicio macOS (`.plist`) y script `install_daemons.sh`.
* `scripts/`: Herramientas auxiliares y asistentes operativos (`auth_youtube.py`).
* `assets/`: Recursos gráficos oficiales del canal (`avatar.jpg`, `banner.jpg`).
* `src/`: Módulos del núcleo (Core Engine) bajo separación estricta de responsabilidades.
* `tests/`: Batería de pruebas unitarias (`test_config.py`, `test_compliance.py`, `test_sanity.py`).
* **Raíz**: Reservada exclusivamente para archivos de arranque y metadatos (`README.md`, `LICENSE`, `pyproject.toml`, `requirements.txt`, `run.sh`, `main.py`, `.env.example`, `.gitignore`, y symlinks de retrocompatibilidad).

---

## 2. 🛡️ Protocolo de Coexistencia de Hardware con GaTDSEQ (MacBook Pro)

El host de producción 24/7 es un **MacBook Pro** (`gabrieltrujillovallejo@100.108.212.124` vía Tailscale VPN, Intel Core i5 Haswell, macOS Big Sur 11.7.11) que aloja simultáneamente el nodo de cálculo cuantitativo y backtesting **GaTDSEQ** (`~/GaTDSEQ_Worker/`).

Para evitar sobrecalentamiento, estrangulamiento térmico o degradación de los modelos financieros:

1. **Prioridad Relegada de CPU (`Nice 15` / QoS Background)**:
   - Todo servicio de `launchd` o script en segundo plano debe operar con `<key>Nice</key><integer>15</integer>` y `<key>ProcessType</key><string>Background</string>`.
   - GaTDSEQ (que corre con prioridad estándar `nice 0`) siempre tiene preferencia de CPU.
2. **Prioridad Reducida de I/O en SSD (`LowPriorityIO`)**:
   - Activar siempre `<key>LowPriorityIO</key><true/>` y `<key>LowPriorityBackgroundIO</key><true/>`. Las escrituras de vídeo nunca deben bloquear los datasets de GaTDSEQ.
3. **Límite de Hilos en FFmpeg (`Thread-Capping`)**:
   - Por defecto: máximo **2 hilos** (`-threads 2`), dejando 2 hilos libres permanentemente.
   - **Modo Cortesía Activo**: Antes de renderizar, comprobar `is_quant_busy()` (`pgrep -f "optimize_fleet.py|run_backtest.py|xgboost_gate.py"`). Si GaTDSEQ está activo, reducir FFmpeg a **1 solo hilo**.
4. **Aceleración por Hardware (`h264_videotoolbox`)**:
   - Siempre codificar mediante la GPU/ASIC (`h264_videotoolbox`). Jamás usar `libx264` por software en el servidor de producción.
5. **Memoria RAM**:
   - Forzar recolección de basura con `gc.collect()` tras cada vídeo procesado para liberar buffers a GaTDSEQ.

---

## 3. 🖥️ Operación Headless 24/7, Resiliencia y Auto-Healing

1. **Watchdog y Auto-Healing Inmune a Reinicios (`deploy/launchd/watchdog.sh`)**:
   - macOS Big Sur en arranque headless sin sesión de usuario Aqua bloquea `launchctl load` de agentes de usuario.
   - La resiliencia está garantizada mediante `/usr/sbin/cron` (`*/5 * * * * ~/GTAVIHub/deploy/launchd/watchdog.sh`).
   - El watchdog verifica cada 5 minutos la salud de `main.py --telegram` y lo resucita automáticamente si cayó o tras el reinicio preventivo diario de las **04:30 CET** (`com.gatdseq.maintenance`).
2. **Tareas Programadas en Horas Punta (Sweet Spot Algorítmico - 4 Vídeos/Día)**:
   - Registradas en cron con 15 minutos de anticipación (**10:45**, **14:15**, **17:45** y **20:45 CET**) para que la ingesta, renderizado con FFmpeg (limitado por GaTDSEQ), subida e indexación algorítmica culminen exactamente listos para los 4 picos de audiencia diarios (**11:00**, **14:30**, **18:00** y **21:00 CET** en España y LatAm).
   - **Rastreador Nocturno de Likes de X (`00:02 CET`)**: `scripts/x_daily_scout.py` inspecciona los 'Me gusta' de la cuenta (@GaBtc1888) en X cada medianoche, extrayendo nuevos creadores de guías, localizaciones y secretos para auto-registrarlos en `config/channels.json` y enviar reporte a Telegram.
3. **Prevención de Suspensión**:
   - En el host headless, mantener `sudo pmset -c disablesleep 1` activo.
4. **Salida de Logs en Tiempo Real**:
   - Pasar `-u` a Python y fijar `PYTHONUNBUFFERED=1` para garantizar que los logs se vuelquen sin demoras a `logs/`.

---

## 4. 🧹 Protocolo de Higiene Estricta de Disco (Regla 0 Bytes)

1. **Directorio Volátil (`temp/`)**:
   - Debe quedar en **0.00 MB / 0 bytes** tras cada ejecución de `main.py` o `./run.sh --clean`.
2. **Archivos Pesados de Vídeo**:
   - Los archivos `.mp4` en `output/` se eliminan automáticamente tras completarse la subida a las plataformas; únicamente se preservan las miniaturas `.jpg` y los resúmenes `.json`.
3. **Cero Basura en el Entorno**:
   - Jamás dejar archivos `test_*.py`, `scratch_*`, `tmp_*` o `debug_*` sueltos en la raíz.
   - Las pruebas automatizadas deben residir en `tests/` y validarse con `python -m unittest discover -s tests`.
   - Limpiar proactivamente `.DS_Store` y `__pycache__` fuera del `.venv`.

---

## 5. ⚖️ Cumplimiento Legal, Fair Use y Respeto al Creador

1. **Transformación Editorial Real (Anti-Reused Content)**:
   - Todo clip debe incluir reencuadre centrado 83.3% (`1080x1600`), subtítulos Pop Karaoke dinámicos con glow, píldora de gancho superior (0.0s a 2.5s) y audio ducking reactivo a ~18% durante la voz en off.
   - **Regla Estricta de Marca de Agua Única**: La marca de agua del canal (`@GTAVIHubExtra`) debe generarse y superponerse EXCLUSIVAMENTE a través de `render_brand_watermark_pill()` en `src/video_editor.py`. Queda terminantemente prohibido dibujar marcas de agua secundarias, textos fantasma o píldoras de marca dentro de `create_subtle_vignette()` o capas auxiliares para evitar cualquier solapamiento o efecto doble texto.
2. **Atribución Transparente**:
   - Obligatorio incluir mención al autor en el primer párrafo de la descripción (`POR: @Creador`), enlace directo al vídeo original y descargo estatutario de Fair Use (Art. 107 Copyright Act).
3. **Cadencia Orgánica Anti-Spam**:
   - Máximo estricto de **2 a 3 vídeos diarios** por plataforma, espaciados con jitter aleatorio de 10-15 minutos entre redes.

---

## 6. 🔐 Seguridad y Despliegue por Terminal

1. **Gestión de Secretos**:
   - NUNCA subir a Git: `.env`, `token.json`, `client_secrets.json`, `.browser_profiles/`, `data/processed.json`, `data/copilot_state.json`.
   - La transferencia hacia el MacBook Pro se realiza exclusivamente mediante `scp`.
2. **Operación Exclusiva por Terminal**:
   - Todas las configuraciones en el host remoto se realizan mediante SSH y scripts CLI automatizados sobre la red Tailscale (`100.108.212.124`).

---

## 7. 🤖 Centro de Control Móvil Telegram & Modo Co-Pilot

1. **Teclado Táctil Persistente (`ReplyKeyboardMarkup`)**:
   - Barra inferior con acceso rápido a: `[🚀 Forzar Escaneo]`, `[📊 Dashboard]`, `[🎬 Último Clip]`, `[🖥️ Estado Host / GaTDSEQ]`, `[📈 Métricas YouTube]`, `[⚙️ Canales]`, `[🔥 Radar Viral]`, `[🛡️ Modo Co-Pilot]`, `[🧹 Limpiar Temp]`.
2. **Ingesta Bajo Demanda de Enlaces**:
   - Al pegar cualquier enlace de YouTube o TikTok en el bot, se analizan los metadatos y se despliega un selector interactivo inline (`⚡ Short Hormozi`, `🎙️ Doblaje Neural`, `💬 Solo Subtítulos`).
3. **Modo Co-Pilot (Puerta de Enlace Humana)**:
   - Pausa la publicación de cualquier vídeo y envía una vista previa a Telegram con botones `[✅ Aprobar y Publicar]` y `[❌ Descartar y Purgar]`.
   - Los vídeos aprobados se publican en segundo plano; los descartados purgan automáticamente sus archivos pesados de disco.
4. **Telemetría y Métricas en Vivo**:
   - `/host`: CPU load, RAM real en macOS, almacenamiento libre en SSD, batería y estado del quantitative worker de GaTDSEQ.
   - `/stats`: Suscriptores, visualizaciones y analíticas de los últimos clips mediante YouTube Data API v3 (`token.json`).
5. **Gestión Dinámica de Canales**:
   - `/channels`: Lista interactiva con conmutadores táctiles para activar/desactivar las 22 fuentes sin editar código.
   - `/addchannel <url> [nombre]`: Inclusión inmediata de nuevas fuentes en `config/channels.json`.
6. **Radar Viral y Algoritmo de Engagement (`src/viral_discovery.py`)**:
   - `/radar` o botón `[🔥 Radar Viral]`: Escanea YouTube en tiempo real buscando clips emergentes con puntuación de engagement (0 a 100).
   - Ingesta de 1 toque mediante botones `[⚡ Ingestar #1]` y auto-registro de creadores emergentes con `[➕ Añadir Nuevos Creadores]`.
7. **Centinela de Tráfico e Intención de Búsqueda en Vivo (`src/traffic_sentinel.py`)**:
   - `/traffic` o `/sentinel`: Rastreo en tiempo real de intenciones de búsqueda activas mediante YouTube Suggest API y noticias de última hora en Google News (últimas 24h).
   - Genera consultas dinámicas que alimentan a `viral_discovery.py` y sincroniza las palabras clave más tecleadas por los usuarios con los metadatos y ganchos de `ai_selector.py`.

---

## 8. 📜 Directriz Permanente: Compliance Multiplataforma y Sincronización de Repositorios

1. **Adaptación Obligatoria al Compliance y ToS de Cada Red Social**:
   - Toda nueva funcionalidad, automatización, ajuste de copy o estrategia de crecimiento debe revisarse y adaptarse **por diseño** a los Términos y Condiciones (ToS) y políticas anti-spam vigentes de cada plataforma (**YouTube, TikTok, X, Instagram**).
   - **Prohibido** implementar prácticas sancionables: spam de comentarios o menciones a terceros, enlaces externos en cuerpos principales donde la red los penaliza, clientes privados móviles no oficiales en cuentas nuevas (`instagrapi`), o duplicación masiva entre cuentas.
   - Priorizar siempre **APIs oficiales** (YouTube Data API v3 para subidas, playlists y metadatos) y señales orgánicas reales.
2. **Actualización Obligatoria de Repositorios y Diario**:
   - Todo cambio verificado con tests (`python3 -m unittest discover -s tests`) debe quedar **commiteado, pusheado a `origin/main` y sincronizado en el MacBook Pro (`100.108.212.124`)**.
   - Los hitos arquitectónicos, reglas operativas y cambios relevantes de estrategia deben quedar registrados en `docs/DIARIO_DE_DESARROLLO.md` y `AGENTS.md`.

---

## 9. 🏆 Estándar Alfa Blindado: Guías, Localizaciones y Secretos (2026-11-24)

Este formato queda **blindado como directriz obligatoria** para toda la red (`YouTube Shorts`, `TikTok`, `X`):

1. **Nicho Exclusivo (100% Guías, Localizaciones, Recompensas y Secretos):**
   - `config/channels.json`, `src/traffic_sentinel.py` y `src/ai_selector.py` quedan restringidos a guías accionables (coches gratis, métodos de dinero, armas ocultas, recompensas y secretos con ubicación). Prohibido seleccionar comparativas técnicas, físicas puras o noticias genéricas.
   - Prioridad absoluta a **Shorts nativos (`12–65s`)** sobre vídeos largos 16:9 cuando existan en el pool.
2. **Estructura Visual Obligatoria (Frame 0 Gameplay → Mapa → Gameplay):**
   - **Prohibido abrir con mapa estático en Frame 0 (`0.0s`):** `ensure_non_map_first_frame()` en `src/video_editor.py` muestrea `4.0s–11.0s` y antepone un gancho de 1.5s con gameplay puro/recompensa si `0.2s` muestra mapa o menú. El mapa aparece inmediatamente después (`t >= 1.5s`), seguido de la ejecución en gameplay.
   - **Cabecera limpia en modo Caspahz (`caspahz_style=True`):** Prohibidos los titulares cambiantes superiores que distraen de la voz en off; solo gameplay limpio, logo `VI EXTRA` y subtítulos karaoke.
3. **Safe Zones Móviles (`1080x1920` / `2160x3840`):**
   - Barra superior UI libre (`y >= 175px` para logo `VI EXTRA` y overlays); subtítulos acotados a `max_w=740px` con desplazamiento izquierdo `-45px` para no colisionar con la barra lateral derecha (Like, Guardar, Compartir).
4. **Locución Directa y Segura (`0.25s` + Recompensa Primero + Vocabulario Limpio):**
   - Arranque de voz capado a **`0.25s` (`250ms`)** máximo en `src/dubber.py` (cero silencios largos iniciales).
   - **Sin preguntas retóricas:** La primera frase anuncia directamente el modelo exacto del coche, arma o recompensa, seguido de la ubicación y pasos.
   - **Sanitización anti-shadowban (`sanitize_banned_words` en `src/translator.py`):** Sustitución automática de términos sensibles (`cocaína`, `drogas`, `marihuana`, etc.) por `recompensa` / `mercancía` en títulos, descripciones, voz y subtítulos.
5. **Protección Anti-Ban de Cuentas (Máximo 2/día en Co-Pilot):**
   - `LAUNCH_AUTOPILOT=false`, tope de `2/día` en YouTube y TikTok, `TIKTOK_COOLDOWN_MINUTES=240`, `ENABLE_INSTAGRAM=false` y prohibido privatizar vídeos en ráfaga durante los primeros 14 días.

---

## 10. 🚀 Estándar Alfa v2 Blindado: Vision 2-Fases, 4K UHD, Feed 3:4 y Estrategia Multiplataforma (2026-11-26)

1. **Alineación Visual en 2 Fases (`src/guide_story_compiler.py`):**
   - Toda guía Multi-Beat descarga primero el origen en **4K UHD (`height<=3840`)**, filtra menús/tablas estáticas (`sanitize_gameplay_beats_against_menus()`, preservando siempre `map_location`) y re-narra viendo el proxy montado (`narrate_compiled_beats_from_video()`).
   - Acto 2 (`map_location`) capado a **`2.0–3.2s`** con paneo/zoom suave (`1.08x`) en Shorts; prioridad a tramos con acción dinámica (disparos, persecuciones, conducción).
2. **Safe Zone Cuadrícula `3:4` (`src/video_editor.py`, `src/thumbnail_generator.py`, `src/pipeline.py`):**
   - Marca de agua `VI EXTRA` en **`155px`**, opacidad **`68%`**, posición **`y=262px`**.
   - Portada Frame 0 (`Caspahz Cover`) de **`0.35s`** con título bajado a **`y=16.5%` (`317px`)**.
3. **Estrategia Segura por Plataforma (`MAX_DAILY_UPLOADS_*`):**
   - **YouTube Shorts (`2/día`):** API oficial v3 (`15–24s` vertical `9:16`).
   - **TikTok (`2/día`, cooldown `240`m):** Playwright temporal hasta aprobación de `GTAVIExtra` (`7711344507748419605`, `In review`) para API oficial v2.
   - **X / Twitter (`MAX_DAILY_UPLOADS_X=0` en Playwright):** generación dedicada `X Long Guide` (`45–70s`, `16:9` nativo luminoso con subs `42px`) vía `scripts/build_x_long_guide.py --send-telegram`, entregando vídeo + copy limpio en Telegram para publicación manual sin riesgo de shadowban.
4. **Tracking A/B y Limpieza Automática:**
   - Snapshots `6h/24h/48h` + etiquetas A/B en `data/performance_records.json`, scorecard semanal los domingos `20:00 CET` (`scripts/weekly_tracking_scorecard.py`) y purga diaria de multimedia en Telegram a las `03:30 CET` (`scripts/clean_telegram_media.py`).
