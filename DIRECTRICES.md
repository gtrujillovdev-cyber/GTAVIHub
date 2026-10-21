# 📋 Directrices Operativas, Formato Visual y Calidad (GTA VI Hub Spain)

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

## 📐 Estándar Visual y Editorial Definitivo (YouTube Shorts 9:16)

1. **Encuadre Maximizado con Zoom & Crop (83.3% del Alto):**
   * El vídeo de origen (16:9) se escala a **1080x1600 px**, cortando los laterales proporcionales para centrar la cara del streamer o la acción principal del juego.
   * Llena el **83.3%** del lienzo vertical (zona activa desde `y = 160` hasta `y = 1760`).
   * Las franjas de desenfoque de fondo (*velvet blur* con `boxblur=25:5`) se reducen a un elegante cojín de **160 px** en la parte superior e inferior.
   * Sombras de unión suaves en `y = 160` e `y = 1760` para integrar el vídeo sobre el desenfoque sin cortes duros.
   * Filtro de enfoque cinematográfico (`unsharp=3:3:0.6:3:3:0.0`) para nitidez 4K en caras y texturas.

2. **Subtítulos Flotantes Modernos (Estilo Opus Clip / CapCut / MrBeast):**
   * **CERO Cajas ni Rótulos:** Quedan terminantemente prohibidas las pastillas oscuras, cajas fucsia/cian, pegatinas superpuestas y caracteres rotos `[]`.
   * **Tipografía:** `Avenir Next Heavy` (moderna, geométrica y con kerning perfecto).
   * **Tamaño:** `58 px` en lienzo 9:16 vertical.
   * **Partición Dinámica:** Ráfagas rápidas de **2 a 3 palabras** adaptadas al ritmo natural de la voz.
   * **Paleta de Color:** Primera palabra clave en **Amarillo Eléctrico (`#FFE500`)**, resto de palabras en **Blanco Puro (`#FFFFFF`)**.
   * **Contraste y Profundidad:** Trazo negro nítido de 3.5 px y sombra 3D suave (offset `+3, +4`).
   * **Constraints de Margen y Zona Segura:** Ancho máximo restringido a `720 px` (mínimo 180 px libres a cada borde lateral) y anclaje vertical centrado en `y = 1280` (sobre la interfaz de YouTube Shorts).

3. **Audio de Alta Fidelidad y Presencia Móvil:**
   * **Masterización Automática:** Normalización EBU R128 a nivel estándar de YouTube Shorts (`loudnorm=I=-14:LRA=7:TP=-1.5`).
   * Garantiza que la voz suene nítida, potente y sin distorsión en los altavoces de cualquier smartphone.

4. **Arranque Inmediato a 0.0s (Sin Retrasos):**
   * El vídeo y el audio comienzan en el milisegundo 0.0s sin pantallas de intro, bumpers o transiciones que demoren el gancho.

---

## 🧹 Directriz Estricta de Limpieza de Directorios y Scripts Temporales

> ⚠️ **Tolerancia CERO al Desorden:**  
> El entorno de desarrollo y producción debe permanecer **100% pulcro, modular y profesional**. Queda terminantemente prohibido dejar scripts temporales, pruebas aisladas o imágenes intermedias en la raíz del proyecto.

### Reglas Obligatorias de Limpieza:

1. **Scripts Temporales y de Prueba:**
   * **Prohibición:** No deben persistir archivos como `test_*.py`, `scratch_*.py`, `debug_*.py` o similares en el directorio del proyecto tras finalizar una prueba o verificación.
   * **Metodología de Pruebas:** Cualquier script de depuración o validación rápida debe ejecutarse mediante comandos en línea (`python3 -c "..."`) o en el directorio temporal, y ser purgado inmediatamente al concluir.
   * **Automatización:** El módulo `src/cleaner.py` (`clean_workspace_residuals()`) inspecciona periódicamente y purga de forma proactiva cualquier archivo con prefijo `test_*`, `frame_*` o `scratch_*`.

2. **Archivos Multimedia Intermedios y Cuadros de Inspección:**
   * Los fotogramas extraídos para pruebas visuales (`frame_*.jpg`, `test_*.png`) deben eliminarse inmediatamente tras su evaluación.
   * La carpeta `temp/` debe quedar en **0 bytes** al finalizar cada ejecución de `main.py`.

3. **Archivos Pesados de Salida (.mp4):**
   * Una vez que un vídeo es subido a YouTube, su archivo `.mp4` local se borra automáticamente de `output/` (a menos que se pase `--keep-local-video`). Se conservan únicamente el informe `.json` y la miniatura `.jpg`.
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
