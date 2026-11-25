import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.clean_telegram_media import clean_telegram_media, log_telegram_media_message


class TestCleanTelegramMedia(unittest.TestCase):
    def test_log_and_clean_respects_hours_and_48h_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "telegram_media_log.json"
            now = time.time()
            entries = [
                {"chat_id": "123", "message_id": 101, "kind": "video", "label": "old_expired", "sent_at": now - 49 * 3600},
                {"chat_id": "123", "message_id": 102, "kind": "video", "label": "deletable", "sent_at": now - 15 * 3600},
                {"chat_id": "123", "message_id": 103, "kind": "photo", "label": "fresh", "sent_at": now - 1 * 3600},
            ]
            log_file.write_text(json.dumps(entries), encoding="utf-8")

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": True}

            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake_token"}), \
                 patch("scripts.clean_telegram_media.requests.post", return_value=mock_resp) as mock_post:
                stats = clean_telegram_media(hours=12.0, log_file=log_file)

            self.assertEqual(stats["deleted"], 1)
            self.assertEqual(stats["expired_48h"], 1)
            self.assertEqual(stats["kept"], 1)
            self.assertEqual(stats["failed"], 0)
            mock_post.assert_called_once()
            remaining = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertEqual([e["message_id"] for e in remaining], [103])

    def test_log_telegram_media_message_appends(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "telegram_media_log.json"
            log_telegram_media_message("123", 555, kind="video", label="clip.mp4", log_file=log_file)
            data = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["message_id"], 555)
            self.assertEqual(data[0]["kind"], "video")


if __name__ == "__main__":
    unittest.main()
