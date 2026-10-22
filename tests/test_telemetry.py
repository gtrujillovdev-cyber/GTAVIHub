import unittest
from src.telemetry import (
    get_ram_info,
    get_battery_info,
    get_uptime_info,
    get_disk_info,
    get_gatdseq_status,
    get_host_telemetry_report
)

class TestTelemetry(unittest.TestCase):
    def test_ram_info_format(self):
        ram = get_ram_info()
        self.assertIsInstance(ram, str)
        self.assertTrue("GB" in ram)

    def test_battery_info(self):
        batt = get_battery_info()
        self.assertIsInstance(batt, str)
        self.assertTrue(len(batt) > 0)

    def test_uptime_info(self):
        uptime = get_uptime_info()
        self.assertIsInstance(uptime, str)
        self.assertTrue(len(uptime) > 0)

    def test_disk_info(self):
        disk = get_disk_info()
        self.assertIn("total_gb", disk)
        self.assertIn("used_gb", disk)
        self.assertIn("free_gb", disk)
        self.assertGreater(disk["total_gb"], 0)

    def test_gatdseq_status(self):
        status = get_gatdseq_status()
        self.assertIn("busy", status)
        self.assertIn("policy", status)
        self.assertIsInstance(status["busy"], bool)

    def test_host_telemetry_report(self):
        report = get_host_telemetry_report()
        self.assertIn("TELEMETRÍA DEL HOST", report)
        self.assertIn("GaTDSEQ", report)
        self.assertIn("CPU Load", report)
        self.assertIn("Memoria RAM", report)

if __name__ == "__main__":
    unittest.main()
