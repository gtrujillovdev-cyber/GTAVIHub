import os
import unittest
from unittest.mock import patch

from src.social_publisher import AntiBanValidator
from src.config import get_ffmpeg_threads, FFMPEG_THREADS


class TestSocialLimits(unittest.TestCase):
    def test_per_platform_limits_from_env(self):
        env = {
            "MAX_DAILY_UPLOADS_YOUTUBE": "4",
            "MAX_DAILY_UPLOADS_TIKTOK": "5",
            "MAX_DAILY_UPLOADS_INSTAGRAM": "7",
        }
        with patch.dict(os.environ, env):
            self.assertEqual(AntiBanValidator.get_daily_limit("youtube"), 4)
            self.assertEqual(AntiBanValidator.get_daily_limit("TikTok"), 5)
            self.assertEqual(AntiBanValidator.get_daily_limit("instagram"), 7)

    def test_generic_fallback(self):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("MAX_DAILY_UPLOADS")}
        clean["MAX_DAILY_UPLOADS"] = "3"
        with patch.dict(os.environ, clean, clear=True):
            for platform in ("youtube", "tiktok", "instagram", "otra"):
                self.assertEqual(AntiBanValidator.get_daily_limit(platform), 3)

    def test_monitor_does_not_use_removed_constant(self):
        self.assertFalse(hasattr(AntiBanValidator, "MAX_DAILY_UPLOADS"))
        import pathlib
        src = (pathlib.Path(__file__).parent.parent / "src" / "monitor.py").read_text()
        self.assertNotIn("AntiBanValidator.MAX_DAILY_UPLOADS", src)

    def test_ffmpeg_threads_courtesy_mode(self):
        with patch("src.config.is_quant_busy", return_value=True):
            self.assertEqual(get_ffmpeg_threads(), 1)
        with patch("src.config.is_quant_busy", return_value=False):
            self.assertEqual(get_ffmpeg_threads(), FFMPEG_THREADS)


if __name__ == "__main__":
    unittest.main()
