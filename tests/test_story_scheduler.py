import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from src.story_scheduler import (
    load_stories_state,
    save_stories_state,
    can_publish_story,
    get_next_story_type,
    build_next_rotating_deal_story,
    build_content_teaser_story,
    MAX_STORIES_PER_DAY,
    ROTATING_PRODUCTS
)

class TestStoryScheduler(unittest.TestCase):
    def test_rotating_products_list(self):
        self.assertGreaterEqual(len(ROTATING_PRODUCTS), 3)
        self.assertIn("volante_logitech_g29", ROTATING_PRODUCTS)
        self.assertIn("ps5_pro", ROTATING_PRODUCTS)

    def test_daily_limit_blocking(self):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        save_stories_state({
            "today_date": today_str,
            "today_count": MAX_STORIES_PER_DAY,
            "last_published": datetime.now(timezone.utc).isoformat()
        })
        allowed, reason = can_publish_story(force=False)
        self.assertFalse(allowed)
        self.assertIn("Límite diario alcanzado", reason)

    def test_interval_blocking(self):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        save_stories_state({
            "today_date": today_str,
            "today_count": 1,
            "last_published": recent
        })
        allowed, reason = can_publish_story(force=False)
        self.assertFalse(allowed)
        self.assertIn("Descanso entre historias", reason)

    def test_build_next_rotating_deal_story(self):
        img, url, cap, key = build_next_rotating_deal_story()
        self.assertTrue(img.exists())
        self.assertIn(key, ROTATING_PRODUCTS)
        self.assertIn("gtavihub-21", url)
        img.unlink(missing_ok=True)

    def test_build_content_teaser_story(self):
        img, url, cap = build_content_teaser_story(video_title="TEST GTA 6 CLIP")
        self.assertTrue(img.exists())
        self.assertIn("linktr.ee", url)
        img.unlink(missing_ok=True)
