import os
import json
import fcntl
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import DATA_DIR, OUTPUT_DIR, TEMP_DIR, COPILOT_AUTO_APPROVE_SECONDS
from .channels import mark_video_processed
from .cleaner import clean_uploaded_video_file, clean_temp_directory

_PUBLISH_LOCK = threading.Lock()
COPILOT_STATE_FILE = DATA_DIR / "copilot_state.json"
PENDING_DIR = DATA_DIR / "pending_approvals"
PENDING_DIR.mkdir(parents=True, exist_ok=True)

def is_copilot_enabled() -> bool:
    """Verifica si el modo Co-Pilot (aprobación previa manual) está activo (True por defecto)."""
    if not COPILOT_STATE_FILE.exists():
        return True
    try:
        with open(COPILOT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return bool(data.get("enabled", True))
    except Exception:
        return True

def set_copilot_enabled(enabled: bool):
    """Activa o desactiva el modo Co-Pilot."""
    try:
        data = {"enabled": enabled, "updated_at": datetime.now().isoformat()}
        with open(COPILOT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Co-Pilot] Error actualizando estado: {e}")


def evaluate_autopilot_eligibility(
    candidate_score: float,
    recent_metrics: list,
    has_static_penalty: bool = False,
    min_views: int = 1000,
    min_likes: int = 25,
    min_likes_ratio: float = 0.025,
    circuit_breaker_ratio: float = 0.015,
    min_viewed_rate: float = 0.70,
) -> Dict[str, Any]:
    """
    Evalúa si un candidato puede publicarse en Autopilot desatendido con garantías estadísticas:
    - Exige score >= 90 sin penalización por pantalla estática.
    - Exige muestra mínima (views >= 1000 o likes >= 25) para evitar ruido de muestras pequeñas.
    - Exige likes/views >= 2.5% (y viewed_rate >= 70% si está disponible en métricas).
    - Dispara circuit breaker y reactiva Co-Pilot si los últimos 5+ clips caen <= 1.5%.
    """
    window = list(recent_metrics or [])[-5:]
    total_views = sum(int(m.get("views") if m.get("views") is not None else (m.get("views_24h") or 0)) for m in window)
    total_likes = sum(int(m.get("likes") if m.get("likes") is not None else (m.get("likes_24h") or 0)) for m in window)
    trailing_ratio = (total_likes / total_views) if total_views > 0 else 0.0

    viewed_rates = [float(m["viewed_rate"]) for m in window if m.get("viewed_rate") is not None]
    avg_viewed_rate = (sum(viewed_rates) / len(viewed_rates)) if viewed_rates else None

    if len(window) >= 5 and total_views >= min_views and trailing_ratio <= circuit_breaker_ratio:
        set_copilot_enabled(True)
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": True,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": f"Circuit breaker: ratio {trailing_ratio:.2%} <= {circuit_breaker_ratio:.2%} en últimos 5 clips",
        }

    if has_static_penalty:
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": False,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": "Penalización por pantalla estática activa",
        }

    if float(candidate_score or 0) < 90.0:
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": False,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": f"Score editorial insuficiente ({candidate_score} < 90)",
        }

    if total_views < min_views and total_likes < min_likes:
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": False,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": f"Muestra estadística insuficiente ({total_views} vistas, {total_likes} likes)",
        }

    if avg_viewed_rate is not None and avg_viewed_rate < min_viewed_rate:
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": False,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": f"Retención inicial baja (Viewed {avg_viewed_rate:.1%} < {min_viewed_rate:.0%})",
        }

    if trailing_ratio < min_likes_ratio:
        return {
            "allow_autopilot": False,
            "circuit_breaker_triggered": False,
            "trailing_likes_ratio": round(trailing_ratio, 4),
            "reason": f"Ratio likes/views insuficiente ({trailing_ratio:.2%} < {min_likes_ratio:.2%})",
        }

    return {
        "allow_autopilot": True,
        "circuit_breaker_triggered": False,
        "trailing_likes_ratio": round(trailing_ratio, 4),
        "reason": "Elegible para Autopilot desatendido",
    }

