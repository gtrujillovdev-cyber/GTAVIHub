# 📖 Guía Completa de Uso y Operación - GTA VI Hub Spain Pipeline

Bienvenido a la documentación oficial del sistema de producción autónoma de contenidos para **GTA VI Hub Spain**. Este pipeline ha sido diseñado específicamente para operar en equipos **macOS Apple Silicon (M1/M2/M3/M4)** con aceleración por hardware (`VideoToolbox`), generando vídeos verticales de máxima retención para **YouTube Shorts, TikTok e Instagram Reels** bajo un marco estricto de **Fair Use (Uso Legítimo)** y respeto absoluto a los creadores originales.

### 🌐 Redes Sociales Oficiales del Canal:
- 🔴 **YouTube Shorts:** [GTA VI Hub Spain](https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q)
- 📸 **Instagram Reels:** [@gtavihubspain](https://www.instagram.com/gtavihubspain/)
- 🎵 **TikTok:** [@gtavihubspain](https://www.tiktok.com/@gtavihubspain)

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
- macOS con procesador Apple Silicon (M1, M2, M3 o M4).
- Python 3.11 o superior.
- FFmpeg instalado con soporte `h264_videotoolbox` (`brew install ffmpeg`).

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

### Paso 5: Configurar Bot de Control Remoto de Telegram (Opcional)
Para recibir las notificaciones push en tu móvil y controlar el Mac por SSH:
1. Crea un bot en Telegram hablando con `@BotFather` para obtener tu `TELEGRAM_BOT_TOKEN`.
2. Obtén tu Chat ID hablando con `@userinfobot` para tu `TELEGRAM_CHAT_ID`.
3. Añade ambos campos a tu `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   TELEGRAM_CHAT_ID=987654321
   ```
4. Inicia el bot con `./run.sh telegram` o déjalo corriendo en segundo plano.

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

Para que el sistema funcione de forma 100% autónoma sin necesidad de tener abierta la ventana de la terminal:

1. El archivo de servicio ya está configurado en `assets/com.gtavihub.automation.plist`.
2. Horarios programados de publicación automática:
   - **14:00** (Hora punta de almuerzo en España).
   - **19:30** (Hora punta de tarde gaming en España).
3. Activar el servicio en tu Mac:
   ```bash
   cp assets/com.gtavihub.automation.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.gtavihub.automation.plist
   ```
4. Desactivar el servicio en cualquier momento:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.gtavihub.automation.plist
   ```

---

## 9. Protocolo de Limpieza Estricta y Disco

Para evitar que el disco duro de tu Mac se llene con vídeos pesados:
1. La carpeta `temp/` se purga automáticamente a **0 bytes** al finalizar cada vídeo.
2. Los vídeos subidos a las plataformas se eliminan de `output/`, conservando únicamente su miniatura `.jpg` y su informe `.json` con enlaces.
3. Si el directorio `output/` supera **1 GB**, el auditor elimina de forma automática los clips locales más antiguos.
