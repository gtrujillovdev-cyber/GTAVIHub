"""
performance_tracker.py — Bucle de feedback post-publicación (24h)

Registra cada vídeo publicado y rastrea sus métricas reales 24h después
para alimentar al Learning Engine con datos de rendimiento concretos.
"""
import sys
import json
import subprocess
from datetime import datetime, timedelta, timezone
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

def _extract_youtube_id(url: str) -> str:
    """Extrae el video ID de YouTube desde URLs youtu.be, watch?v= o /shorts/."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    if "youtu.be/" in u:
        return u.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0].strip("/")
    if "/shorts/" in u:
        return u.split("/shorts/", 1)[1].split("?", 1)[0].split("&", 1)[0].strip("/")
    if "v=" in u:
        return u.split("v=", 1)[1].split("&", 1)[0].strip("/")
    return ""


def record_published_video(
    video_id: str,
    title: str,
    youtube_url: str,
    base_score: int = 0,
    velocity_vpd: float = 0.0,
    days_old: int = 0,
    is_short: bool = True,
    target_channel: str = "main",
    **kwargs
) -> None:
    """
    Registra un vídeo recién publicado en performance_records.json
    con etiquetas A/B de experimento y estructura de snapshots 6h/24h/48h.
    """
    records = _load_records()
    yt_vid = _extract_youtube_id(youtube_url)
    # Evitar duplicados por video_id o youtube_video_id
    for existing in records:
        if existing.get("video_id") == video_id or (yt_vid and existing.get("youtube_video_id") == yt_vid):
            # Enriquecer si faltaba youtube_url o experiment
            if youtube_url and not existing.get("youtube_url"):
                existing["youtube_url"] = youtube_url
            if yt_vid and not existing.get("youtube_video_id"):
                existing["youtube_video_id"] = yt_vid
            if kwargs.get("tiktok_url") and not existing.get("tiktok_url"):
                existing["tiktok_url"] = kwargs["tiktok_url"]
            _save_records(records)
            return

    now_dt = datetime.now()
    experiment = {
        "source_type": kwargs.get("source_type") or ("native_short" if is_short else "16:9_multibeat"),
        "preset": kwargs.get("preset") or "D_89%",
        "has_frame0_cover": bool(kwargs.get("has_frame0_cover", True)),
        "duration_sec": kwargs.get("duration_sec"),
        "topic": kwargs.get("topic") or classify_clip_angle(title),
        "publish_slot": kwargs.get("publish_slot") or now_dt.strftime("%H:%M"),
    }
    records.append({
        "video_id": video_id,
        "youtube_video_id": yt_vid or None,
        "title": title,
        "youtube_url": youtube_url,
        "tiktok_url": kwargs.get("tiktok_url"),
        "base_score": base_score,
        "velocity_vpd": velocity_vpd,
        "days_old": days_old,
        "is_short": is_short,
        "target_channel": target_channel,
        "published_at": now_dt.isoformat(),
        "metrics_fetched_at": None,
        "views_24h": None,
        "likes_24h": None,
        "comments_24h": None,
        "experiment": experiment,
        "snapshots": {"6h": None, "24h": None, "48h": None},
    })
    _save_records(records)

def fetch_pending_metrics(max_fetch: int = 5) -> int:
    """
    Busca vídeos publicados hace más de 23h cuyas métricas aún no se han recogido
    y actualiza sus views/likes reales priorizando YouTube Data API v3 y usando yt-dlp como respaldo.
    Retorna el número de registros actualizados.
    """
    try:
        sync_live_channel_metrics(limit=max(12, max_fetch * 2))
    except Exception:
        pass
    try:
        from .learning_engine import sync_tiktok_insights_to_playbook
        sync_tiktok_insights_to_playbook()
    except Exception:
        pass
    records = _load_records()
    now = datetime.now(timezone.utc)
    updated = 0

    for rec in records:
        if rec.get("metrics_fetched_at"):
            continue
        published_at_str = rec.get("published_at", "")
        if not published_at_str:
            continue
        try:
            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            if published_at.tzinfo is None:
                published_at = published_at.astimezone()
            published_at = published_at.astimezone(timezone.utc)
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
                # Engagement rate como proxy de retención (likes+comments*3 / views)
                v = rec.get("views_24h") or 0
                l = rec.get("likes_24h") or 0
                c = rec.get("comments_24h") or 0
                rec["engagement_rate_24h"] = round((l + c * 3) / max(v, 1), 4) if v > 0 else 0
                rec["metrics_fetched_at"] = now.isoformat()
                updated += 1
                print(f"[PerformanceTracker] Métricas actualizadas: {rec['title'][:40]} — {rec['views_24h']} vistas (engagement: {rec['engagement_rate_24h']:.3f})")
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
        eng_rate = r.get("engagement_rate_24h") or 0
        angle = classify_clip_angle(r.get("title", ""))
        lines.append(
            f"  - '{r['title'][:50]}' [{angle}]: {r['views_24h']} vistas"
            f", {r.get('likes_24h', '?')} likes, engagement={eng_rate:.3f}"
        )

    if bottom:
        lines.append("BOTTOM PERFORMERS:")
        for r in bottom:
            angle = classify_clip_angle(r.get("title", ""))
            lines.append(
                f"  - '{r['title'][:50]}' [{angle}]: {r['views_24h']} vistas"
                f", {r.get('likes_24h', '?')} likes"
            )

    return "\n".join(lines)


ANGLE_CATALOG: Dict[str, tuple[str, ...]] = {
    "fisicas_motor": (
        "física", "fisica", "physics", "agua", "water", "rage", "rage 9", "colision",
        "colisión", "deformacion", "deformación", "choque", "crash", "ragdoll",
        "mecanica", "mecánica", "mecanicas", "mecánicas", "agarre", "animacion",
        "animación", "conduccion", "conducción", "disparo", "combate", "pelea",
        " ia ", "npc", "npcs", "destruccion", "destrucción"
    ),
    "reaccion_streamer": (
        "reaccion", "reacción", "reaction", "reacts", "xqc", "ibai", "rubius", "elrubius",
        "illojuan", "xokas", "elxokas", "willyrex", "auron", "auronplay", "thegrefg",
        "grefg", "vegetta", "vegetta777", "djmariio", "streamer", "streamers",
        "directo", "flipa", "alucina", "prueba", "jugando"
    ),
    "policia_caos": (
        "policia", "policía", "police", "chase", "persecucion", "persecución",
        "swat", "estrellas", "wanted", "caos", "chaos", "tiroteo", "atraco",
        "escape", "huida", "arresto"
    ),
    "historia_misiones": (
        "mision", "misión", "mission", "missions", "prologo", "prólogo", "prologue",
        "intro", "lucia", "lucía", "jason", "historia", "story", "campaña", "final",
        "walkthrough"
    ),
    "comparativa_tecnica": (
        "ps5", "ps5 pro", "xbox", "fps", " vs ", "comparativa", "comparison", "graficos",
        "gráficos", "graphics", "4k", "digital foundry", "elanalistadebits", "ray tracing", "rtx"
    ),
    "secretos_detalles": (
        "secreto", "secretos", "secret", "secrets", "oculto", "ocultos", "hidden",
        "easter egg", "easter eggs", "detalle", "detalles", "detail", "details",
        "mapa", "map", "leonida", "vice city", "curiosidad", "curiosidades",
        "loot", "ubicacion", "ubicación", "truco", "trucos", "dinero"
    ),
    "realismo_inmersion": (
        "real life", "looks real", "too real", "realistic", "realism", "realismo",
        "insane", "mindblowing", "mind blowing", "incredible", "amazing",
        "open world", "mundo abierto", "inmersion", "inmersión", "density",
        "next gen", "next-gen", "absurdly"
    ),
    "tips_guias": (
        "tip", "tips", "trick", "tricks", "guide", "how to", "where to find",
        "best weapon", "best car", "legendary weapon", "rare car", "money glitch",
        "fast cash", "loadout", "unlock", "how to get", "how to find",
        "guia", "guía", "consejo", "consejos", "mejor arma", "mejor coche",
        "arma legendaria", "coche raro", "dinero rapido", "dinero rápido",
        "como conseguir", "cómo conseguir", "como encontrar", "cómo encontrar",
        "desbloquear", "spot", "spots", "farm", "grinding"
    ),
}

ANGLE_LABELS: Dict[str, str] = {
    "fisicas_motor": "Físicas, Mecánicas y Motor RAGE 9",
    "reaccion_streamer": "Streamers y Momentos Virales",
    "policia_caos": "Persecuciones Policiales y Caos",
    "historia_misiones": "Historia, Misiones y Protagonistas",
    "comparativa_tecnica": "Comparativas Técnicas y Gráficos PS5 Pro",
    "secretos_detalles": "Secretos, Mapa y Detalles Ocultos",
    "realismo_inmersion": "Realismo, Mundo Abierto e Inmersión",
    "tips_guias": "Tips, Guías y Ubicaciones de Loot",
    "gameplay_general": "Gameplay General",
}


def classify_clip_angle(title: str, uploader: str = "") -> str:
    """Clasifica el ángulo temático de un vídeo por su título y uploader."""
    combined = f" {(title or '').lower()} {(uploader or '').lower()} "
    for angle, kws in ANGLE_CATALOG.items():
        if any(kw in combined for kw in kws):
            return angle
    return "gameplay_general"


def sync_live_channel_metrics(limit: int = 12) -> List[Dict[str, Any]]:
    """
    Consulta métricas en vivo (vistas, likes, comentarios y velocidad vistas/h)
    de los vídeos recientes de @GTAVIHubExtra vía YouTube Data API v3 y actualiza
    performance_records.json sin esperar 23h.
    """
    from .youtube_analytics import fetch_recent_videos
    from datetime import timezone

    recent = fetch_recent_videos(limit=limit)
    if not recent:
        return []

    records = _load_records()
    by_id = {r.get("video_id"): r for r in records if r.get("video_id")}
    by_yt_id = {}
    for r in records:
        yt_id = r.get("youtube_video_id") or _extract_youtube_id(r.get("youtube_url", ""))
        if yt_id:
            r["youtube_video_id"] = yt_id
            by_yt_id[yt_id] = r
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    live_items: List[Dict[str, Any]] = []

    for v in recent:
        vid = v.get("id")
        if not vid:
            continue
        views = int(v.get("views") or 0)
        likes = int(v.get("likes") or 0)
        comments = int(v.get("comments") or 0)
        pub_raw = v.get("published_at") or ""
        age_hours = 1.0
        if pub_raw:
            try:
                pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                age_hours = max(0.25, (now_utc - pub_dt).total_seconds() / 3600.0)
            except Exception:
                age_hours = 1.0

        vph = round(views / max(age_hours, 0.5), 1)
        eng_score = likes + (comments * 3)
        eng_rate = round(eng_score / max(views, 1), 4) if views > 0 else 0.0
        angle = classify_clip_angle(v.get("title", ""))

        entry = by_id.get(vid) or by_yt_id.get(vid)
        if entry is None:
            entry = {
                "video_id": vid,
                "youtube_video_id": vid,
                "title": v.get("title", ""),
                "youtube_url": v.get("url", f"https://youtu.be/{vid}"),
                "base_score": 0,
                "velocity_vpd": 0.0,
                "days_old": int(age_hours // 24),
                "is_short": True,
                "target_channel": "extra",
                "published_at": pub_raw or now_local.isoformat(),
                "metrics_fetched_at": None,
                "views_24h": None,
                "likes_24h": None,
                "comments_24h": None,
                "experiment": {
                    "source_type": "unknown",
                    "preset": "D_89%",
                    "has_frame0_cover": True,
                    "duration_sec": None,
                    "topic": angle,
                    "publish_slot": (pub_raw[11:16] if len(pub_raw) >= 16 else now_local.strftime("%H:%M")),
                },
                "snapshots": {"6h": None, "24h": None, "48h": None},
            }
            records.append(entry)
            by_id[vid] = entry
            by_yt_id[vid] = entry

        entry["youtube_video_id"] = vid
        entry["views_live"] = views
        entry["likes_live"] = likes
        entry["comments_live"] = comments
        entry["engagement_rate_live"] = eng_rate
        entry["views_per_hour"] = vph
        entry["age_hours"] = round(age_hours, 2)
        entry["angle"] = angle
        entry["last_live_sync_at"] = now_local.isoformat()

        snaps = entry.setdefault("snapshots", {"6h": None, "24h": None, "48h": None})
        snap_payload = {
            "views": views,
            "likes": likes,
            "comments": comments,
            "vph": vph,
            "engagement_rate": eng_rate,
            "captured_at": now_local.isoformat(),
        }
        if age_hours >= 5.5 and snaps.get("6h") is None:
            snaps["6h"] = snap_payload
        if age_hours >= 23.0 and snaps.get("24h") is None:
            snaps["24h"] = snap_payload
        if age_hours >= 47.0 and snaps.get("48h") is None:
            snaps["48h"] = snap_payload

        if age_hours >= 23.0 and entry.get("views_24h") is None:
            entry["views_24h"] = views
            entry["likes_24h"] = likes
            entry["comments_24h"] = comments
            entry["engagement_rate_24h"] = eng_rate
            entry["metrics_fetched_at"] = now_local.isoformat()

        live_items.append({
            "video_id": vid,
            "title": v.get("title", ""),
            "url": v.get("url", f"https://youtu.be/{vid}"),
            "views": views,
            "likes": likes,
            "comments": comments,
            "age_hours": round(age_hours, 1),
            "views_per_hour": vph,
            "engagement_score": eng_score,
            "angle": angle,
            "launch_rank": round(vph * 2.0 + eng_score * 5.0 + views * 0.25, 2),
        })

    _save_records(records)
    live_items.sort(key=lambda x: x["launch_rank"], reverse=True)
    return live_items


def detect_and_apply_winning_angles(limit: int = 12) -> Dict[str, Any]:
    """
    Detecta qué clips y ángulos están rindiendo mejor en las últimas horas y
    actualiza data/viral_playbook.json para replicar ese ángulo en las próximas rondas.
    """
    live_items = sync_live_channel_metrics(limit=limit)
    if not live_items:
        return {"ok": False, "reason": "Sin datos recientes en YouTube Data API.", "top_clips": []}

    winner = live_items[0]
    win_angle = winner["angle"]
    # Si el #1 es gameplay_general pero hay un candidato en el top con ángulo específico y tracción relevante, considerarlo
    if win_angle == "gameplay_general":
        for cand in live_items[1:4]:
            if cand["angle"] != "gameplay_general" and cand["views"] > 0:
                win_angle = cand["angle"]
                break

    # Escudo Anti-Monocultura / Saturación de Contenido:
    # Si este ángulo ya acapara >= 2 de los últimos 4 vídeos en el canal, rotar al siguiente mejor
    # clip con un ángulo fresco para mantener la variedad editorial y no cansar a la audiencia.
    try:
        from .config import PROCESSED_FILE
        import json
        if PROCESSED_FILE.exists():
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                hist = json.load(f)
                recent_pub = [e for e in hist if e.get("status") in ("completed", "published_via_copilot")][-5:]
                recent_published_angles = [
                    classify_clip_angle(e.get("title") or e.get("original_title") or "", e.get("creator") or "")
                    for e in recent_pub
                ]
                if recent_published_angles.count(win_angle) >= 2:
                    for cand in live_items:
                        c_angle = cand.get("angle")
                        if c_angle != win_angle and c_angle != "gameplay_general" and recent_published_angles.count(c_angle) < 2:
                            winner = cand
                            win_angle = c_angle
                            break
    except Exception as e:
        print(f"[PerformanceTracker] Warning evaluando rotación anti-monocultura: {e}")

    priority_kws = list(ANGLE_CATALOG.get(win_angle, ()))[:10]
    angle_label = ANGLE_LABELS.get(win_angle, win_angle)

    try:
        from .learning_engine import load_viral_playbook, save_viral_playbook
        pb = load_viral_playbook()
        heur = pb.setdefault("active_heuristics", {})
        plat_alphas = pb.setdefault("platform_alphas", {})
        plat_alphas["youtube"] = {
            "priority_angle": win_angle,
            "priority_angle_label": angle_label,
            "priority_keywords": priority_kws,
            "winning_clip": {
                "video_id": winner["video_id"],
                "title": winner["title"],
                "views": winner["views"],
                "views_per_hour": winner["views_per_hour"],
                "likes": winner["likes"],
                "comments": winner["comments"],
            },
            "last_winner_sync": datetime.now().isoformat(),
        }
        heur["priority_angle"] = win_angle
        heur["priority_angle_label"] = angle_label
        tt_kws = (plat_alphas.get("tiktok") or {}).get("priority_keywords") or []
        merged_global = []
        for kw in list(priority_kws[:6]) + list(tt_kws[:6]):
            if kw not in merged_global:
                merged_global.append(kw)
        heur["priority_keywords"] = merged_global[:12] if merged_global else priority_kws
        heur["winning_clip"] = plat_alphas["youtube"]["winning_clip"]
        heur["last_winner_sync"] = plat_alphas["youtube"]["last_winner_sync"]
        save_viral_playbook(pb)
    except Exception as e:
        print(f"[PerformanceTracker] Warning actualizando playbook ganador: {e}")

    return {
        "ok": True,
        "winner": winner,
        "priority_angle": win_angle,
        "priority_angle_label": angle_label,
        "priority_keywords": priority_kws,
        "top_clips": live_items[:5],
    }


def detect_outliers(min_records: int = 6) -> Dict[str, Any]:
    """
    Detecta outliers positivos y negativos en el rendimiento real del canal.
    Un outlier positivo tiene >2x la mediana de vistas; uno negativo <0.3x.
    Retorna patrones accionables para recalibrar el scoring.
    """
    records = _load_records()
    with_metrics = [r for r in records if r.get("views_24h") is not None and r["views_24h"] > 0]
    if len(with_metrics) < min_records:
        return {"ok": False, "reason": f"Insuficientes registros con metricas ({len(with_metrics)}/{min_records})"}

    views_list = sorted([r["views_24h"] for r in with_metrics])
    median_views = views_list[len(views_list) // 2]
    if median_views <= 0:
        return {"ok": False, "reason": "Mediana de vistas es 0"}

    positive_outliers = [r for r in with_metrics if r["views_24h"] > median_views * 2.0]
    negative_outliers = [r for r in with_metrics if r["views_24h"] < median_views * 0.3]

    # Extraer angulos ganadores y perdedores
    pos_angles = [classify_clip_angle(r.get("title", "")) for r in positive_outliers]
    neg_angles = [classify_clip_angle(r.get("title", "")) for r in negative_outliers]

    return {
        "ok": True,
        "total_records": len(with_metrics),
        "median_views": median_views,
        "positive_outliers": len(positive_outliers),
        "negative_outliers": len(negative_outliers),
        "winning_angles": list(set(pos_angles)),
        "losing_angles": list(set(neg_angles)),
        "top_performer": max(with_metrics, key=lambda r: r["views_24h"]) if with_metrics else None,
        "worst_performer": min(with_metrics, key=lambda r: r["views_24h"]) if with_metrics else None,
    }


def recalibrate_scoring_weights() -> Dict[str, Any]:
    """
    Feedback Loop autonomo: analiza outliers y ajusta el playbook
    para priorizar angulos ganadores y penalizar los perdedores.
    Se invoca desde el ciclo de learning_engine o desde el scheduler.
    """
    from .config import ENABLE_FEEDBACK_LOOP
    if not ENABLE_FEEDBACK_LOOP:
        return {"ok": False, "reason": "ENABLE_FEEDBACK_LOOP desactivado"}

    analysis = detect_outliers()
    if not analysis.get("ok"):
        return analysis

    winning = analysis.get("winning_angles", [])
    losing = analysis.get("losing_angles", [])
    median = analysis.get("median_views", 0)

    if not winning and not losing:
        return {"ok": True, "action": "no_adjustment", "reason": "Sin outliers claros"}

    try:
        from .learning_engine import load_viral_playbook, save_viral_playbook
        pb = load_viral_playbook()
        fb = pb.setdefault("feedback_loop", {})
        fb["last_run"] = datetime.now().isoformat()
        fb["median_views_24h"] = median
        fb["total_records_analyzed"] = analysis["total_records"]

        # Registrar angulos ganadores como boost y perdedores como penalizacion
        if winning:
            fb["boosted_angles"] = winning
        if losing:
            fb["penalized_angles"] = losing

        # Inyectar keywords de angulos ganadores en priority_keywords del playbook
        heur = pb.setdefault("active_heuristics", {})
        existing_kws = heur.get("priority_keywords", [])
        for angle in winning:
            angle_kws = list(ANGLE_CATALOG.get(angle, ()))[:5]
            for kw in angle_kws:
                if kw not in existing_kws:
                    existing_kws.append(kw)
        heur["priority_keywords"] = existing_kws[:15]

        # Registrar en avoid_keywords los terminos de angulos perdedores (maximo 5)
        if losing:
            avoid = heur.get("avoid_keywords", [])
            for angle in losing:
                label = ANGLE_LABELS.get(angle, angle)
                if label not in avoid:
                    avoid.append(label)
            heur["avoid_keywords"] = avoid[:8]

        save_viral_playbook(pb)
        action = f"boost={winning}, penalize={losing}"
        print(f"[Feedback Loop] Recalibrado: {action} (mediana={median} vistas/24h)")
        return {"ok": True, "action": action, "median": median, "analysis": analysis}

    except Exception as e:
        print(f"[Feedback Loop] Error recalibrando: {e}")
        return {"ok": False, "reason": str(e)}


def format_winner_replication_report(summary: Dict[str, Any]) -> str:
    """Formatea el informe táctico de clips ganadores y réplica para Telegram."""
    if not summary.get("ok"):
        return f"⚠️ *Radar de Ganadores:* {summary.get('reason', 'Sin métricas disponibles aún.')}"

    top_clips = summary.get("top_clips", [])
    winner = summary.get("winner", {})
    label = summary.get("priority_angle_label", "Gameplay")
    lines = [
        "🏆 *RADAR DE CLIPS GANADORES & RÉPLICA AUTOMÁTICA*",
        "═" * 34,
        f"🎯 *Ángulo ganador actual:* `{label}`",
        "_(El selector IA ya prioriza (+18 pts) candidatos de este mismo tema en la siguiente ronda)_\n",
        "📊 *Top rendimiento reciente (@GTAVIHubExtra):*",
    ]
    for idx, c in enumerate(top_clips[:4], 1):
        medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else "•"))
        title_clean = str(c.get("title", "")).replace("*", "").replace("`", "")[:46]
        lines.append(
            f"{medal} *{title_clean}*\n"
            f"   👁 `{c['views']}` (`{c['views_per_hour']}/h`) | ❤️ `{c['likes']}` | 💬 `{c['comments']}` | _{c['age_hours']}h_"
        )
    if winner.get("url"):
        lines.append(f"\n🔗 *Clip #1:* {winner['url']}")
    return "\n".join(lines)


def detect_cross_platform_opportunities(min_views_yt: int = 5000) -> List[Dict[str, Any]]:
    """
    Detecta clips que rindieron bien en YouTube pero no se publicaron en TikTok (o viceversa).
    Retorna lista de oportunidades de re-publicación cross-platform.
    """
    records = _load_records()
    opportunities = []

    for rec in records:
        views_yt = rec.get("views_24h") or 0
        tiktok_views = rec.get("tiktok_views") or 0
        title = rec.get("title", "")
        video_id = rec.get("video_id", "")
        published_at = rec.get("published_at", "")

        if not video_id or not title:
            continue

        # Clip exitoso en YouTube pero sin presencia significativa en TikTok
        if views_yt >= min_views_yt and tiktok_views < 500:
            opportunities.append({
                "video_id": video_id,
                "title": title,
                "youtube_views": views_yt,
                "tiktok_views": tiktok_views,
                "gap": "youtube_to_tiktok",
                "reason": f"YT={views_yt} vistas pero TT={tiktok_views}. Re-publicar en TikTok.",
                "published_at": published_at,
            })

        # Clip exitoso en TikTok pero bajo en YouTube
        if tiktok_views >= 10000 and views_yt < 1000:
            opportunities.append({
                "video_id": video_id,
                "title": title,
                "youtube_views": views_yt,
                "tiktok_views": tiktok_views,
                "gap": "tiktok_to_youtube",
                "reason": f"TT={tiktok_views} vistas pero YT={views_yt}. Re-publicar en YouTube.",
                "published_at": published_at,
            })

    opportunities.sort(key=lambda x: max(x["youtube_views"], x["tiktok_views"]), reverse=True)
    return opportunities[:5]


def format_cross_platform_report() -> str:
    """Genera un reporte Telegram de oportunidades cross-platform."""
    opps = detect_cross_platform_opportunities()
    if not opps:
        return "✅ *Cross-Platform:* Sin asimetrías significativas detectadas."

    lines = [
        "🔄 *OPORTUNIDADES CROSS-PLATFORM DETECTADAS*",
        "═" * 34,
    ]
    for o in opps:
        title_clean = str(o["title"]).replace("*", "").replace("`", "")[:45]
        lines.append(
            f"• *{title_clean}*\n"
            f"   📊 YT: `{o['youtube_views']}` | TT: `{o['tiktok_views']}`\n"
            f"   💡 _{o['reason']}_"
        )
    return "\n".join(lines)


def diagnose_underperformers(views_threshold: int = 500, max_diagnose: int = 4) -> Dict[str, Any]:
    """
    Auto-diagnostica clips con bajo rendimiento, identifica la causa raiz con Gemini
    y aplica correcciones al playbook para que no se repita el patron.

    Ciclo cerrado: detectar -> diagnosticar -> corregir -> continuar.
    """
    records = _load_records()
    with_metrics = [
        r for r in records
        if r.get("views_24h") is not None and r["views_24h"] >= 0
    ]
    if len(with_metrics) < 3:
        return {"ok": False, "reason": "Insuficientes registros para diagnosticar"}

    views_list = sorted([r["views_24h"] for r in with_metrics])
    median_views = views_list[len(views_list) // 2] if views_list else 0

    # Umbral dinamico: el peor entre el threshold fijo y 0.4x la mediana
    effective_threshold = min(views_threshold, int(median_views * 0.4)) if median_views > 0 else views_threshold
    underperformers = [
        r for r in with_metrics
        if r["views_24h"] < effective_threshold
        and not r.get("diagnosed")
    ]

    if not underperformers:
        return {"ok": True, "action": "no_underperformers", "median": median_views}

    # Top performers como referencia de lo que SI funciona
    top_performers = sorted(with_metrics, key=lambda r: r["views_24h"], reverse=True)[:3]
    top_context = "\n".join(
        f"  - '{r['title'][:60]}': {r['views_24h']} vistas, {r.get('likes_24h', 0)} likes"
        for r in top_performers
    )
    under_context = "\n".join(
        f"  - '{r['title'][:60]}': {r['views_24h']} vistas, {r.get('likes_24h', 0)} likes, angulo={classify_clip_angle(r.get('title', ''))}"
        for r in underperformers[:max_diagnose]
    )

    corrections = []
    try:
        from .translator import get_gemini_client, generate_content_with_retry
        client = get_gemini_client()
        if not client:
            raise ValueError("Gemini no disponible")

        prompt = (
            "Eres el analista de rendimiento del canal GTA VI Hub Spain en YouTube Shorts/TikTok.\n\n"
            f"CLIPS QUE FUNCIONARON (referencia):\n{top_context}\n\n"
            f"CLIPS QUE FRACASARON (<{effective_threshold} vistas/24h):\n{under_context}\n\n"
            f"Mediana del canal: {median_views} vistas/24h.\n\n"
            "Analiza cada clip fracasado y responde SOLO con JSON array:\n"
            '[{"title": "...", "cause": "titulo generico|hook debil|angulo saturado|timing malo|duracion inadecuada|contenido irrelevante", '
            '"fix": "correccion concreta para el playbook", '
            '"avoid_pattern": "patron a evitar en titulos futuros"}]\n'
            "Se breve y accionable. Max 1 frase por campo."
        )

        resp = generate_content_with_retry(
            client=client,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        raw = (getattr(resp, "text", "") or "").strip()
        corrections = json.loads(raw)
        if not isinstance(corrections, list):
            corrections = [corrections]
    except Exception as e:
        # Fallback heuristico sin Gemini
        print(f"[AutoDiagnosis] Gemini no disponible ({e}), usando heuristicas.")
        for r in underperformers[:max_diagnose]:
            title = r.get("title", "")
            dur = float(r.get("duration") or r.get("clip_duration") or 0)
            cause = "titulo generico"
            fix = "Usar titulo con dato especifico y numero"
            if dur > 45:
                cause = "duracion inadecuada"
                fix = "Priorizar clips de 18-28s para Shorts"
            elif dur < 10:
                cause = "duracion inadecuada"
                fix = "Clips demasiado cortos sin contexto"
            elif len(title) < 25:
                cause = "titulo generico"
                fix = "Titulo mas largo con detalle concreto y emoji"
            corrections.append({
                "title": title[:60],
                "cause": cause,
                "fix": fix,
                "avoid_pattern": title[:30].lower()
            })

    # Aplicar correcciones al playbook
    applied = []
    try:
        from .learning_engine import load_viral_playbook, save_viral_playbook
        pb = load_viral_playbook()
        fb = pb.setdefault("feedback_loop", {})
        diagnostics = fb.setdefault("underperformer_diagnostics", [])
        avoid_patterns = fb.get("title_avoid_patterns", [])

        for corr in corrections[:max_diagnose]:
            diag_entry = {
                "timestamp": datetime.now().isoformat(),
                "title": corr.get("title", ""),
                "cause": corr.get("cause", ""),
                "fix": corr.get("fix", ""),
            }
            diagnostics.append(diag_entry)
            applied.append(diag_entry)

            avoid = corr.get("avoid_pattern", "")
            if avoid and len(avoid) > 5 and avoid not in avoid_patterns:
                avoid_patterns.append(avoid)

        fb["title_avoid_patterns"] = avoid_patterns[-15:]
        fb["underperformer_diagnostics"] = diagnostics[-20:]
        fb["last_diagnosis"] = datetime.now().isoformat()
        save_viral_playbook(pb)
    except Exception as e:
        print(f"[AutoDiagnosis] Error actualizando playbook: {e}")

    # Marcar diagnosticados para no repetir
    ids_diagnosed = {r.get("video_id") for r in underperformers[:max_diagnose]}
    for r in records:
        if r.get("video_id") in ids_diagnosed:
            r["diagnosed"] = True
    _save_records(records)

    print(f"[AutoDiagnosis] {len(applied)} clips diagnosticados y correcciones aplicadas al playbook.")
    return {
        "ok": True,
        "action": "diagnosed_and_corrected",
        "diagnosed_count": len(applied),
        "median": median_views,
        "threshold": effective_threshold,
        "corrections": applied,
    }


def _effective_views(rec: Dict[str, Any]) -> int:
    yt_v = rec.get("views_live") if rec.get("views_live") is not None else (rec.get("views_24h") or 0)
    tt_v = rec.get("tiktok_views") or 0
    return int(yt_v or 0) + int(tt_v or 0)


def generate_weekly_scorecard(days: int = 7, update_playbook: bool = True) -> Dict[str, Any]:
    """
    Genera un scorecard A/B de los últimos `days` días con Top 3, Bottom 3,
    rendimiento por formato (`source_type`), por tema (`topic`/`angle`) y por franja horaria.
    Opcionalmente actualiza `data/viral_playbook.json`.
    """
    records = _load_records()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    recent: List[Dict[str, Any]] = []

    for r in records:
        pub = r.get("published_at") or ""
        in_window = True
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.astimezone()
                if dt.astimezone(timezone.utc) < cutoff:
                    in_window = False
            except Exception:
                in_window = True
        if in_window and (
            r.get("views_live") is not None
            or r.get("views_24h") is not None
            or r.get("tiktok_views") is not None
        ):
            recent.append(r)

    if not recent:
        return {"ok": False, "days": days, "total_clips": 0, "top": [], "bottom": [], "by_topic": {}, "by_source": {}, "by_slot": {}}

    ranked = sorted(recent, key=_effective_views, reverse=True)
    top3 = [
        {
            "title": (r.get("title") or r.get("video_id") or "?")[:55],
            "yt_views": int(r.get("views_live") if r.get("views_live") is not None else (r.get("views_24h") or 0)),
            "tt_views": int(r.get("tiktok_views") or 0),
            "total_views": _effective_views(r),
            "topic": (r.get("experiment") or {}).get("topic") or r.get("angle") or classify_clip_angle(r.get("title", "")),
            "source_type": (r.get("experiment") or {}).get("source_type") or ("native_short" if r.get("is_short") else "16:9_multibeat"),
        }
        for r in ranked[:3]
    ]
    bottom3 = [
        {
            "title": (r.get("title") or r.get("video_id") or "?")[:55],
            "yt_views": int(r.get("views_live") if r.get("views_live") is not None else (r.get("views_24h") or 0)),
            "tt_views": int(r.get("tiktok_views") or 0),
            "total_views": _effective_views(r),
            "topic": (r.get("experiment") or {}).get("topic") or r.get("angle") or classify_clip_angle(r.get("title", "")),
        }
        for r in (ranked[-3:] if len(ranked) > 3 else [])
    ]

    def _agg_bucket(key_fn) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, List[int]] = {}
        for r in recent:
            k = key_fn(r)
            buckets.setdefault(k, []).append(_effective_views(r))
        return {
            k: {"clips": len(vals), "avg_views": round(sum(vals) / len(vals), 1), "total_views": sum(vals)}
            for k, vals in sorted(buckets.items(), key=lambda kv: sum(kv[1]) / len(kv[1]), reverse=True)
        }

    by_topic = _agg_bucket(lambda r: (r.get("experiment") or {}).get("topic") or r.get("angle") or classify_clip_angle(r.get("title", "")))
    by_source = _agg_bucket(lambda r: (r.get("experiment") or {}).get("source_type") or ("native_short" if r.get("is_short") else "16:9_multibeat"))
    by_slot = _agg_bucket(lambda r: ((r.get("experiment") or {}).get("publish_slot") or (r.get("published_at") or "")[11:13] or "??")[:2] + ":00")

    scorecard = {
        "ok": True,
        "days": days,
        "generated_at": datetime.now().isoformat(),
        "total_clips": len(recent),
        "total_views": sum(_effective_views(r) for r in recent),
        "top": top3,
        "bottom": bottom3,
        "by_topic": by_topic,
        "by_source": by_source,
        "by_slot": by_slot,
    }

    if update_playbook:
        try:
            from .learning_engine import load_viral_playbook, save_viral_playbook
            pb = load_viral_playbook()
            heur = pb.setdefault("active_heuristics", {})
            heur["ab_tracking_summary"] = {
                "updated_at": scorecard["generated_at"],
                "days": days,
                "total_clips": scorecard["total_clips"],
                "best_topic": next(iter(by_topic.keys()), None),
                "best_source_type": next(iter(by_source.keys()), None),
                "best_hour_slot": next(iter(by_slot.keys()), None),
            }
            save_viral_playbook(pb)
        except Exception as e:
            print(f"[PerformanceTracker] Aviso actualizando ab_tracking_summary en playbook: {e}")

    return scorecard


def format_weekly_scorecard_telegram(scorecard: Dict[str, Any]) -> str:
    """Formatea el scorecard semanal en texto compacto (sin multimedia) para Telegram."""
    if not scorecard.get("ok"):
        return f"📊 *Scorecard Tracking ({scorecard.get('days', 7)}d)*\nSin clips con métricas registradas todavía."

    lines = [
        f"📊 *Scorecard Tracking ({scorecard['days']} días)*",
        f"🎬 Clips medidos: *{scorecard['total_clips']}* | 👁️ Vistas totales (YT+TT): *{scorecard['total_views']}*",
        "",
        "🏆 *TOP 3:*",
    ]
    for i, c in enumerate(scorecard.get("top", []), 1):
        lines.append(f"{i}. {c['title']} — *{c['total_views']}* (YT:{c['yt_views']} / TT:{c['tt_views']}) `[{c['source_type']}]`")

    if scorecard.get("bottom"):
        lines.append("")
        lines.append("📉 *BOTTOM 3:*")
        for c in scorecard["bottom"]:
            lines.append(f"• {c['title']} — {c['total_views']} (YT:{c['yt_views']} / TT:{c['tt_views']})")

    if scorecard.get("by_topic"):
        best_t, st = next(iter(scorecard["by_topic"].items()))
        lines.append("")
        lines.append(f"🎯 *Mejor tema:* `{best_t}` (media {st['avg_views']} vistas en {st['clips']} clips)")
    if scorecard.get("by_source"):
        best_s, ss = next(iter(scorecard["by_source"].items()))
        lines.append(f"🎞️ *Mejor formato:* `{best_s}` (media {ss['avg_views']} vistas)")
    if scorecard.get("by_slot"):
        best_h, sh = next(iter(scorecard["by_slot"].items()))
        lines.append(f"⏰ *Mejor franja:* `{best_h}` (media {sh['avg_views']} vistas)")

    return "\n".join(lines)