def stage_pending_video(
    video_id: str,
    original_url: str,
    original_title: str,
    creator_name: str,
    output_video_path: Path,
    thumbnail_path: Optional[Path],
    metadata: Dict[str, Any],
    is_short: bool,
    mode: str,
    publish_all: bool = False,
    privacy_status: str = "private",
    stagger_delay: int = 12,
    keep_local_video: bool = False
) -> Path:
    """Guarda un vídeo renderizado en espera de revisión humana antes de publicar."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    item_file = PENDING_DIR / f"{video_id}.json"
    
    payload = {
        "video_id": video_id,
        "original_url": original_url,
        "original_title": original_title,
        "creator_name": creator_name,
        "output_video": str(output_video_path.resolve()),
        "thumbnail": str(thumbnail_path.resolve()) if thumbnail_path and thumbnail_path.exists() else None,
        "metadata": metadata,
        "is_short": is_short,
        "mode": mode,
        "publish_all": publish_all,
        "privacy_status": privacy_status,
        "stagger_delay": stagger_delay,
        "keep_local_video": keep_local_video,
        "staged_at": datetime.now().isoformat()
    }
    
    with open(item_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    return item_file

def get_pending_video(video_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene los datos de un vídeo pendiente por su ID."""
    item_file = PENDING_DIR / f"{video_id}.json"
    if not item_file.exists():
        return None
    try:
        with open(item_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def get_all_pending_videos() -> List[Dict[str, Any]]:
    """Obtiene la lista de todos los vídeos pendientes de aprobación."""
    results = []
    if not PENDING_DIR.exists():
        return results
    for f in PENDING_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                results.append(json.load(fp))
        except Exception:
            pass
    return results

def approve_and_publish_video(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Ejecuta la aprobación y publicación de un vídeo en espera:
    1. Lee los metadatos y rutas guardadas.
    2. Sube a YouTube o multiplataforma.
    3. Registra en processed.json.
    4. Purga el archivo de staging y vídeo local (si corresponde).
    """
    # Lock POSIX cross-process para impedir dobles subidas entre --auto y --telegram
    os_lock_path = DATA_DIR / ".publish.lock"
    os_lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(os_lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            with _PUBLISH_LOCK:
                data = get_pending_video(video_id)
                if not data:
                    print(f"[Co-Pilot] No se encontró el vídeo pendiente {video_id}")
                    return None
                if data.get("status") == "publishing":
                    print(f"[Co-Pilot] El vídeo {video_id} ya se encuentra en proceso de publicación.")
                    return None

                try:
                    data["status"] = "publishing"
                    (PENDING_DIR / f"{video_id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    video_path = Path(data["output_video"])
    thumb_path = Path(data["thumbnail"]) if data.get("thumbnail") else None
    metadata = data.get("metadata", {})
    creator = data.get("creator_name", "Rockstar Games")
    publish_all = data.get("publish_all", False)
    privacy_status = data.get("privacy_status", "private")
    stagger_delay = data.get("stagger_delay", 12)
    is_short = data.get("is_short", False)
    keep_local_video = data.get("keep_local_video", False)

    uploaded_yt_id = None
    multiplatform_results = {}

    if publish_all:
        from .social_publisher import SocialPublisher
        publisher = SocialPublisher(dry_run=False)
        multiplatform_results = publisher.publish_all(
            video_path=video_path,
            metadata={
                "title": metadata.get("title", f"GTA 6 - {data.get('original_title')}").upper(),
                "description": metadata.get("description", ""),
                "thumbnail_path": thumb_path if thumb_path and thumb_path.exists() else None,
                "pinned_comment": metadata.get("pinned_comment"),
                "debate_question": metadata.get("debate_question", ""),
                "tags": metadata.get("tags"),
                "original_url": data.get("original_url", ""),
                "privacy": privacy_status,
                "mode": metadata.get("mode") or data.get("mode", "subs"),
                "has_voiceover": metadata.get("has_voiceover", False) or data.get("mode") in ["dub", "voice"],
                "is_transformed_visual": bool(metadata.get("is_transformed_visual", False)),
                "block_instagram": metadata.get("block_instagram", False),
                "allowed_platforms": metadata.get("allowed_platforms"),
                "target_channel": "youtube_extra"
            },
            creator_name=creator,
            stagger_delay_minutes=stagger_delay
        )
        if multiplatform_results.get("youtube"):
            yt_res = str(multiplatform_results["youtube"])
            uploaded_yt_id = yt_res.split("youtu.be/")[-1] if "youtu.be/" in yt_res else yt_res
    else:
        from .uploader import upload_to_youtube
        uploaded_yt_id = upload_to_youtube(
            video_path=video_path,
            title=metadata.get("title", f"GTA 6 - {data.get('original_title')}").upper(),
            description=metadata.get("description", ""),
            tags=metadata.get("tags"),
            privacy_status=privacy_status,
            is_short=is_short,
            thumbnail_path=thumb_path if thumb_path and thumb_path.exists() else None,
            pinned_comment=metadata.get("pinned_comment"),
            target_account="extra"
        )

    # Registro en processed.json (solo marcar published_via_copilot si al menos 1 plataforma devolvió URL real)
    if uploaded_yt_id:
        yt_url = str(uploaded_yt_id) if str(uploaded_yt_id).startswith("http") else f"https://youtu.be/{uploaded_yt_id}"
    else:
        yt_url = None
    has_published_any = bool(
        yt_url
        or (publish_all and any(v and str(v).startswith("http") for v in multiplatform_results.values()))
    )
    if not has_published_any:
        print(f"[Co-Pilot] ⚠️ Ninguna plataforma confirmó publicación para {video_id}. Marcando como 'upload_failed'.")
        try:
            data["status"] = "upload_failed"
            (PENDING_DIR / f"{video_id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return None
    mark_video_processed({
        "id": video_id,
        "title": data.get("original_title"),
        "creator": creator,
        "url": data.get("original_url"),
        "status": "published_via_copilot",
        "thumbnail": str(thumb_path) if thumb_path else None,
        "youtube_title": metadata.get("title", ""),
        "youtube_uploaded_url": yt_url,
        "multiplatform": multiplatform_results if publish_all else None,
        "approved_at": datetime.now().isoformat()
    })

    # Conexión con PerformanceTracker y ChannelSentinel para monitorización y bucle cerrado
    if yt_url:
        try:
            from .performance_tracker import record_published_video
            from .channel_sentinel import record_video_for_sentinel
            record_published_video(
                video_id=video_id,
                title=data.get("original_title", "GTA 6 Video"),
                youtube_url=yt_url,
                base_score=0,
                target_channel="extra"
            )
            plat_urls = {"youtube": yt_url}
            if multiplatform_results:
                for p, p_res in multiplatform_results.items():
                    if p_res and str(p_res).startswith("http"):
                        plat_urls[p] = str(p_res)
            record_video_for_sentinel(
                video_id=video_id,
                title=data.get("original_title", "GTA 6 Video"),
                archetype=metadata.get("archetype", "general"),
                target_channel="extra",
                platform_urls=plat_urls
            )
        except Exception as e:
            print(f"[Co-Pilot] Aviso registrando telemetría: {e}")

    # Limpieza
    if uploaded_yt_id and not keep_local_video:
        clean_uploaded_video_file(video_path)

    # Eliminar staging
    staged_file = PENDING_DIR / f"{video_id}.json"
    if staged_file.exists():
        staged_file.unlink()

    return {
        "video_id": video_id,
        "title": metadata.get("title", data.get("original_title")),
        "youtube_url": yt_url,
        "multiplatform": multiplatform_results
    }

def reject_and_purge_video(video_id: str) -> bool:
    """Descarta el vídeo pendiente, elimina sus archivos y lo marca como rechazado."""
    data = get_pending_video(video_id)
    if not data:
        return False

    video_path = Path(data.get("output_video", ""))
    thumb_path = Path(data.get("thumbnail", ""))

    if video_path.exists():
        try:
            video_path.unlink()
        except Exception:
            pass

    if thumb_path.exists():
        try:
            thumb_path.unlink()
        except Exception:
            pass

    # Marcar en processed.json para no insistir en descargarlo de nuevo
    mark_video_processed({
        "id": video_id,
        "title": data.get("original_title"),
        "creator": data.get("creator_name"),
        "url": data.get("original_url"),
        "status": "rejected_by_operator",
        "rejected_at": datetime.now().isoformat()
    })

    # Purgar archivo staged
    staged_file = PENDING_DIR / f"{video_id}.json"
    if staged_file.exists():
        staged_file.unlink()

    clean_temp_directory(video_id)
    return True

COPILOT_AUTO_APPROVE_TIMEOUT_MIN = int(os.getenv("COPILOT_AUTO_APPROVE_TIMEOUT_MIN", "15"))
COPILOT_AUTO_APPROVE_ENABLED = os.getenv("COPILOT_AUTO_APPROVE_ENABLED", "false").lower() in ("true", "1", "yes")

def check_and_auto_approve_expired_videos(timeout_minutes: int = COPILOT_AUTO_APPROVE_TIMEOUT_MIN) -> List[Dict[str, Any]]:
    """
    En modo Co-Pilot estricto, los vídeos NUNCA se auto-aprueban solos salvo que
    COPILOT_AUTO_APPROVE_ENABLED=true esté explícitamente configurado en .env.
    """
    if not COPILOT_AUTO_APPROVE_ENABLED:
        return []
    pending = get_all_pending_videos()
    approved = []
    now = datetime.now()
    for item in pending:
        vid_id = item.get("video_id")
        staged_str = item.get("staged_at")
        if not vid_id or not staged_str:
            continue
        try:
            staged_dt = datetime.fromisoformat(staged_str)
            diff_min = (now - staged_dt).total_seconds() / 60.0
            if diff_min >= timeout_minutes:
                print(f"[Co-Pilot] ⏱️ Tiempo de cortesía ({diff_min:.1f}m >= {timeout_minutes}m) expirado para {vid_id}. Auto-aprobando publicación...")
                res = approve_and_publish_video(vid_id)
                if res:
                    approved.append(res)
                    try:
                        from .telegram_bot import send_telegram_alert
                        title = res.get("title", vid_id)
                        send_telegram_alert(
                            f"🚀 *[Co-Pilot Auto-Aprobación]*\n"
                            f"Expiró el tiempo de cortesía de {timeout_minutes} min sin respuesta.\n"
                            f"Vídeo publicado automáticamente:\n`{str(title)[:60]}`"
                        )
                    except Exception as tg_err:
                        print(f"[Co-Pilot] Info Telegram Auto-Approve Alert: {tg_err}")
        except Exception as e:
            print(f"[Co-Pilot] Error verificando timeout de {vid_id}: {e}")

    return approved


def schedule_auto_approve_if_pending(
    video_id: str,
    timeout_sec: Optional[int] = None,
    notify_telegram: bool = True,
) -> Optional[threading.Timer]:
    """
    Programa la auto-publicación tras `timeout_sec` segundos si el operador no veta ni aprueba antes.
    Respeta COPILOT_AUTO_APPROVE_ENABLED salvo que se fuerce timeout_sec explícito en tests.
    """
    if timeout_sec is None and not COPILOT_AUTO_APPROVE_ENABLED:
        return None
    delay = COPILOT_AUTO_APPROVE_SECONDS if timeout_sec is None else int(timeout_sec)
    if delay <= 0:
        return None

    def _worker():
        pending = get_pending_video(video_id)
        if not pending or pending.get("status") == "publishing":
            return
        print(f"[Co-Pilot] ⏱️ Ventana de veto de {delay}s expirada sin rechazo para {video_id}. Publicando automáticamente...")
        res = approve_and_publish_video(video_id)
        if res and notify_telegram:
            try:
                from .telegram_bot import send_telegram_alert
                title = res.get("title", video_id)
                yt_url = res.get("youtube_url") or ""
                link_line = f"\n🔗 {yt_url}" if yt_url else ""
                send_telegram_alert(
                    f"🚀 *[Co-Pilot Auto-Publicado ({delay}s)]*\n"
                    f"`{str(title)[:65]}`{link_line}"
                )
            except Exception as tg_err:
                print(f"[Co-Pilot] Info Telegram Auto-Approve Alert: {tg_err}")

    timer = threading.Timer(delay, _worker)
    timer.daemon = False
    timer.start()
    return timer
