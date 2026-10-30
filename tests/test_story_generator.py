import unittest
from pathlib import Path
from src.story_generator import (
    generate_clean_product_story,
    build_hardware_deal_story,
    PALETTE,
    STORY_WIDTH,
    STORY_HEIGHT
)

class TestStoryGenerator(unittest.TestCase):
    def test_dimensions_and_palette(self):
        self.assertEqual(STORY_WIDTH, 1080)
        self.assertEqual(STORY_HEIGHT, 1920)
        self.assertIn("neon_magenta", PALETTE)
        self.assertIn("miami_cyan", PALETTE)
        self.assertIn("leonida_gold", PALETTE)

    def test_generate_clean_product_story(self):
        out_path = Path("output/stories/test_unit_story.jpg")
        res = generate_clean_product_story(
            badge_text="🏎️ TEST GTA VI",
            product_title="LOGITECH G29",
            price_tag="199€",
            discount_pill="-35% DTO",
            cta_text="VER OFERTA ➔",
            output_path=out_path
        )
        self.assertTrue(res.exists())
        self.assertGreater(res.stat().st_size, 50000) # Más de 50KB
        res.unlink(missing_ok=True)

    def test_build_hardware_deal_story(self):
        img_path, url, caption = build_hardware_deal_story("volante_logitech_g29")
        self.assertTrue(img_path.exists())
        self.assertIn("amazon.es", url)
        self.assertIn("gtavihub-21", url)
        self.assertIn("#GTA6", caption)
        img_path.unlink(missing_ok=True)
