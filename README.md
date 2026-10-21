<p align="center">
  <img src="assets/banner.jpg" alt="GTA VI Hub Spain Banner" width="100%" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Hardware-Apple%20Silicon%20%26%20Intel-f5a623?style=for-the-badge&logo=apple&logoColor=white" />
  <img src="https://img.shields.io/badge/GPU_Codec-VideoToolbox%20H.264-00bcd4?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Telegram_Bot-@gtavihub__spain__bot-26a5e4?style=for-the-badge&logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/Pipeline-Aut%C3%B3nomo%2024%2F7-ff007f?style=for-the-badge" />
</p>

# 🎮 GTA VI Hub Spain — Autonomous Content Engine (macOS)

Pipeline de producción y distribución audiovisual 100% autónomo para **YouTube Shorts, TikTok e Instagram Reels**, optimizado para ejecutarse silenciosamente en segundo plano 24/7 en macOS (**Apple Silicon M1/M2/M3/M4 o Intel**) con aceleración por hardware nativa (`h264_videotoolbox`) y control remoto bidireccional vía **Telegram Bot**.

---

### 🌐 Canales, Redes Sociales y Bot Oficiales

| Plataforma | Canal / Bot Oficial | Identidad Visual | Estado |
| :--- | :--- | :---: | :---: |
| 🔴 **YouTube Shorts** | [**GTA VI Hub Spain**](https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q) | Avatar Neón + Portada 4K | **Conectado (OAuth2 API v3)** |
| 📸 **Instagram Reels** | [**@gtavihubspain**](https://www.instagram.com/gtavihubspain/) | Avatar Neón + Bio Oficial | **Activo y Verificado** |
| 🎵 **TikTok** | [**@gtavihubspain**](https://www.tiktok.com/@gtavihubspain) | Avatar Neón + Bio Oficial | **Activo y Verificado** |
| 🤖 **Telegram Bot** | [**@gtavihub_spain_bot**](https://t.me/gtavihub_spain_bot) | GTA VI Hub Monitor | **Activo 24/7 (Daemon launchd)** |

---

## 🏗️ Arquitectura del Sistema

```mermaid
flowchart TD
    A["📡 1. Detección Autónoma\n(channels.json: DaniRep, IlloJuan, Mors Mutual...)"] --> B["📥 2. Ingesta 1080p + Subtítulos\n(yt-dlp multi-stream)"]
    B --> C["🤖 3. Procesamiento y Traducción\n(Gemini 2.5 Flash + Fallback Local)"]
    C --> D["🎨 4. Motor Visual Broadcast\n(VideoToolbox GPU M4)"]
    
    subgraph Transformación Visual
        D1["Encuadre Maximizado 83.3% (1080x1600 px)"]
        D2["Fondos Velvet Blur (160 px sup/inf)"]
        D3["Subtítulos Hormozi Pop Bounce (+4px)"]
        D4["Píldora Translúcida de Gancho (0.0s - 2.5s)"]
        D5["Emojis Nativos Apple (🗺️, 🚨, 🤯, 😂, 💰, 🏎️)"]
        D6["Masterización Audio -14 LUFS (EBU R128)"]
    end
    D --> D1 & D2 & D3 & D4 & D5 & D6
    
    D1 & D2 & D3 & D4 & D5 & D6 --> E["⚖️ 5. Auditoría Anti-Ban y Fair Use\n(Verificación obligatoria de créditos y autor)"]
    E --> F["🚀 6. Publicación Escalonada (+12 min Jitter)"]
    
    F --> G1["🔴 YouTube Shorts (API v3)"]
    F --> G2["🎵 TikTok (Perfil Persistente)"]
    F --> G3["📸 Instagram Reels (Meta Graph / Web)"]
    
    G1 & G2 & G3 --> H["🧹 7. Limpieza Estricta\n(0 bytes en temp/, purga de mp4 local)"]
    H --> I["📱 8. Notificaciones Push Telegram + Daemon launchd"]
```

---

## ⚡ Estándares Broadcast y Retención Móvil

1. **Reencuadre Cinematográfico al 83.3% (`1080x1600 px`):**
   * El clip horizontal 16:9 se amplía recortando laterales para centrar al streamer o la jugabilidad.
   * Franjas superior e inferior con desenfoque aterciopelado (*velvet blur*) de solo 160 px, integradas con sombras de profundidad multinivel.
2. **Subtítulos Dinámicos Alex Hormozi (Pop Bounce):**
   * La palabra activa **aumenta de escala dinámicamente (`+4px`)**, iluminándose en amarillo eléctrico o rosa neón con halo de lectura.
   * Filtro de *rolling buffer* para evitar solapamientos y anclaje en `y=1280` (zona segura sobre los botones de TikTok/Reels).
3. **Audio Ducking Dinámico Inteligente (`sidechaincompress`):**
   * El sonido original del juego se comprime dinámicamente a ~18% solo mientras el locutor habla, recuperando automáticamente el 100% de fuerza sonora en silencios, efectos y disparos.
   * Normalización formal EBU R128 (`-14 LUFS`) para presencia equilibrada en altavoces de smartphone.
4. **Detector de Picos Virales en Directos Largos (*Heatmap Slicer*):**
   * Analiza el mapa de calor de YouTube (*most replayed*) de vídeos largos (>85s) para recortar automáticamente la ventana de 45-55 segundos de máxima retención, resincronizando los subtítulos.
5. **Control Remoto y Notificaciones Push vía Telegram (`src/telegram_bot.py`):**
   * Envía la miniatura renderizada y los enlaces de publicación directamente a tu móvil.
   * Admite comandos remotos interactivos: `/status`, `/run`, `/audit`, `/clean` y `/preview`.

---

## 🚀 Guía de Comandos Rápidos (`run.sh`)

```bash
# 1. Panel de control y monitorización en tiempo real
./run.sh status

# 2. Iniciar el bot de control remoto y notificaciones de Telegram
./run.sh telegram

# 3. Auditar cumplimiento de políticas de YouTube, TikTok y Meta
./run.sh audit

# 4. Simular publicación completa multiplataforma (Sandbox seguro)
./run.sh --url "<ENLACE_YOUTUBE>" --publish-all --dry-run

# 5. Procesar un vídeo y abrirlo inmediatamente en QuickTime Player
./run.sh --url "<ENLACE_YOUTUBE>" --preview

# 6. Ejecutar escaneo autónomo de canales (channels.json)
./run.sh --auto

# 7. Forzar purga y limpieza de residuos en disco
./run.sh --clean
```

---

## 🖥️ Operación Desatendida 24/7 en macOS (`launchd`)

Para dejar el motor funcionando de forma continua en tu **MacBook Pro** como servidor headless sin necesidad de mantener encendido tu equipo de trabajo principal:

### 1. Los 2 Demonios Residentes de Producción:
* **`com.gtavihub.telegrambot.plist`**: Demonio interactivo 24/7 (`KeepAlive: true`). Mantiene el bot de Telegram escuchando comandos remotos (`/status`, `/run`, `/audit`, `/clean`, `/preview`) y transmite notificaciones push con miniatura en tiempo real tras cada publicación.
* **`com.gtavihub.automation.plist`**: Tarea programada en segundo plano con ejecución automática diaria en las dos horas punta de España (**14:00** y **19:30 CET**).

### 2. Instalación y Puesta en Marcha:
```bash
# 1. Copiar los servicios a LaunchAgents del usuario
cp assets/com.gtavihub.telegrambot.plist ~/Library/LaunchAgents/
cp assets/com.gtavihub.automation.plist ~/Library/LaunchAgents/

# 2. Cargar y arrancar los demonios en launchd
launchctl load -w ~/Library/LaunchAgents/com.gtavihub.telegrambot.plist
launchctl load -w ~/Library/LaunchAgents/com.gtavihub.automation.plist

# 3. Verificar estado de ejecución de ambos procesos
launchctl list | grep gtavihub
```

### 3. Configuración Headless y Prevención de Suspensión (`pmset`):
Para evitar que el Mac entre en modo reposo al cerrar la tapa o estar desatendido:
```bash
# Mantener el sistema despierto en corriente alterna
sudo pmset -c disablesleep 1

# Verificar configuración activa (SleepDisabled: 1)
pmset -g
```

### 4. Monitorización de Logs en Vivo:
```bash
# Monitorizar actividad del Bot de Telegram
tail -f logs/telegram_bot_stdout.log

# Monitorizar ejecuciones automáticas programadas
tail -f logs/launchd_stdout.log
```

### 5. Detener o Desactivar Servicios:
```bash
launchctl unload ~/Library/LaunchAgents/com.gtavihub.telegrambot.plist
launchctl unload ~/Library/LaunchAgents/com.gtavihub.automation.plist
```

---

## 📚 Documentación de Referencia

* [**Guía de Uso Exhaustiva (`GUIA_DE_USO.md`)**](./GUIA_DE_USO.md): Manual paso a paso, instalación, configuración de OAuth2 y credenciales.
* [**Directrices de Calidad y Anti-Ban (`DIRECTRICES.md`)**](./DIRECTRICES.md): Protocolos de seguridad algorítmica, límites diarios y prevención de strikes.
* [**Lista de Canales Monitorizados (`channels.json`)**](./channels.json): Canales oficiales y creadores configurados.
