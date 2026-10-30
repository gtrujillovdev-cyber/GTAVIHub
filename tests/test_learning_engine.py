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

if __name__ == "__main__":
    unittest.main()
