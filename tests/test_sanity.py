import unittest

class TestSanity(unittest.TestCase):
    def test_imports(self):
        import src.channels
        import src.cleaner
        import src.config
        import src.downloader
        import src.dubber
        import src.monitor
        import src.pipeline
        import src.social_publisher
        import src.telegram_bot
        import src.telemetry
        import src.youtube_analytics
        import src.copilot
        import src.viral_discovery
        import src.thumbnail_generator
        import src.translator
        import src.uploader
        import src.video_editor

    def test_subtitle_burst_timing_clamp(self):
        from src.video_editor import split_cue_into_micro_bursts
        # Frase con duración excesiva de 30 segundos (glitch común de subtítulos automáticos)
        bursts = split_cue_into_micro_bursts("Caray vamos rápido", start=10.0, end=40.0)
        self.assertGreaterEqual(len(bursts), 1)
        # Cada ráfaga nunca debe superar 1.8 segundos
        for b in bursts:
            dur = b["end"] - b["start"]
            self.assertLessEqual(dur, 2.1)
            self.assertGreaterEqual(dur, 0.4)

    def test_tag_cleaning_and_no_word_fusion(self):
        from src.video_editor import clean_text_no_emoji
        # Simulación de tags VTT de YouTube que fusionaban palabras ("FILTRADOUN")
        raw_text = "<c> filtrado</c><c> un</c> tío"
        cleaned = clean_text_no_emoji(raw_text)
        self.assertEqual(cleaned, "filtrado un tío")
        self.assertNotIn("filtradoun", cleaned)

        # Palabras pegadas por mayúsculas
        camel = "filtradoUnMapa"
        cleaned_camel = clean_text_no_emoji(camel)
        self.assertEqual(cleaned_camel, "filtrado Un Mapa")

    def test_word_timing_continuity(self):
        from src.video_editor import calculate_word_timing
        words = ["ILLOJUAN", "ENSEÑA", "EL", "MAPA"]
        timings = calculate_word_timing(words, 1.0, 3.0)
        self.assertEqual(len(timings), 4)
        for i in range(len(timings) - 1):
            # Continuidad perfecta sin huecos oscuros
            self.assertEqual(timings[i]["end"], timings[i + 1]["start"])

    def test_render_karaoke_pill_subtitle(self):
        import tempfile
        from pathlib import Path
        from src.video_editor import render_karaoke_subtitle_state
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp_path = Path(tmp.name)
            ok = render_karaoke_subtitle_state(["ILLOJUAN", "ENSEÑA"], active_idx=0, is_vertical=True, output_path=tmp_path)
            self.assertTrue(ok)
            self.assertTrue(tmp_path.exists())
            self.assertGreater(tmp_path.stat().st_size, 100)

if __name__ == "__main__":
    unittest.main()
