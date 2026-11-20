import unittest
from pathlib import Path
from src.learning_engine import (
    load_viral_playbook,
    save_viral_playbook,
    get_playbook_context_for_prompt,
    generate_learning_telegram_report,
    DEFAULT_PLAYBOOK
)

class TestLearningEngine(unittest.TestCase):
    def test_load_and_save_playbook(self):
        pb = load_viral_playbook()
        self.assertIn("active_heuristics", pb)
        self.assertIn("channel_diagnosis", pb)

        # Test prompt injection string
        prompt_injection = get_playbook_context_for_prompt()
        self.assertIn("DIRECTRICES APRENDIDAS DEL CANAL", prompt_injection)
        self.assertIn("ESTRUCTURAS DE TÍTULO COMPROBADAS", prompt_injection)
        self.assertIn("GANCHOS SUPERIORES", prompt_injection)

    def test_report_generation(self):
        report = generate_learning_telegram_report(DEFAULT_PLAYBOOK)
        self.assertIn("MOTOR DE APRENDIZAJE Y AUTO-PERFECCIONAMIENTO", report)
        self.assertIn("Diagnóstico de Nuestro Canal", report)
        self.assertIn("Benchmarking", report)

    def test_hydrogen_retry_and_cet_phase_alignment(self):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        from src.translator import generate_content_with_retry
        from src.knowledge_recycler import determine_current_phase

        # 1. Al cruzar 2026-11-19 00:00 CET (= 2026-11-18 23:00 UTC), la fase debe cambiar a launch_day
        self.assertEqual(
            determine_current_phase(datetime(2026, 11, 18, 22, 59, tzinfo=timezone.utc)),
            "pre_launch",
        )
        self.assertEqual(
            determine_current_phase(datetime(2026, 11, 18, 23, 1, tzinfo=timezone.utc)),
            "launch_day",
        )

        # 2. generate_content_with_retry debe rotar de gemini-4-hydrogen a gemini-2.5-flash conservando config
        mock_client = MagicMock()
        ok_resp = MagicMock()
        ok_resp.text = '{"status": "ok"}'
        mock_client.models.generate_content.side_effect = [
            RuntimeError("429 RESOURCE_EXHAUSTED"),
            ok_resp,
        ]
        res = generate_content_with_retry(
            client=mock_client,
            contents="ping",
            models=["gemini-4-hydrogen", "gemini-2.5-flash"],
            config={"response_mime_type": "application/json"},
        )
        self.assertEqual(res.text, '{"status": "ok"}')
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        second_call_kwargs = mock_client.models.generate_content.call_args_list[1].kwargs
        self.assertEqual(second_call_kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(second_call_kwargs["config"], {"response_mime_type": "application/json"})

    def test_route_platforms_by_alpha(self):
        from unittest.mock import patch
        from src.learning_engine import route_platforms_by_alpha

        # 1. Universal (secreto / objeto oculto): mantiene todas las redes
        plats_u, _ = route_platforms_by_alpha(
            ["youtube", "tiktok", "instagram"],
            {"title": "ARMA LEGENDARIA OCULTA EN LEONIDA", "has_voiceover": True},
        )
        self.assertEqual(plats_u, ["youtube", "tiktok", "instagram"])

        # 2. TikTok-first (gameplay mudo sin voz ni streamer): evita quemar YouTube Shorts
        plats_tt, _ = route_platforms_by_alpha(
            ["youtube", "tiktok", "instagram"],
            {"title": "GTA 6 Mundo Abierto PS5 Pro", "has_voiceover": False, "mode": "gameplay"},
            creator_name="DubStepZz",
        )
        self.assertEqual(plats_tt, ["tiktok", "instagram"])

        # 3. YouTube-first (streamer hispano cuando YouTube no está en cooldown): reserva TikTok
        with patch("src.uploader._is_youtube_upload_blocked_by_cooldown", return_value=(False, "")):
            plats_yt, _ = route_platforms_by_alpha(
                ["youtube", "tiktok", "instagram"],
                {"title": "Willyrex prueba GTA 6", "has_voiceover": False, "mode": "gameplay"},
                creator_name="Willyrex",
            )
        self.assertEqual(plats_yt, ["youtube", "instagram"])

if __name__ == "__main__":
    unittest.main()
