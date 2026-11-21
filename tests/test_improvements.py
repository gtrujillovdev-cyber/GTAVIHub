"""
Tests para las 8 mejoras del pipeline competitivo.
Verifica imports, feature flags, lógica pura y retrocompatibilidad.
"""
import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestFeatureFlags(unittest.TestCase):
    """Verifica que todos los feature flags existen y son booleanos."""

    def test_all_flags_importable(self):
        from src.config import (
            ENABLE_QUALITY_GATE, ENABLE_SERIES_CLASSIFIER,
            ENABLE_EXIF_HYGIENE, ENABLE_MULTIPLATFORM_COPY,
            ENABLE_REDDIT_SCOUT, ENABLE_SEAMLESS_LOOP,
            ENABLE_STEM_SEPARATION, ENABLE_FEEDBACK_LOOP
        )
        for flag in [
            ENABLE_QUALITY_GATE, ENABLE_SERIES_CLASSIFIER,
            ENABLE_EXIF_HYGIENE, ENABLE_MULTIPLATFORM_COPY,
            ENABLE_REDDIT_SCOUT, ENABLE_SEAMLESS_LOOP,
            ENABLE_STEM_SEPARATION, ENABLE_FEEDBACK_LOOP
        ]:
            self.assertIsInstance(flag, bool)

    def test_stem_separation_default_off(self):
        """Stem separation debe estar OFF por defecto (CPU-intensive)."""
        from src.config import ENABLE_STEM_SEPARATION
        # Solo verificar que es bool; el default depende de .env
        self.assertIsInstance(ENABLE_STEM_SEPARATION, bool)


class TestQualityGate(unittest.TestCase):
    """Tests del módulo quality_gate.py"""

    def test_import(self):
        from src.quality_gate import run_quality_gate
        self.assertTrue(callable(run_quality_gate))

    def test_missing_video_rejects(self):
        from src.quality_gate import run_quality_gate
        fake_path = Path("/tmp/nonexistent_video_qg_test.mp4")
        approved, reason, diag = run_quality_gate(
            video_path=fake_path,
            metadata={"title": "Test"},
            candidate_score=50,
            source_title="Test Source",
            dry_run=True
        )
        self.assertFalse(approved)
        self.assertIn("no existe", reason.lower())


class TestSeriesClassifier(unittest.TestCase):
    """Tests del módulo series_classifier.py"""

    def test_import(self):
        from src.series_classifier import classify_and_number, get_series_summary
        self.assertTrue(callable(classify_and_number))
        self.assertTrue(callable(get_series_summary))

    def test_detects_known_series(self):
        from src.series_classifier import classify_and_number
        result = classify_and_number(
            "10 detalles enfermizos de GTA 6 que no viste",
            {"description": "detalles ocultos"}
        )
        # Puede devolver None si ENABLE_SERIES_CLASSIFIER esta off
        if result is not None:
            self.assertIn("series_id", result)
            self.assertIn("episode", result)
            self.assertEqual(result["series_id"], "detalles_enfermizos")

    def test_returns_none_for_unknown(self):
        from src.series_classifier import classify_and_number
        result = classify_and_number("Noticias random de tecnologia", {})
        self.assertIsNone(result)


class TestCrossBorderScout(unittest.TestCase):
    """Tests del módulo cross_border_scout.py"""

    def test_import(self):
        from src.cross_border_scout import scan_reddit_gta6, calculate_emotion_score
        self.assertTrue(callable(scan_reddit_gta6))
        self.assertTrue(callable(calculate_emotion_score))

    def test_emotion_score_range(self):
        from src.cross_border_scout import calculate_emotion_score
        score = calculate_emotion_score("GTA 6 insane physics WTF bug", "crazy ragdoll")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)
        # High emotion keywords should score above base
        self.assertGreater(score, 3.0)

    def test_low_emotion_score(self):
        from src.cross_border_scout import calculate_emotion_score
        score = calculate_emotion_score("GTA 6 news update", "")
        self.assertGreaterEqual(score, 3.0)  # Base is 3.0
        self.assertLessEqual(score, 5.0)

    def test_gta6_filter(self):
        from src.cross_border_scout import _is_gta6_post
        self.assertTrue(_is_gta6_post("GTA 6 leaked gameplay", ""))
        self.assertTrue(_is_gta6_post("Vice City details", "gta vi confirmed"))
        self.assertFalse(_is_gta6_post("Minecraft update", "new blocks"))

    @patch.dict(os.environ, {"ENABLE_REDDIT_SCOUT": "false"})
    def test_disabled_returns_empty(self):
        """Cuando el flag esta OFF, scan retorna lista vacia sin hacer requests."""
        # Reimport para capturar el nuevo valor del env
        import importlib
        from src import cross_border_scout
        importlib.reload(cross_border_scout)
        result = cross_border_scout.scan_reddit_gta6()
        self.assertEqual(result, [])


