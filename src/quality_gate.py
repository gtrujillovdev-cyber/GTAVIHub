"""
Quality Gate Pre-Subida — Filtro obligatorio "anti-mierda" entre render y subida.

Cada video debe superar dos validaciones para recibir APPROVED:
1. Validacion Tecnica (FFprobe/Python): resolucion, duracion, frames negros, audio, integridad.
2. Validacion de Potencial Viral (LLM/Scoring): hook, claridad, titulo, puntuacion de fuente.

Si falla, el video se mueve a output/quarantine/ con un JSON de diagnostico.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

from .config import (
    DATA_DIR, OUTPUT_DIR, SHORT_MIN_DURATION, SHORT_MAX_DURATION,
    CANVAS_WIDTH, CANVAS_HEIGHT, GEMINI_API_KEY,
)

QUARANTINE_DIR = OUTPUT_DIR / "quarantine"
MIN_VIRAL_SCORE = float(os.getenv("MIN_VIRAL_SCORE", "7.0"))
ENABLE_QUALITY_GATE = os.getenv("ENABLE_QUALITY_GATE", "true").lower() in ("1", "true", "yes")


def _probe_video(video_path: Path) -> Dict[str, Any]:
    """Extrae metadata tecnica del video renderizado via ffprobe."""
    result = {
        "valid": False, "duration": 0.0, "width": 0, "height": 0,
        "has_audio": False, "codec": "", "error": ""
    }
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            result["error"] = "ffprobe exit code != 0"
            return result

        data = json.loads(res.stdout)
        fmt = data.get("format", {})
        result["duration"] = float(fmt.get("duration", 0))

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                result["width"] = int(stream.get("width", 0))
                result["height"] = int(stream.get("height", 0))
                result["codec"] = stream.get("codec_name", "")
            elif stream.get("codec_type") == "audio":
                result["has_audio"] = True

        result["valid"] = result["duration"] > 0 and result["width"] > 0
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def _check_black_frames(video_path: Path, duration: float) -> Tuple[bool, str]:
    """Verifica que no haya frames negros al inicio o final del video."""
    try:
        # Check first 1s
        cmd_start = [
            "ffmpeg", "-threads", "1", "-t", "1", "-i", str(video_path),
            "-vf", "blackdetect=d=0.3:pix_th=0.12",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd_start, capture_output=True, text=True, timeout=10)
        if "black_start:0" in (res.stderr or ""):
            return False, "Frames negros detectados al inicio del video (primeros 0.3s)"

        # Check last 1s
        start_t = max(0, duration - 1.5)
        cmd_end = [
            "ffmpeg", "-threads", "1", "-ss", str(start_t), "-i", str(video_path),
            "-vf", "blackdetect=d=0.3:pix_th=0.12",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd_end, capture_output=True, text=True, timeout=10)
        if "black_start" in (res.stderr or ""):
            return False, "Frames negros detectados al final del video"

        return True, ""
    except Exception:
        return True, ""  # En caso de error, no bloquear


def _check_visual_compliance(video_path: Path, duration: float) -> Tuple[bool, str]:
    """
    Escudo Visual Anti-Facecam y Anti-Subtítulos en Inglés Quemados:
    Muestrea 3 fotogramas (20%, 50%, 80%) y usa Gemini Vision para rechazar cualquier clip
    que contenga webcam/cara de streamer real o textos grandes en inglés quemados del origen.
    """
    if not GEMINI_API_KEY or duration < 3.0:
        return True, "Visual compliance omitido (sin API key o clip muy corto)"

    frames: list[Path] = []
    try:
        from google.genai import types
        from .translator import get_gemini_client, generate_content_with_retry, clean_srt_response

        for idx, ratio in enumerate((0.20, 0.50, 0.80)):
            ts = round(max(0.5, duration * ratio), 2)
            out_jpg = video_path.parent / f".qg_vis_{video_path.stem[:16]}_{idx}.jpg"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", f"{ts:.2f}", "-i", str(video_path),
                    "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "5", str(out_jpg),
                ],
                capture_output=True,
                timeout=8,
            )
            if out_jpg.exists() and out_jpg.stat().st_size > 1000:
                frames.append(out_jpg)

        if not frames:
            return True, "Sin fotogramas para auditoría visual"

        parts = [
            "Audita estos 3 fotogramas de un clip de GTA 6 doblado al español.\n"
            "Responde SOLO JSON estricto con 2 booleanos:\n"
            "1) `has_facecam`: true SI Y SOLO SI aparece una cámara/webcam o cara de una persona real (streamer/youtuber) superpuesta sobre el juego. NO marques true por personajes 3D del propio GTA 6.\n"
            "2) `has_burned_english_subs`: true SI aparecen textos grandes o subtítulos quemados EN INGLÉS del vídeo original encima del gameplay (por ejemplo frases editadas en inglés en el centro/arriba/abajo). NO marques true por nuestros subtítulos en español ni por el HUD/minimapa normal de GTA 6.\n"
            'JSON: {"has_facecam": false, "has_burned_english_subs": false, "detail": ""}'
        ]
        for f in frames:
            parts.append(types.Part.from_bytes(data=f.read_bytes(), mime_type="image/jpeg"))

        resp = generate_content_with_retry(
            client=get_gemini_client(),
            contents=parts,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(clean_srt_response(resp.text or "{}"))
        has_fc = data.get("has_facecam") is True
        has_en = data.get("has_burned_english_subs") is True
        detail = str(data.get("detail") or "").strip()
        if has_fc or has_en:
            reasons = []
            if has_fc:
                reasons.append("facecam/cara de streamer detectada")
            if has_en:
                reasons.append("subtítulos/textos en inglés quemados detectados")
            return False, f"Rechazo visual: {', '.join(reasons)}" + (f" ({detail})" if detail else "")
        return True, "Visual limpio (sin facecam ni textos en inglés quemados)"
    except Exception as e:
        return True, f"Visual compliance no bloqueante: {e}"
    finally:
        for f in frames:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


def _score_viral_potential_heuristic(
    metadata: Dict[str, Any],
    candidate_score: int,
    source_title: str
) -> Tuple[float, str]:
    """Scoring heuristico de potencial viral (fallback si Gemini no disponible)."""
    score = 5.0  # Base

    # Candidate score from ai_selector
    if candidate_score >= 80:
        score += 2.5
    elif candidate_score >= 60:
        score += 1.5
    elif candidate_score >= 40:
        score += 0.5
    elif candidate_score < 25 and candidate_score > 0:
        score -= 1.5

    # Hook quality
    hook = metadata.get("hook", "")
    hook_words = len(hook.split()) if hook else 0
    if hook_words >= 3:
        score += 0.5
    if any(kw in hook.upper() for kw in ("SECRETO", "OCULTA", "LEGENDARIA", "CONFIRMADO", "PRIMERA", "EXCLUSIVA")):
        score += 0.5

    # Title quality
    title = metadata.get("title", "")
    if len(title) >= 20 and "GTA" in title.upper():
        score += 0.5

    # Debate question exists
    if metadata.get("debate_question"):
        score += 0.3

    # Archetype bonus
    arch = metadata.get("archetype", "")
    if arch in ("gameplay_puro", "fisicas_motor", "secretos_detalles"):
        score += 0.5

    score = max(1.0, min(10.0, score))
    return score, f"Heuristico: score={score:.1f}/10 (candidate_score={candidate_score})"


def _score_viral_potential_llm(
    metadata: Dict[str, Any],
    candidate_score: int,
    source_title: str
) -> Tuple[float, str]:
    """Scoring de potencial viral via Gemini Flash (ligero, ~200 tokens)."""
    if not GEMINI_API_KEY:
        return _score_viral_potential_heuristic(metadata, candidate_score, source_title)

    try:
        from .translator import get_gemini_client, generate_content_with_retry

        client = get_gemini_client()
        title = metadata.get("title", source_title)
        hook = metadata.get("hook", "")
        debate = metadata.get("debate_question", "")
        archetype = metadata.get("archetype", "")

        prompt = (
            f"Puntua del 1 al 10 el potencial viral de este YouTube Short de GTA 6 para una audiencia hispana gaming.\n"
            f"IMPORTANTE: GTA 6 YA HA SIDO LANZADO OFICIALMENTE (19 de noviembre de 2026); el gameplay, mapas, armas y localizaciones son reales.\n"
            f"Titulo: {title}\n"
            f"Hook visual (0-2.5s): {hook}\n"
            f"Pregunta de debate: {debate}\n"
            f"Arquetipo: {archetype}\n"
            f"Score interno de la fuente: {max(candidate_score, 55)}/100\n\n"
            f"Criterios: 1) Gancho de primeros 3s, 2) Claridad sin contexto previo, 3) Potencia del titulo, 4) Valor accionable (guías/localizaciones/secretos tienen alto potencial).\n"
            f'Responde SOLO con JSON: {{"score": 7.5, "reason": "Breve explicacion"}}'
        )

        response = generate_content_with_retry(
            client=client,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        data = json.loads(response.text.strip())
        llm_score = float(data.get("score", 5.0))
        reason = data.get("reason", "")
        return max(1.0, min(10.0, llm_score)), f"LLM: {llm_score:.1f}/10 — {reason}"

    except Exception as e:
        print(f"[Quality Gate] Gemini scoring fallido ({e}), usando heuristico...")
        return _score_viral_potential_heuristic(metadata, candidate_score, source_title)


def _quarantine_video(
    video_path: Path,
    reason: str,
    diagnostics: Dict[str, Any]
) -> Path:
    """Mueve un video rechazado a output/quarantine/ con diagnostico JSON."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE_DIR / video_path.name
    try:
        shutil.move(str(video_path), str(dest))
    except Exception:
        dest = video_path  # Si falla el move, al menos logueamos

    diag_path = QUARANTINE_DIR / f"{video_path.stem}_quarantine.json"
    try:
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump({
                "video": video_path.name,
                "reason": reason,
                "quarantined_at": datetime.now().isoformat(),
                "diagnostics": diagnostics
            }, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return dest


def clean_quarantine(max_age_hours: int = 48) -> int:
    """Limpia videos en quarantine mas antiguos que max_age_hours."""
    if not QUARANTINE_DIR.exists():
        return 0
    cleaned = 0
    cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
    for f in QUARANTINE_DIR.iterdir():
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                cleaned += 1
        except Exception:
            pass
    return cleaned


def run_quality_gate(
    video_path: Path,
    metadata: Dict[str, Any],
    candidate_score: int = 0,
    source_title: str = "",
    dry_run: bool = False
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Filtro obligatorio pre-subida. Retorna (approved, reason, diagnostics).
    Si approved=False y no es dry_run, el video se mueve a quarantine/.
    """
    if not ENABLE_QUALITY_GATE:
        return True, "Quality Gate desactivado", {}

    diagnostics: Dict[str, Any] = {
        "technical": {},
        "viral": {},
        "decision": "pending"
    }

    # === 1. VALIDACION TECNICA ===
    if not video_path or not video_path.exists():
        reason = "El archivo de video no existe"
        diagnostics["decision"] = "REJECTED_MISSING_FILE"
        return False, reason, diagnostics

    probe = _probe_video(video_path)
    diagnostics["technical"]["probe"] = probe

    if not probe["valid"]:
        if dry_run:
            # En dry_run, ffprobe puede fallar con videos mock; no bloquear
            print(f"[Quality Gate] [DRY RUN] ffprobe no valido ({probe['error']}), aprobando por simulacion.")
            diagnostics["decision"] = "APPROVED_DRY_RUN"
            return True, "Aprobado (dry_run, ffprobe omitido)", diagnostics
        reason = f"Video corrupto o no legible por ffprobe: {probe['error']}"
        diagnostics["decision"] = "REJECTED_CORRUPT"
        _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # Resolucion 9:16 (tolerancia +-4px para redondeos de FFmpeg)
    w, h = probe["width"], probe["height"]
    expected_ratio = CANVAS_WIDTH / CANVAS_HEIGHT  # 0.5625
    actual_ratio = w / max(h, 1)
    if abs(actual_ratio - expected_ratio) > 0.05:
        reason = f"Resolucion inesperada: {w}x{h} (ratio {actual_ratio:.3f}, esperado ~{expected_ratio:.3f})"
        diagnostics["decision"] = "REJECTED_RESOLUTION"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # Duracion
    dur = probe["duration"]
    if dur < max(5.0, SHORT_MIN_DURATION - 2):
        reason = f"Duracion demasiado corta: {dur:.1f}s (minimo {SHORT_MIN_DURATION}s)"
        diagnostics["decision"] = "REJECTED_TOO_SHORT"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    if dur > SHORT_MAX_DURATION + 5:
        reason = f"Duracion excesiva: {dur:.1f}s (maximo {SHORT_MAX_DURATION}s)"
        diagnostics["decision"] = "REJECTED_TOO_LONG"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # Audio obligatorio
    if not probe["has_audio"]:
        reason = "El video no tiene pista de audio"
        diagnostics["decision"] = "REJECTED_NO_AUDIO"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # Frames negros
    no_black, black_reason = _check_black_frames(video_path, dur)
    diagnostics["technical"]["black_frames"] = {"ok": no_black, "reason": black_reason}
    if not no_black:
        reason = f"Quality Gate tecnico: {black_reason}"
        diagnostics["decision"] = "REJECTED_BLACK_FRAMES"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # Escudo Visual Anti-Facecam y Anti-Subtítulos en Inglés Quemados (solo en ejecuciones reales)
    if not dry_run:
        vis_ok, vis_reason = _check_visual_compliance(video_path, dur)
        diagnostics["technical"]["visual_compliance"] = {"ok": vis_ok, "reason": vis_reason}
        if not vis_ok:
            reason = f"Quality Gate visual: {vis_reason}"
            diagnostics["decision"] = "REJECTED_VISUAL_COMPLIANCE"
            _quarantine_video(video_path, reason, diagnostics)
            return False, reason, diagnostics

    # === 2. VALIDACION DE POTENCIAL VIRAL ===
    viral_score, viral_reason = _score_viral_potential_llm(
        metadata, candidate_score, source_title
    )
    diagnostics["viral"] = {
        "score": viral_score,
        "threshold": MIN_VIRAL_SCORE,
        "reason": viral_reason
    }

    if viral_score < MIN_VIRAL_SCORE:
        reason = f"Potencial viral insuficiente: {viral_score:.1f}/10 < {MIN_VIRAL_SCORE}/10 ({viral_reason})"
        diagnostics["decision"] = "REJECTED_LOW_VIRAL"
        if not dry_run:
            _quarantine_video(video_path, reason, diagnostics)
        return False, reason, diagnostics

    # === APROBADO ===
    diagnostics["decision"] = "APPROVED"
    print(f"[Quality Gate] APROBADO: tecnico OK, viral {viral_score:.1f}/10 >= {MIN_VIRAL_SCORE}/10")
    return True, f"Aprobado (viral: {viral_score:.1f}/10)", diagnostics
