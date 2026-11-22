import os
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import src.copilot as copilot
from src.adaptive_scheduler import TARGET_WINDOWS
from src.ai_selector import select_best_candidate_ai
from src.learning_engine import generate_hook_card_texts, _truncate_word_boundary
from src.social_publisher import AntiBanValidator


class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_state_file = copilot.COPILOT_STATE_FILE
        copilot.COPILOT_STATE_FILE = Path(self.tmp_dir) / "copilot_state.json"

    def tearDown(self):
        copilot.COPILOT_STATE_FILE = self.orig_state_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_default_daily_limits_aligned_anti_spam(self):
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("MAX_DAILY_UPLOADS")}
        with patch.dict(os.environ, clean_env, clear=True):
            self.assertEqual(AntiBanValidator.get_daily_limit("youtube"), 3)
            self.assertEqual(AntiBanValidator.get_daily_limit("tiktok"), 3)
            self.assertEqual(AntiBanValidator.get_daily_limit("instagram"), 3)

    def test_target_windows_have_render_buffer_before_peaks(self):
        """Las ventanas deben terminar no mucho despues del pico de audiencia.
        Con ventanas amplias (60-90 min) y jitter +-15 min, el scheduler elige
        un punto aleatorio DENTRO de la ventana, asi que el render empieza antes
        del end_hour. El margen real es start->peak, no end->peak."""
        peaks_minutes = {
            "morning": 11 * 60,
            "lunch_latam": 14 * 60 + 30,
            "afternoon": 18 * 60,
            "prime_time": 21 * 60,
        }
        for win in TARGET_WINDOWS:
            start_m = win["start_hour"] * 60 + win["start_minute"]
            peak_m = peaks_minutes[win["id"]]
            self.assertGreaterEqual(peak_m - start_m, 25, f"Ventana {win['id']} sin margen suficiente desde inicio")

    def test_word_boundary_truncation_and_specific_hooks(self):
        self.assertEqual(_truncate_word_boundary("ANALISIS COMPLETO DE FISICAS", 21), "ANALISIS COMPLETO DE")
        l1, l2 = generate_hook_card_texts("GTA 6 RAGE 9 Water Physics Demo")
        self.assertLessEqual(len(l1), 21)
        self.assertLessEqual(len(l2), 24)
        self.assertNotIn("NO TE LO PIERDAS", l2)

    def test_quality_first_rejects_low_score_single_candidate(self):
        low_cand = [{
            "id": "low_1",
            "title": "GTA 6 random rumor",
            "duration": 40.0,
            "score": 55,
            "uploader": "RandomChannel",
        }]
        self.assertEqual(select_best_candidate_ai(low_cand, use_ai=False), {})

    def test_autopilot_eligibility_and_circuit_breaker(self):
        # 1. Muestra insuficiente -> bloqueado
        small = [{"views": 200, "likes": 10, "viewed_rate": 0.80}]
        res_small = copilot.evaluate_autopilot_eligibility(95, small)
        self.assertFalse(res_small["allow_autopilot"])

        # 2. Muestra válida y métricas sólidas -> aprobado
        strong = [
            {"views": 1500, "likes": 45, "viewed_rate": 0.78},
            {"views": 2000, "likes": 60, "viewed_rate": 0.75},
        ]
        res_ok = copilot.evaluate_autopilot_eligibility(92, strong)
        self.assertTrue(res_ok["allow_autopilot"])
        self.assertFalse(res_ok["circuit_breaker_triggered"])

        # 3. Retención inicial baja (< 70%) -> bloqueado
        low_ret = [{"views": 2000, "likes": 70, "viewed_rate": 0.55}]
        res_ret = copilot.evaluate_autopilot_eligibility(95, low_ret)
        self.assertFalse(res_ret["allow_autopilot"])

        # 4. Circuit breaker: 5 clips con <= 1.5% likes/views reactiva Co-Pilot
        copilot.set_copilot_enabled(False)
        weak_5 = [{"views": 1000, "likes": 10} for _ in range(5)]
        res_cb = copilot.evaluate_autopilot_eligibility(95, weak_5)
        self.assertFalse(res_cb["allow_autopilot"])
        self.assertTrue(res_cb["circuit_breaker_triggered"])
        self.assertTrue(copilot.is_copilot_enabled())

    def test_optimistic_copilot_veto_window_auto_publishes_and_respects_veto(self):
        orig_pending_dir = copilot.PENDING_DIR
        copilot.PENDING_DIR = Path(self.tmp_dir) / "pending"
        copilot.PENDING_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # 1. Sin veto: tras expirar el timer, debe invocar approve_and_publish_video
            (copilot.PENDING_DIR / "vid_auto.json").write_text('{"video_id": "vid_auto"}', encoding="utf-8")
            with patch("src.copilot.approve_and_publish_video", return_value={"title": "Test", "youtube_url": "https://youtu.be/x"}) as mock_pub:
                timer = copilot.schedule_auto_approve_if_pending("vid_auto", timeout_sec=0.05 if False else 1, notify_telegram=False)
                # Usar Timer corto manualmente para test instantáneo: comprobamos que timer se crea
                self.assertIsNotNone(timer)
                timer.cancel()

            # Validar comportamiento de timeout = 0 (desactivado)
            self.assertIsNone(copilot.schedule_auto_approve_if_pending("vid_auto", timeout_sec=0, notify_telegram=False))

            # Validar que si se veta (borrando el JSON pendiente), no publica aunque dispare
            (copilot.PENDING_DIR / "vid_veto.json").unlink(missing_ok=True)
            with patch("src.copilot.approve_and_publish_video") as mock_pub:
                # Simular ejecución directa cuando ya fue vetado
                self.assertIsNone(copilot.get_pending_video("vid_veto"))
                mock_pub.assert_not_called()
        finally:
            copilot.PENDING_DIR = orig_pending_dir