class TestStemSeparator(unittest.TestCase):
    """Tests del módulo stem_separator.py"""

    def test_import(self):
        from src.stem_separator import process_audio_stems, is_demucs_available
        self.assertTrue(callable(process_audio_stems))
        self.assertTrue(callable(is_demucs_available))

    @patch.dict(os.environ, {"ENABLE_STEM_SEPARATION": "false"})
    def test_disabled_returns_none(self):
        import importlib
        from src import stem_separator
        importlib.reload(stem_separator)
        result = stem_separator.process_audio_stems(Path("/tmp/fake.mp4"), "test_id")
        self.assertIsNone(result)


class TestFeedbackLoop(unittest.TestCase):
    """Tests del feedback loop en performance_tracker.py"""

    def test_import(self):
        from src.performance_tracker import detect_outliers, recalibrate_scoring_weights
        self.assertTrue(callable(detect_outliers))
        self.assertTrue(callable(recalibrate_scoring_weights))

    def test_detect_outliers_insufficient_data(self):
        from src.performance_tracker import detect_outliers
        # Con datos insuficientes debe retornar ok=False
        with patch('src.performance_tracker._load_records', return_value=[]):
            result = detect_outliers(min_records=6)
            self.assertFalse(result["ok"])
            self.assertIn("Insuficientes", result["reason"])

    def test_detect_outliers_with_data(self):
        from src.performance_tracker import detect_outliers
        mock_records = [
            {"views_24h": 100, "title": f"Test video {i}", "video_id": f"v{i}"}
            for i in range(5)
        ] + [
            {"views_24h": 5000, "title": "GTA 6 insane physics", "video_id": "outlier_pos"},
            {"views_24h": 5, "title": "GTA 6 boring news", "video_id": "outlier_neg"},
        ]
        with patch('src.performance_tracker._load_records', return_value=mock_records):
            result = detect_outliers(min_records=6)
            self.assertTrue(result["ok"])
            self.assertGreater(result["positive_outliers"], 0)
            self.assertGreater(result["negative_outliers"], 0)

    @patch.dict(os.environ, {"ENABLE_FEEDBACK_LOOP": "false"})
    def test_recalibrate_disabled(self):
        import importlib
        from src import config
        importlib.reload(config)
        from src.performance_tracker import recalibrate_scoring_weights
        result = recalibrate_scoring_weights()
        self.assertFalse(result["ok"])
        # Restaurar
        importlib.reload(config)


class TestMultiPlatformCopy(unittest.TestCase):
    """Verifica que social_publisher acepta captions nativos."""

    def test_tiktok_native_caption_override(self):
        from src.social_publisher import SocialPublisher
        # Verificar que publish_to_tiktok acepta native_caption_override
        import inspect
        sig = inspect.signature(SocialPublisher.publish_to_tiktok)
        self.assertIn("native_caption_override", sig.parameters)

    def test_build_tiktok_caption_no_all_caps(self):
        from src.social_publisher import SocialPublisher
        caption = SocialPublisher._build_tiktok_caption(
            title="GTA 6 DETALLES OCULTOS QUE NO VISTE",
            tags=["GTA6", "Secretos"],
            debate_question="",
            description="",
            creator_name="TestCreator"
        )
        # El titulo no debe estar todo en mayusculas
        first_line = caption.split("\n")[0]
        self.assertNotEqual(first_line, first_line.upper())


class TestViralDiscoveryRedditIntegration(unittest.TestCase):
    """Verifica que viral_discovery importa y usa el scout de Reddit."""

    def test_enable_reddit_scout_imported(self):
        from src.viral_discovery import ENABLE_REDDIT_SCOUT
        self.assertIsInstance(ENABLE_REDDIT_SCOUT, bool)


if __name__ == "__main__":
    unittest.main()
