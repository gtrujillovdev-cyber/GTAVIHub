import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import src.performance_tracker as pt


class TestTrackingScorecard(unittest.TestCase):
    def test_record_published_video_and_sync_matches_by_youtube_url_and_snapshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            perf_file = Path(tmpdir) / "performance_records.json"
            with patch.object(pt, "PERF_FILE", perf_file):
                pt.record_published_video(
                    video_id="source_orig_123",
                    title="Cómo conseguir este Truffade Thrax GRATIS en GTA 6",
                    youtube_url="https://youtu.be/YT_UP_999",
                    is_short=False,
                    source_type="16:9_multibeat",
                    preset="D_89%",
                    has_frame0_cover=True,
                    duration_sec=21.0,
                    topic="coche_gratis",
                    publish_slot="10:53",
                )
                pub_25h_ago = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
                mock_recent = [
                    {
                        "id": "YT_UP_999",
                        "title": "Cómo conseguir este Truffade Thrax GRATIS en GTA 6",
                        "url": "https://youtu.be/YT_UP_999",
                        "views": 1450,
                        "likes": 88,
                        "comments": 12,
                        "published_at": pub_25h_ago,
                    }
                ]
                with patch("src.youtube_analytics.fetch_recent_videos", return_value=mock_recent):
                    live = pt.sync_live_channel_metrics(limit=10)

                self.assertEqual(len(live), 1)
                saved = json.loads(perf_file.read_text(encoding="utf-8"))
                self.assertEqual(len(saved), 1)  # No duplicate row created
                rec = saved[0]
                self.assertEqual(rec["video_id"], "source_orig_123")
                self.assertEqual(rec["youtube_video_id"], "YT_UP_999")
                self.assertEqual(rec["views_live"], 1450)
                self.assertEqual(rec["views_24h"], 1450)
                self.assertIsNotNone(rec["snapshots"]["6h"])
                self.assertIsNotNone(rec["snapshots"]["24h"])
                self.assertIsNone(rec["snapshots"]["48h"])
                self.assertEqual(rec["experiment"]["source_type"], "16:9_multibeat")
                self.assertEqual(rec["experiment"]["topic"], "coche_gratis")

                scorecard = pt.generate_weekly_scorecard(days=7, update_playbook=False)
                self.assertTrue(scorecard["ok"])
                self.assertEqual(scorecard["total_clips"], 1)
                self.assertEqual(scorecard["total_views"], 1450)
                text = pt.format_weekly_scorecard_telegram(scorecard)
                self.assertIn("Scorecard Tracking", text)
                self.assertIn("16:9_multibeat", text)


if __name__ == "__main__":
    unittest.main()
