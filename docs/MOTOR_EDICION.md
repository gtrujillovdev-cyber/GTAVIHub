# Motor de Edición de Vídeos — Directrices y Arquitectura

## 1. Visión General

El motor de edición transforma cada clip seleccionado en un Short viral 9:16 listo para publicar.
Aplica reencuadre, subtítulos dinámicos, gancho visual, audio ducking y codificación hardware.

## 2. Flujo de Procesamiento (`process_single_video`)

```
download_video_and_subtitles()
        │
        ├── find_viral_heatmap_segment()   ← recorte al pico de retención
        ├── snap_window_to_subtitles()     ← ajuste a frase limpia
        │
translate_srt()  ──►  es_srt_path
        │
[opcional] generate_voiceover()  ──►  dub_audio_path
        │
generate_video_metadata()  ──►  título / descripción / gancho
        │
render_final_video()
        │
[POST-RENDER] ffprobe validation  ← duración mínima 5s
        │
create_video_thumbnail()
        │
upload_to_youtube() / SocialPublisher
```

## 3. Segmentación por Heatmap y Motor AVD (`find_viral_heatmap_segment`)

Analiza el "most replayed" heatmap de YouTube vía yt-dlp para detectar el segmento que maximiza el **Average View Duration (AVD)** y el tiempo de atención total (Watch Time), sin truncar narrativas ni mutilar contexto.

### Duraciones candidatas adaptativas (Context-Aware)

| Rango de Duración | Arquetipo / Uso | Impacto Algorítmico |
|---|---|---|
| **19s – 28s** | Momentos de impacto rápido, choques, loops continuos | Alta tasa de repetición (Loop Rate > 100%) |
| **30s – 42s** | Físicas de vehículos, tiroteos, reacciones de streamers | Gran equilibrio entre retención y contexto |
| **45s – 58s** | Comparativas de mapa, easter eggs complejos, misiones | **Máximo Watch Time absoluto (AVD en segundos)** |

### Fórmula del Motor AVD (Average View Duration)

```python
# 1. Tiempo de atención neto esperado (segundos)
estimated_avd_s = c_dur * avg_retention * (1.0 + peak_retention * 0.35)

# 2. Factor de estabilidad de retención (penaliza acantilados de abandono)
cliff_penalty = max(0.5, min(1.0, (min_retention / (avg_retention + 1e-4))))

# 3. Score AVD absoluto optimizado para YouTube Shorts & TikTok
avd_score = estimated_avd_s * (0.7 + 0.3 * cliff_penalty)
```

- **Vídeos orgánicos cortos (≤ 60s):** NUNCA se recortan. Se respeta íntegramente la duración orgánica del autor (cero cortes).
- **Finalización de frase limpia:** El módulo `snap_window_to_subtitles` sincroniza el corte final con signos de puntuación (`.!?:…`), expandiendo hasta 58s si es necesario para no dejar ideas incompletas.

## 4. Ajuste por Subtítulos (`snap_window_to_subtitles`)

Evita que el clip empiece o acabe a media frase.

1. **v_start:** se desplaza al inicio del cue más cercano (tolerancia ≤ 3.5s). Si queda < 4s del inicio del vídeo, se fuerza a 0.0s.
2. **v_end:** selecciona el cue candidato que termine una frase completa (signos de puntuación `.!?:…`) con pausa posterior ≥ 0.35s, penalizando las duraciones largas respecto al target del heatmap.

## 5. Renderizado Final (`render_final_video`)

### Transformaciones obligatorias

| Transformación | Especificación | Justificación |
|---------------|----------------|---------------|
| **Formato D: Pro-Cinema 83.3%** | 1080×1600 @ y=160, crop lateral mínimo (16.7%) | Espectáculo visual máximo, físicas RAGE 9, coches, agua e inmersión cinemática |
| **Formato C: Smart Frame 4:5** | 1080×1350 @ y=285 (70.3% cobertura vertical) | Margen seguro para HUD crítico, minimapa, armas y streamings con webcam |
| **Formato A: Cinema Full** | 1080×608 @ y=656 (31.6% cobertura, 0% recorte) | Reservado exclusivamente para tráilers oficiales 21:9 ultra-panorámicos |
| **Formato Nativo** | 1080×1920 (100% cobertura) | Vídeos que ya son nativos verticales 9:16 |
| **Gancho superior** | 0.0s–2.5s, 2 líneas contrastadas | Blanco + Amarillo Neón (Top Hook dinámico) |
| **Subtítulos Karaoke** | Pop Bounce, glow dinámico por palabra | Retención activa (Anti-drop visual) |
| **Escudo de Audio (Audio Shield)** | Detección estricta de volumen (ffmpeg volumedetect) | Bloquea y aborta clips con volumen < -42dB o B-rolls mudos |
| **Audio Ducking** | ~18% durante voz en off (modo dub) | Claridad y protagonismo del mensaje |
| **Codificación** | `h264_videotoolbox` (GPU/ASIC) | Obligatorio; jamás `libx264` |
| **Bitrate vídeo** | 8–10 Mbps | Calidad óptima YouTube/TikTok |
| **Bitrate audio** | 192 kbps AAC | Estándar broadcast |

### Restricciones de hardware (GaTDSEQ coexistence)

- **Hilos FFmpeg por defecto:** 2 (`get_ffmpeg_threads()`).
- **Modo Cortesía:** si `is_quant_busy()` detecta GaTDSEQ activo → 1 hilo.
- **NUNCA** usar `libx264` en el host de producción (MacBook Pro Haswell).

## 6. Validación Post-Render (ffprobe)

Tras el renderizado, se valida que el archivo de salida es un vídeo real y no está truncado:

```python
ffprobe -v quiet -show_entries format=duration -of csv=p=0 output.mp4
```

- Si `duration < 5s` → el archivo se descarta y el pipeline aborta limpiamente.
- Si la llamada a ffprobe falla → advertencia en log, pero el pipeline continúa.

## 7. Generación de Miniatura (`create_video_thumbnail`)

- Resolución: 1280×720 (horizontal) o 1080×1920 (vertical Shorts).
- Texto del gancho superpuesto con estilo Hormozi Pop Bounce.
- Se preserva en `output/` junto al `.json` de metadatos tras eliminar el `.mp4` subido.

## 8. Metadatos Virales (`generate_video_metadata`)

Gemini Flash genera en cada vídeo:
- **Título:** mayúsculas, emojis temáticos, `#GTA6`, sin clichés prohibidos del Playbook.
- **Descripción:** atribución `POR: @Creador`, enlace original, descargo Fair Use (Art. 107).
- **Comentario anclado:** pregunta polarizante para fomentar engagement.
- **Gancho:** 2 líneas para la píldora visual de 0–2.5s.

## 9. Limpieza de Disco (Regla 0 Bytes)

| Momento | Acción |
|---------|--------|
| Tras renderizado | `clean_temp_directory(video_id)` — vacía `temp/` |
| Tras subida exitosa | `clean_uploaded_video_file(output_path)` — borra `.mp4` de `output/` |
| Siempre | `gc.collect()` para liberar buffers a GaTDSEQ |

## 10. Protocolo de Mantenimiento

- **Cambiar estilo de subtítulos:** modificar `render_final_video` en `src/video_editor.py`.
- **Ajustar duración del heatmap:** editar `candidate_durations` en `src/downloader.py`.
- **Cambiar gancho visual:** pasar `hook_override` al llamar a `process_single_video`.
- **Auditar rendimientos de edición:** revisar `data/performance_records.json` (views/likes a 24h).
- **Tests de regresión:** `python -m unittest discover -s tests` antes de cualquier cambio.
