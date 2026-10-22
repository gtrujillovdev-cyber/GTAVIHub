import unittest
from pathlib import Path
from src.config import BASE_DIR, OUTPUT_DIR, TEMP_DIR, CHANNELS_FILE, PROCESSED_FILE, is_quant_busy

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
        # is_quant_busy debe retornar un booleano sin lanzar excepciones
        busy = is_quant_busy()
        self.assertIsInstance(busy, bool)

if __name__ == "__main__":
    unittest.main()
