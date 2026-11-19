import json
import tempfile
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import src.performance_tracker as pt
from src.pipeline import process_single_video
from src.translator import generate_mechanical_editorial_srt, generate_editorial_commentary_srt
from src.ai_selector import _resolve_recommended_mode
from src.social_publisher import AntiBanValidator
from src.channels import get_daily_published_count


class TestPhase1Fixes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_perf_file = pt.PERF_FILE
        pt.PERF_FILE = Path(self.test_dir) / "performance_records.json"

    def tearDown(self):
        pt.PERF_FILE = self.orig_perf_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_fetch_pending_metrics_mixed_naive_and_aware_datetimes(self):
        old_utc = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        old_naive = (datetime.now() - timedelta(hours=25)).isoformat()
        recent_utc = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        records = [
            {
                "video_id": "vid_utc",
                "title": "Video UTC",
                "youtube_url": "https://youtu.be/vid_utc",
                "published_at": old_utc,
                "metrics_fetched_at": None,
            },
            {
                "video_id": "vid_naive",
                "title": "Video Naive",
                "youtube_url": "https://youtu.be/vid_naive",
                "published_at": old_naive,
                "metrics_fetched_at": None,
            },
            {
                "video_id": "vid_recent",
                "title": "Video Recent",
                "youtube_url": "https://youtu.be/vid_recent",
                "published_at": recent_utc,
                "metrics_fetched_at": None,
            },
        ]
        pt.PERF_FILE.write_text(json.dumps(records), encoding="utf-8")

        mock_proc = MagicMock(returncode=0, stdout="1500\t42\t5\n")
        with patch("src.performance_tracker.subprocess.run", return_value=mock_proc):
            updated = pt.fetch_pending_metrics(max_fetch=5)

        self.assertEqual(updated, 2)
        saved = json.loads(pt.PERF_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["views_24h"], 1500)
        self.assertEqual(saved[1]["views_24h"], 1500)
        self.assertIsNone(saved[2].get("views_24h"))

    def test_pipeline_precheck_aborts_when_quotas_full(self):
        with patch("src.social_publisher.AntiBanValidator.check_daily_limit", return_value=False), \
             patch("src.pipeline.enforce_storage_limits"), \
             patch("src.pipeline.download_video_and_subtitles") as mock_dl:
            res = process_single_video(
                url="https://youtu.be/test_vid_123",
                video_id="test_vid_123",
                original_title="GTA 6 PS5 Pro Gameplay",
                mode="subs",
                auto_upload=True,
            )
        self.assertIsNone(res)
        mock_dl.assert_not_called()

    def test_mechanical_editorial_srt_fallback_on_quota_error(self):
        dummy_video = Path(self.test_dir) / "clip.mp4"
        dummy_video.write_bytes(b"\x00" * 1024)
        out_srt = Path(self.test_dir) / "editorial.srt"

        # Direct mechanical generation
        ok = generate_mechanical_editorial_srt(
            out_srt,
            original_title="GTA 6 PS5 Pro vs Xbox Series X 4K FPS",
            duration_sec=24.0,
        )
        self.assertTrue(ok)
        txt = out_srt.read_text(encoding="utf-8")
        self.assertIn("-->", txt)
        self.assertIn("comparativa", txt.lower())

        # Fallback when Gemini raises 429 quota error
        out_srt2 = Path(self.test_dir) / "editorial_429.srt"
        with patch("src.translator.get_gemini_client", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
            ok2 = generate_editorial_commentary_srt(
                video_path=dummy_video,
                output_srt=out_srt2,
                original_title="GTA 6 Physics Water Details",
                creator_name="Rockstar",
                duration_sec=22.0,
            )
        self.assertTrue(ok2)
        self.assertIn("físicas", out_srt2.read_text(encoding="utf-8").lower())

    def test_resolve_recommended_mode_promotes_english_subs_to_dub(self):
        self.assertEqual(_resolve_recommended_mode("subs", {"lang": "en", "title": "GTA 6 Secrets"}), "dub")
        self.assertEqual(_resolve_recommended_mode("subs", {"lang": "es", "title": "Willyrex GTA 6"}), "subs")
        self.assertEqual(_resolve_recommended_mode("gameplay", {"lang": "en", "title": "GTA 6 Free Roam"}), "gameplay")

    def test_check_daily_limit_does_not_count_skipped_platform(self):
        today_iso = datetime.now().isoformat()
        records = [
            {
                "id": "vid1",
                "title": "GTA 6 Video 1",
                "status": "completed",
                "date": today_iso,
                "youtube_title": "GTA 6 Video 1",
                "youtube_url": "https://youtube.com/watch?v=source1",
                "multiplatform": {
                    "youtube": None,
                    "tiktok": "https://tiktok.com/@gtavihubextra/1",
                    "instagram": "Bloqueado por Compliance Shield"
                }
            },
            {
                "id": "vid2",
                "title": "GTA 6 Video 2",
                "status": "completed",
                "date": today_iso,
                "youtube_title": "GTA 6 Video 2",
                "youtube_url": "https://youtube.com/watch?v=source2",
                "multiplatform": {
                    "youtube": "https://youtu.be/real_yt",
                    "tiktok": "https://tiktok.com/@gtavihubextra/2",
                    "instagram": "https://instagram.com/reel/1"
                }
            }
        ]
        proc_file = Path(self.test_dir) / "processed.json"
        proc_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.social_publisher.PROCESSED_FILE", proc_file), \
             patch("src.channels.PROCESSED_FILE", proc_file), \
             patch.object(AntiBanValidator, "get_daily_limit", return_value=2):
            # YouTube only has 1 actual upload, so with limit=2 it should be OK (True)
            self.assertTrue(AntiBanValidator.check_daily_limit("youtube"))
            # TikTok has 2 uploads, so with limit=2 it should hit limit (False)
            self.assertFalse(AntiBanValidator.check_daily_limit("tiktok"))
            # get_daily_published_count only counts videos with at least 1 published URL
            self.assertEqual(get_daily_published_count(), 2)
            self.assertEqual(get_daily_published_count("youtube"), 1)
            self.assertEqual(get_daily_published_count("tiktok"), 2)


if __name__ == "__main__":
    unittest.main()
