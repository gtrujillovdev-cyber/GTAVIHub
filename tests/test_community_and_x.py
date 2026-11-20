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
        self.assertIn("🎮 Físicas del agua en GTA 6 con RAGE 9", caption)
        self.assertIn("💬 ¿Crees que correrá a 60 FPS en consola? 👇", caption)
        self.assertIn("RAGE 9 alcanzan un nivel brutal", caption)
        self.assertIn("📌 Crédito: @RockstarIntel", caption)
        self.assertNotIn("https://", caption)
        self.assertNotIn("Art. 107", caption)
        self.assertEqual(caption.count("#"), 5)


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


if __name__ == "__main__":
    unittest.main()
