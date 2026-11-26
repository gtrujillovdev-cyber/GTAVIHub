import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.guide_story_compiler import sanitize_gameplay_beats_against_menus


class TestGuideMenuFilter(unittest.TestCase):
    def test_shifts_static_menu_beat_and_keeps_map_beat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_vid = Path(tmpdir) / "src.mp4"
            fake_vid.write_bytes(b"fake")

            beats = [
                {"act": "reward_hook", "start_sec": 10.0, "end_sec": 14.5, "narration_es": "Consigue el coche."},
                {"act": "map_location", "start_sec": 30.0, "end_sec": 36.0, "narration_es": "Ve a este punto del mapa."},
                {"act": "claim_payoff", "start_sec": 80.0, "end_sec": 86.0, "narration_es": "Sube y guárdalo."},
            ]

            # Simular: t=10s es tabla de estadísticas (motion=1.8, bright_ui=0.62); t=15s (+5s) es gameplay real (motion=19.5)
            # t=80s ya es gameplay en movimiento (motion=16.0)
            def _fake_measure(_vid, s, _d, _w):
                if abs(s - 10.0) < 0.1:
                    return (1.8, 0.62)
                if abs(s - 15.0) < 0.1:
                    return (19.5, 0.08)
                return (16.0, 0.10)

            with patch("src.guide_story_compiler._measure_segment_motion_and_ui", side_effect=_fake_measure):
                cleaned = sanitize_gameplay_beats_against_menus(fake_vid, beats, source_duration=200.0, work_dir=Path(tmpdir))

            self.assertEqual(cleaned[0]["start_sec"], 15.0)
            self.assertEqual(cleaned[0]["end_sec"], 19.5)
            # map_location intacto
            self.assertEqual(cleaned[1]["start_sec"], 30.0)
            # claim_payoff ya tenía movimiento -> intacto
            self.assertEqual(cleaned[2]["start_sec"], 80.0)


if __name__ == "__main__":
    unittest.main()
