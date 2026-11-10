#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Asegurar path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import certifi
    for _cert_var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        _cv = os.environ.get(_cert_var)
        if _cv and not os.path.exists(_cv):
            os.environ[_cert_var] = certifi.where()
except Exception:
    pass

from src.config import MAX_VIDEOS_PER_RUN, CHANNELS_FILE, is_quant_busy, get_max_videos_per_run
from src.channels import fetch_channel_candidates
from src.pipeline import process_single_video

def extract_video_id(url: str):
    """Extrae el ID de un vídeo y metadatos usando yt-dlp."""
    try:
        res = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--impersonate", "chrome", "--no-check-certificates", "--print", "%(id)s", "--print", "%(title)s", "--print", "%(uploader)s", url],
            capture_output=True, text=True, check=True
        )
        lines = res.stdout.strip().split("\n")
        v_id = lines[0].strip()
        title = lines[1].strip() if len(lines) > 1 else v_id
        uploader = lines[2].strip() if len(lines) > 2 else ""
        return v_id, title, uploader
    except Exception as e:
        print(f"[!] Error extrayendo ID de {url}: {e}")
        return "custom_video", "GTA 6 Video", ""

def main():
    parser = argparse.ArgumentParser(
        description="GTA 6 Automation Pipeline - Reposteador y Traductor Autónomo para YouTube"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Modo autónomo: Escanea los canales en channels.json y procesa los vídeos nuevos."
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Procesar un vídeo individual a partir de su enlace de YouTube."
    )
    parser.add_argument(
        "--mode",
        choices=["subs", "dub"],
        default="subs",
        help="Modo de traducción: 'subs' (subtítulos estilizados dinámicos) o 'dub' (doblaje de voz con Edge-TTS + subtítulos)."
    )
    parser.add_argument(
        "--format",
        choices=["auto", "short", "normal"],
        default="auto",
        help="Forzar formato del vídeo de salida: 'short' (9:16 vertical), 'normal' (16:9), o 'auto'."
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Subir automáticamente a YouTube al finalizar el renderizado."
    )
    parser.add_argument(
        "--privacy",
        choices=["private", "public", "unlisted"],
        default=os.getenv("YOUTUBE_PRIVACY_STATUS", "public"),
        help="Visibilidad del vídeo en YouTube al subirlo: public (por defecto), private o unlisted."
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=MAX_VIDEOS_PER_RUN,
        help=f"Número máximo de vídeos a procesar por ejecución en modo --auto (default: {MAX_VIDEOS_PER_RUN})."
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        help="Mostrar los canales configurados en channels.json."
    )
    parser.add_argument(
        "--keep-local-video",
        action="store_true",
        help="Conservar copia local del archivo .mp4 tras subirlo a YouTube (por defecto se elimina para ahorrar disco)."
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Abrir automáticamente el vídeo generado en pantalla (QuickTime) al finalizar para inspección local."
    )
    parser.add_argument(
        "--publish-all",
        action="store_true",
        help="Publicación unificada y escalonada en YouTube Shorts, TikTok e Instagram Reels."
    )
    parser.add_argument(
        "--no-copilot",
        action="store_true",
        help="Ignorar modo Co-Pilot y forzar la publicación directa sin requerir confirmación táctil en Telegram."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulación de subida segura en modo sandbox sin alterar cuentas ni gastar cuotas."
    )
    parser.add_argument(
        "--stagger-delay",
        type=int,
        default=12,
        help="Minutos de intervalo escalonado entre plataformas para evitar detección de bots (default: 12)."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Ejecutar limpieza estricta inmediata de archivos temporales y verificar límites de disco."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Mostrar panel de control, monitorización en tiempo real y cuotas de publicación."
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Auditar y repasar las políticas normativas de YouTube, TikTok y Meta para evitar strikes."
    )
    parser.add_argument(
        "--login-social",
        action="store_true",
        help="Abrir asistente de terminal para iniciar sesión y guardar cookies de TikTok e Instagram."
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Iniciar el bot de control remoto y notificaciones de Telegram."
    )
    parser.add_argument(
        "--launch-mode",
        action="store_true",
        help="Modo de Alta Frecuencia para el Día del Estreno (priorización hiper-agresiva por velocidad de vistas y frescura en tiempo real)."
    )
    parser.add_argument(
        "--radar", "--viral-radar",
        dest="viral_radar",
        action="store_true",
        help="Escanea el Radar Viral en busca de los clips y canales con mayor engagement."
    )
    parser.add_argument(
        "--auto-viral",
        action="store_true",
        help="Ingesta y procesa automáticamente el clip #1 más viral del Radar."
    )
    parser.add_argument(
        "--update-deals",
        action="store_true",
        help="Sincroniza y actualiza las ofertas de hardware y periféricos de Amazon para GTA VI (ciclo de 3 días)."
    )

    args = parser.parse_args()

    # Timeout global de sockets para evitar cuelgues indefinidos en APIs (Google, Telegram, etc.)
    import socket
    socket.setdefaulttimeout(35)

    # Prioridad de cortesía en el planificador de CPU para convivir con GaTDSEQ
    try:
        current_nice = os.nice(0)
        if current_nice < 15:
            os.nice(15 - current_nice)
    except Exception:
        pass

    # Lockfile y guardia de cadencia diaria para ejecuciones autónomas
    if args.auto or args.auto_viral:
        lock_file = Path("/tmp/gtavihub_pipeline.lock")
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text().strip())
                os.kill(old_pid, 0)
                print(f"[!] Ya existe una ejecución de pipeline en curso (PID: {old_pid}). Abortando para evitar solapamientos.")
                return
            except (OSError, ValueError):
                pass
        lock_file.write_text(str(os.getpid()))
        import atexit
        atexit.register(lambda: lock_file.unlink(missing_ok=True) if lock_file.exists() else None)

        from src.channels import get_daily_published_count
        from src.config import MAX_DAILY_UPLOADS
        daily_count = get_daily_published_count()
        if daily_count >= MAX_DAILY_UPLOADS and not args.dry_run:
            print(f"[Anti-Spam Shield] Límite diario alcanzado ({daily_count}/{MAX_DAILY_UPLOADS} vídeos en 24h). Omitiendo tanda para proteger el canal.")
            return

    if args.telegram:
        from src.telegram_bot import start_telegram_bot_daemon
        start_telegram_bot_daemon()
        return

    if args.update_deals:
        from src.deal_scanner import scan_and_update_deals
        print("\n[*] Ejecutando escáner y sincronización de ofertas de Amazon (ciclo 3 días)...")
        res = scan_and_update_deals(force=True, notify_telegram=True)
        print(f"[✓] {res['message']} (Total ofertas: {res.get('total_deals', 0)})")
        print(res.get("report", ""))
        return

    if args.viral_radar:
        from src.viral_discovery import scan_viral_radar, print_viral_leaderboard
        print("[*] Iniciando escaneo del Radar Viral de GTA 6...")
        candidates = scan_viral_radar(max_candidates=10)
        print_viral_leaderboard(candidates)
        return

    if args.auto_viral:
        if not args.publish_all and not args.upload:
            args.publish_all = True
            args.upload = True
        from src.viral_discovery import scan_viral_radar
        from src.channels import mark_video_processed
        print("[*] Buscando el clip #1 de mayor engagement viral para ingesta inmediata...")
        candidates = scan_viral_radar(max_candidates=5)
        if candidates:
            top_clip = candidates[0]
            print(f"[🔥] Seleccionado: '{top_clip['title']}' (Score: {top_clip['score']}/100) de {top_clip['uploader']}")
            res = process_single_video(
                url=top_clip["url"],
                video_id=top_clip["id"],
                original_title=top_clip["title"],
                creator_name=top_clip["uploader"],
                mode=args.mode,
                force_short=True if (args.publish_all or top_clip.get("is_short")) else None,
                auto_upload=args.upload,
                privacy_status=args.privacy,
                keep_local_video=args.keep_local_video,
                publish_all=args.publish_all,
                dry_run=args.dry_run,
                stagger_delay=args.stagger_delay,
                copilot_mode=False if args.no_copilot else None
            )
            # Si el procesamiento falló, marcar como procesado para evitar bucle infinito
            if res is None:
                mark_video_processed({
                    "id": top_clip["id"],
                    "title": top_clip["title"],
                    "creator": top_clip["uploader"],
                    "status": "skipped",
                    "reason": "processing_failed"
                })
                print(f"[*] Vídeo {top_clip['id']} marcado como skipped para evitar reselección.")
            return
        else:
            print("[*] No se encontraron clips virales en el radar con score suficiente. Activando fallback a canales monitoreados...")
            args.auto = True

    if args.status:
        from src.monitor import print_pipeline_dashboard
        print_pipeline_dashboard()
        return

    if args.audit:
        from src.compliance_auditor import ComplianceAuditor
        ComplianceAuditor.print_compliance_scorecard()
        return

    if args.login_social:
        from src.social_publisher import open_login_assistant
        open_login_assistant()
        return

    if args.clean:
        from src.cleaner import clean_temp_directory, enforce_storage_limits
        print("[*] Ejecutando limpieza estricta de directorios...")
        clean_temp_directory()
        enforce_storage_limits(max_mb=500)
        print("[✓] Limpieza completada con éxito.")
        return

    if args.list_channels:
        if CHANNELS_FILE.exists():
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                print(f.read())
        else:
            print("channels.json no encontrado.")
        return

    # Determinación de force_short
    force_short = None
    if args.format == "short":
        force_short = True
    elif args.format == "normal":
        force_short = False
    elif args.publish_all:
        # Publicación multiplataforma (Shorts, TikTok, Reels) REQUIERE formato vertical 9:16
        force_short = True
    elif args.url and "/shorts/" in args.url.lower():
        force_short = True

    # Modo 1: URL individual
    if args.url:
        video_id, title, uploader = extract_video_id(args.url)
        print(f"[*] Procesando URL directa: {title} ({video_id}) de {uploader or 'Desconocido'}")
        res = process_single_video(
            url=args.url,
            video_id=video_id,
            original_title=title,
            creator_name=uploader,
            mode=args.mode,
            force_short=force_short,
            auto_upload=args.upload,
            privacy_status=args.privacy,
            keep_local_video=args.keep_local_video,
            publish_all=args.publish_all,
            dry_run=args.dry_run,
            stagger_delay=args.stagger_delay,
            copilot_mode=False if args.no_copilot else None
        )
        if args.preview and res and "output_video" in res:
            vid_path = Path(res["output_video"])
            if vid_path.exists():
                print(f"[*] Abriendo vista previa local: {vid_path.name}")
                subprocess.run(["open", str(vid_path)])
        return

    # Modo 2: Modo autónomo (canales) & Modo Día del Estreno (Launch Mode)
    if args.auto or args.launch_mode:
        # En modo autónomo, publicar multiplataforma por defecto (Co-Pilot sigue activo como puerta humana)
        if not args.publish_all and not args.upload:
            args.publish_all = True
            args.upload = True
        launch_active = args.launch_mode or (datetime.now() >= datetime.fromisoformat("2026-11-19"))
        tag = "🚀 [MODO DÍA DEL ESTRENO]" if launch_active else "[*]"
        print(f"{tag} Iniciando escaneo autónomo multi-fuente (72 canales + 64 queries)...")
        effective_limit = args.max_videos if args.max_videos != MAX_VIDEOS_PER_RUN else get_max_videos_per_run()
        candidates = fetch_channel_candidates(max_per_channel=effective_limit)
        
        if not candidates:
            print("[✓] No hay vídeos nuevos pendientes de procesar en ningún canal.")
            return

        print(f"[!] Se encontraron {len(candidates)} vídeos candidatos.")
        
        from src.ai_selector import select_best_candidate_ai
        from src.channels import filter_repetitive_candidates
        
        count = 0
        remaining = list(candidates)
        while remaining and count < effective_limit:
            remaining = filter_repetitive_candidates(remaining)
            if not remaining:
                break
            chosen = select_best_candidate_ai(remaining, launch_mode=launch_active)
            if not chosen:
                break
            
            # Quitar de la lista de pendientes para la siguiente iteración
            chosen_id = chosen.get("id")
            remaining = [c for c in remaining if c.get("id") != chosen_id]
            
            # Construir gancho de 2 líneas si la IA o el Playbook generaron líneas específicas
            custom_hook = None
            if chosen.get("hook_line1") and chosen.get("hook_line2"):
                custom_hook = f"{chosen['hook_line1']}\n{chosen['hook_line2']}"

            res = process_single_video(
                url=chosen["url"],
                video_id=chosen["id"],
                original_title=chosen["title"],
                creator_name=chosen.get("uploader") or chosen.get("source_name", ""),
                source_lang=chosen.get("lang", "en"),
                mode=chosen.get("recommended_mode") or args.mode,
                force_short=True if (args.publish_all or chosen.get("is_short") or force_short) else force_short,
                auto_upload=args.upload,
                privacy_status=args.privacy,
                keep_local_video=args.keep_local_video,
                publish_all=args.publish_all,
                dry_run=args.dry_run,
                stagger_delay=args.stagger_delay,
                copilot_mode=False if args.no_copilot else None,
                hook_override=custom_hook,
                block_instagram=chosen.get("block_instagram", False),
                allowed_platforms=chosen.get("allowed_platforms"),
                allow_official_commentary=bool(chosen.get("allow_official_commentary", False))
            )
            if res:
                count += 1

        print(f"\n[✓] Ejecución autónoma finalizada. Procesados: {count} vídeos.")
        return

    # Si no se pasó ningún argumento
    parser.print_help()

if __name__ == "__main__":
    main()
