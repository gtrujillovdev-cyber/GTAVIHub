import json
import unittest
from pathlib import Path

from src.ai_selector import is_location_reward_guide, _visual_appeal_adjustment
from src.learning_engine import generate_hook_card_texts
from src.viral_discovery import calculate_virality_score


class TestLocationGuideModel(unittest.TestCase):
    def test_channels_json_includes_caspahz_and_guide_queries(self):
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "channels.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        names = {c.get("name") for c in data.get("channels", [])}
        self.assertIn("Caspahz (Shorts)", names)
        self.assertIn("Caspahz (Guías)", names)

        queries = [q.get("query", "") for q in data.get("search_queries", [])]
        self.assertTrue(any("free car location" in q for q in queries))
        self.assertTrue(any("fastest money method" in q for q in queries))

    def test_location_reward_guide_detection_and_scoring(self):
        self.assertTrue(is_location_reward_guide("GTA 6: FREE $24,000 Rolls Royce (Sell It for Cash!)"))
        self.assertTrue(is_location_reward_guide("GTA 6: FASTEST Money Method - $500K Per Hour at Any Chapter!"))
        self.assertTrue(is_location_reward_guide("GTA 6: Dónde encontrar el coche gratis en el mapa"))
        self.assertFalse(is_location_reward_guide("GTA 6 Worth It Review and Thoughts Podcast"))

        guide_boost = _visual_appeal_adjustment({
            "title": "GTA 6: FREE $24,000 Rolls Royce Location (Sell It for Cash!)",
            "duration": 20,
        })
        generic_boost = _visual_appeal_adjustment({
            "title": "GTA 6 Launch Thoughts Podcast",
            "duration": 180,
        })
        self.assertGreater(guide_boost, generic_boost)
        self.assertGreaterEqual(guide_boost, 50.0)

    def test_virality_score_and_hook_card(self):
        res = calculate_virality_score(
            title="GTA 6: FREE $32,000 Supercar Location",
            duration=22.0,
            views=45000,
            days_old=1,
            like_count=1800,
        )
        self.assertGreater(res["score"], 50)

        l1, l2 = generate_hook_card_texts("GTA 6: FREE $32,000 Supercar!")
        self.assertEqual(l1, "EN ESTA UBICACIÓN")
        self.assertIn("GRATIS", l2)


if __name__ == "__main__":
    unittest.main()
