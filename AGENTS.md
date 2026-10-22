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

El host de producción 24/7 es un **MacBook Pro** (`gabrieltrujillovallejo@192.168.1.193`, Intel Core i5 Haswell, macOS Big Sur 11.7.11) que aloja simultáneamente el nodo de cálculo cuantitativo y backtesting **GaTDSEQ** (`~/GaTDSEQ_Worker/`).

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

## 3. 🖥️ Operación Headless 24/7 y macOS `launchd`

1. **Los 2 Demonios Residentes**:
   - `com.gtavihub.telegrambot.plist`: Daemon residente (`KeepAlive: true`, `RunAtLoad: true`) con polling continuo para control remoto y notificaciones push con miniatura.
   - `com.gtavihub.automation.plist`: Tarea programada en segundo plano para horas punta en España (**14:00** y **19:30 CET**).
2. **Prevención de Suspensión**:
   - En el host headless, mantener `sudo pmset -c disablesleep 1` activo.
3. **Salida de Logs en Tiempo Real**:
   - Pasar `-u` a Python y fijar `PYTHONUNBUFFERED=1` en los plist para garantizar que los logs se vuelquen sin demoras a `logs/`.
4. **Instalación Automatizada**:
   - Utilizar siempre `./deploy/launchd/install_daemons.sh` para actualizar o recargar servicios en el Mac.

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
2. **Atribución Transparente**:
   - Obligatorio incluir mención al autor en el primer párrafo de la descripción (`POR: @Creador`), enlace directo al vídeo original y descargo estatutario de Fair Use (Art. 107 Copyright Act).
3. **Cadencia Orgánica Anti-Spam**:
   - Máximo estricto de **2 a 3 vídeos diarios** por plataforma, espaciados con jitter aleatorio de 10-15 minutos entre redes.

---

## 6. 🔐 Seguridad y Despliegue por Terminal

1. **Gestión de Secretos**:
   - NUNCA subir a Git: `.env`, `token.json`, `client_secrets.json`, `.browser_profiles/`.
   - La transferencia hacia el MacBook Pro se realiza exclusivamente mediante `scp`.
2. **Operación Exclusiva por Terminal**:
   - Todas las configuraciones en el host remoto se realizan mediante SSH y scripts CLI automatizados.
