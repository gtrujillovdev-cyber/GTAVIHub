import unittest
from unittest.mock import MagicMock, patch
from src.ai_selector import select_best_candidate_ai

class TestAiSelector(unittest.TestCase):
    def setUp(self):
        self.mock_candidates = [
            {
                "id": "vid_southpark",
                "title": "SOUTH PARK GTA 6 PARODY VIRAL SCENE",
                "duration": 28.0,
                "views": 450000,
                "velocity": 15000.0,
                "days_old": 1,
                "score": 95,
                "uploader": "Comedy Central Fan",
                "is_short": True
            },
            {
                "id": "vid_physics",
                "title": "GTA 6 RAGE 9 WATER PHYSICS REALISTIC ACCIDENT",
                "duration": 22.0,
                "views": 250000,
                "velocity": 8000.0,
                "days_old": 2,
                "score": 88,
                "uploader": "Tech Analyst",
                "is_short": True
            },
            {
                "id": "vid_old_filler",
                "title": "GTA 6 STREAMER TALKS ABOUT TRAILER",
                "duration": 50.0,
                "views": 12000,
                "velocity": 100.0,
                "days_old": 25,
                "score": 55,
                "uploader": "Old Streamer",
                "is_short": True
            }
        ]

    def test_empty_candidates_returns_empty(self):
        res = select_best_candidate_ai([])
        self.assertEqual(res, {})

    def test_single_candidate_enrichment(self):
        single = [self.mock_candidates[0]]
        res = select_best_candidate_ai(single)
        self.assertEqual(res["id"], "vid_southpark")
        self.assertIn("hook_line1", res)
        self.assertIn("hook_line2", res)

    @patch("src.ai_selector.get_gemini_client")
    def test_ai_selection_with_mock_gemini(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '''
        {
            "selected_index": 0,
            "justification": "South Park parody has massive pop culture momentum and high retention.",
            "recommended_title": "¡INCREÍBLE! 💀 SOUTH PARK DESTROZA GTA 6 CON ESTA PARODIA VIRAL 🔥 #GTA6",
            "hook_line1": "SOUTH PARK LO HIZO",
            "hook_line2": "¡PARODIA A GTA 6! 💀",
            "audience_appeal": "Atracción inmediata para fans de GTA y comedia"
        }
        '''
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = select_best_candidate_ai(self.mock_candidates, launch_mode=False)
        self.assertEqual(res["id"], "vid_southpark")
        self.assertTrue(res["ai_selection"])
        self.assertEqual(res["hook_line1"], "SOUTH PARK LO HIZO")
        self.assertEqual(res["hook_line2"], "¡PARODIA A GTA 6! 💀")
        self.assertIn("South Park parody", res["ai_justification"])

    @patch("src.ai_selector.get_gemini_client")
    def test_heuristic_fallback_when_gemini_fails(self, mock_get_client):
        mock_get_client.return_value = None  # Simular fallo de cliente API

        res = select_best_candidate_ai(self.mock_candidates, launch_mode=False)
        self.assertFalse(res["ai_selection"])
        self.assertEqual(res["id"], "vid_southpark")  # Mayor score heurístico
        self.assertIsNotNone(res["hook_line1"])
        self.assertIsNotNone(res["hook_line2"])

    @patch("src.ai_selector.get_gemini_client")
    def test_launch_mode_heuristic_prioritizes_velocity(self, mock_get_client):
        mock_get_client.return_value = None

        launch_candidates = [
            {
                "id": "vid_slow_old",
                "title": "GTA 6 OLD SPECULATION",
                "duration": 30.0,
                "views": 500000,
                "velocity": 500.0,
                "days_old": 10,
                "score": 90
            },
            {
                "id": "vid_fresh_breakout",
                "title": "GTA 6 MISSION 1 REAL GAMEPLAY LEAK",
                "duration": 25.0,
                "views": 40000,
                "velocity": 40000.0,
                "days_old": 1,
                "score": 85
            }
        ]

        res = select_best_candidate_ai(launch_candidates, launch_mode=True)
        self.assertEqual(res["id"], "vid_fresh_breakout")

if __name__ == "__main__":
    unittest.main()
