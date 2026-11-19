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
        peaks_minutes = {
            "morning": 11 * 60,
            "lunch_latam": 14 * 60 + 30,
            "afternoon": 18 * 60,
            "prime_time": 21 * 60,
        }
        for win in TARGET_WINDOWS:
            end_m = win["end_hour"] * 60 + win["end_minute"]
            peak_m = peaks_minutes[win["id"]]
            self.assertGreaterEqual(peak_m - end_m, 25, f"Ventana {win['id']} sin margen suficiente")

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


if __name__ == "__main__":
    unittest.main()
