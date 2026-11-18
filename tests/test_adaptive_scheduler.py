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

if __name__ == "__main__":
    unittest.main()
