#!/usr/bin/env python3
"""
scripts/build_x_long_guide.py
=============================
Genera (y opcionalmente publica) una guía dedicada para X (Twitter) de 45–70s
en formato horizontal 16:9 nativo (sin recortar laterales/HUD), usando Gemini Vision
(18 fotogramas), doblaje neural ES sincronizado acto a acto, subtítulos limpios
y marca de agua VI EXTRA.

Uso:
  python3 scripts/build_x_long_guide.py --url "https://www.youtube.com/watch?v=..."
  python3 scripts/build_x_long_guide.py --url "https://www.youtube.com/watch?v=..." --publish
  python3 scripts/build_x_long_guide.py --url "https://www.youtube.com/watch?v=..." --send-telegram
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from src.config import OUTPUT_DIR, TEMP_DIR
from src.guide_story_compiler import build_multi_beat_guide_package_from_url
from src.video_editor import render_video_with_subs


def _extract_id(url: str) -> tuple[str, str]:
    res = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--impersonate", "chrome", "--no-check-certificates",
         "--print", "%(id)s", "--print", "%(uploader)s", url],
        capture_output=True, text=True, timeout=30,
    )
    lines = [l.strip() for l in (res.stdout or "").splitlines() if l.strip()]
    vid = lines[0] if lines else "xlong_clip"
    uploader = lines[1] if len(lines) > 1 else ""
    return vid, uploader


def main() -> int:
    parser = argparse.ArgumentParser(description="Compilador dedicado X Long Guide (45-70s, 16:9 nativo).")
    parser.add_argument("--url", required=True, help="URL de guía 16:9 (>=65s) en YouTube o X.")
    parser.add_argument("--publish", action="store_true", help="Publicar directamente en X vía SocialPublisher.")
    parser.add_argument("--dry-run", action="store_true", help="Simular publicación en X.")
    parser.add_argument("--send-telegram", action="store_true", help="Enviar preview a Telegram.")
    args = parser.parse_args()

    vid, creator = _extract_id(args.url)
    print(f"[X Long Guide] Compilando guía 45-70s (16:9) para {vid} (Creador: {creator or '?'})...")

    pkg = build_multi_beat_guide_package_from_url(args.url, vid, work_dir=TEMP_DIR, profile="x_long")
    if not pkg:
        print("[!] No se pudo compilar el paquete X Long Guide (verifica duración >= 65s y GEMINI_API_KEY).")
        return 1

    comp_mp4, srt_path, dub_mp3, plan = pkg
    title_es = plan.get("short_title_es") or f"Guía completa GTA 6 ({vid})"
    slug = re.sub(r"[^\w\s-]", "", title_es).strip()
    slug = re.sub(r"[\s_]+", "_", slug)[:48].strip("_") or vid
    out_mp4 = OUTPUT_DIR / f"X_LONG_{slug}_{vid}.mp4"

    ok = render_video_with_subs(
        video_path=comp_mp4,
        srt_path=srt_path,
        output_path=out_mp4,
        dub_audio=dub_mp3,
        is_vertical=False,  # 16:9 nativo para X (sin recortes laterales)
        hook_text="",
        caspahz_style=True,
    )

    for tmp_f in (comp_mp4, srt_path, dub_mp3):
        try:
            Path(tmp_f).unlink(missing_ok=True)
        except Exception:
            pass

    if not ok or not out_mp4.exists():
        print("[!] Error renderizando X Long Guide final.")
        return 1

    size_mb = out_mp4.stat().st_size / (1024 * 1024)
    print(f"[✓ X Long Guide] Listo -> {out_mp4.name} ({size_mb:.1f} MB)")

    if args.send_telegram:
        from src.telegram_bot import send_telegram_video
        send_telegram_video(
            out_mp4,
            f"🐦 *X Long Guide (45-70s · 16:9 nativo)*\n📹 `{out_mp4.name}`\n📦 `{size_mb:.1f} MB`",
        )

    if args.publish or args.dry_run:
        from src.social_publisher import SocialPublisher
        pub = SocialPublisher(dry_run=args.dry_run)
        res_url = pub.publish_to_x(
            video_path=out_mp4,
            title=title_es,
            tags=["GTA6", "GTAVI", "GTAVISpain", "GTA6Guias"],
            creator_name=creator,
        )
        print(f"[X Long Guide] Resultado X: {res_url}")
        if res_url and not args.dry_run:
            out_mp4.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
