# 📖 Guía Completa de Uso y Operación - GTA VI Hub Spain Pipeline

Bienvenido a la documentación oficial del sistema de producción autónoma de contenidos para **GTA VI Hub Spain**. Este pipeline ha sido diseñado específicamente para operar en equipos **macOS (Apple Silicon M1/M2/M3/M4 o Intel)** con aceleración por hardware (`VideoToolbox`), generando vídeos verticales de máxima retención para **YouTube Shorts, TikTok e Instagram Reels** bajo un marco estricto de **Fair Use (Uso Legítimo)** y respeto absoluto a los creadores originales.

### 🌐 Canales, Redes Sociales y Bot Oficiales:
- 🔴 **YouTube Shorts:** [GTA VI Hub Spain](https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q)
- 📸 **Instagram Reels:** [@gtavihubspain](https://www.instagram.com/gtavihubspain/)
- 🎵 **TikTok:** [@gtavihubspain](https://www.tiktok.com/@gtavihubspain)
- 🤖 **Telegram Bot:** [@gtavihub_spain_bot](https://t.me/gtavihub_spain_bot)

---

## 📑 Índice de Contenidos
1. [Arquitectura y Filosofía del Sistema](#1-arquitectura-y-filosofía-del-sistema)
2. [Instalación y Configuración Inicial](#2-instalación-y-configuración-inicial)
3. [Manual de Comandos del CLI (`run.sh`)](#3-manual-de-comandos-del-cli-runsh)
4. [El Formato Visual Viral (Hormozi / Broadcast)](#4-el-formato-visual-viral-hormozi--broadcast)
5. [Estrategia Multiplataforma y Blindaje Anti-Ban](#5-estrategia-multiplataforma-y-blindaje-anti-ban)
6. [Respeto al Creador y Políticas Anti-Strike](#6-respeto-al-creador-y-políticas-anti-strike)
7. [Monitorización en Tiempo Real y Salud del Sistema](#7-monitorización-en-tiempo-real-y-salud-del-sistema)
8. [Automatización Desatendida con `launchd` en macOS](#8-automatización-desatendida-con-launchd-en-macos)
9. [Protocolo de Limpieza Estricta y Disco](#9-protocolo-de-limpieza-estricta-y-disco)
10. [Protocolo de Coexistencia de Hardware con GaTDSEQ](#10-protocolo-de-coexistencia-de-hardware-con-gatdseq)
11. [Centro de Control Móvil Telegram y Modo Co-Pilot](#11-centro-de-control-móvil-telegram-y-modo-co-pilot)
12. [Motor de Descubrimiento Viral y Algoritmo de Engagement](#12-motor-de-descubrimiento-viral-y-algoritmo-de-engagement)
13. [Directorio de Canales y Fuentes Autorizadas](#13-directorio-de-canales-y-fuentes-autorizadas)

---

## 1. Arquitectura y Filosofía del Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       CICLO AUTÓNOMO EDITORIAL                          │
└─────────────────────────────────────────────────────────────────────────┘
   │
   ├─► 1. DETECCIÓN: Escaneo de canales en channels.json (DaniRep, IlloJuan, Mors Mutual...)
   │
   ├─► 2. DESCARGA & PROCESAMIENTO: Extracción de vídeo 1080p y subtítulos nativos (.srt)
   │
   ├─► 3. TRADUCCIÓN / ADAPTACIÓN: Gemini 2.5 Flash con fallback de seguridad local
   │
   ├─► 4. TRANSFORMACIÓN VISUAL:
   │     ├─ Reencuadre 83.3% vertical (1080x1600 px) cortando laterales
   │     ├─ Fondos Velvet Blur superior e inferior (160 px)
   │     ├─ Píldora de gancho superior en cristal oscuro (0.0s a 2.5s)
   │     ├─ Subtítulos Pop Karaoke palabra por palabra (+4px, halo neón)
   │     └─ Inyección automática de Emojis nativos de Apple (🗺️, 🚨, 🤯, 😂)
   │
   ├─► 5. MASTERIZACIÓN DE AUDIO: Normalización EBU R128 (-14 LUFS) sin silencios
   │
   ├─► 6. AUDITORÍA ANTI-BAN: Verificación de créditos, enlace original y Fair Use
   │
   └─► 7. DISTRIBUCIÓN ESCALONADA: Publicación en YouTube, TikTok y Reels (+12 min jitter)
```

---

## 2. Instalación y Configuración Inicial

### Requisitos Previos:
- macOS con procesador **Apple Silicon (M1/M2/M3/M4) o Intel x86_64** (macOS 11 Big Sur o posterior).
- Python 3.11 o superior.
- FFmpeg con soporte `h264_videotoolbox` (`brew install ffmpeg` o binario estático).

### Paso 1: Clonar e Instalar Dependencias
```bash
git clone https://github.com/gtrujillovdev-cyber/GTAVIHub.git
cd GTAVIHub
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Paso 2: Configurar Variables de Entorno (`.env`)
Crea un archivo `.env` en la raíz copiando `.env.example`:
```env
GEMINI_API_KEY=tu_clave_de_gemini
YOUTUBE_PRIVACY_STATUS=private
MAX_VIDEOS_PER_RUN=2
TELEGRAM_BOT_TOKEN=8779197930:AAG3...
TELEGRAM_CHAT_ID=1097154358
```

### Paso 3: Autenticación con YouTube
Para conectar tu canal de YouTube de forma oficial mediante OAuth2:
```bash
./run.sh auth
```
Se abrirá el navegador para autorizar la aplicación de Google Cloud y se generará el archivo seguro `token.json` (protegido por `.gitignore`).

### Paso 4: Iniciar Sesión en TikTok e Instagram (Perfil Persistente)
Para vincular tus cuentas de TikTok e Instagram guardando las cookies locales de forma permanente:
```bash
./run.sh login-social
```
Se abrirá Chromium con tus pestañas listas; tras iniciar sesión, presiona `ENTER` en la terminal para almacenar la sesión de forma segura.

### Paso 5: Configurar Bot de Control Remoto de Telegram (24/7)
Para recibir las notificaciones push en tu móvil y controlar el Mac remotamente:
1. Habla con `@BotFather` para obtener tu `TELEGRAM_BOT_TOKEN`.
2. Habla con `@userinfobot` para obtener tu Chat ID numérico (`TELEGRAM_CHAT_ID`).
3. Añade ambos campos a tu `.env`.
4. El bot responde de forma segura **exclusivamente a tu Chat ID**:
   - `/status` — Dashboard en vivo, almacenamiento y cuotas.
   - `/run` — Forzar escaneo y publicación inmediata.
   - `/audit` — Auditoría de políticas de copyright y anti-ban.
   - `/clean` — Purga estricta de residuos temporales a 0 bytes.
   - `/preview` — Ver el último clip renderizado con su miniatura.
5. Inicia el bot con `./run.sh telegram` o actívalo como servicio desatendido `launchd`.

---

## 3. Manual de Comandos del CLI (`run.sh`)

El ejecutable `./run.sh` es el punto de entrada unificado:

| Comando | Descripción |
| :--- | :--- |
| `./run.sh` | Ejecuta el escaneo autónomo estándar de canales (`--auto`). |
| `./run.sh telegram` | Inicia el **Bot de Telegram** para control remoto y alertas al móvil. |
| `./run.sh status` | Muestra el **panel de control en tiempo real** (disco, cuotas, sesiones y vídeos de hoy). |
| `./run.sh audit` | Ejecuta la **auditoría de políticas y respeto al autor** (YouTube, TikTok y Meta). |
| `./run.sh --url "<ENLACE>"` | Procesa un vídeo individual de YouTube o Short. |
| `./run.sh --url "<ENLACE>" --preview` | Procesa el vídeo y lo abre inmediatamente en **QuickTime Player** para inspección visual. |
| `./run.sh --url "<ENLACE>" --publish-all --dry-run` | Simula la publicación en **YouTube, TikTok e Instagram** verificando las reglas anti-ban sin alterar cuentas. |
| `./run.sh login-social` | Abre Chromium para iniciar sesión y guardar las cookies permanentes de **TikTok e Instagram**. |
| `./run.sh --clean` | Purga forzosamente todos los residuos temporales de `temp/` y verifica límites de disco. |

---

## 4. El Formato Visual Viral (Hormozi / Broadcast)

El motor visual integrado en [`src/video_editor.py`](file:///Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/GTA6Channel/src/video_editor.py) aplica automáticamente los estándares de retención más altos de la industria móvil:

1. **Encuadre Maximizado al 83.3% (`1080x1600 px`):**
   - El contenido 16:9 se amplía cortando bandas laterales para centrar la cara del streamer o la acción principal del juego.
   - Franjas de fondo con desenfoque aterciopelado (*velvet blur*) de solo 160 px arriba y abajo, con sombras cinemáticas de profundidad en las uniones.
2. **Subtítulos Pop Karaoke Dinámicos:**
   - La frase completa permanece fija horizontalmente en `y=1280` (zona segura sobre los botones de la app móvil).
   - La palabra que está siendo pronunciada **aumenta de escala dinámicamente (`+4px`)**, iluminándose con un resplandor dorado o rosa neón.
   - Cero cajas oscuras toscas ni marcos fucsia.
3. **Emojis Nativos de Apple Contextuales:**
   - Si la palabra activa coincide con un evento clave, flota sobre ella un emoji nítido de alta definición:
     - *Mapa* ➔ 🗺️ | *Filtración / Leaks* ➔ 🚨 | *Loco / Flipas* ➔ 🤯 | *Broma / Risa* ➔ 😂 | *Dinero* ➔ 💰 | *Coche* ➔ 🏎️ | *Policía* ➔ 🚓 | *Fuego / Brutal* ➔ 🔥
4. **Píldora Flotante de Gancho Superior (0.0s a 2.5s):**
   - Cápsula translúcida en cristal oscuro (`y=85`) que plantea la incógnita inicial y se desvanece a los 2.5 segundos para no estorbar el contenido.
5. **Ducking Dinámico de Audio Inteligente (`sidechaincompress`):**
   - El audio del juego o vídeo original se atenúa de forma reactiva al 18% únicamente mientras la voz doblada habla, recuperando automáticamente el 100% de fuerza sonora en silencios, efectos y disparos.
6. **Detector de Picos Virales en Directos Largos (YouTube Heatmap):**
   - En vídeos largos (>85s), analiza los datos de *most replayed* para recortar la ventana de 45-55s de mayor retención de audiencia, resincronizando automáticamente los subtítulos al fragmento recortado.
7. **Audio Masterizado Móvil (-14 LUFS):**
   - Volumen potente y equilibrado bajo la norma EBU R128. Cero pantallas de espera o intros lentas: el contenido arranca en el milisegundo 0.0s.

---

## 5. Estrategia Multiplataforma y Blindaje Anti-Ban

Para publicar en las 3 plataformas principales sin caer en bloqueos algorítmicos:

| Red Social | Mecanismo Técnico | Huella Digital & Anti-Ban |
| :--- | :--- | :--- |
| **YouTube Shorts** | API v3 Oficial OAuth2 / YouTube Studio | Autenticación formal con `token.json`. Subida en `private` o `unlisted` para revisión inicial. |
| **TikTok** | **Playwright con perfil persistente en macOS** | Navegación local hacia `tiktok.com/creator-center/upload`. Utiliza tu IP residencial de fibra óptica, WebGL de la GPU Apple M4 y cookies reales de sesión en `assets/.browser_profiles/`. Indetectable. |
| **Instagram Reels** | **Meta Graph API oficial** o Web Session | Publicación mediante API de Instagram Creator o automatización directa en Reels. |

### Las 3 Reglas de Oro Anti-Ban:
- ⏳ **Escalonamiento Temporal (*Staggering*):** Se publica primero en YouTube, se espera un retardo aleatorio de **10 a 16 minutos**, se sube a TikTok, y se espera otro retardo para Instagram.
- 🛑 **Límite Orgánico Diario:** Máximo estricto de **2 a 3 vídeos diarios** por plataforma.
- 🛡️ **Auditoría Previa Obligatoria:** Si la descripción no acredita al autor o no incluye el descargo de Fair Use, el sistema detiene la publicación preventivamente.

---

## 6. Respeto al Creador y Políticas Anti-Strike

> 🚨 **Principio Fundamental:**  
> Este canal divulga, traduce y analiza contenido de la comunidad. Jamás resubimos vídeos en bruto ni nos atribuimos la autoría ajena.

Cada publicación ensambla automáticamente:
1. **Atribución Clara y Enlace Directo:**
   ```
   ═══════════════════════════════════════
   📌 CRÉDITOS DEL CONTENIDO ORIGINAL:
   ═══════════════════════════════════════
   👤 Creador / Fuente Original: @NombreDelCreador
   🔗 Vídeo Original: https://youtube.com/watch?v=...
   ¡Apoya el canal original en el enlace superior!
   ```
2. **Descargo Legal de Fair Use (Art. 107 Copyright Act de 1976):**
   Aviso estatutario que fundamenta la legalidad de la transformación con fines de comentario, análisis y traducción.
3. **Revisión Periódica de Políticas (`./run.sh audit`):**
   El sistema audita cada 7 días las directrices vigentes de Google, ByteDance y Meta para adaptarse a cualquier cambio algorítmico.

---

## 7. Monitorización en Tiempo Real y Salud del Sistema

### Comprobar el Panel de Control
```bash
./run.sh status
```
Salida en consola:
```
══════════════════════════════════════════════════════════════════════
 🚀 GTA VI HUB SPAIN - MONITOR DEL PIPELINE AUTÓNOMO (macOS M4)
══════════════════════════════════════════════════════════════════════
📁 ALMACENAMIENTO Y DISCO:
  • Carpeta Temporal (temp/)   : 0.00 MB [✓ ÓPTIMO: Limpio]
  • Carpeta Salida (output/)   : 124.62 MB / 1000 MB límite preventivo

🔐 ESTADO DE CONECTIVIDAD Y SESIONES:
  • YouTube OAuth2 (token.json): [✓ Conectado / Activo]
  • Apple Silicon M4 Hardware  : [✓ VideoToolbox H.264 Acelerado por GPU]

🛡️ CUOTAS DIARIAS ORGÁNICAS (Anti-Spam / Anti-Ban):
  • YouTube Shorts : 0 / 3 vídeos subidos hoy
  • TikTok         : 0 / 3 vídeos subidos hoy
  • Instagram Reels: 0 / 3 vídeos subidos hoy

⚖️ AUDITORÍA DE POLÍTICAS Y RESPETO AL CREADOR:
  • Estado Normativo           : [✓ Al día / Compliant]
  • Frecuencia de Repaso       : Cada 7 días (ejecutar ./run.sh audit)
```

### Notificaciones Nativas en macOS
Cada vez que el sistema finaliza un vídeo en segundo plano, tu Mac emitirá un aviso nativo del sistema con el título del clip y el creador acreditado.

---

## 8. Automatización Desatendida con `launchd` en macOS

Para que el sistema funcione de forma 100% autónoma como un servidor 24/7 en tu MacBook Pro (sin requerir tener terminales abiertas ni depender de tu MacBook Air):

### Los 2 Demonios Residentes:
1. **`com.gtavihub.telegrambot.plist`**:
   - Demonio interactivo 24/7 (`KeepAlive: true`).
   - Mantiene el bot de Telegram escuchando comandos remotos (`/status`, `/run`, `/audit`, `/clean`, `/preview`) y transmite las notificaciones con miniatura en tiempo real.
2. **`com.gtavihub.automation.plist`**:
   - Demonio programado para horas punta en España:
     - **14:00** (Hora punta de almuerzo).
     - **19:30** (Hora punta de tarde gaming).

### Instalación de los Servicios:
```bash
# Instalador automático en 1 comando (ajusta rutas y recarga demonios)
./deploy/launchd/install_daemons.sh

# Comprobar que ambos están registrados y activos
launchctl list | grep gtavihub
```

### Configuración Headless y Energía (`pmset`):
Para evitar que el Mac se duerma al cerrar la pantalla o estar desatendido:
```bash
sudo pmset -c disablesleep 1
pmset -g
```

### Monitorización de Logs en Tiempo Real:
```bash
# Monitorizar el bot de Telegram
tail -f logs/telegram_bot_stdout.log

# Monitorizar la automatización diaria
tail -f logs/launchd_stdout.log
```

### Desactivar los Servicios:
```bash
launchctl unload ~/Library/LaunchAgents/com.gtavihub.telegrambot.plist
launchctl unload ~/Library/LaunchAgents/com.gtavihub.automation.plist
```

---

## 9. Protocolo de Limpieza Estricta y Disco

Para evitar que el disco duro de tu Mac se llene con vídeos pesados:
1. La carpeta `temp/` se purga automáticamente a **0 bytes** al finalizar cada vídeo.
2. Los vídeos subidos a las plataformas se eliminan de `output/`, conservando únicamente su miniatura `.jpg` y su informe `.json` con enlaces.
3. Si el directorio `output/` supera **1 GB**, el auditor elimina de forma automática los clips locales más antiguos.

---

## 10. Protocolo de Coexistencia de Hardware con GaTDSEQ

Para garantizar que el motor de GTA VI Hub y los procesos de **GaTDSEQ** (cálculo cuantitativo, backtesting y optimización de flotas con Pandas/XGBoost) convivan pacíficamente en el mismo host headless sin sobrecalentar el hardware ni degradar el rendimiento:

### 1. Jerarquía de CPU (`Nice 15` / QoS Background)
- Ambos demonios (`com.gtavihub.telegrambot` y `com.gtavihub.automation`) se inician con prioridad de planificación reducida:
  ```xml
  <key>Nice</key>
  <integer>15</integer>
  <key>ProcessType</key>
  <string>Background</string>
  ```
- En macOS, los procesos con prioridad estándar (`nice 0`, como los scripts de GaTDSEQ) siempre reciben ciclos de CPU prioritarios. GTA VI Hub solo utiliza ciclos desocupados.

### 2. Prioridad de I/O Reducida en SSD (`LowPriorityIO`)
- Las lecturas/escrituras de vídeo se etiquetan como operaciones secundarias con `<key>LowPriorityIO</key><true/>`. Si GaTDSEQ está escribiendo logs, guardando modelos o leyendo datasets de mercado, el subsistema de almacenamiento de macOS atiende primero a GaTDSEQ.

### 3. Límite Dinámico de Hilos en FFmpeg (`Thread-Capping`)
- Por defecto, la codificación de vídeo se restringe a un máximo de **2 hilos** de CPU (`FFMPEG_THREADS=2`), manteniendo libres permanentemente al menos 2 núcleos lógicos del Intel Core i5.
- **Detección Automática de Carga Cuantitativa (`is_quant_busy()`):**  
  Antes de procesar un fotograma, el sistema inspecciona si hay procesos de GaTDSEQ activos (`optimize_fleet.py`, `run_backtest.py`, `xgboost_gate.py`). Si detecta un cálculo en curso, reduce de inmediato el uso de FFmpeg a **1 solo hilo** para evitar contención de caché o picos térmicos.

### 4. Aceleración Gráfica VideoToolbox
- Todo el renderizado H.264 corre sobre el chip acelerador de hardware de la GPU (`h264_videotoolbox`), evitando que la CPU del Mac sufra cargas pesadas durante la compresión.

### 5. Consumo de Memoria en Reposo (~70 MB)
- El bot en reposo consume únicamente el 0.9% de la RAM del equipo, y tras cada renderizado el recolector de basura purga todos los objetos de imagen para devolver la memoria al sistema operativo.

---

## 11. Centro de Control Móvil Telegram y Modo Co-Pilot

El bot oficial de Telegram (**@gtavihub_spain_bot**) transforma tu teléfono móvil en un centro de comando táctil integral:

### 1. Teclado Táctil Persistente (`ReplyKeyboardMarkup`)
En lugar de escribir comandos manualmente, la barra inferior de Telegram muestra permanentemente botones de acceso rápido:
- `[🚀 Forzar Escaneo]`: Dispara una búsqueda y publicación inmediata en segundo plano.
- `[📊 Dashboard]`: Muestra cuotas, almacenamiento y sesiones de redes.
- `[🎬 Último Clip]`: Envía la miniatura y datos del último vídeo generado.
- `[🖥️ Estado Host / GaTDSEQ]`: Carga de CPU, memoria RAM real, espacio en SSD, batería y quant.
- `[📈 Métricas YouTube]`: Suscriptores, visualizaciones y analíticas de subidas recientes vía API v3.
- `[⚙️ Canales]`: Panel inline interactivo para activar o pausar canales con 1 toque.
- `[🔥 Radar Viral]`: Rastrea clips emergentes de GTA 6 con máximo engagement y clasifica los mejores contenidos.
- `[🛡️ Modo Co-Pilot]`: Activa o desactiva la aprobación previa humana antes de publicar.
- `[🧹 Limpiar Temp]`: Purga cualquier residuo en `temp/` a 0 bytes.

### 2. Ingesta de Enlaces Bajo Demanda
Pega cualquier URL de **YouTube** (`/watch?v=...`, `youtu.be/...`, `/shorts/...`) o **TikTok** en el chat:
1. El bot detectará el enlace, extraerá el título y la duración.
2. Presentará una botonera interactiva:
   - `[⚡ Short Vertical Hormozi]`: Encuadre vertical 9:16 con subtítulos dinámicos Pop Bounce.
   - `[🎙️ Doblaje Neural + Subs]`: Doblaje al español neutro mediante Edge-TTS y subtítulos.
   - `[💬 Solo Subtítulos (Orig)]`: Conserva el audio original e inserta subtítulos quemados.
   - `[❌ Cancelar]`
3. Al pulsar una opción, el procesamiento arranca en un hilo secundario sin bloquear el bot.

### 3. Modo Co-Pilot (Puerta de Enlace Humana)
Para operar con total tranquilidad sin temor a publicaciones erróneas:
- Al activar Co-Pilot (`/copilot`), el pipeline renderiza el vídeo y su miniatura, pero **pausa la publicación**.
- Envía una tarjeta a Telegram con la miniatura y dos botones:
  - `[✅ Aprobar y Publicar]`: Sube inmediatamente a YouTube Shorts, TikTok e Instagram Reels.
  - `[❌ Descartar y Purgar]`: Cancela el contenido y elimina los archivos de vídeo del disco.

### 4. Gestión Dinámica de Canales
- `/channels`: Despliega los canales monitorizados con botones `[✅]` y `[❌]` para conmutar su estado en vivo.
- `/addchannel <url> [nombre]`: Añade una fuente directamente al monitoreo de `config/channels.json`.
- `/delchannel <número o nombre>`: Da de baja una fuente.

---

## 12. Motor de Descubrimiento Viral y Algoritmo de Engagement

Ubicado en `src/viral_discovery.py`, este motor rastrea dinámicamente YouTube mediante múltiples consultas simultáneas (`ytsearch`) en busca de clips sobre GTA 6 con tracción explosiva:

### 1. Algoritmo de Puntuación Multi-Factor (0 a 100 Puntos)
- **Volumen de Vistas (0 - 40 pts):** Escala logarítmica: $\ge 500\text{K}$ (40 pts), $\ge 100\text{K}$ (30 pts), $\ge 20\text{K}$ (20 pts), $\ge 5\text{K}$ (15 pts).
- **Retención y Formato (0 - 30 pts):** Otorga la puntuación máxima a clips verticales de corta duración ($10\text{s} \le \text{duración} \le 65\text{s}$).
- **Densidad de Palabras Clave Virales (0 - 20 pts):** Analiza la presencia de términos detonantes: `trailer 2`, `filtración`, `mapa`, `vice city`, `lucia`, `jason`, `leak`, `gameplay`, `fecha`, `exclusiva`.
- **Bonificación de Impulso (+10 pts):** Detección de etiquetas `#shorts` o términos de revelación inmediata.

### 2. Censo Dinámico de Creadores Emergentes (`data/discovered_channels.json`)
- Si el radar detecta un clip con puntuación superior a 60 cuyo creador no figura en la lista de monitoreo, lo cataloga como `[NUEVO CANAL]`.
- Al pulsar `[➕ Añadir Nuevos Creadores]` en Telegram o invocar `auto_register_top_channels()`, estos canales se agregan automáticamente a la lista permanente.

### 3. Comandos de Terminal y Telegram
```bash
# Escanear el Radar Viral y mostrar el Leaderboard en terminal:
./run.sh radar

# Ingestar y publicar directamente el vídeo #1 en engagement:
./run.sh --auto-viral
```

---

## 13. Directorio de Canales y Fuentes Autorizadas

La lista de fuentes en `config/channels.json` cuenta con 22 canales de referencia:

1. **Oficiales & Análisis Técnico (Global / EN):**
   - Rockstar Games, GTA Series Videos, TGG, LegacyKillaHD, DarkViperAU, Mors Mutual, IGN, GameSpot.
2. **Streamers Top Hispanos (ES / LatAm):**
   - DaniRep, IlloJuan (LMDShow), ElXokas, Ibai Llanos, AuronPlay, Rubius Z, TheGrefg, Nexxuz HD, DjMaRiiO, Pelicanger.
3. **Prensa Especializada (ES):**
   - 3DJuegos, Vandal, Hobby Consolas, Eurogamer España.
