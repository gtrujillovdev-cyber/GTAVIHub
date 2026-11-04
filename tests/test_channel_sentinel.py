import unittest
import json
from pathlib import Path
from datetime import datetime, timedelta
from src.config import DATA_DIR
from src.channel_sentinel import (
    load_sentinel_state, save_sentinel_state,
    load_analytics_history, save_analytics_history,
    record_video_for_sentinel, evaluate_and_heal_channels,
    get_resilient_publishing_target, calibrate_simulation_from_real_data,
    SENTINEL_STATE_FILE, ANALYTICS_HISTORY_FILE
)

class TestChannelSentinel(unittest.TestCase):
    def setUp(self):
        self.original_state = None
        self.original_history = None
        if SENTINEL_STATE_FILE.exists():
            self.original_state = SENTINEL_STATE_FILE.read_text(encoding="utf-8")
        if ANALYTICS_HISTORY_FILE.exists():
            self.original_history = ANALYTICS_HISTORY_FILE.read_text(encoding="utf-8")
        # Asegurar estado limpio para cada test
        from src.channel_sentinel import DEFAULT_STATE
        save_sentinel_state(DEFAULT_STATE)
        save_analytics_history([])

    def tearDown(self):
        if self.original_state is not None:
            SENTINEL_STATE_FILE.write_text(self.original_state, encoding="utf-8")
        elif SENTINEL_STATE_FILE.exists():
            SENTINEL_STATE_FILE.unlink()

        if self.original_history is not None:
            ANALYTICS_HISTORY_FILE.write_text(self.original_history, encoding="utf-8")
        elif ANALYTICS_HISTORY_FILE.exists():
            ANALYTICS_HISTORY_FILE.unlink()

    def test_record_video_for_sentinel(self):
        record_video_for_sentinel(
            video_id="test_vid_123",
            title="GTA 6 Water Physics Gameplay",
            platform_urls={"youtube": "https://youtu.be/test_vid_123"},
            target_channel="main",
            archetype="rage9_physics"
        )
        history = load_analytics_history()
        self.assertTrue(any(v["video_id"] == "test_vid_123" for v in history))

    def test_resilient_routing_default_main(self):
        # En estado normal (healthy), el target debe ser main
        target = get_resilient_publishing_target("youtube")
        self.assertEqual(target, "main")

    def test_shadowban_detection_and_failover_routing(self):
        # Simular 2 vídeos consecutivos con bajas visualizaciones (< 400 vistas) en el canal principal
        history = [
            {
                "video_id": "flop_1",
                "title": "Bad Clip 1",
                "target_channel": "main",
                "published_at": (datetime.now() - timedelta(hours=10)).isoformat(),
                "final_views": 150,
                "final_likes": 5
            },
            {
                "video_id": "flop_2",
                "title": "Bad Clip 2",
                "target_channel": "main",
                "published_at": (datetime.now() - timedelta(hours=9)).isoformat(),
                "final_views": 180,
                "final_likes": 6
            }
        ]
        save_analytics_history(history)

        # Ejecutar evaluación de salud
        eval_result = evaluate_and_heal_channels()
        ch_state = eval_result["channels"]["youtube_main"]
        self.assertEqual(ch_state["status"], "quarantine")
        self.assertGreaterEqual(ch_state["consecutive_flops"], 2)

        # Verificar que el target de publicación conmute automáticamente al canal EXTRA
        new_target = get_resilient_publishing_target("youtube")
        self.assertEqual(new_target, "extra")

    def test_auto_healing_recovery(self):
        # Simular que el canal principal vuelve a tener un vídeo saludable (>= 400 vistas)
        state = load_sentinel_state()
        state["channels"]["youtube_main"]["status"] = "quarantine"
        save_sentinel_state(state)

        healthy_history = [
            {
                "video_id": "healthy_clip",
                "title": "Viral RAGE 9 Physics",
                "target_channel": "main",
                "published_at": (datetime.now() - timedelta(hours=5)).isoformat(),
                "final_views": 18500,
                "final_likes": 1200
            }
        ]
        save_analytics_history(healthy_history)

        evaluate_and_heal_channels()
        updated_state = load_sentinel_state()
        self.assertEqual(updated_state["channels"]["youtube_main"]["status"], "healthy")

    def test_simulation_calibration_output(self):
        # Verificar que calibrate_simulation_from_real_data retorne la estructura completa
        calib = calibrate_simulation_from_real_data()
        self.assertIn("empirical_median_views", calib)
        self.assertIn("empirical_mean_views", calib)
        self.assertIn("calibration_source", calib)
        self.assertGreater(calib["empirical_median_views"], 0)

if __name__ == "__main__":
    unittest.main()
