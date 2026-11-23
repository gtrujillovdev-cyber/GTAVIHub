import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.community_manager import generate_community_reply, is_safe_follower_comment
from src.social_publisher import SocialPublisher
from src import x_scout


class TestTikTokCaptionAesthetics(unittest.TestCase):
    def test_build_tiktok_caption_rich_and_clean(self):
        desc = (
            "POR: @RockstarIntel\n"
            "https://youtu.be/abc123\n"
            "Las físicas del agua en Vice City con RAGE 9 alcanzan un nivel brutal en PS5 Pro.\n"
            "Fair Use Art. 107 Copyright Act"
        )
        caption = SocialPublisher._build_tiktok_caption(
            title="Físicas del agua en GTA 6 con RAGE 9",
            tags=["GTA6", "RAGE9", "ViceCity", "PS5Pro", "Gaming", "ExtraTag"],
            debate_question="¿Crees que correrá a 60 FPS en consola?",
            description=desc,
            creator_name="RockstarIntel",
        )
        self.assertIn("Físicas del agua en GTA 6 con RAGE 9", caption)
        self.assertNotIn("🎮", caption.splitlines()[0])
        self.assertIn("💬 ¿Crees que correrá a 60 FPS en consola?", caption)
        self.assertIn("RAGE 9 alcanzan un nivel brutal", caption)
        self.assertIn("📌 Crédito: @RockstarIntel", caption)
        self.assertNotIn("https://", caption)
        self.assertNotIn("Art. 107", caption)
        self.assertEqual(caption.count("#"), 4)


class TestCommunityManager(unittest.TestCase):
    def test_spam_filter(self):
        self.assertFalse(is_safe_follower_comment("ok"))
        self.assertFalse(is_safe_follower_comment("Check my profile https://spam.com"))
        self.assertFalse(is_safe_follower_comment("Gana dinero con crypto telegram"))
        self.assertTrue(is_safe_follower_comment("Brutal el detalle de las olas en Vice City!"))

    def test_fallback_reply_without_api_key(self):
        with patch("src.community_manager.GEMINI_API_KEY", ""), patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            reply = generate_community_reply("Qué locura de gráficos", video_title="GTA 6 PS5 Pro")
            self.assertTrue(len(reply) > 10)
            self.assertNotIn("http", reply.lower())


class TestXTasteProfile(unittest.TestCase):
    def test_taste_profile_and_boost(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof_path = Path(tmp) / "x_taste_profile.json"
            with patch.object(x_scout, "X_TASTE_PROFILE_FILE", prof_path):
                liked = [
                    {"title": "GTA 6 RAGE 9 water physics comparison on PS5 Pro", "uploader": "@GTA6Intel"},
                    {"title": "GTA 6 physics and destruction vs GTA 5", "uploader": "@GTA6Intel"},
                ]
                prof = x_scout.update_x_taste_profile(liked)
                self.assertIn("fisicas", prof["preferred_topics"])
                self.assertIn("@GTA6Intel", prof["preferred_creators"])
                boost = x_scout.get_x_taste_boost("GTA 6 water physics breakdown", "@GTA6Intel")
                self.assertGreaterEqual(boost, 10)

    def test_ingest_x_likes_as_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "curated_queue.json"
            with patch("src.channels.CURATED_QUEUE_FILE", queue_path), \
                 patch("src.channels.get_processed_ids", return_value=set()), \
                 patch("src.channels.auto_register_source_from_metadata", return_value={"success": True}) as mock_reg:
                liked_cands = [
                    {
                        "id": "x_999111222",
                        "url": "https://x.com/RockstarIntel/status/999111222",
                        "title": "GTA 6 Vice City night rain physics",
                        "uploader": "RockstarIntel",
                        "platform": "x",
                        "score": 88,
                        "is_liked": True,
                    }
                ]
                stats = x_scout.ingest_x_likes_as_sources(liked_cands)
                self.assertEqual(stats["queued_clips"], 1)
                self.assertEqual(stats["registered_sources"], 1)
                self.assertTrue(queue_path.exists())
                mock_reg.assert_called_once()

    def test_tiktok_official_api_upload(self):
        import json as _json
        import time as _time
        from unittest.mock import MagicMock
        from src.social_publisher import SocialPublisher

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            vid = tmp_p / "clip.mp4"
            vid.write_bytes(b"0" * 1024)
            tok = tmp_p / "tiktok_token.json"
            tok.write_text(_json.dumps({"access_token": "tok_123", "obtained_at": int(_time.time()), "expires_in": 86400}))

            init_resp = MagicMock()
            init_resp.json.return_value = {"error": {"code": "ok"}, "data": {"upload_url": "https://open.tiktokapis.com/upload/abc", "publish_id": "pub_99"}}
            put_resp = MagicMock()
            put_resp.status_code = 201

            pub = SocialPublisher(dry_run=False)
            with patch("requests.post", return_value=init_resp) as m_post, \
                 patch("requests.put", return_value=put_resp) as m_put, \
                 patch("src.social_publisher._record_tiktok_upload") as m_rec:
                url = pub._publish_to_tiktok_official_api(vid, "Armas secretas GTA 6 #GTA6", tok)

            self.assertEqual(url, "https://www.tiktok.com/@gtavihubextra")
            m_post.assert_called_once()
            m_put.assert_called_once()
            m_rec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
