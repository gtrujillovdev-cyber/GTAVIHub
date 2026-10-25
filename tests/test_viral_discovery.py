import unittest
from pathlib import Path
from src.viral_discovery import (
    calculate_virality_score,
    get_viral_radar_summary,
    track_discovered_channels,
    DEFAULT_VIRAL_QUERIES,
    VIRAL_KEYWORDS
)
from src.channels import list_monitored_channels
from src.telegram_bot import get_viral_radar_inline_keyboard

class TestViralDiscovery(unittest.TestCase):
    def test_virality_score_high_engagement_short(self):
        # Vídeo vertical corto (Short) con muchas vistas y palabras clave
        res = calculate_virality_score(
            title="NUEVO TRAILER 2 GTA 6 FILTRACION MAPA VICE CITY",
            duration=35.0,
            views=350_000
        )
        self.assertGreaterEqual(res["score"], 80)
        self.assertTrue(res["is_short"])
        self.assertEqual(res["format_score"], 35)
        self.assertGreaterEqual(res["views_score"], 35)
        self.assertGreaterEqual(len(res["matches"]), 3)

    def test_virality_score_low_engagement_long(self):
        # Vídeo largo, sin palabras clave y pocas vistas
        res = calculate_virality_score(
            title="Gameplay casual caminando",
            duration=1500.0,
            views=200
        )
        self.assertLess(res["score"], 30)
        self.assertFalse(res["is_short"])
        self.assertEqual(res["format_score"], 0)
        self.assertEqual(res["views_score"], 5)

    def test_monitored_channels_expanded(self):
        channels = list_monitored_channels()
        # Debe haber al menos 20 canales de alta autoridad configurados
        self.assertGreaterEqual(len(channels), 20)
        for ch in channels:
            self.assertIn("name", ch)
            self.assertIn("url", ch)
            self.assertIn("enabled", ch)
            self.assertTrue(ch["url"].startswith("https://www.youtube.com/"))
            self.assertTrue(len(ch["name"]) > 0)

    def test_track_discovered_channels(self):
        mock_candidates = [
            {
                "id": "mock_vid_99",
                "title": "EXCLUSIVA GTA 6 LEAK",
                "duration": 40.0,
                "views": 80000,
                "uploader": "NuevoCreadorGTA",
                "channel_url": "https://www.youtube.com/@NuevoCreadorGTA/videos",
                "score": 88,
                "is_short": True,
                "is_new_channel": True
            }
        ]
        res = track_discovered_channels(mock_candidates)
        self.assertIsInstance(res, list)
        matched = [c for c in res if c.get("url") == "https://www.youtube.com/@NuevoCreadorGTA/videos"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "NuevoCreadorGTA")
        self.assertEqual(matched[0]["best_score"], 88)

    def test_viral_radar_summary(self):
        mock_candidates = [
            {
                "id": "test_1",
                "title": "NUEVA FILTRACION GTA 6",
                "url": "https://youtube.com/watch?v=test_1",
                "duration": 45.0,
                "views": 150000,
                "uploader": "GTA Channel",
                "score": 90,
                "is_short": True,
                "is_new_channel": True
            }
        ]
        summary = get_viral_radar_summary(mock_candidates)
        self.assertIn("RADAR VIRAL GTA 6", summary)
        self.assertIn("NUEVA FILTRACION GTA 6", summary)
        self.assertIn("90/100", summary)

    def test_viral_radar_inline_keyboard(self):
        mock_candidates = [
            {"id": "1", "is_short": True},
            {"id": "2", "is_short": False}
        ]
        kb = get_viral_radar_inline_keyboard(mock_candidates)
        self.assertIn("inline_keyboard", kb)
        buttons = [b["text"] for row in kb["inline_keyboard"] for b in row]
        self.assertIn("⚡ Ingestar #1", buttons)
        self.assertIn("⚡ Ingestar #2", buttons)
        self.assertIn("➕ Añadir Nuevos Creadores", buttons)
        self.assertIn("🔄 Actualizar Radar", buttons)

if __name__ == "__main__":
    unittest.main()
