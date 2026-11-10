import unittest
from unittest import mock
from pathlib import Path
import tempfile
from src.translator import transcribe_and_translate_audio_gemini

class TestAudioTranscription(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_nonexistent_audio(self):
        output_srt = self.temp_path / "out.srt"
        success, has_speech = transcribe_and_translate_audio_gemini(
            Path("/nonexistent/audio.mp3"),
            output_srt
        )
        self.assertFalse(success)
        self.assertFalse(has_speech)

    def test_almost_empty_audio(self):
        small_audio = self.temp_path / "tiny.mp3"
        small_audio.write_bytes(b"12345")
        output_srt = self.temp_path / "out.srt"
        success, has_speech = transcribe_and_translate_audio_gemini(
            small_audio,
            output_srt
        )
        self.assertTrue(success)
        self.assertFalse(has_speech)

    @mock.patch("src.translator.get_gemini_client")
    @mock.patch("src.translator.generate_content_with_retry")
    def test_no_speech_detected(self, mock_generate, mock_get_client):
        audio_file = self.temp_path / "gameplay.mp3"
        audio_file.write_bytes(b"A" * 2000)
        output_srt = self.temp_path / "out.srt"

        mock_resp = mock.Mock()
        mock_resp.text = "NO_SPEECH"
        mock_generate.return_value = mock_resp

        success, has_speech = transcribe_and_translate_audio_gemini(
            audio_file,
            output_srt
        )
        self.assertTrue(success)
        self.assertFalse(has_speech)
        self.assertFalse(output_srt.exists())

    @mock.patch("src.translator.get_gemini_client")
    @mock.patch("src.translator.generate_content_with_retry")
    def test_valid_speech_translation(self, mock_generate, mock_get_client):
        audio_file = self.temp_path / "speech.mp3"
        audio_file.write_bytes(b"A" * 2000)
        output_srt = self.temp_path / "out.srt"

        mock_resp = mock.Mock()
        mock_resp.text = (
            "1\n00:00:01,000 --> 00:00:03,500\n"
            "Atención a las físicas del agua\n\n"
            "2\n00:00:03,600 --> 00:00:06,000\n"
            "Rockstar ha mejorado todo\n\n"
        )
        mock_generate.return_value = mock_resp

        success, has_speech = transcribe_and_translate_audio_gemini(
            audio_file,
            output_srt
        )
        self.assertTrue(success)
        self.assertTrue(has_speech)
        self.assertTrue(output_srt.exists())
        content = output_srt.read_text(encoding="utf-8")
        self.assertIn("físicas del agua", content)

if __name__ == "__main__":
    unittest.main()
