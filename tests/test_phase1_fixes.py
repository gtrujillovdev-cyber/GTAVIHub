import json
import tempfile
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import src.performance_tracker as pt
from src.pipeline import process_single_video
from src.translator import generate_mechanical_editorial_srt, generate_editorial_commentary_srt
from src.ai_selector import _resolve_recommended_mode, select_best_candidate_ai
from src.social_publisher import AntiBanValidator
from src.channels import get_daily_published_count


class TestPhase1Fixes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_perf_file = pt.PERF_FILE
        pt.PERF_FILE = Path(self.test_dir) / "performance_records.json"

    def tearDown(self):
        pt.PERF_FILE = self.orig_perf_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_fetch_pending_metrics_mixed_naive_and_aware_datetimes(self):
        old_utc = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        old_naive = (datetime.now() - timedelta(hours=25)).isoformat()
        recent_utc = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        records = [
            {
                "video_id": "vid_utc",
                "title": "Video UTC",
                "youtube_url": "https://youtu.be/vid_utc",
                "published_at": old_utc,
                "metrics_fetched_at": None,
            },
            {
                "video_id": "vid_naive",
                "title": "Video Naive",
                "youtube_url": "https://youtu.be/vid_naive",
                "published_at": old_naive,
                "metrics_fetched_at": None,
            },
            {
                "video_id": "vid_recent",
                "title": "Video Recent",
                "youtube_url": "https://youtu.be/vid_recent",
                "published_at": recent_utc,
                "metrics_fetched_at": None,
            },
        ]
        pt.PERF_FILE.write_text(json.dumps(records), encoding="utf-8")

        mock_proc = MagicMock(returncode=0, stdout="1500\t42\t5\n")
        with patch("src.performance_tracker.subprocess.run", return_value=mock_proc):
            updated = pt.fetch_pending_metrics(max_fetch=5)

        self.assertEqual(updated, 2)
        saved = json.loads(pt.PERF_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["views_24h"], 1500)
        self.assertEqual(saved[1]["views_24h"], 1500)
        self.assertIsNone(saved[2].get("views_24h"))

    def test_pipeline_precheck_aborts_when_quotas_full(self):
        with patch("src.social_publisher.AntiBanValidator.check_daily_limit", return_value=False), \
             patch("src.pipeline.enforce_storage_limits"), \
             patch("src.pipeline.download_video_and_subtitles") as mock_dl:
            res = process_single_video(
                url="https://youtu.be/test_vid_123",
                video_id="test_vid_123",
                original_title="GTA 6 PS5 Pro Gameplay",
                mode="subs",
                auto_upload=True,
            )
        self.assertIsNone(res)
        mock_dl.assert_not_called()

    def test_mechanical_editorial_srt_fallback_on_quota_error(self):
        dummy_video = Path(self.test_dir) / "clip.mp4"
        dummy_video.write_bytes(b"\x00" * 1024)
        out_srt = Path(self.test_dir) / "editorial.srt"

        # Direct mechanical generation
        ok = generate_mechanical_editorial_srt(
            out_srt,
            original_title="GTA 6 PS5 Pro vs Xbox Series X 4K FPS",
            duration_sec=24.0,
        )
        self.assertTrue(ok)
        txt = out_srt.read_text(encoding="utf-8")
        self.assertIn("-->", txt)
        self.assertIn("comparativa", txt.lower())

        # Fallback when Gemini raises 429 quota error
        out_srt2 = Path(self.test_dir) / "editorial_429.srt"
        with patch("src.translator.get_gemini_client", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
            ok2 = generate_editorial_commentary_srt(
                video_path=dummy_video,
                output_srt=out_srt2,
                original_title="GTA 6 Physics Water Details",
                creator_name="Rockstar",
                duration_sec=22.0,
            )
        self.assertTrue(ok2)
        self.assertIn("físicas", out_srt2.read_text(encoding="utf-8").lower())

    def test_resolve_recommended_mode_promotes_english_subs_to_dub(self):
        self.assertEqual(_resolve_recommended_mode("subs", {"lang": "en", "title": "GTA 6 Secrets"}), "dub")
        self.assertEqual(_resolve_recommended_mode("subs", {"lang": "es", "title": "Willyrex GTA 6"}), "subs")
        self.assertEqual(_resolve_recommended_mode("gameplay", {"lang": "en", "title": "GTA 6 Free Roam"}), "gameplay")

    def test_check_daily_limit_does_not_count_skipped_platform(self):
        today_iso = datetime.now().isoformat()
        records = [
            {
                "id": "vid1",
                "title": "GTA 6 Video 1",
                "status": "completed",
                "date": today_iso,
                "youtube_title": "GTA 6 Video 1",
                "youtube_url": "https://youtube.com/watch?v=source1",
                "multiplatform": {
                    "youtube": None,
                    "tiktok": "https://tiktok.com/@gtavihubextra/1",
                    "instagram": "Bloqueado por Compliance Shield"
                }
            },
            {
                "id": "vid2",
                "title": "GTA 6 Video 2",
                "status": "completed",
                "date": today_iso,
                "youtube_title": "GTA 6 Video 2",
                "youtube_url": "https://youtube.com/watch?v=source2",
                "multiplatform": {
                    "youtube": "https://youtu.be/real_yt",
                    "tiktok": "https://tiktok.com/@gtavihubextra/2",
                    "instagram": "https://instagram.com/reel/1"
                }
            }
        ]
        proc_file = Path(self.test_dir) / "processed.json"
        proc_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.social_publisher.PROCESSED_FILE", proc_file), \
             patch("src.channels.PROCESSED_FILE", proc_file), \
             patch.object(AntiBanValidator, "get_daily_limit", return_value=2):
            # YouTube only has 1 actual upload, so with limit=2 it should be OK (True)
            self.assertTrue(AntiBanValidator.check_daily_limit("youtube"))
            # TikTok has 2 uploads, so with limit=2 it should hit limit (False)
            self.assertFalse(AntiBanValidator.check_daily_limit("tiktok"))
            # get_daily_published_count only counts videos with at least 1 published URL
            self.assertEqual(get_daily_published_count(), 2)
            self.assertEqual(get_daily_published_count("youtube"), 1)
            self.assertEqual(get_daily_published_count("tiktok"), 2)

    def test_select_best_candidate_ai_force_heuristic_skips_gemini(self):
        cands = [
            {
                "id": "c1",
                "title": "GTA 6 Gameplay PS5 Pro 4K Free Roam",
                "uploader": "Gamer1",
                "duration": 25,
                "score": 90,
                "views_per_hour": 5000,
                "hours_old": 2,
                "url": "https://youtu.be/c1"
            },
            {
                "id": "c2",
                "title": "GTA 6 Podcast Discussion Radio Show",
                "uploader": "Talk1",
                "duration": 1800,
                "score": 70,
                "views_per_hour": 200,
                "hours_old": 40,
                "url": "https://youtu.be/c2"
            }
        ]
        with patch("src.ai_selector.get_gemini_client") as mock_client:
            chosen = select_best_candidate_ai(cands, launch_mode=True, use_ai=False)
            mock_client.assert_not_called()
            self.assertEqual(chosen.get("id"), "c1")
            self.assertFalse(chosen.get("ai_selection"))
            self.assertIn("Dry-Run", chosen.get("ai_justification"))

    def test_4k_download_selector_prioritizes_1440p_vp9_and_avoids_av01(self):
        from src.downloader import download_video_and_subtitles

        captured_cmds = []

        def fake_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            m = MagicMock(returncode=1, stdout="", stderr="mock fail")
            if "-f" in cmd:
                raise __import__("subprocess").CalledProcessError(1, cmd, stderr="mock fail")
            return m

        with patch("src.downloader.ENABLE_4K_SHORTS", True), \
             patch("src.downloader.TEMP_DIR", Path(self.test_dir)), \
             patch("src.downloader._inspect_remote_video_info", return_value={"duration": 30.0}), \
             patch("src.downloader._fetch_subtitles_yt", return_value=(None, "es")), \
             patch("src.downloader.subprocess.run", side_effect=fake_run):
            download_video_and_subtitles("https://youtu.be/test4k123", "test4k123", source_lang="es")

        fmt_cmds = [c for c in captured_cmds if "-f" in c]
        self.assertTrue(fmt_cmds)
        fmt_idx = fmt_cmds[0].index("-f") + 1
        fmt_str = fmt_cmds[0][fmt_idx]
        self.assertTrue(fmt_str.startswith("bestvideo[height>=1440][height<=2160][vcodec!^=av01]"))
        self.assertNotIn("[vcodec!=av01]", fmt_str)

    def test_video_editor_cleans_temp_pngs_and_caps_filter_threads_on_timeout(self):
        import subprocess
        from src.video_editor import render_final_video

        in_mp4 = Path(self.test_dir) / "input.mp4"
        out_mp4 = Path(self.test_dir) / "output.mp4"
        in_mp4.write_bytes(b"\x00" * 2048)

        captured = {}

        def fake_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "ffmpeg":
                captured["cmd"] = cmd
                raise subprocess.TimeoutExpired(cmd, timeout=360)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("src.video_editor.get_video_dimensions", return_value=(1920, 1080)), \
             patch("src.video_editor._probe_duration", return_value=20.0), \
             patch("src.video_editor.is_quant_busy", return_value=True), \
             patch("src.video_editor.subprocess.run", side_effect=fake_run):
            ok = render_final_video(
                input_video=in_mp4,
                output_video=out_mp4,
                hook_text="TEST HOOK\nLINE TWO",
                format_preset="D",
            )

        self.assertFalse(ok)
        self.assertIn("-filter_threads", captured["cmd"])
        self.assertIn("-filter_complex_threads", captured["cmd"])
        # Ningún PNG temporal huérfano tras el timeout
        leftover_pngs = list(Path(self.test_dir).glob("*.png"))
        self.assertEqual(leftover_pngs, [])

    def test_social_publisher_skips_downscale_on_dry_run_and_quota_full(self):
        from src.social_publisher import SocialPublisher

        dummy_vid = Path(self.test_dir) / "master_4k.mp4"
        dummy_vid.write_bytes(b"\x00" * 5000)

        with patch("src.social_publisher.prepare_social_compatible_video") as mock_prep, \
             patch("src.social_publisher.AntiBanValidator.check_daily_limit", return_value=True):
            pub = SocialPublisher(dry_run=True)
            tt_url = pub.publish_to_tiktok(dummy_vid, "GTA 6 Test", ["GTA6"])
            ig_url = pub.publish_to_instagram(dummy_vid, "GTA 6 Test")
            self.assertIsNotNone(tt_url)
            self.assertIsNotNone(ig_url)
            mock_prep.assert_not_called()

    def test_transcript_hook_penalizes_menu_and_copyright_chatter(self):
        from src.downloader import find_best_transcript_hook_window

        srt_file = Path(self.test_dir) / "rubius_audit.srt"
        srt_file.write_text(
            "1\n00:01:00,000 --> 00:01:08,000\n"
            "Vale uy como que tienda ah skins de pago o estudio fotografico confirmado.\n\n"
            "2\n00:01:08,500 --> 00:01:22,000\n"
            "Voy a dejar la musica con licencia pero apago la radio por copyright en el vod.\n\n"
            "3\n00:05:00,000 --> 00:05:12,000\n"
            "Madre mia mira la fisica del agua y esa explosion brutal en la persecucion policial!\n\n"
            "4\n00:05:12,500 --> 00:05:24,500\n"
            "Que locura de detalles y realismo con el coche en GTA 6!\n",
            encoding="utf-8",
        )
        win = find_best_transcript_hook_window(srt_file, min_dur=16, max_dur=28, total_duration=400.0, use_ai=False)
        self.assertIsNotNone(win)
        # Debe elegir el tramo de acción real (300s+) y NO el menú de ajustes/copyright (60s-82s)
        self.assertGreaterEqual(win[0], 290.0)

    def test_pipeline_spanish_streamer_gets_karaoke_and_heavy_english_gets_dub(self):
        from src.pipeline import process_single_video

        tmp_vid = Path(self.test_dir) / "streamer.mp4"
        tmp_vid.write_bytes(b"\x00" * 4096)
        es_srt = Path(self.test_dir) / "streamer.srt"
        es_srt.write_text(
            "1\n00:00:01,000 --> 00:00:10,000\n"
            "Madre mía chavales mirad cómo acaba de explotar ese coche de policía en GTA 6 qué locura de físicas!\n",
            encoding="utf-8",
        )

        render_calls = []

        def fake_render(*args, **kwargs):
            render_calls.append(kwargs)
            out_v = kwargs["output_video"]
            out_v.write_bytes(b"\x00" * 4096)
            return True

        out_dir = Path(self.test_dir) / "out"
        out_dir.mkdir(exist_ok=True)
        with patch("src.pipeline.TEMP_DIR", Path(self.test_dir)), \
             patch("src.pipeline.OUTPUT_DIR", out_dir), \
             patch("src.pipeline.download_video_and_subtitles", return_value=(tmp_vid, es_srt, "es")), \
             patch("src.pipeline.get_video_dimensions", return_value=(1920, 1080)), \
             patch("src.pipeline.detect_horizontal_split_screen", return_value=False), \
             patch("src.audio_shield.detect_audio_levels", return_value={"has_audio": True, "mean_volume": -18.0, "max_volume": -2.0}), \
             patch("src.pipeline.translate_srt", side_effect=lambda s, d, **kw: (d.write_text(s.read_text(encoding="utf-8"), encoding="utf-8"), True)[1]), \
             patch("src.pipeline.generate_video_metadata", return_value={"title": "TEST ES STREAMER", "description": "desc", "tags": ["GTA6"]}), \
             patch("src.pipeline.render_final_video", side_effect=fake_render), \
             patch("src.pipeline.create_video_thumbnail"), \
             patch("src.pipeline.is_copilot_enabled", return_value=False), \
             patch("src.pipeline.clean_temp_directory"), \
             patch("src.pipeline.mark_video_processed"), \
             patch("src.pipeline.notify_macos"), \
             patch("src.telegram_bot.send_telegram_video", return_value=True), \
             patch("src.telegram_bot.send_telegram_photo", return_value=True), \
             patch("src.telegram_bot.send_telegram_alert", return_value=True), \
             patch("src.pipeline.subprocess.run", return_value=MagicMock(returncode=0, stdout="22.0", stderr="")):
            process_single_video(
                url="https://youtu.be/es_stream_1",
                video_id="es_stream_1",
                original_title="GTA 6 MUNDO ABIERTO",
                creator_name="Rubius Z",
                source_lang="es",
                mode="gameplay",
                auto_upload=False,
            )

        self.assertTrue(render_calls)
        self.assertIsNotNone(render_calls[0].get("srt_subtitles"))

    def test_word_boundary_truncation_never_chops_mid_word(self):
        from src.translator import truncate_on_word_boundary
        from src.video_editor import render_persistent_context_badge

        sample = "DANIREP • PRIMERA CONDUCCIÓN MOTO"
        self.assertEqual(truncate_on_word_boundary(sample, 42), sample)
        # Cuando excede el tope, debe cortar en límite de palabra y nunca en "MOT"
        trimmed = truncate_on_word_boundary(sample, 32)
        self.assertEqual(trimmed, "DANIREP • PRIMERA CONDUCCIÓN")
        self.assertFalse(trimmed.endswith("MOT"))

        badge_out = Path(self.test_dir) / "badge_danirep.png"
        ok = render_persistent_context_badge(
            badge_out,
            text=sample,
            archetype="reaccion_streamer",
            scale_factor=2.0,
        )
        self.assertTrue(ok)
        self.assertTrue(badge_out.exists())


if __name__ == "__main__":
    unittest.main()
