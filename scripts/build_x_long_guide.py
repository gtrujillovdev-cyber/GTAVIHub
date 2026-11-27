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
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from src.config import DATA_DIR, OUTPUT_DIR, TEMP_DIR
from src.guide_story_compiler import (
    VisualComplianceRejectedError,
    build_multi_beat_guide_package_from_url,
)
from src.video_editor import render_final_video

X_LONG_HISTORY_FILE = DATA_DIR / "x_long_sent.json"


def _load_x_long_sent() -> set[str]:
    if not X_LONG_HISTORY_FILE.exists():
        return set()
    try:
        data = json.loads(X_LONG_HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
        if isinstance(data, dict):
            return {str(k) for k in data.keys()}
    except Exception:
        pass
    return set()


def _save_x_long_sent(vid: str) -> None:
    sent = _load_x_long_sent()
    sent.add(str(vid))
    try:
        X_LONG_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        X_LONG_HISTORY_FILE.write_text(
            json.dumps(sorted(sent), indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _pick_auto_x_long_candidates(max_candidates: int = 6) -> list[tuple[str, str, str]]:
    """
    Escanea las fuentes configuradas y devuelve hasta `max_candidates` tuplas (url, vid, creator)
    de guías 16:9 (>=65s) de GTA 6 aún no enviadas como X Long Guide.
    """
    from src.ai_selector import is_location_reward_guide
    from src.channels import fetch_all_channels, filter_repetitive_candidates

    sent_ids = _load_x_long_sent()
    raw = fetch_all_channels() or []
    filtered = filter_repetitive_candidates(raw, processed_entries=[])

    ranked = []
    for c in filtered:
        vid = str(c.get("id") or "").strip()
        url = str(c.get("url") or "").strip()
        title = str(c.get("title") or "").strip()
        creator = str(c.get("creator") or c.get("channel") or "").strip()
        dur = float(c.get("duration") or 0)
        if not vid or not url or vid in sent_ids:
            continue
        if "/shorts/" in url.lower():
            continue
        if dur and dur < 65.0:
            continue
        if not is_location_reward_guide(title):
            continue
        vph = float(c.get("vph") or c.get("views_per_hour") or c.get("views") or 0)
        ranked.append((vph, url, vid, creator))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [(u, v, cr) for _, u, v, cr in ranked[:max_candidates]]


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
    parser.add_argument("--url", default="", help="URL de guía 16:9 (>=65s) en YouTube o X.")
    parser.add_argument("--auto", action="store_true", help="Seleccionar automáticamente la mejor guía 16:9 del día.")
    parser.add_argument("--publish", action="store_true", help="Publicar directamente en X vía SocialPublisher.")
    parser.add_argument("--dry-run", action="store_true", help="Simular publicación en X.")
    parser.add_argument("--send-telegram", action="store_true", help="Enviar preview + copy limpio a Telegram.")
    args = parser.parse_args()

    if not args.url and not args.auto:
        print("[!] Debes pasar --url <URL> o --auto.")
        return 1

    targets: list[tuple[str, str, str]] = []
    if args.url:
        vid, creator = _extract_id(args.url)
        targets.append((args.url, vid, creator))
    else:
        print(f"[X Long Guide AUTO] Buscando la mejor guía 16:9 (>=65s) del día ({datetime.now().strftime('%Y-%m-%d %H:%M')})...")
        targets = _pick_auto_x_long_candidates(max_candidates=6)
        if not targets:
            print("[!] No se encontraron guías 16:9 nuevas (>=65s) elegibles para X Long Guide.")
            return 1

    pkg = None
    vid = ""
    creator = ""
    for target_url, t_vid, t_creator in targets:
        print(f"[X Long Guide] Compilando guía 45-70s (16:9) para {t_vid} (Creador: {t_creator or '?'})...")
        try:
            pkg = build_multi_beat_guide_package_from_url(target_url, t_vid, work_dir=TEMP_DIR, profile="x_long")
        except VisualComplianceRejectedError as vis_err:
            print(f"[✗ X Long Guide] Rechazado por Escudo Visual ({t_vid}): {vis_err}")
            try:
                from src.channels import record_rejected_video
                record_rejected_video(t_vid, reason=f"x_long_visual: {vis_err}")
            except Exception:
                pass
            continue
        if pkg:
            vid, creator = t_vid, t_creator
            break

    if not pkg:
        print("[!] No se pudo compilar ningún paquete X Long Guide válido.")
        return 1

    comp_mp4, srt_path, dub_mp3, plan = pkg
    title_es = plan.get("short_title_es") or f"Guía completa GTA 6 ({vid})"
    slug = re.sub(r"[^\w\s-]", "", title_es).strip()
    slug = re.sub(r"[\s_]+", "_", slug)[:48].strip("_") or vid
    out_mp4 = OUTPUT_DIR / f"X_LONG_{slug}_{vid}.mp4"

    ok = render_final_video(
        input_video=comp_mp4,
        output_video=out_mp4,
        srt_subtitles=srt_path,
        dub_audio=dub_mp3,
        force_short_format=False,  # 16:9 nativo para X (sin recortes laterales)
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
        import os
        import requests
        from src.telegram_bot import send_telegram_video
        from src.translator import sanitize_banned_words

        clean_title = sanitize_banned_words(title_es).strip()
        credit = f"Via {creator}" if creator and creator.lower() not in ("rockstar games", "?") else ""
        tags_line = "#GTA6 #GTAVI #GTAVISpain #GTA6Guias"
        parts = [clean_title]
        if credit:
            parts.append(credit)
        parts.append(tags_line)
        x_post_copy = "\n\n".join(parts)[:280]

        ok_tg = send_telegram_video(
            out_mp4,
            f"🐦 *X Long Guide listo para subir manual (16:9)*\n📹 `{out_mp4.name}`\n📦 `{size_mb:.1f} MB`\n\n👇 En el siguiente mensaje tienes el texto listo para copiar y pegar en X.",
        )
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and chat_id:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": x_post_copy},
                timeout=15,
            )
        if ok_tg:
            _save_x_long_sent(vid)
            if not (args.publish or args.dry_run):
                out_mp4.unlink(missing_ok=True)

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
