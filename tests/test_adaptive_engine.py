import unittest
from pathlib import Path
from src.viral_discovery import calculate_virality_score
from src.downloader import snap_window_to_subtitles
from src.config import TEMP_DIR, SHORT_MIN_DURATION

class TestAdaptiveEngine(unittest.TestCase):
    def test_velocity_scoring_day1_breakout(self):
        # Vídeo subido hoy (days_old=1) con 12.000 visualizaciones debe recibir puntuación breakout inmediata (>= 28 pts)
        score_data = calculate_virality_score(
            title="NUEVO GAMEPLAY GTA 6 FILTRADO VICE CITY",
            duration=22.0,
            views=12_000,
            days_old=1,
            like_count=1_200
        )
        self.assertGreaterEqual(score_data["velocity_score"], 28)
        self.assertEqual(score_data["velocity_vpd"], 12000.0)

    def test_adaptive_snapping_short_meme(self):
        # Un clip meme o golpe de efecto de 15 segundos debe encajar sin ser descartado por límites rígidos
        test_srt = TEMP_DIR / "test_adaptive_snap.srt"
        content = (
            "1\n00:00:00,000 --> 00:00:04,000\nMira lo que hace este personaje en GTA 6.\n\n"
            "2\n00:00:04,200 --> 00:00:09,500\nEs totalmente surrealista la reacción.\n\n"
            "3\n00:00:09,800 --> 00:00:15,500\n¡No me lo puedo creer, ha saltado por el aire!\n\n"
            "4\n00:00:16,000 --> 00:00:25,000\nIncreíble momento de físicas.\n\n"
        )
        test_srt.write_text(content, encoding="utf-8")
        try:
            start, end = snap_window_to_subtitles(
                srt_path=test_srt,
                v_start=0.0,
                v_end=15.0,
                min_duration=SHORT_MIN_DURATION,
                max_duration=58.0
            )
            # La duración ajustada debe ser ~15.5s (cierre de frase 3), respetando el arquetipo corto
            self.assertEqual(start, 0.0)
            self.assertAlmostEqual(end, 15.5, delta=1.0)
            self.assertLessEqual(end - start, 20.0)
        finally:
            if test_srt.exists():
                test_srt.unlink()

    def test_adaptive_metadata_archetype_inference(self):
        from src.translator import generate_video_metadata
        # Prueba de inferencia y metadatos adaptados
        meta_parody = generate_video_metadata(
            original_title="South Park GTA 6 Parody Scene Hilarious",
            creator_name="South Park Studios"
        )
        self.assertIn("archetype", meta_parody)
        self.assertTrue(len(meta_parody["debate_question"]) > 5)
        self.assertTrue(len(meta_parody["hook"]) > 2)

if __name__ == "__main__":
    unittest.main()
