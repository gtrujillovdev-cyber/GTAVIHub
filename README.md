# 🎮 GTA6Channel - Pipeline Autónomo Ultra-Ligero para YouTube (M4 Mac)

Sistema automatizado de captación, traducción, edición y subida de contenido sobre **GTA VI** diseñado para ejecutarse silenciosamente en segundo plano en un Mac con Apple Silicon (M4), consumiendo el mínimo de recursos y memoria.

---

## ⚡ Principales Características y Ahorro de Recursos

1. **Subtítulos automáticos:** Extrae los subtítulos que YouTube ya genera en inglés con `yt-dlp` (ahorra el 100% de cómputo local de Whisper).
2. **Traducción con Gemini 2.5 Flash:** Traduce los subtítulos respetando sincronización y terminología gamer sin tocar la CPU/RAM del Mac.
3. **Aceleración por Hardware M4:** Renderizado con `ffmpeg` usando `h264_videotoolbox` nativo de Apple Silicon. Un vídeo se procesa en 10-20 segundos.
4. **Subtítulos dinámicos estilo Shorts:** Subtítulos en negrita con contorno negro en zona segura para no tapar los botones de YouTube.
5. **Doblaje opcional (`--mode dub`):** Locución en español ultra-natural mediante `edge-tts` con *audio ducking* automático (la música y efectos de fondo bajan al 15% y la voz traducida suena al 100%).
6. **Subida Automática a YouTube:** Sube el vídeo directamente a tu canal con etiquetas, categoría de Gaming y el estado de privacidad deseado (`private`, `unlisted` o `public`).
7. **Anti-Duplicados:** Registro automático en `processed.json` para no repetir vídeos.

---

## 🔐 1. Vincular tu Canal de YouTube (Solo se hace una vez)

Para que el script pueda subir vídeos a tu canal automáticamente:

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto y habilita la **YouTube Data API v3**
3. Ve a **Credenciales** -> **Crear credenciales** -> **ID de cliente de OAuth** (tipo: **Aplicación de escritorio / Desktop App**)
4. Descarga el JSON y guárdalo en la carpeta del proyecto con el nombre:
   ```bash
   client_secrets.json
   ```
5. Ejecuta el asistente de autenticación:
   ```bash
   ./run.sh auth
   ```
   *Se abrirá el navegador para seleccionar tu cuenta y canal de YouTube. Al aceptar, guardará `token.json` y el canal quedará logeado para siempre (se renueva solo vía refresh token).*

---

## 📺 2. Lista de Canales Configurados (`channels.json`)

El archivo `channels.json` ya viene precargado con los 7 canales de mayor relevancia y filtraciones de GTA VI:
- **Rockstar Games**: Tráilers y comunicados oficiales.
- **GTA Series Videos**: El canal líder mundial en desgloses fotograma a fotograma.
- **GTA 6 News / Hub**: Actualizaciones y filtraciones rápidas.
- **Mors Mutual Insurance**: Clips dinámicos ideales para Shorts.
- **LegacyKillaHD**: Noticias y opiniones de insiders.
- **Badger Goodger**: Lore y análisis de desarrollo.
- **INTER**: Comparativas gráficas y técnicas.

---

## 🚀 3. Modos de Uso

### A. Escaneo y Subida 100% Autónomo:
```bash
# Procesa vídeos nuevos de los canales y los sube a tu canal en Privado (para que tú los revises):
./run.sh --auto --upload --privacy private

# Si quieres que se publiquen directamente en Público:
./run.sh --auto --upload --privacy public
```

### B. Procesar un vídeo específico:
```bash
# Solo subtítulos dinámicos + Subida en Privado:
./run.sh --url "https://www.youtube.com/watch?v=ID_VIDEO" --mode subs --upload

# Con doblaje de voz + Subida en Privado:
./run.sh --url "https://www.youtube.com/watch?v=ID_VIDEO" --mode dub --upload

# Forzar formato vertical 9:16 Shorts con blur cinemático de fondo:
./run.sh --url "https://www.youtube.com/watch?v=ID_VIDEO" --format short --upload
```

---

## ⏰ 4. Programación en Segundo Plano (Cron en el M4)

Para que el Mac M4 trabaje solo cada 3 horas:

```bash
crontab -e
```
Añadir:
```cron
0 */3 * * * /Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/GTA6Channel/run.sh --auto --upload --privacy private >> /Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/GTA6Channel/cron.log 2>&1
```

---

## 📋 5. Directrices Operativas y Ciclo de Calidad (Metodología Oficial)

> **Documento Oficial de Referencia:** Consulta [`DIRECTRICES.md`](./DIRECTRICES.md) para el desglose exhaustivo de los protocolos técnicos.

Hasta que hallemos el formato definitivo perfecto, **siempre** procederemos bajo este ciclo iterativo:

```
[1. Creación & Rotulado] ➡️ [2. Sandbox / YouTube Studio Web (0 Cuota)] ➡️ [3. Comprobación] ➡️ [4. Borrado Definitivo] ➡️ [5. Auditoría de Infraestructura]
```

### Reglas Esenciales del Protocolo:
1. **Modo Sandbox sin Consumo de Cuota:** Durante la fase de pruebas y ajuste de diseño, **no se utiliza la API de YouTube (`--upload`)** para no consumir las 1.600 unidades por subida. Las comprobaciones se hacen directamente en local (`--preview` abre el vídeo en pantalla al instante) o subiendo vía **YouTube Studio Web** mediante el navegador automático (0 consumo de cuota API).
2. **Subtitulado con Constraints:** Margen mínimo de **160 px** a cada lado (anchura máxima 760 px en lienzo de 1080 px). Partición obligatoria en 2 líneas si supera 3 palabras. Palabra clave en Cian Neón (`#00E6FF`) y cuerpo en Amarillo Neón (`#FFE600`) con contorno de 6 px y sombra 3D.
3. **Transformación Editorial Real:** Intro bumper de 1.4s con impacto de graves (*sub-bass drop*), fondo velvet blur en Shorts y marcas de canal persistentes.
4. **Metadatos y Fair Use:** Títulos en **MAYÚSCULAS COMPLETAS** (< 55 caracteres), cero placeholders, créditos musicales explícitos y descargo bajo el Artículo 107 de la *Copyright Act* de 1976.
5. **Limpieza Estricta de Disco:** La carpeta `temp/` debe quedar siempre en **0 bytes**. El archivo `.mp4` pesado local se elimina automáticamente tras confirmar la subida para no saturar el SSD del Mac.
6. **Auditoría Continua de Infraestructura:** Evaluación en cada ciclo de los motores de descarga, subtitulado, renderizado por hardware M4, IA Gemini, subida OAuth y almacenamiento.

