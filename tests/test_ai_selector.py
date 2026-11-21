import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.ai_selector import select_best_candidate_ai

class TestAiSelector(unittest.TestCase):
    def setUp(self):
        self.mock_candidates = [
            {
                "id": "vid_physics_viral",
                "title": "GTA 6 RAGE 9 WATER PHYSICS REALISTIC ACCIDENT",
                "duration": 28.0,
                "views": 850000,
                "velocity": 45000.0,
                "days_old": 1,
                "score": 96,
                "uploader": "Digital Foundry Fan",
                "is_short": True
            },
            {
                "id": "vid_map_secrets",
                "title": "GTA 6 LEONIDA MAP HIDDEN LOCATIONS REVEALED",
                "duration": 22.0,
                "views": 350000,
                "velocity": 18000.0,
                "days_old": 2,
                "score": 89,
                "uploader": "GTA Series Breakdown",
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
        self.assertEqual(res["id"], "vid_physics_viral")
        self.assertIn("hook_line1", res)
        self.assertIn("hook_line2", res)

    @patch("src.ai_selector.get_gemini_client")
    def test_ai_selection_with_mock_gemini(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '''
        {
            "selected_index": 0,
            "justification": "RAGE 9 physics breakdown has highest retention and technical appeal.",
            "recommended_title": "¡BRUTAL! 🌊 FÍSICAS DE AGUA EN GTA 6 DESTROZAN TODO 🔥 #GTA6",
            "hook_line1": "FÍSICAS RAGE 9",
            "hook_line2": "¡AGUA HIPERREALISTA! 🌊",
            "audience_appeal": "Atracción inmediata para la comunidad de GTA 6"
        }
        '''
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = select_best_candidate_ai(self.mock_candidates, launch_mode=False)
        self.assertEqual(res["id"], "vid_physics_viral")
        self.assertTrue(res["ai_selection"])
        self.assertEqual(res["hook_line1"], "FÍSICAS RAGE 9")
        # Hook truncado a max 20 chars en límite de palabra
        self.assertLessEqual(len(res["hook_line2"]), 22)
        self.assertIn("RAGE 9 physics", res["ai_justification"])

    @patch("src.ai_selector.get_gemini_client")
    def test_heuristic_fallback_when_gemini_fails(self, mock_get_client):
        mock_get_client.return_value = None  # Simular fallo de cliente API

        res = select_best_candidate_ai(self.mock_candidates, launch_mode=False)
        self.assertFalse(res["ai_selection"])
        self.assertEqual(res["id"], "vid_physics_viral")  # Mayor score heurístico
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
                "title": "GTA 6 MISSION 1 REAL GAMEPLAY BREAKOUT",
                "duration": 25.0,
                "views": 40000,
                "velocity": 40000.0,
                "days_old": 1,
                "score": 85
            }
        ]

        res = select_best_candidate_ai(launch_candidates, launch_mode=True)
        self.assertEqual(res["id"], "vid_fresh_breakout")

    @patch("src.ai_selector.get_gemini_client")
    def test_recommended_mode_defaults_to_dub_on_non_comparison_en_titles(self, mock_get_client):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '''
        {
            "selected_index": 0,
            "justification": "Análisis con narración inglesa sobre físicas.",
            "recommended_title": "DETALLES OCULTOS DE NPC EN GTA 6 🔥 #GTA6",
            "hook_line1": "DETALLES NPC",
            "hook_line2": "INCREÍBLE REALISMO",
            "audience_appeal": "Viral"
        }
        '''
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        cands = [{
            "id": "vid_npc_en",
            "title": "GTA 6 RAGE 9 NPC Physics Details Explained",
            "lang": "en",
            "duration": 30.0,
            "views": 100000,
            "velocity": 5000.0,
            "days_old": 1,
            "score": 90,
            "uploader": "SomeCreator"
        }]
        res = select_best_candidate_ai(cands, launch_mode=False)
        self.assertEqual(res["recommended_mode"], "dub")

        cands_vs = [{
            "id": "vid_fps_vs",
            "title": "GTA 6 30 FPS vs 60 FPS Comparison",
            "lang": "en",
            "duration": 27.0,
            "views": 200000,
            "velocity": 10000.0,
            "days_old": 1,
            "score": 95,
            "uploader": "Enigma Gaming"
        }]
        mock_resp.text = '''
        {
            "selected_index": 0,
            "justification": "Comparativa directa de rendimiento.",
            "recommended_title": "30 FPS VS 60 FPS EN GTA 6 #GTA6",
            "hook_line1": "30 FPS VS 60 FPS",
            "hook_line2": "DIFERENCIA BRUTAL",
            "audience_appeal": "Visual"
        }
        '''
        res_vs = select_best_candidate_ai(cands_vs, launch_mode=False)
        self.assertEqual(res_vs["recommended_mode"], "gameplay")

    @patch("src.ai_selector.get_gemini_client")
    def test_heuristic_prefers_visual_comparison_over_talking_head(self, mock_get_client):
        mock_get_client.return_value = None
        pool = [
            {
                "id": "talk_high_vph",
                "title": "GTA 6 30fps Debate Review Reaction",
                "uploader": "ReactionDude",
                "lang": "en",
                "duration": 520.0,
                "allow_long_clipping": True,
                "views": 180000,
                "views_per_hour": 12000.0,
                "hours_old": 15.0,
                "score": 80,
            },
            {
                "id": "visual_comp",
                "title": "GTA 6 VS RDR 2 COMPARISON (NEW DETAILS)",
                "uploader": "Onespot Gaming",
                "lang": "en",
                "duration": 179.0,
                "allow_long_clipping": True,
                "views": 17000,
                "views_per_hour": 230.0,
                "hours_old": 74.0,
                "score": 34,
            },
        ]
        with patch("src.channels.PROCESSED_FILE", Path("/nonexistent/processed.json")), \
             patch("src.channels.get_processed_ids", return_value=set()):
            res = select_best_candidate_ai(pool, launch_mode=False)
        self.assertEqual(res["id"], "visual_comp")

    def test_resolve_mode_and_reject_long_low_score_solo_filler(self):
        from src.ai_selector import _resolve_recommended_mode

        self.assertEqual(
            _resolve_recommended_mode("", {"title": "NO avances la HISTORIA de GTA 6", "lang": "es"}),
            "subs",
        )
        self.assertEqual(
            _resolve_recommended_mode("", {"title": "GTA 6 PS5 Pro 60 FPS Comparison", "lang": "es"}),
            "gameplay",
        )
        with patch("src.channels.PROCESSED_FILE", Path("/nonexistent/processed.json")), \
             patch("src.channels.get_processed_ids", return_value=set()):
            solo_filler = [{
                "id": "low_solo_long",
                "title": "Charla larga sin chicha sobre GTA 6",
                "lang": "es",
                "duration": 600,
                "allow_long_clipping": True,
                "score": 40,
            }]
            self.assertEqual(select_best_candidate_ai(solo_filler, launch_mode=False), {})

    def test_anti_monoculture_and_angle_classification(self):
        import json
        import tempfile
        from src.performance_tracker import classify_clip_angle

        # 1. Verificar clasificación correcta de creadores y mecánicas
        willy_angle = classify_clip_angle("WILLYREX PRUEBA LA MECÁNICA DE AGARRE EN GTA 6", "Willyrex")
        self.assertIn(willy_angle, ("reaccion_streamer", "fisicas_motor"))
        self.assertNotEqual(willy_angle, "gameplay_general")

        # 2. Verificar que cuando el canal ya tiene varias comparativas técnicas, rota temáticamente
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_proc = Path(tmpdir) / "processed.json"
            # Historial simulado saturado de comparativas técnicas
            hist = [
                {"id": "c1", "title": "GTA 6 vs GTA 5 Graphics", "status": "completed"},
                {"id": "c2", "title": "PS5 Pro vs Xbox Series X", "status": "completed"},
                {"id": "c3", "title": "Grand Theft Auto VI 4K Comparison", "status": "completed"}
            ]
            tmp_proc.write_text(json.dumps(hist), encoding="utf-8")

            cands = [
                {
                    "id": "cand_comp_repetitive",
                    "title": "GTA 6 Digital Foundry Technical Tech Review",
                    "uploader": "Digital Foundry",
                    "duration": 600,
                    "score": 90,
                    "views_per_hour": 15000,
                    "allow_long_clipping": True
                },
                {
                    "id": "cand_physics_fresh",
                    "title": "GTA 6 RAGE 9 Físicas de Choques y Agua Impresionantes",
                    "uploader": "GameV",
                    "duration": 25,
                    "score": 88,
                    "views_per_hour": 14000,
                    "allow_long_clipping": True
                }
            ]

            with patch("src.config.PROCESSED_FILE", tmp_proc), \
                 patch("src.channels.PROCESSED_FILE", tmp_proc), \
                 patch("src.channels.get_processed_ids", return_value=set()):
                chosen = select_best_candidate_ai(cands, launch_mode=False, use_ai=False)
                # El escudo anti-monocultura y anti-cháchara debe seleccionar el clip de físicas frescas
                self.assertEqual(chosen.get("id"), "cand_physics_fresh")


if __name__ == "__main__":
    unittest.main()
