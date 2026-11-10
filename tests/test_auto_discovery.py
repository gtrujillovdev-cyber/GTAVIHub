import unittest
import json
import shutil
from pathlib import Path
from src.config import DATA_DIR, CHANNELS_FILE
from src.channels import (
    auto_register_source_from_metadata,
    get_discovered_sources_report,
    DISCOVERED_CHANNELS_FILE
)

class TestAutoDiscovery(unittest.TestCase):
    def setUp(self):
        # Backup files
        self.orig_channels = None
        if CHANNELS_FILE.exists():
            self.orig_channels = CHANNELS_FILE.read_text(encoding="utf-8")

        self.orig_discovered = None
        if DISCOVERED_CHANNELS_FILE.exists():
            self.orig_discovered = DISCOVERED_CHANNELS_FILE.read_text(encoding="utf-8")

        # Initialize mock clean environment
        CHANNELS_FILE.write_text(json.dumps({"channels": [], "search_queries": []}), encoding="utf-8")
        DISCOVERED_CHANNELS_FILE.write_text(json.dumps({}), encoding="utf-8")

    def tearDown(self):
        # Restore files
        if self.orig_channels is not None:
            CHANNELS_FILE.write_text(self.orig_channels, encoding="utf-8")
        elif CHANNELS_FILE.exists():
            CHANNELS_FILE.unlink()

        if self.orig_discovered is not None:
            DISCOVERED_CHANNELS_FILE.write_text(self.orig_discovered, encoding="utf-8")
        elif DISCOVERED_CHANNELS_FILE.exists():
            DISCOVERED_CHANNELS_FILE.unlink()

    def test_auto_register_new_source(self):
        mock_meta = {
            "id": "abc12345",
            "title": "GTA 6 Nuevos Detalles de Gráficos RAGE 9",
            "uploader": "CanalPruebaGTA",
            "platform": "YouTube",
            "channel_url": "https://www.youtube.com/@CanalPruebaGTA",
            "uploader_url": "https://www.youtube.com/@CanalPruebaGTA",
            "url": "https://youtube.com/shorts/abc12345",
            "strategy": {
                "archetype": "Listicle de Detalles & Curiosidades",
                "recommended_opt": "short",
                "badge": "⚡ Short Hormozi"
            }
        }

        res = auto_register_source_from_metadata(mock_meta)
        self.assertTrue(res["success"])
        self.assertTrue(res["is_new"])
        self.assertEqual(res["uploader"], "CanalPruebaGTA")
        self.assertEqual(res["occurrences"], 1)

        # Check discovered_channels.json
        with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            disc = json.load(f)
        self.assertTrue(any("CanalPruebaGTA" in k or v.get("name") == "CanalPruebaGTA" for k, v in disc.items()))

        # Check channels.json
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertTrue(any(c["name"].startswith("CanalPruebaGTA") for c in cfg.get("channels", [])))

    def test_auto_register_existing_source_increments(self):
        mock_meta = {
            "id": "clip_1",
            "title": "Clip 1 GTA 6",
            "uploader": "CreadorRecurrente",
            "platform": "YouTube",
            "channel_url": "https://www.youtube.com/@CreadorRecurrente/shorts",
            "strategy": {"archetype": "Comparativa Gráfica en Loop", "recommended_opt": "gameplay"}
        }

        # First ingestion
        res1 = auto_register_source_from_metadata(mock_meta)
        self.assertTrue(res1["is_new"])
        self.assertEqual(res1["occurrences"], 1)

        # Second ingestion with new title
        mock_meta["id"] = "clip_2"
        mock_meta["title"] = "Clip 2 GTA 6"
        res2 = auto_register_source_from_metadata(mock_meta)
        self.assertFalse(res2["is_new"])
        self.assertEqual(res2["occurrences"], 2)

        # Check sample titles
        with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            disc = json.load(f)
        found = next((v for v in disc.values() if v.get("name") == "CreadorRecurrente"), None)
        self.assertIsNotNone(found)
        self.assertIn("Clip 2 GTA 6", found["sample_titles"])
        self.assertIn("Clip 1 GTA 6", found["sample_titles"])

    def test_ignore_generic_uploader(self):
        mock_meta = {
            "id": "gen_1",
            "title": "GTA 6 Video",
            "uploader": "Comunidad GTA 6",
            "platform": "YouTube"
        }
        res = auto_register_source_from_metadata(mock_meta)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "ignored")

    def test_get_discovered_sources_report(self):
        mock_meta = {
            "id": "rep_1",
            "title": "GTA 6 Report",
            "uploader": "ReporteroLeonida",
            "platform": "YouTube",
            "strategy": {"archetype": "Noticias & Novedades"}
        }
        auto_register_source_from_metadata(mock_meta)
        report = get_discovered_sources_report()
        self.assertIn("MOTOR DE APRENDIZAJE", report)
        self.assertIn("ReporteroLeonida", report)

if __name__ == "__main__":
    unittest.main()
