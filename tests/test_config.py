import unittest
from pathlib import Path
from src.config import (
    BASE_DIR, OUTPUT_DIR, TEMP_DIR, CHANNELS_FILE, PROCESSED_FILE, is_quant_busy,
    SHORT_MIN_DURATION, SHORT_MAX_DURATION, SHORT_TARGET_DURATION,
    ENABLE_AFFILIATE_CTAS, AFFILIATE_CTA_TIKTOK, AFFILIATE_CTA_INSTAGRAM
)
from src.downloader import snap_window_to_subtitles

class TestConfig(unittest.TestCase):
    def test_base_directory(self):
        self.assertTrue(BASE_DIR.exists())
        self.assertTrue((BASE_DIR / "main.py").exists())

    def test_channels_file_exists(self):
        self.assertTrue(CHANNELS_FILE.exists(), f"{CHANNELS_FILE} debe existir.")

    def test_output_temp_dirs(self):
        self.assertTrue(OUTPUT_DIR.exists())
        self.assertTrue(TEMP_DIR.exists())

    def test_quant_coexistence_helper(self):
        busy = is_quant_busy()
        self.assertIsInstance(busy, bool)

    def test_dynamic_duration_settings(self):
        self.assertGreaterEqual(SHORT_MIN_DURATION, 20)
        self.assertLessEqual(SHORT_MAX_DURATION, 58)
        self.assertLessEqual(SHORT_MIN_DURATION, SHORT_TARGET_DURATION)
        self.assertLessEqual(SHORT_TARGET_DURATION, SHORT_MAX_DURATION)

    def test_affiliate_settings(self):
        self.assertIsInstance(ENABLE_AFFILIATE_CTAS, bool)
        self.assertFalse(ENABLE_AFFILIATE_CTAS)  # Desactivado por defecto hasta que el usuario cree las cuentas
        self.assertTrue(len(AFFILIATE_CTA_TIKTOK) > 0)
        self.assertTrue(len(AFFILIATE_CTA_INSTAGRAM) > 0)

    def test_snap_window_to_subtitles_mock(self):
        # Crear un archivo de prueba SRT en temp
        test_srt = TEMP_DIR / "test_snap.srt"
        content = (
            "1\n00:00:10,000 --> 00:00:14,000\nPrimera frase de prueba.\n\n"
            "2\n00:00:14,200 --> 00:00:20,000\nSegunda frase interesante.\n\n"
            "3\n00:00:20,500 --> 00:00:30,000\nTercera frase del video!\n\n"
            "4\n00:00:30,200 --> 00:00:44,000\nCuarta frase con final de oración.\n\n"
            "5\n00:00:44,500 --> 00:00:55,000\nQuinta frase extra.\n"
        )
        test_srt.write_text(content, encoding="utf-8")
        try:
            # v_start estimado en 11.0s, v_end estimado en 45.0s (duración ~34s)
            s, e = snap_window_to_subtitles(test_srt, 11.0, 45.0, min_duration=25, max_duration=40)
            # El inicio debe ajustarse a 10.0s (cue 1) y el fin a 44.0s (cue 4, duración 34s)
            self.assertEqual(s, 10.0)
            self.assertEqual(e, 44.0)
            self.assertGreaterEqual(e - s, 25)
            self.assertLessEqual(e - s, 40)
        finally:
            if test_srt.exists():
                test_srt.unlink()

    def test_gameplay_release_date_toggle(self):
        from src.config import is_gameplay_enabled, GAMEPLAY_RELEASE_DATE
        import src.config as cfg
        self.assertEqual(GAMEPLAY_RELEASE_DATE, "2026-11-19")
        # En la fecha actual de octubre 2026 debe ser False
        cfg.FORCE_ENABLE_GAMEPLAY = False
        self.assertFalse(is_gameplay_enabled())
        # Con override manual debe ser True
        cfg.FORCE_ENABLE_GAMEPLAY = True
        self.assertTrue(is_gameplay_enabled())
        cfg.FORCE_ENABLE_GAMEPLAY = False

if __name__ == "__main__":
    unittest.main()
