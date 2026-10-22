import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import DATA_DIR, OUTPUT_DIR, TEMP_DIR
from .channels import mark_video_processed
from .cleaner import clean_uploaded_video_file, clean_temp_directory

COPILOT_STATE_FILE = DATA_DIR / "copilot_state.json"
PENDING_DIR = DATA_DIR / "pending_approvals"
PENDING_DIR.mkdir(parents=True, exist_ok=True)

def is_copilot_enabled() -> bool:
    """Verifica si el modo Co-Pilot (aprobación previa manual) está activo."""
    if not COPILOT_STATE_FILE.exists():
        return False
    try:
        with open(COPILOT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return bool(data.get("enabled", False))
    except Exception:
        return False

def set_copilot_enabled(enabled: bool):
    """Activa o desactiva el modo Co-Pilot."""
    try:
        data = {"enabled": enabled, "updated_at": datetime.now().isoformat()}
        with open(COPILOT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Co-Pilot] Error actualizando estado: {e}")

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
    data = get_pending_video(video_id)
    if not data:
        print(f"[Co-Pilot] No se encontró el vídeo pendiente {video_id}")
        return None

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
                "thumbnail_path": thumb_path if thumb_path and thumb_path.exists() else None
            },
            creator_name=creator,
            stagger_delay_minutes=stagger_delay
        )
        if multiplatform_results.get("youtube"):
            uploaded_yt_id = multiplatform_results["youtube"]
    else:
        from .uploader import upload_to_youtube
        uploaded_yt_id = upload_to_youtube(
            video_path=video_path,
            title=metadata.get("title", f"GTA 6 - {data.get('original_title')}").upper(),
            description=metadata.get("description", ""),
            privacy_status=privacy_status,
            is_short=is_short,
            thumbnail_path=thumb_path if thumb_path and thumb_path.exists() else None
        )

    # Registro en processed.json
    yt_url = f"https://youtu.be/{uploaded_yt_id}" if uploaded_yt_id else None
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
