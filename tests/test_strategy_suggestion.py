import unittest
from src.downloader import suggest_video_strategy

class TestStrategySuggestion(unittest.TestCase):
    def test_comparativa_loop(self):
        strat = suggest_video_strategy(
            title="GTA VI Trailer 2 - GTA 6 vs GTA 5 Graphics",
            duration_sec=13,
            uploader="Vililo"
        )
        self.assertEqual(strat["recommended_opt"], "gameplay")
        self.assertEqual(strat["archetype"], "Comparativa Visual en Loop")
        self.assertIn("Loop", strat["badge"])
        self.assertIn("VS", strat["hook_text"])

    def test_listicle_spanish(self):
        strat = suggest_video_strategy(
            title="5 DETALLES ALUCINANTES de los GRÁFICOS de GTA 6 🔥",
            duration_sec=38,
            uploader="Vandal"
        )
        self.assertEqual(strat["recommended_opt"], "short")
        self.assertEqual(strat["archetype"], "Listicle de Detalles & Curiosidades")
        self.assertIn("Listicle", strat["badge"])

    def test_listicle_english(self):
        strat = suggest_video_strategy(
            title="5 secrets in GTA 6 map that confirm Vice City",
            duration_sec=35,
            uploader="GTA Series Videos"
        )
        self.assertEqual(strat["recommended_opt"], "dub")
        self.assertIn("Listicle", strat["archetype"])
        self.assertIn("Doblaje", strat["badge"])

    def test_physics_gameplay(self):
        strat = suggest_video_strategy(
            title="GTA 6 RAGE 9 WATER PHYSICS REALISTIC ACCIDENT",
            duration_sec=28,
            uploader="Rockstar Mag"
        )
        self.assertEqual(strat["recommended_opt"], "gameplay")
        self.assertIn("Físicas", strat["archetype"])

    def test_english_general_breakdown(self):
        strat = suggest_video_strategy(
            title="Everything we learned from the new trailer",
            duration_sec=50,
            uploader="TGG"
        )
        self.assertEqual(strat["recommended_opt"], "dub")
        self.assertIn("Inglés", strat["archetype"])

if __name__ == "__main__":
    unittest.main()
