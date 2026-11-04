import unittest
from pathlib import Path
import tempfile
from src.audio_shield import (
    detect_audio_levels,
    measure_speech_density,
    validate_audio_and_speech_vitality
)


class TestAudioShield(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_nonexistent_video(self):
        res = detect_audio_levels(Path("/nonexistent/video.mp4"))
        self.assertFalse(res["has_audio"])
        self.assertEqual(res["mean_volume"], -99.0)

    def test_speech_density_empty(self):
        srt_file = self.temp_path / "empty.srt"
        srt_file.write_text("", encoding="utf-8")
        res = measure_speech_density(srt_file, duration=25.0)
        self.assertTrue(res["has_srt"])
        self.assertEqual(res["word_count"], 0)
        self.assertFalse(res["has_substantive_speech"])

    def test_speech_density_sparse_broll(self):
        # Un clip con solo 2 o 3 palabras residuales (ej: risa o exclamación corta en 40s)
        srt_file = self.temp_path / "sparse.srt"
        content = """1\n00:00:01,000 --> 00:00:03,000\nIncreíble\n\n"""
        srt_file.write_text(content, encoding="utf-8")
        res = measure_speech_density(srt_file, duration=35.0)
        self.assertEqual(res["word_count"], 1)
        self.assertFalse(res["has_substantive_speech"])

    def test_speech_density_substantive(self):
        # Clip con comentario activo y narrativa continua
        srt_file = self.temp_path / "rich.srt"
        content = """1\n00:00:01,000 --> 00:00:05,000\nAtención a las nuevas físicas de agua en GTA 6 porque Rockstar ha superado todo lo visto.\n\n2\n00:00:05,500 --> 00:00:10,000\nEl motor RAGE 9 calcula la densidad de los fluidos y el impacto en los vehículos en tiempo real.\n\n"""
        srt_file.write_text(content, encoding="utf-8")
        res = measure_speech_density(srt_file, duration=22.0)
        self.assertGreater(res["word_count"], 15)
        self.assertTrue(res["has_substantive_speech"])

    def test_validation_rejects_sparse_speech_without_voiceover(self):
        srt_file = self.temp_path / "sparse.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHola\n\n", encoding="utf-8")
        # Video dummy simulado
        fake_video = self.temp_path / "dummy.mp4"
        fake_video.write_bytes(b"dummy_data")

        # Mock detect_audio_levels para simular audio presente pero mudo en discurso
        import unittest.mock as mock
        with mock.patch("src.audio_shield.detect_audio_levels") as mock_audio, \
             mock.patch("subprocess.run") as mock_subp:
            mock_audio.return_value = {"has_audio": True, "mean_volume": -18.0, "max_volume": -1.5}
            mock_subp.return_value = mock.Mock(stdout="30.0", returncode=0)

            is_valid, reason, _ = validate_audio_and_speech_vitality(
                video_path=fake_video,
                srt_path=srt_file,
                has_voiceover=False,
                mode="subs"
            )
            self.assertFalse(is_valid)
            self.assertIn("Densidad de voz insuficiente", reason)

    def test_validation_accepts_when_has_voiceover(self):
        # Si tiene voz en off neural generada, no importa que el SRT original no tuviera voz previa
        fake_video = self.temp_path / "dummy.mp4"
        fake_video.write_bytes(b"dummy_data")

        import unittest.mock as mock
        with mock.patch("src.audio_shield.detect_audio_levels") as mock_audio, \
             mock.patch("subprocess.run") as mock_subp:
            mock_audio.return_value = {"has_audio": True, "mean_volume": -14.0, "max_volume": -1.0}
            mock_subp.return_value = mock.Mock(stdout="24.0", returncode=0)

            is_valid, reason, _ = validate_audio_and_speech_vitality(
                video_path=fake_video,
                srt_path=None,
                has_voiceover=True,
                mode="dub"
            )
            self.assertTrue(is_valid)
            self.assertIn("verificadas con éxito", reason)


if __name__ == "__main__":
    unittest.main()
