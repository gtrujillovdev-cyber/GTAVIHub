import unittest
from pathlib import Path
from unittest.mock import patch

from src.thumbnail_generator import (
    _classify_caspahz_cover_badge,
    _condense_caspahz_cover_title,
    _split_caspahz_two_lines,
)
from src.social_publisher import AntiBanValidator


class TestCaspahzCoverAndReliability(unittest.TestCase):
    def test_classify_caspahz_cover_badge(self):
        badge_car, _, _ = _classify_caspahz_cover_badge("COCHE GRATIS BUGATTI EN LEONIDA")
        self.assertEqual(badge_car, "COCHE GRATIS")

        badge_gun, _, _ = _classify_caspahz_cover_badge("ARMA OCULTA EN EL PANTANO")
        self.assertEqual(badge_gun, "ARMA OCULTA")

        badge_money, _, _ = _classify_caspahz_cover_badge("CÓMO GANAR $500K POR HORA")
        self.assertEqual(badge_money, "MÉTODO $")

        badge_sec, _, _ = _classify_caspahz_cover_badge("SECRETO BAJO EL AGUA", "secretos")
        self.assertEqual(badge_sec, "SECRETO GTA 6")

    def test_condense_caspahz_cover_title(self):
        condensed = _condense_caspahz_cover_title("GTA 6: CÓMO CONSEGUIR EL BUGATTI GRATIS #GTA6 🔥", max_chars=26)
        self.assertNotIn("#", condensed)
        self.assertLessEqual(len(condensed), 26)
        self.assertTrue(len(condensed) > 0)

    def test_zero_daily_limit_returns_false_silently(self):
        with patch.dict("os.environ", {"MAX_DAILY_UPLOADS_INSTAGRAM": "0"}):
            self.assertFalse(AntiBanValidator.check_daily_limit("instagram"))

    def test_split_caspahz_two_lines(self):
        l1, l2, col = _split_caspahz_two_lines("CÓMO ROBAR COCHES Y GANAR $500K EN GTA 6")
        self.assertEqual(l1, "DINERO")
        self.assertEqual(l2, "$500K")
        self.assertEqual(col, (184, 255, 60))


if __name__ == "__main__":
    unittest.main()
