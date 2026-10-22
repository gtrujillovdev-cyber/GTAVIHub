import unittest

class TestSanity(unittest.TestCase):
    def test_imports(self):
        import src.channels
        import src.cleaner
        import src.config
        import src.downloader
        import src.dubber
        import src.monitor
        import src.pipeline
        import src.social_publisher
        import src.telegram_bot
        import src.telemetry
        import src.youtube_analytics
        import src.copilot
        import src.thumbnail_generator
        import src.translator
        import src.uploader
        import src.video_editor

if __name__ == "__main__":
    unittest.main()
