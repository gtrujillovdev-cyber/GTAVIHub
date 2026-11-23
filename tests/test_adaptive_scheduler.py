import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
import tempfile
import shutil

from src.adaptive_scheduler import (
    generate_daily_schedule,
    get_daily_schedule,
    get_due_window,
    mark_window_completed,
    format_schedule_summary,
    TARGET_WINDOWS
)
import src.adaptive_scheduler as adaptive_scheduler

class TestAdaptiveScheduler(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_file = adaptive_scheduler.SCHEDULE_FILE
        adaptive_scheduler.SCHEDULE_FILE = Path(self.test_dir) / "test_schedule.json"

    def tearDown(self):
        adaptive_scheduler.SCHEDULE_FILE = self.orig_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_schedule_generation(self):
        today = date(2026, 11, 16)
        sched = generate_daily_schedule(target_date=today, force_regenerate=True)
        self.assertEqual(sched["date"], "2026-11-16")
        self.assertEqual(len(sched["windows"]), 4)

        # Verificar que cada ventana cae en su rango
        for win, target in zip(sched["windows"], TARGET_WINDOWS):
            self.assertEqual(win["id"], target["id"])
            total_m = win["hour"] * 60 + win["minute"]
            start_m = target["start_hour"] * 60 + target["start_minute"]
            end_m = target["end_hour"] * 60 + target["end_minute"]
            self.assertGreaterEqual(total_m, start_m)
            self.assertLessEqual(total_m, end_m)
            self.assertFalse(win["completed"])

    def test_get_due_window_and_mark_completed(self):
        today = date(2026, 11, 16)
        sched = generate_daily_schedule(target_date=today, force_regenerate=True)

        first_win = sched["windows"][0]
        test_now = datetime(2026, 11, 16, first_win["hour"], first_win["minute"]) + timedelta(minutes=5)

        due = get_due_window(now_dt=test_now)
        self.assertIsNotNone(due)
        self.assertEqual(due["id"], first_win["id"])

        # Marcar completada
        mark_window_completed(due["id"], published_url="https://youtu.be/test1234", target_date=today)

        # Ya no debe estar due
        due_again = get_due_window(now_dt=test_now)
        if due_again:
            self.assertNotEqual(due_again["id"], first_win["id"])

    def test_summary_format(self):
        summary = format_schedule_summary(target_date=date(2026, 11, 16))
        self.assertIn("Planificador Adaptativo", summary)
        self.assertIn("CET", summary)

    def test_launch_night_windows_injected_and_backfilled(self):
        launch_day = date(2026, 11, 19)
        sched = generate_daily_schedule(target_date=launch_day, force_regenerate=True)
        ids = [w["id"] for w in sched["windows"]]
        self.assertEqual(ids[:2], ["midnight_drop", "late_night_wave"])
        self.assertEqual(len(ids), 6)

        # Simular horario cacheado antiguo de 4 ventanas para el 19-N y verificar backfill automático
        from src.adaptive_scheduler import load_all_schedules, save_all_schedules
        all_sched = load_all_schedules()
        all_sched[launch_day.isoformat()]["windows"] = [
            w for w in sched["windows"] if w["id"] not in ("midnight_drop", "late_night_wave")
        ]
        save_all_schedules(all_sched)

        reloaded = get_daily_schedule(launch_day)
        reloaded_ids = [w["id"] for w in reloaded["windows"]]
        self.assertIn("midnight_drop", reloaded_ids)
        self.assertIn("late_night_wave", reloaded_ids)

    def test_no_round_minutes_or_zero_seconds(self):
        test_day = date(2026, 11, 24)
        for _ in range(15):
            sched = generate_daily_schedule(target_date=test_day, force_regenerate=True)
            for win in sched["windows"]:
                self.assertNotEqual(win["minute"] % 5, 0, f"Minuto redondo detectado: {win}")
                self.assertIn("second", win)
                self.assertNotEqual(win["second"] % 10, 0, f"Segundo redondo detectado: {win}")

        # Verificar que get_due_window respeta el segundo exacto
        first_win = sched["windows"][0]
        before_sec = datetime(2026, 11, 24, first_win["hour"], first_win["minute"], first_win["second"] - 1)
        exact_sec = datetime(2026, 11, 24, first_win["hour"], first_win["minute"], first_win["second"])
        self.assertIsNone(get_due_window(now_dt=before_sec))
        due = get_due_window(now_dt=exact_sec)
        self.assertIsNotNone(due)
        self.assertEqual(due["id"], first_win["id"])

    def test_dynamic_intra_network_stagger_respects_skipped_platforms(self):
        from unittest.mock import patch, MagicMock
        from src.social_publisher import SocialPublisher

        pub = SocialPublisher(dry_run=False)
        sleep_calls = []
        with patch.dict("os.environ", {"ENABLE_INSTAGRAM": "true"}), \
             patch("src.social_publisher.time.sleep", side_effect=lambda s: sleep_calls.append(s)), \
             patch("src.audio_shield.detect_audio_levels", return_value={"has_audio": True, "mean_volume": -18.0}), \
             patch("src.social_publisher.AntiBanValidator.validate_metadata", return_value=True), \
             patch("src.social_publisher.ComplianceAuditor.is_platform_eligible", side_effect=lambda platform, **kw: (platform != "instagram", "blocked_ig")), \
             patch.object(pub, "publish_to_youtube", return_value="https://youtu.be/ok"), \
             patch.object(pub, "publish_to_tiktok", return_value="https://tiktok.com/ok"), \
             patch.object(pub, "_notify_telegram"):
            res = pub.publish_all(
                video_path=Path("dummy.mp4"),
                metadata={"title": "GTA 6 secreto oculto", "description": "Desc"},
                creator_name="Creator",
                platforms=["instagram", "youtube", "tiktok"],
                stagger_delay_minutes=12,
            )

        self.assertIn("Bloqueado", res["instagram"])
        # Exactamente 2 publicaciones reales -> 1 micro-jitter inicial (17-73s) + 1 pausa intraredes (480-1080s+)
        self.assertEqual(len(sleep_calls), 2)
        self.assertTrue(17 <= sleep_calls[0] <= 73)
        self.assertTrue(sleep_calls[1] >= 480)
        self.assertNotEqual(sleep_calls[1] % 60, 0)

if __name__ == "__main__":
    unittest.main()
