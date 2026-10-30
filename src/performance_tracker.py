"""
performance_tracker.py — Bucle de feedback post-publicación (24h)

Registra cada vídeo publicado y rastrea sus métricas reales 24h después
para alimentar al Learning Engine con datos de rendimiento concretos.
"""
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import DATA_DIR

PERF_FILE = DATA_DIR / "performance_records.json"

def _load_records() -> List[Dict[str, Any]]:
    if not PERF_FILE.exists():
        return []
    try:
        with open(PERF_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_records(records: List[Dict[str, Any]]) -> None:
    try:
        with open(PERF_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[PerformanceTracker] Error guardando registros: {e}")

def record_published_video(
    video_id: str,
    title: str,
    youtube_url: str,
    base_score: int = 0,
    velocity_vpd: float = 0.0,
    days_old: int = 0,
    is_short: bool = True
) -> None:
    """
    Registra un vídeo recién publicado en performance_records.json.
    Se llamará desde pipeline.py tras mark_video_processed.
    """
    records = _load_records()
    # Evitar duplicados por video_id
    if any(r.get("video_id") == video_id for r in records):
        return
    records.append({
        "video_id": video_id,
        "title": title,
        "youtube_url": youtube_url,
        "base_score": base_score,
        "velocity_vpd": velocity_vpd,
        "days_old": days_old,
        "is_short": is_short,
        "published_at": datetime.now().isoformat(),
        "metrics_fetched_at": None,
        "views_24h": None,
        "likes_24h": None,
        "comments_24h": None,
    })
    _save_records(records)

def fetch_pending_metrics(max_fetch: int = 5) -> int:
    """
    Busca vídeos publicados hace más de 23h cuyas métricas aún no se han recogido
    y actualiza sus views/likes reales vía yt-dlp.
    Retorna el número de registros actualizados.
    """
    records = _load_records()
    now = datetime.now()
    updated = 0

    for rec in records:
        if rec.get("metrics_fetched_at"):
            continue
        published_at_str = rec.get("published_at", "")
        if not published_at_str:
            continue
        try:
            published_at = datetime.fromisoformat(published_at_str)
        except ValueError:
            continue

        age_hours = (now - published_at).total_seconds() / 3600
        if age_hours < 23:
            continue

        url = rec.get("youtube_url", "")
        if not url or "youtu" not in url:
            continue

        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--skip-download",
                "--print", "%(view_count)s\t%(like_count)s\t%(comment_count)s",
                url
            ], capture_output=True, text=True, timeout=20)

            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split("\t")
                rec["views_24h"] = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
                rec["likes_24h"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                rec["comments_24h"] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                rec["metrics_fetched_at"] = now.isoformat()
                updated += 1
                print(f"[PerformanceTracker] Métricas actualizadas: {rec['title'][:40]} — {rec['views_24h']} vistas")
        except Exception as e:
            print(f"[PerformanceTracker] Error obteniendo métricas para {url}: {e}")

        if updated >= max_fetch:
            break

    if updated > 0:
        _save_records(records)
    return updated

def get_performance_context_for_playbook() -> str:
    """
    Genera un bloque de texto inyectable en el prompt del Learning Engine
    con los top performers y bottom performers reales del canal.
    """
    records = _load_records()
    # Solo considerar registros con métricas reales
    with_metrics = [r for r in records if r.get("views_24h") is not None]
    if not with_metrics:
        return ""

    with_metrics.sort(key=lambda x: x.get("views_24h", 0), reverse=True)
    top = with_metrics[:3]
    bottom = with_metrics[-3:] if len(with_metrics) > 3 else []

    lines = ["Rendimiento real de nuestros vídeos publicados (primeras 24h):"]
    lines.append("TOP PERFORMERS:")
    for r in top:
        eng = ""
        if r.get("likes_24h") and r.get("views_24h", 0) > 0:
            eng = f", engagement={r['likes_24h']/r['views_24h']:.3f}"
        lines.append(
            f"  - '{r['title'][:50]}': {r['views_24h']} vistas"
            f", {r.get('likes_24h', '?')} likes{eng}"
        )

    if bottom:
        lines.append("BOTTOM PERFORMERS:")
        for r in bottom:
            lines.append(
                f"  - '{r['title'][:50]}': {r['views_24h']} vistas"
                f", {r.get('likes_24h', '?')} likes"
            )

    return "\n".join(lines)
