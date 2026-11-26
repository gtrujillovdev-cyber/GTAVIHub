import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.guide_story_compiler import plan_multi_beat_guide
from src.social_publisher import prepare_social_compatible_video


class TestXLongGuide(unittest.TestCase):
    def test_plan_x_long_guide_supports_6_acts_45_to_70s(self):
        fake_json = json.dumps({
            "short_title_es": "GUIA COMPLETA COCHE EMERUS GRATIS",
            "cover_line1": "EMERUS",
            "cover_line2": "GRATIS",
            "beats": [
                {"act": "reward_hook", "start_sec": 5.0, "end_sec": 11.0, "narration_es": "Consigue el Emerus gratis en Vice City."},
                {"act": "map_location", "start_sec": 20.0, "end_sec": 24.5, "narration_es": "Ve a este punto exacto del mapa."},
                {"act": "approach_route", "start_sec": 35.0, "end_sec": 45.0, "narration_es": "Entra por la calle lateral del edificio."},
                {"act": "action_steps", "start_sec": 60.0, "end_sec": 73.0, "narration_es": "Evita al guardia y abre el portón trasero."},
                {"act": "claim_payoff", "start_sec": 90.0, "end_sec": 102.0, "narration_es": "Sube al coche y llévalo directo a tu garaje."},
                {"act": "bonus_cta", "start_sec": 110.0, "end_sec": 117.5, "narration_es": "Guarda este post en marcadores para cuando juegues."},
            ],
        })
        mock_resp = MagicMock()
        mock_resp.text = fake_json

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}), \
             patch("src.guide_story_compiler.get_gemini_client", return_value=MagicMock()), \
             patch("src.guide_story_compiler.generate_content_with_retry", return_value=mock_resp):
            plan = plan_multi_beat_guide("GTA 6 Emerus Guide", 180.0, [], [], profile="x_long")

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan["beats"]), 6)
        total = sum(b["end_sec"] - b["start_sec"] for b in plan["beats"])
        self.assertGreaterEqual(total, 45.0)
        self.assertLessEqual(total, 70.0)
        map_beat = [b for b in plan["beats"] if b["act"] == "map_location"][0]
        self.assertLessEqual(map_beat["end_sec"] - map_beat["start_sec"], 5.5)

    def test_prepare_social_compatible_video_keeps_1080p_landscape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vid = Path(tmpdir) / "x_long.mp4"
            vid.write_bytes(b"0" * 2048)
            fake_probe = MagicMock(returncode=0, stdout="1920,1080\n")
            with patch("src.social_publisher.subprocess.run", return_value=fake_probe):
                out_p, is_tmp = prepare_social_compatible_video(vid)
            self.assertEqual(out_p, vid)
            self.assertFalse(is_tmp)


if __name__ == "__main__":
    unittest.main()
