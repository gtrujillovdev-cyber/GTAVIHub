import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.viral_discovery import calculate_virality_score
from src.downloader import snap_window_to_subtitles, find_best_transcript_hook_window
from src.channels import _parse_iso8601_duration, enrich_candidates_with_yt_api
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

    def test_parse_iso8601_duration(self):
        self.assertEqual(_parse_iso8601_duration("PT30S"), 30.0)
        self.assertEqual(_parse_iso8601_duration("PT13M45S"), 825.0)
        self.assertEqual(_parse_iso8601_duration("PT1H2M10S"), 3730.0)
        self.assertEqual(_parse_iso8601_duration("P1DT2H"), 93600.0)
        self.assertEqual(_parse_iso8601_duration("INVALID"), 0.0)
        self.assertEqual(_parse_iso8601_duration(""), 0.0)

    def test_enrich_candidates_with_yt_api_velocity(self):
        pub_5h_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        mock_yt = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "FIQ3resuPbU",
                    "snippet": {
                        "title": "GTA 6 Trailer: Everything New YOU MISSED + 30 FPS Confirmed!",
                        "channelTitle": "TGG",
                        "publishedAt": pub_5h_ago,
                    },
                    "statistics": {
                        "viewCount": "400000",
                        "likeCount": "24000",
                    },
                    "contentDetails": {
                        "duration": "PT13M45S",
                    },
                }
            ]
        }
        candidates = [
            {
                "id": "FIQ3resuPbU",
                "title": "placeholder",
                "duration": 0.0,
                "views": 0,
                "allow_long_clipping": True,
                "source_type": "viral_search",
            }
        ]
        with patch("src.uploader.get_authenticated_youtube_service", return_value=mock_yt):
            enriched = enrich_candidates_with_yt_api(candidates)

        self.assertEqual(len(enriched), 1)
        c = enriched[0]
        self.assertEqual(c["uploader"], "TGG")
        self.assertEqual(c["duration"], 825.0)
        self.assertEqual(c["views"], 400000)
        self.assertEqual(c["like_count"], 24000)
        self.assertAlmostEqual(c["hours_old"], 5.0, delta=0.3)
        self.assertGreater(c["views_per_hour"], 70000.0)

    def test_find_best_transcript_hook_window_skips_sponsor(self):
        test_srt = TEMP_DIR / "test_hook_window.srt"
        content = (
            "1\n00:00:00,500 --> 00:00:05,500\nWelcome back to the channel guys subscribe for more updates today!\n\n"
            "2\n00:00:06,000 --> 00:00:12,000\nBefore we jump in hit that like button and check the link in description.\n\n"
            "3\n00:00:12,500 --> 00:00:22,000\nToday's video is sponsored by NordVPN use code GTA6 at checkout for a huge discount.\n\n"
            "4\n00:00:22,500 --> 00:00:34,000\nNordVPN keeps your connection safe and encrypted everywhere with Patreon bonus perks.\n\n"
            "5\n00:00:40,000 --> 00:00:47,000\nNow pause right here! Look closely at the official Rockstar pre-load gameplay trailer frame!\n\n"
            "6\n00:00:47,500 --> 00:00:55,000\nConfirmed 30 FPS on PS5 with insane water physics in Vice City Leonida!\n\n"
            "7\n00:00:55,500 --> 00:01:03,000\nOh my god Lucia and Jason detail is 150 GB download size confirmed November 19!\n\n"
            "8\n00:01:15,000 --> 00:01:22,000\nThanks for watching subscribe to the channel and see you tomorrow.\n\n"
        )
        test_srt.write_text(content, encoding="utf-8")
        try:
            win = find_best_transcript_hook_window(
                test_srt,
                title="GTA 6 Breakdown",
                min_dur=18,
                max_dur=30,
                total_duration=90.0,
                use_ai=False,
            )
            self.assertIsNotNone(win)
            w_start, w_end = win
            # Debe saltarse el intro (0-12s) y el sponsor de NordVPN (12-34s) y capturar el bloque de revelación (40-63s)
            self.assertGreaterEqual(w_start, 35.0)
            self.assertLessEqual(w_end, 68.0)
            self.assertGreaterEqual(w_end - w_start, 18.0)
        finally:
            if test_srt.exists():
                test_srt.unlink()

if __name__ == "__main__":
    unittest.main()
