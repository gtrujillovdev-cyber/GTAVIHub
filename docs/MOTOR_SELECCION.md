# Motor de Selección de Vídeos — Directrices y Arquitectura

## 1. Visión General

El motor de selección decide qué clip de GTA 6 procesar y publicar en cada ciclo.
Combina scraping multi-fuente, scoring algorítmico y una capa de IA (Gemini Flash)
para elegir el contenido con mayor potencial viral en el momento exacto.

## 2. Flujo de Selección

```
fetch_channel_candidates()  ──┐
                               ├──► _merge_candidate()  ──► AI Selector (Gemini)  ──► pipeline.py
scan_viral_radar()         ──┘     (deduplicación +           (pool de 15)
                                    cross-source bonus)
```

### 2.1 Fuentes de candidatos

| Fuente | Módulo | Señal primaria |
|--------|--------|----------------|
| Canales monitorizados | `src/channels.py` → `fetch_channel_candidates` | Velocidad (vistas/día) |
| Búsquedas virales | `src/viral_discovery.py` → `scan_viral_radar` | Engagement + keywords |

### 2.2 Deduplicación y cross-source bonus

Cuando el mismo vídeo aparece en varias fuentes o queries, `_merge_candidate()` aplica un **bonus de +5 puntos** por cada fuente adicional (tope: 100 pts). El campo `source_count` registra cuántas fuentes lo detectaron simultáneamente — es una señal de momento viral.

## 3. Algoritmo de Scoring (`calculate_virality_score`)

**Versión 2 — Velocity-first (oct 2026)**

| Componente | Peso | Lógica |
|-----------|------|--------|
| Velocity Score (vistas/día) | 0–30 pts | **Eje primario.** > 50k vpd = 30pts, > 10k = 20pts, > 2k = 12pts |
| Views Absolutas | 0–25 pts | > 1M = 25pts; escala logarítmica |
| Format Score (duración) | 0–20 pts | 18–28s = 20pts (sweet spot Shorts) |
| Keyword Score | 0–15 pts | Coincidencias en `VIRAL_KEYWORDS` |
| Engagement Rate (likes/vistas) | 0–10 pts | > 0.04 = 10pts; > 0.02 = 6pts |
| Creator/Pop Bonus | 0–10 pts | Creador conocido, cultural pop |
| Freshness Penalty | −5 pts | Si el vídeo tiene > 14 días |

**Nota técnica:** La velocidad es el eje primario porque el algoritmo de YouTube distribuye activamente el contenido en ascenso, no el que ya acumuló vistas históricamente.

### 3.1 Filtro de palabras excluidas

- `EXCLUDED_KEYWORDS`: lista ampliada de términos prohibidos (clickbait, off-topic).
- `_EXCLUDED_WHOLE_WORDS = {"mod", "mods", "fake", "loop", "cgi"}`: verificación por límite de palabra (`\b`) para evitar falsos positivos como "modo" o "modelo".

## 4. Filtro de Exclusividad GTA 6 (`is_strictly_gta6`)

4 capas de validación antes de que cualquier candidato entre al pipeline:

1. Presencia de keyword GTA 6 (variantes: "gta vi", "gta6", "grand theft auto 6").
2. Ausencia de términos off-topic con regex de límite de palabra.
3. Exclusión de expresiones compuestas (ej. `r"\b(?:3d|blender|cgi)\s*render\b"`).
4. Verificación final en `process_single_video` como fail-safe de defensa en profundidad.

## 5. Selector con IA (`select_best_candidate_ai`)

- **Pool:** 15 candidatos pre-filtrados (subida de 10 → 15 en oct 2026).
- **Modelo:** Gemini Flash (`GEMINI_MODEL` en `config.py`).
- **Señales clave expuestas a la IA:** `velocity_vpd`, `source_count`, `engagement_rate`, `days_old`, `base_score`.
- **Criterios editoriales:** velocidad viral, multi-fuente, engagement, cultura pop, anti-clickbait.
- **Fallback heurístico:** si Gemini falla, ordena por `score` descendente (o por velocidad en `launch_mode`).

## 6. Playbook de Optimización Continua (`data/viral_playbook.json`)

El Learning Engine actualiza periódicamente el playbook con:
- Duración óptima detectada (actualmente 18–28s).
- Plantillas de títulos con mayor CTR.
- Clichés prohibidos (detectados en nuestro canal con bajo rendimiento).
- Ganchos de 0–2.5s de mayor retención.

El playbook se inyecta automáticamente en el prompt del selector IA y en el generador de metadatos.

## 7. Bucle de Feedback Post-Publicación (`src/performance_tracker.py`)

1. `record_published_video()` — registra el vídeo en `data/performance_records.json` justo tras publicar.
2. `fetch_pending_metrics()` — 23–24h después, obtiene views/likes reales vía yt-dlp.
3. `get_performance_context_for_playbook()` — genera un bloque top/bottom performers inyectable en el prompt del Learning Engine para que el ciclo de aprendizaje use datos reales, no solo benchmarks de competidores.

## 8. Parámetros Clave de Configuración

| Parámetro | Valor actual | Archivo |
|-----------|-------------|---------|
| `SHORT_MIN_DURATION` | 10s | `src/config.py` |
| `SHORT_MAX_DURATION` | 52s | `src/config.py` |
| `SHORT_TARGET_DURATION` | 24s | `src/config.py` |
| `min_score` en `scan_viral_radar` | 60 pts | `src/viral_discovery.py` |
| Pool AI Selector | 15 candidatos | `src/ai_selector.py` |

## 9. Protocolo de Mantenimiento

- **Añadir nueva fuente:** editar `config/channels.json` o usar `/addchannel` en Telegram.
- **Ajustar pesos de scoring:** modificar `calculate_virality_score` en `src/viral_discovery.py`.
- **Forzar ciclo de aprendizaje:** `/aprender` en el bot Telegram o `python main.py --learn`.
- **Auditar candidatos descartados:** activar log verbose con `PYTHONUNBUFFERED=1` y revisar líneas `[Filtro GTA 6]`.