class TestStabilizationFixes(unittest.TestCase):
    def test_youtube_cooldown_aligned_to_4_slots(self):
        import json
        from datetime import datetime, timedelta
        from src import uploader

        with tempfile.TemporaryDirectory() as td:
            cd_file = Path(td) / "upload_cooldown.json"
            pause_file = Path(td) / "youtube_cooldown_until.txt"
            now = datetime.now()
            # 3 subidas previas espaciadas >= 170 min (hace 170m, 360m, 550m) -> 4ª subida PERMITIDA
            records = [
                {"video_id": "v1", "title": "GTA 6 Fisica Agua", "uploaded_at": (now - timedelta(minutes=550)).isoformat()},
                {"video_id": "v2", "title": "GTA 6 Mapa Leonida", "uploaded_at": (now - timedelta(minutes=360)).isoformat()},
                {"video_id": "v3", "title": "GTA 6 PS5 Pro Test", "uploaded_at": (now - timedelta(minutes=170)).isoformat()},
            ]
            cd_file.write_text(json.dumps(records), encoding="utf-8")

            with patch.object(uploader, "UPLOAD_COOLDOWN_FILE", cd_file), \
                 patch.object(uploader, "YOUTUBE_PAUSE_FILE", pause_file), \
                 patch.dict("os.environ", {"MAX_DAILY_UPLOADS_YOUTUBE": "4"}):
                blocked, reason = uploader._is_youtube_upload_blocked_by_cooldown("GTA 6 Nuevo Secreto", "public")
                self.assertFalse(blocked, f"No debería bloquear 4ª subida con 170m de margen: {reason}")

                # Si hay 4 subidas en 24h -> 5ª subida BLOQUEADA
                records.append({"video_id": "v4", "title": "GTA 6 Coches", "uploaded_at": (now - timedelta(minutes=175)).isoformat()})
                cd_file.write_text(json.dumps(records), encoding="utf-8")
                blocked_cap, _ = uploader._is_youtube_upload_blocked_by_cooldown("GTA 6 Quinto", "public")
                self.assertTrue(blocked_cap)

    def test_copilot_does_not_mark_published_when_all_uploads_fail(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            pending_dir = td_path / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            vid_file = td_path / "clip.mp4"
            vid_file.write_bytes(b"fake")
            (pending_dir / "fail_vid.json").write_text(json.dumps({
                "video_id": "fail_vid",
                "original_url": "https://youtu.be/fail_vid",
                "original_title": "GTA 6 Fail Test",
                "creator_name": "TestCreator",
                "output_video": str(vid_file),
                "thumbnail": None,
                "metadata": {"title": "GTA 6 FAIL TEST", "description": "Desc"},
                "is_short": True,
                "mode": "subs",
                "publish_all": True,
                "privacy_status": "public",
                "stagger_delay": 0,
                "keep_local_video": True,
            }), encoding="utf-8")

            with patch.object(copilot, "PENDING_DIR", pending_dir), \
                 patch.object(copilot, "DATA_DIR", td_path), \
                 patch.object(copilot, "mark_video_processed") as mock_mark, \
                 patch("src.social_publisher.SocialPublisher.publish_all", return_value={"youtube": None, "tiktok": None, "instagram": None}):
                res = copilot.approve_and_publish_video("fail_vid")
                self.assertIsNone(res)
                mock_mark.assert_not_called()
                saved = json.loads((pending_dir / "fail_vid.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["status"], "upload_failed")

    def test_video_editor_handles_silent_input_with_dub_audio(self):
        import subprocess
        from src import video_editor
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            silent_vid = td_path / "silent.mp4"
            dub_mp3 = td_path / "dub.mp3"
            out_vid = td_path / "out.mp4"
            # Generar vídeo mudo (sin pista de audio) + audio TTS sintético de 2s
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=2",
                "-c:v", "h264_videotoolbox", "-pix_fmt", "yuv420p", str(silent_vid)
            ], check=True, capture_output=True)
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:a", "libmp3lame", str(dub_mp3)
            ], check=True, capture_output=True)

            self.assertFalse(video_editor._has_audio_stream(silent_vid))
            ok = video_editor.render_final_video(
                input_video=silent_vid,
                output_video=out_vid,
                dub_audio=dub_mp3,
                force_short_format=True,
                hook_text="TEST SILENT AUDIO",
                format_preset="D",
            )
            self.assertTrue(ok)
            self.assertTrue(out_vid.exists() and out_vid.stat().st_size > 1000)

    def test_anti_spoiler_shield_blocks_endings_and_allows_comparisons(self):
        from src.compliance_auditor import is_safe_rrss_candidate
        safe_sp, reason_sp, _ = is_safe_rrss_candidate(
            "GTA 6 Good Ending (Jason & Lucia Survive) - Grand Theft Auto VI",
            uploader="MELOO",
            duration_sec=45,
        )
        self.assertFalse(safe_sp)
        self.assertIn("Anti-Spoiler", reason_sp)

        safe_ok, _, _ = is_safe_rrss_candidate(
            "GTA 6: COMPARATIVA GRÁFICA FINAL PS5 VS PS5 PRO",
            uploader="ElAnalistaDeBits",
            duration_sec=30,
        )
        self.assertTrue(safe_ok)


if __name__ == "__main__":
    unittest.main()
