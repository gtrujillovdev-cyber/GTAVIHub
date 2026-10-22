# 📋 Directrices Operativas, Formato Visual y Calidad (GTA VI Hub Spain)

### 🌐 Canales, Redes y Bot Oficiales:
- **YouTube:** [GTA VI Hub Spain](https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q)
- **Instagram:** [@gtavihubspain](https://www.instagram.com/gtavihubspain/)
- **TikTok:** [@gtavihubspain](https://www.tiktok.com/@gtavihubspain)
- **Telegram Bot:** [@gtavihub_spain_bot](https://t.me/gtavihub_spain_bot)

> **Regla de Oro del Proyecto:**  
> Cada iteración técnica o visual se rige bajo el protocolo estricto:  
> **Generación Local ➡️ Comprobación (QuickTime / Sandbox Web) ➡️ Borrado de Residuos ➡️ Auditoría ➡️ Consolidación en Git.**

---

## 🔄 El Ciclo de Iteración Obligatorio

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│  1. Creación   │ ──> │   2. Sandbox   │ ──> │ 3. Comprobación│
│  y Rotulado    │     │   (0 Cuota API)│     │(QuickTime/Móvil│
└────────────────┘     └────────────────┘     └────────────────┘
                                                        │
                                                        ▼
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│  6. Git Commit │ <── │ 5. Auditoría e │ <── │  4. Limpieza   │
│  y Producción  │     │ Infraestructura│     │ Total Residuos │
└────────────────┘     └────────────────┘     └────────────────┘
```

---

## ⚖️ Directrices de Seguridad de Cuenta y Cumplimiento Legal (Anti-Ban / Anti-Strike)

> 🚨 **Prioridad Absoluta:**  
> La supervivencia y reputación de las cuentas en **YouTube, TikTok e Instagram** prima sobre cualquier automatización. Se aplican 5 reglas estrictas e innegociables para evitar *shadowbans*, huelgas de derechos (*copyright strikes*) o suspensión de canales.

### 1. Transformación Editorial Sustancial (Anti-Contenido Reutilizado):
* **Prohibición Total de Resubida en Bruto:** Jamás se publicará un vídeo descargado tal cual.
* Para cumplir con la doctrina de **Fair Use (Uso Legítimo)** y las políticas de monetización y originalidad de YouTube, TikTok y Meta, todo clip debe incorporar:
  * **Reencuadre Cinematográfico:** Escalado al 83.3% vertical (`1080x1600 px`) con recorte lateral centrado y fondo *velvet blur*.
  * **Aporte Crítico / Informativo:** Subtítulos cinemáticos dinámicos quemados en imagen, ganchos textuales y títulos analíticos.
  * **Tratamiento Audiovisual:** Filtro de nitidez 4K (`unsharp`), corrección de contraste/color y masterización de audio.

### 2. Blindaje de Música y Derechos de Autor (Anti-Copyright Strike):
* Cuando el contenido contenga canciones comerciales con copyright (ej. temas oficiales de Rockstar Games / UMG como Tom Petty):
  * **Atenuación / Ducking:** El audio de fondo debe atenuarse al 15-20% si se dobla con voz en off, o ecualizarse para que no dispare *Content ID*.
  * **Metadatos Legales Obligatorios:** Inclusión automática en la descripción de los créditos del tema, creadores originales y el descargo legal formal:
    > *"Aviso de Uso Legítimo (Fair Use): Este vídeo contiene material transformado con fines de análisis, crítica y divulgación bajo el Artículo 107 de la Copyright Act de 1976."*

### 3. Atribución Transparente y Cero Placeholders:
* Enlaces reales inyectados automáticamente hacia el vídeo original y mención expresa del creador de contenido o streamer de origen (`POR: @Creador`).

### 4. Cadencia de Publicación Orgánica (Anti-Spam):
* **Límite Diario:** Máximo de **2 a 3 vídeos diarios** por plataforma. Publicar ráfagas masivas (10-20 vídeos al día) activa los filtros de *spam* y congela el alcance de las cuentas (*shadowban*).
* **Escalonamiento Temporal:** Entre la publicación en YouTube, TikTok e Instagram debe existir un intervalo aleatorio de 5 a 15 minutos (nunca al mismo segundo exacto).

### 5. Aislamiento y Huella Digital Humana (Anti-Detección de Bots):
* Para TikTok e Instagram, la automatización debe utilizar perfiles persistentes de navegador con *cookies* de sesión reales y retardos aleatorios (*jitter* humano), evitando peticiones sin cabeceras que disparen *captchas*.

---

## 📐 Estándar Visual y Editorial (YouTube Shorts, TikTok y Reels 9:16)

1. **Encuadre Maximizado con Zoom & Crop (83.3% del Alto):**
   * El vídeo de origen (16:9) se escala a **1080x1600 px**, cortando los laterales proporcionales para centrar la cara del streamer o la acción principal del juego.
   * Llena el **83.3%** del lienzo vertical (zona activa desde `y = 160` hasta `y = 1760`).
   * Franjas de fondo con desenfoque aterciopelado (*velvet blur* con `boxblur=25:5`) reducidas a un cojín de **160 px** arriba y abajo.
   * Sombras de unión suaves en `y = 160` e `y = 1760` para integrar el vídeo sobre el desenfoque sin cortes duros.
   * Filtro de enfoque cinematográfico (`unsharp=3:3:0.6:3:3:0.0`) para nitidez 4K en caras y texturas.

2. **Subtítulos Flotantes con Karaoke Dinámico Anti-Solapamiento:**
   * **CERO Cajas ni Rótulos:** Quedan terminantemente prohibidas las pastillas oscuras, cajas fucsia/cian, pegatinas superpuestas y caracteres rotos `[]`.
   * **Tipografía:** `Avenir Next Heavy` (58 px).
   * **Desduplicación Estricta:** Filtro de *rolling buffer* para que las palabras nunca se repitan ni se pisen.
   * **Karaoke Palabra por Palabra:** La frase permanece fija horizontalmente mientras la palabra activa se ilumina en **Amarillo Eléctrico (`#FFE500`)** y las restantes en **Blanco Puro (`#FFFFFF`)**.
   * **Constraints de Margen y Zona Segura:** Ancho máximo restringido a `720 px` y anclaje vertical centrado en `y = 1280` (sobre los botones de la app móvil).

3. **Audio de Alta Fidelidad y Presencia Móvil:**
   * **Masterización Automática:** Normalización EBU R128 a nivel estándar móvil (`loudnorm=I=-14:LRA=7:TP=-1.5`).
   * Garantiza volumen potente y presencia clara en altavoces de smartphone.

4. **Arranque Inmediato a 0.0s (Sin Retrasos):**
   * El vídeo y el audio comienzan en el milisegundo 0.0s sin pantallas de intro, bumpers o transiciones que demoren el gancho.

---

## 🧹 Directriz Estricta de Limpieza de Directorios y Scripts Temporales

> ⚠️ **Tolerancia CERO al Desorden:**  
> El entorno de desarrollo y producción debe permanecer **100% pulcro, modular y profesional**. Queda terminantemente prohibido dejar scripts temporales, pruebas aisladas o imágenes intermedias en la raíz del proyecto.

### Reglas Obligatorias de Limpieza:

1. **Scripts Temporales y de Prueba:**
   * No deben persistir archivos como `test_*.py`, `scratch_*.py`, `debug_*.py` o similares tras una prueba.
   * Se ejecutan en memoria o en `temp/`, y son purgados de inmediato.
   * `src/cleaner.py` (`clean_workspace_residuals()`) purga proactivamente cualquier archivo temporal residual.

2. **Archivos Multimedia Intermedios y Cuadros de Inspección:**
   * Los fotogramas extraídos para pruebas (`frame_*.jpg`, `test_*.png`) se eliminan tras su evaluación.
   * La carpeta `temp/` debe quedar en **0 bytes** al finalizar cada ejecución de `main.py`.

3. **Archivos Pesados de Salida (.mp4):**
   * Una vez subido el vídeo a las plataformas, su archivo `.mp4` pesado local se borra automáticamente de `output/`. Se conservan únicamente el informe `.json` y la miniatura `.jpg`.
   * Límite preventivo de almacenamiento en disco: **1 GB máximo** en la carpeta `output/`.

---

## 🛡️ Protocolo Sandbox y Ahorro de Cuota API de YouTube

1. **Pruebas Locales Instantáneas (`--preview`):**
   * Cada renderizado se comprueba localmente abriendo el vídeo en QuickTime Player (`open output/SHORT_...mp4`).
   * **Consumo de cuota API: 0 unidades.**
2. **Pruebas de Subida en YouTube Studio Web (0 Cuota API):**
   * Si se desea validar la visualización real dentro de YouTube o en la app móvil antes de la aprobación definitiva, la subida se efectúa vía web en YouTube Studio (mediante subagente de navegador o Chrome).
   * **Consumo de cuota API: 0 unidades.**
3. **Reserva de la API de YouTube (`--upload`):**
   * El flag `--upload` (que consume 1.600 unidades de la API de YouTube Data v3 por vídeo) queda reservado exclusivamente para la ejecución en producción desatendida.

---

## 📦 Control de Versiones y Repositorio Git

1. **Archivos Versionados:**
   * Código fuente (`src/`, `main.py`, `run.sh`, `auth_youtube.py`).
   * Activos oficiales del canal (`assets/avatar.jpg`, `assets/banner.jpg`).
   * Configuración de canales (`channels.json`).
   * Documentación y directrices (`README.md`, `DIRECTRICES.md`, `.gitignore`, `.env.example`).
2. **Archivos Excluidos Obligatoriamente (.gitignore):**
   * Secretos y tokens: `.env`, `client_secrets.json`, `token.json`.
   * Entornos virtuales: `.venv/`.
   * Directorios de trabajo: `temp/`, `output/`.
   * Archivos multimedia pesados: `*.mp4`, `*.mp3`, `*.mov`.
   * Archivos y scripts temporales: `test_*`, `frame_*`, `scratch_*`.
