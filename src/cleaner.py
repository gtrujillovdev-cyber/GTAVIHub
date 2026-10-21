import os
import shutil
from pathlib import Path
from typing import Optional
from .config import TEMP_DIR, OUTPUT_DIR, BASE_DIR

def clean_workspace_residuals(base_dir: Optional[Path] = None):
    """
    Regla estricta 0: Limpieza total de scripts temporales, pruebas y residuos del directorio.
    Elimina cualquier archivo efímero o de depuración en la raíz, temp/ o output/.
    """
    target_dir = base_dir or BASE_DIR
    patterns = [
        "test_*",
        "frame_*",
        "scratch_*",
        "debug_*",
        "*.tmp*",
        "*_preview_*.jpg",
        "*_preview_*.png"
    ]
    
    for pat in patterns:
        # En la raíz
        for p in target_dir.glob(pat):
            if p.is_file() and p.name not in [".env", ".gitignore", "main.py", "run.sh"]:
                try:
                    p.unlink()
                    print(f"[Cleaner] Script/Archivo temporal purgado: {p.name}")
                except OSError:
                    pass
        # En output/
        if OUTPUT_DIR.exists():
            for p in OUTPUT_DIR.glob(pat):
                if p.is_file():
                    try:
                        p.unlink()
                        print(f"[Cleaner] Residuo de prueba purgado de output: {p.name}")
                    except OSError:
                        pass
        # En temp/
        if TEMP_DIR.exists():
            for p in TEMP_DIR.glob(pat):
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass

def clean_temp_directory(video_id: Optional[str] = None):
    """
    Regla estricta 1: Limpieza total de archivos temporales.
    Si se especifica video_id, borra todo lo relativo a ese vídeo.
    Si no, limpia cualquier residuo en TEMP_DIR.
    """
    clean_workspace_residuals()
    
    if not TEMP_DIR.exists():
        return

    if video_id:
        for p in TEMP_DIR.glob(f"*{video_id}*"):
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
            except OSError as e:
                print(f"[Cleaner] Error eliminando {p.name}: {e}")
    else:
        for p in TEMP_DIR.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
            except OSError as e:
                print(f"[Cleaner] Error limpiando temp {p.name}: {e}")

def clean_uploaded_video_file(video_path: Path):
    """
    Regla estricta 2: Una vez subido el vídeo a YouTube con éxito,
    se elimina el archivo pesado .mp4 local para no consumir disco en el Mac.
    Se conserva el informe JSON y la miniatura JPG.
    """
    try:
        if video_path and video_path.exists() and video_path.is_file():
            size_mb = video_path.stat().st_size / (1024 * 1024)
            video_path.unlink()
            print(f"[✓ Cleaner] Archivo pesado {video_path.name} ({size_mb:.1f} MB) eliminado del disco tras la subida.")
    except Exception as e:
        print(f"[Cleaner] No se pudo eliminar {video_path}: {e}")

def enforce_storage_limits(max_mb: int = 1000):
    """
    Regla estricta 3: Auditoría preventiva de almacenamiento y limpieza.
    Garantiza que la carpeta de output y temp no superen el límite fijado (1GB por defecto).
    """
    clean_temp_directory()
    clean_workspace_residuals()
    
    if not OUTPUT_DIR.exists():
        return

    # Si hay mp4 antiguos en output sin subir, listar por fecha y purgar los más viejos
    mp4_files = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime)
    total_size = sum(f.stat().st_size for f in mp4_files) / (1024 * 1024)

    while total_size > max_mb and mp4_files:
        oldest = mp4_files.pop(0)
        size = oldest.stat().st_size / (1024 * 1024)
        try:
            oldest.unlink()
            total_size -= size
            print(f"[Cleaner] Purga de espacio: Eliminado {oldest.name} (-{size:.1f} MB)")
        except OSError:
            pass