import unittest
import re
from pathlib import Path
from src.video_editor import parse_srt_file, split_cue_into_micro_bursts
from src.config import TEMP_DIR, SUBTITLE_OFFSET


def parse_first_cue_start(srt_path: Path) -> float:
    """Versión local para test sin depender de edge_tts vía dubber."""
    if not srt_path.exists():
        return 0.0
    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "-->" in line:
                    start_str = line.split("-->")[0].strip().replace(",", ".")
                    parts = start_str.split(":")
                    if len(parts) == 3:
                        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    elif len(parts) == 2:
                        return float(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return 0.0

class TestSubtitleSync(unittest.TestCase):
    def setUp(self):
        self.test_srt = TEMP_DIR / "test_sync_sample.srt"

    def tearDown(self):
        if self.test_srt.exists():
            self.test_srt.unlink()

    def test_subtitle_offset_calibration(self):
        # Un cue a las 00:00:02.000 con offset -0.45s debe iniciar en 1.55s
        content = (
            "1\n00:00:02,000 --> 00:00:05,000\nEl Joker de Florida exige dinero a Rockstar.\n\n"
        )
        self.test_srt.write_text(content, encoding="utf-8")
        bursts = parse_srt_file(self.test_srt, offset_seconds=-0.45)
        self.assertTrue(len(bursts) > 0)
        # El primer burst debe iniciar exactamente en 1.55s (2.0s - 0.45s)
        self.assertAlmostEqual(bursts[0]["start"], 1.55, places=2)

    def test_split_micro_bursts_proportional(self):
        # 6 palabras en un intervalo de 3.0s deben dividirse en 2 ráfagas armónicas
        bursts = split_cue_into_micro_bursts(
            text="GTA 6 mapa filtrado es gigante",
            start=1.0,
            end=4.0,
            max_words=3
        )
        self.assertEqual(len(bursts), 2)
        self.assertEqual(bursts[0]["text"], "GTA 6 mapa")
        self.assertEqual(bursts[1]["text"], "filtrado es gigante")
        self.assertEqual(bursts[0]["start"], 1.0)
        self.assertGreater(bursts[1]["start"], bursts[0]["start"])
        self.assertLessEqual(bursts[1]["end"], 4.0)

    def test_first_cue_detection_for_tts(self):
        content = (
            "1\n00:00:01,800 --> 00:00:04,500\nInicio de la locución tras silencio.\n\n"
        )
        self.test_srt.write_text(content, encoding="utf-8")
        first_t = parse_first_cue_start(self.test_srt)
        self.assertAlmostEqual(first_t, 1.8, places=2)

if __name__ == "__main__":
    unittest.main()
