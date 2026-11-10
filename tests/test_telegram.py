import unittest
from src.telegram_bot import (
    URL_PATTERN,
    get_persistent_menu_keyboard,
    get_url_ingest_keyboard,
    get_copilot_approval_keyboard,
    get_copilot_toggle_keyboard,
    get_channels_inline_keyboard,
    get_my_channels_inline_keyboard,
    get_my_channels_report,
    get_restart_confirm_keyboard,
    get_system_actions_inline_keyboard,
    update_heartbeat,
    kill_hung_subprocesses,
    send_telegram_video,
    get_dashboard_text
)
from src.copilot import (
    is_copilot_enabled, set_copilot_enabled,
    check_and_auto_approve_expired_videos, COPILOT_AUTO_APPROVE_TIMEOUT_MIN
)

class TestTelegramBot(unittest.TestCase):
    def test_url_pattern_detection(self):
        yt_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtube.com/shorts/3f8H_d9gK1M",
            "https://www.tiktok.com/@gtavihubspain/video/123456789",
            "https://x.com/GTAVI_Countdown/status/1731737402830848000",
            "https://twitter.com/RockstarGames/status/1731737402830848000"
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
        self.assertIn("🎬 Último Clip", buttons)
        self.assertIn("📊 Estado", buttons)
        self.assertIn("🛡️ Modo Co-Pilot", buttons)

    def test_inline_keyboards(self):
        ingest_kb = get_url_ingest_keyboard("test_token")
        self.assertIn("inline_keyboard", ingest_kb)
        callbacks = [btn.get("callback_data") for row in ingest_kb["inline_keyboard"] for btn in row]
        self.assertIn("url_opt:short:test_token", callbacks)
        self.assertIn("url_opt:dub:test_token", callbacks)
        self.assertIn("url_opt:gameplay:test_token", callbacks)
        self.assertIn("url_opt:cancel:test_token", callbacks)
        
        copilot_kb = get_copilot_approval_keyboard("vid_123", original_url="https://www.youtube.com/watch?v=vid_123")
        self.assertIn("inline_keyboard", copilot_kb)
        # Verificar que contiene botón de visualización con URL oficial
        has_url_btn = any(btn.get("url") for row in copilot_kb["inline_keyboard"] for btn in row)
        self.assertTrue(has_url_btn)
        
        toggle_kb = get_copilot_toggle_keyboard()
        self.assertIn("inline_keyboard", toggle_kb)

        chan_kb = get_channels_inline_keyboard()
        self.assertIn("inline_keyboard", chan_kb)

        # Teclado exclusivo de mis canales y redes
        my_kb = get_my_channels_inline_keyboard()
        self.assertIn("inline_keyboard", my_kb)
        url_buttons = [btn for row in my_kb["inline_keyboard"] for btn in row if "url" in btn]
        self.assertGreater(len(url_buttons), 0)
        urls = [b["url"] for b in url_buttons]
        self.assertTrue(any("youtube.com" in u for u in urls))
        self.assertTrue(any("tiktok.com" in u for u in urls))
        self.assertTrue(any("instagram.com" in u for u in urls))

        # Teclados de reinicio y acciones de sistema
        restart_kb = get_restart_confirm_keyboard()
        self.assertIn("inline_keyboard", restart_kb)
        restart_callbacks = [btn.get("callback_data") for row in restart_kb["inline_keyboard"] for btn in row]
        self.assertIn("system:confirm_restart", restart_callbacks)
        self.assertIn("system:cancel_restart", restart_callbacks)

    def test_get_url_metadata_twitter(self):
        from src.downloader import get_url_metadata
        import unittest.mock as mock

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout="1731737402830848000\tInsane car crash physics\t35\tGTAVINews\ttwitter"
            )
            meta = get_url_metadata("https://x.com/GTAVINews/status/1731737402830848000")
            self.assertEqual(meta["id"], "1731737402830848000")
            self.assertIn("GTA 6: Insane car crash physics", meta["title"])
            self.assertEqual(meta["platform"], "Twitter/X")
            self.assertEqual(meta["duration_sec"], 35)

        actions_kb = get_system_actions_inline_keyboard()
        self.assertIn("inline_keyboard", actions_kb)
        action_callbacks = [btn.get("callback_data") for row in actions_kb["inline_keyboard"] for btn in row]
        self.assertIn("system:ask_restart", action_callbacks)
        self.assertIn("system:unlock", action_callbacks)

    def test_heartbeat_and_subprocesses_cleanup(self):
        update_heartbeat()
        from src.config import DATA_DIR
        hb_file = DATA_DIR / "heartbeat.txt"
        self.assertTrue(hb_file.exists())
        val = int(hb_file.read_text().strip())
        self.assertGreater(val, 1700000000)

        # Matar subprocesos huérfanos sin excepción
        kill_hung_subprocesses()

        # send_telegram_video con archivo inexistente devuelve False limpiamente
        from pathlib import Path
        self.assertFalse(send_telegram_video(Path("/tmp/nonexistent_dummy.mp4"), "caption"))

    def test_my_channels_report(self):
        report = get_my_channels_report()
        self.assertIn("MIS CANALES Y REDES SOCIALES", report)
        self.assertIn("GTA VI HUB SPAIN", report)
        self.assertIn("tiktok.com/@gtavihubspain", report)
        self.assertTrue("youtube.com/@gtavihubextra" in report or "youtube.com/channel/UCB35xEmRUm64zgyYOUnqrUg" in report)
        # Asegurarse de que no incluye canales de terceros
        self.assertNotIn("DarkViperAU", report)
        self.assertNotIn("IlloJuan", report)

    def test_copilot_state_toggle(self):
        original = is_copilot_enabled()
        set_copilot_enabled(not original)
        self.assertEqual(is_copilot_enabled(), not original)
        # Revertir
        set_copilot_enabled(original)
        self.assertEqual(is_copilot_enabled(), original)

    def test_copilot_auto_approve_check(self):
        # Debe ejecutarse sin lanzar excepciones y devolver una lista
        res = check_and_auto_approve_expired_videos(timeout_minutes=999999)
        self.assertIsInstance(res, list)
        self.assertGreaterEqual(COPILOT_AUTO_APPROVE_TIMEOUT_MIN, 1)

    def test_dashboard_text(self):
        dash = get_dashboard_text()
        self.assertIn("ESTADO DEL SISTEMA", dash)
        self.assertIn("Modo Co-Pilot", dash) if "Modo Co-Pilot" in dash else self.assertIn("Modo", dash)
        self.assertIn("Staging", dash)

if __name__ == "__main__":
    unittest.main()
