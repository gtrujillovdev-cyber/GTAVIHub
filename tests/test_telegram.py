import unittest
from src.telegram_bot import (
    URL_PATTERN,
    get_persistent_menu_keyboard,
    get_url_ingest_keyboard,
    get_copilot_approval_keyboard,
    get_copilot_toggle_keyboard,
    get_channels_inline_keyboard,
    get_channel_links_inline_keyboard,
    get_channels_profiles_report,
    get_dashboard_text
)
from src.copilot import is_copilot_enabled, set_copilot_enabled

class TestTelegramBot(unittest.TestCase):
    def test_url_pattern_detection(self):
        yt_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtube.com/shorts/3f8H_d9gK1M",
            "https://www.tiktok.com/@gtavihubspain/video/123456789"
        ]
        for url in yt_urls:
            m = URL_PATTERN.search(url)
            self.assertIsNotNone(m, f"Debe detectar la URL: {url}")
            self.assertEqual(m.group(0), url)

        # URLs no compatibles o texto simple
        non_urls = [
            "hola que tal",
            "/run",
            "https://github.com/foo/bar"
        ]
        for text in non_urls:
            m = URL_PATTERN.search(text)
            self.assertIsNone(m, f"No debe detectar: {text}")

    def test_persistent_keyboard_structure(self):
        kb = get_persistent_menu_keyboard()
        self.assertIn("keyboard", kb)
        self.assertTrue(kb.get("persistent"))
        self.assertTrue(kb.get("resize_keyboard"))
        buttons = [btn["text"] for row in kb["keyboard"] for btn in row]
        self.assertIn("🚀 Forzar Escaneo", buttons)
        self.assertIn("📊 Dashboard", buttons)
        self.assertIn("🖥️ Estado Host / GaTDSEQ", buttons)
        self.assertIn("📈 Métricas YouTube", buttons)
        self.assertIn("⚙️ Canales", buttons)
        self.assertIn("🔥 Radar Viral", buttons)
        self.assertIn("🛡️ Modo Co-Pilot", buttons)
        self.assertIn("🌐 Perfiles Oficiales", buttons)

    def test_inline_keyboards(self):
        ingest_kb = get_url_ingest_keyboard("test_token")
        self.assertIn("inline_keyboard", ingest_kb)
        
        copilot_kb = get_copilot_approval_keyboard("vid_123", original_url="https://www.youtube.com/watch?v=vid_123")
        self.assertIn("inline_keyboard", copilot_kb)
        # Verificar que contiene botón de visualización con URL oficial
        has_url_btn = any(btn.get("url") for row in copilot_kb["inline_keyboard"] for btn in row)
        self.assertTrue(has_url_btn)
        
        toggle_kb = get_copilot_toggle_keyboard()
        self.assertIn("inline_keyboard", toggle_kb)

        chan_kb = get_channels_inline_keyboard()
        self.assertIn("inline_keyboard", chan_kb)

        # Teclado de enlaces web a canales y perfiles oficiales
        links_kb = get_channel_links_inline_keyboard(page=0)
        self.assertIn("inline_keyboard", links_kb)
        url_buttons = [btn for row in links_kb["inline_keyboard"] for btn in row if "url" in btn]
        self.assertGreater(len(url_buttons), 0)
        # Verificar que contiene enlaces a redes oficiales
        urls = [b["url"] for b in url_buttons]
        self.assertTrue(any("youtube.com" in u for u in urls))
        self.assertTrue(any("tiktok.com" in u for u in urls))

    def test_channels_profiles_report(self):
        report = get_channels_profiles_report()
        self.assertIn("PERFILES Y CANALES OFICIALES", report)
        self.assertIn("GTA VI HUB SPAIN", report)
        self.assertIn("Rockstar Games", report)
        self.assertIn("https://www.youtube.com/@RockstarGames", report)
        self.assertIn("tiktok.com/@gtavihubspain", report)

    def test_copilot_state_toggle(self):
        original = is_copilot_enabled()
        set_copilot_enabled(not original)
        self.assertEqual(is_copilot_enabled(), not original)
        # Revertir
        set_copilot_enabled(original)
        self.assertEqual(is_copilot_enabled(), original)

    def test_dashboard_text(self):
        dash = get_dashboard_text()
        self.assertIn("ESTADO DEL PIPELINE", dash)
        self.assertIn("Almacenamiento", dash)
        self.assertIn("Modo Co-Pilot", dash)

if __name__ == "__main__":
    unittest.main()
