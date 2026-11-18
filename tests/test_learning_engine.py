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

if __name__ == "__main__":
    unittest.main()
