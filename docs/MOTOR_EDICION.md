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

## 3. Segmentación por Heatmap (`find_viral_heatmap_segment`)

Analiza el "most replayed" heatmap de YouTube vía yt-dlp para detectar el segmento de máxima retención.

### Duraciones candidatas (oct 2026)

| Duración | Prioridad | Justificación |
|----------|-----------|---------------|
| 20s | ★★★★★ | Mayor loop-rate en Shorts |
| 24s | ★★★★☆ | Sweet spot óptimo del Playbook |
| 28s | ★★★★☆ | Límite superior del sweet spot |
| 34s | ★★★☆☆ | Fallback para contenido denso |
| 40s | ★★☆☆☆ | Solo si no hay ventana mejor |

### Fórmula de scoring ponderado

```python
window_score = avg_val * (1 + peak_val * 0.4) * (28 / max(c_dur, 20))
```

- `avg_val`: retención media de la ventana.
- `peak_val * 0.4`: bonus por picos de intensidad (momentos que se repiten).
- `(28 / c_dur)`: penalización por duraciones largas — favorece clips cortos con máxima retención sobre mesetas mediocres largas.

**Vídeos cortos (≤ 65s):** se preserva la duración orgánica completa sin ningún corte.

## 4. Ajuste por Subtítulos (`snap_window_to_subtitles`)

Evita que el clip empiece o acabe a media frase.

1. **v_start:** se desplaza al inicio del cue más cercano (tolerancia ≤ 3.5s). Si queda < 4s del inicio del vídeo, se fuerza a 0.0s.
2. **v_end:** selecciona el cue candidato que termine una frase completa (signos de puntuación `.!?:…`) con pausa posterior ≥ 0.35s, penalizando las duraciones largas respecto al target del heatmap.

## 5. Renderizado Final (`render_final_video`)

### Transformaciones obligatorias

| Transformación | Especificación | Justificación |
|---------------|----------------|---------------|
| Reencuadre adaptativo | Nativo 9:16 / Cinema Full-Frame (1080×608 0% corte) / Dynamic Smart Crop (1080×1080) | Adaptado al arquetipo |
| Gancho superior | 0.0s–2.5s, 2 líneas contrastadas | Blanco + Amarillo Neón |
| Subtítulos Karaoke | Pop Bounce, glow dinámico por palabra | Retención activa |
| Audio Ducking | ~18% durante voz en off (modo dub) | Claridad del mensaje |
| Codificación | `h264_videotoolbox` (GPU/ASIC) | Obligatorio; jamás `libx264` |
| Bitrate vídeo | 8 Mbps | Calidad YouTube/TikTok |
| Bitrate audio | 192 kbps AAC | Estándar de plataforma |

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
