import unittest
from datetime import datetime, timezone, timedelta
from src.deal_scanner import (
    load_deals_state,
    save_deals_state,
    should_update_deals,
    get_days_until_next_update,
    scan_and_update_deals,
    format_deals_report,
    CURATED_DEALS_CATALOG
)

class TestDealScanner(unittest.TestCase):
    def test_catalog_structure(self):
        self.assertGreater(len(CURATED_DEALS_CATALOG), 0)
        keys = [item["key"] for item in CURATED_DEALS_CATALOG]
        self.assertIn("volante_logitech_g29", keys)
        self.assertIn("monitor_gaming_4k", keys)
        self.assertIn("ssd_ps5_2tb", keys)

    def test_should_update_when_empty(self):
        # Con estado reseteado o fecha antigua debe retornar True
        now_past = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        save_deals_state({"last_updated": now_past, "interval_days": 3, "active_deals": []})
        self.assertTrue(should_update_deals(interval_days=3))

    def test_should_not_update_when_recent(self):
        # Con actualización hace 1 hora no debe actualizar
        now_recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        save_deals_state({"last_updated": now_recent, "interval_days": 3, "active_deals": []})
        self.assertFalse(should_update_deals(interval_days=3))
        self.assertGreater(get_days_until_next_update(interval_days=3), 2.0)

    def test_scan_and_update_deals_force(self):
        res = scan_and_update_deals(force=True, notify_telegram=False)
        self.assertEqual(res["status"], "updated")
        self.assertGreater(res["total_deals"], 0)
        self.assertIn("RADAR DE OFERTAS AMAZON", res["report"])

    def test_format_deals_report(self):
        sample_state = {
            "tag": "gtavihub-21",
            "updates_count": 5,
            "active_deals": [
                {
                    "title": "Logitech G29",
                    "badge": "🏎️ VOLANTE",
                    "url": "https://amazon.es/test",
                    "note": "Rebaja 30%"
                }
            ]
        }
        report = format_deals_report(sample_state)
        self.assertIn("gtavihub-21", report)
        self.assertIn("Logitech G29", report)
