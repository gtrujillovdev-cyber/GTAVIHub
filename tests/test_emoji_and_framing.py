import unittest
from pathlib import Path
from PIL import Image, ImageDraw

from src.emoji_renderer import (
    split_text_and_emojis,
    clean_text_preserve_emojis,
    get_best_emoji_font,
    render_emoji_image,
    measure_composite_line,
    draw_composite_line
)
from src.thumbnail_generator import get_best_font, _draw_hook_text
from src.video_editor import (
    render_top_hook_headline,
    render_retention_hook,
    render_karaoke_subtitle_state,
    get_emoji_font
)


class TestEmojiAndFraming(unittest.TestCase):

    def test_split_text_and_emojis(self):
        text = "¡BOMBAZO GTA 6! 🔥🌴"
        tokens = split_text_and_emojis(text)
        self.assertEqual(tokens, [("text", "¡BOMBAZO GTA 6! "), ("emoji", "🔥"), ("emoji", "🌴")])

        # Caso texto puro sin emojis
        self.assertEqual(split_text_and_emojis("TEXTO PLANO"), [("text", "TEXTO PLANO")])

        # Caso solo emojis
        self.assertEqual(split_text_and_emojis("🚨🤯"), [("emoji", "🚨"), ("emoji", "🤯")])

        # Caso vacío
        self.assertEqual(split_text_and_emojis(""), [])

    def test_clean_text_preserve_emojis(self):
        raw = "   <c>¡FILTRACIÓN</c>&nbsp;NUEVA! 🌴🔥  "
        cleaned = clean_text_preserve_emojis(raw)
        self.assertEqual(cleaned, "¡FILTRACIÓN NUEVA! 🌴🔥")

    def test_get_best_emoji_font_no_crash(self):
        # Verificar que varios tamaños no provoquen "OSError: invalid pixel size"
        for size in [20, 36, 40, 44, 46, 58, 64, 80]:
            font, base_size = get_best_emoji_font(size)
            if font is not None:
                self.assertIn(base_size, [20, 26, 32, 40, 48, 52, 64, 96])

    def test_render_emoji_image(self):
        font, _ = get_best_emoji_font(44)
        if font is not None:
            # Si hay soporte nativo de emojis en el sistema
            img = render_emoji_image("🔥", target_size=44)
            self.assertIsNotNone(img)
            self.assertEqual(img.mode, "RGBA")
            self.assertLessEqual(img.height, 44)
            self.assertGreater(img.width, 10)

    def test_composite_line_drawing(self):
        canvas = Image.new("RGBA", (500, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        font = get_best_font(40)
        tokens = split_text_and_emojis("GTA 6 🔥")

        w, h = measure_composite_line(tokens, font, emoji_size=40)
        self.assertGreater(w, 50)
        self.assertGreater(h, 20)

        end_x = draw_composite_line(canvas, draw, tokens, 10, 10, font, fill_color=(255, 230, 0, 255), emoji_size=40)
        self.assertGreater(end_x, 10)
        bbox = canvas.getbbox()
        self.assertIsNotNone(bbox)

    def test_thumbnail_draw_hook_with_emojis(self):
        thumb = Image.new("RGBA", (1280, 720), (20, 20, 25, 255))
        style = {
            "font_size_ratio": 0.07,
            "text_stroke_width": 6,
            "text_stroke": [0, 0, 0],
            "text_color": [255, 230, 0]
        }
        # Debe ejecutarse sin lanzar excepciones ni dibujar cajas de error
        _draw_hook_text(thumb, "¡ANUNCIO OFICIAL! 🔥🌴", 1280, 720, style, target_img=thumb)
        self.assertIsNotNone(thumb.getbbox())

    def test_render_top_hook_headline(self):
        out_path = Path("temp/test_hook_headline.png")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            success = render_top_hook_headline("¡BOMBAZO GTA 6! 🔥", out_path)
            self.assertTrue(success)
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 100)
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_render_retention_hook(self):
        out_path = Path("temp/test_retention.png")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            success = render_retention_hook(out_path, text="¡OJO A ESTO! 👀")
            self.assertTrue(success)
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 100)
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_render_karaoke_subtitle_state(self):
        out_path = Path("temp/test_karaoke.png")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # "caiman" dispara active_emoji = 🐊
            success = render_karaoke_subtitle_state(["MIRA", "EL", "CAIMAN"], 2, True, out_path)
            self.assertTrue(success)
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 100)
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_get_emoji_font_backwards_compatibility(self):
        f = get_emoji_font(44)
        # No debe lanzar excepción OSError
        if f is not None:
            self.assertTrue(hasattr(f, "getbbox"))

    def test_is_color_emoji_supported(self):
        from src.emoji_renderer import is_color_emoji_supported
        res = is_color_emoji_supported()
        self.assertIsInstance(res, bool)

    def test_shorts_clean_description_anti_spam(self):
        from src.translator import generate_video_metadata
        meta_short = generate_video_metadata(
            original_title="Lucia y Jason Gameplay Filtrado de GTA 6",
            original_url="https://youtube.com/watch?v=abc123xyz",
            is_short=True,
            creator_name="Rockstar Games"
        )
        desc = meta_short.get("description", "")
        # En Shorts NO debe haber bloques gigantes de afiliados con tag=gtavihub-21
        self.assertNotIn("tag=gtavihub-21", desc)
        # La descripción debe ser compacta (< 1000 caracteres)
        self.assertLess(len(desc), 1000)
        # Pero el COMENTARIO FIJADO sí debe contener el enlace de monetización
        self.assertIn("pinned_comment", meta_short)
        self.assertIn("linktr.ee", meta_short["pinned_comment"].lower())

    def test_should_toggle_engagement_boost(self):
        from src.uploader import should_toggle_engagement_boost, BOOST_STATE_FILE
        if BOOST_STATE_FILE.exists():
            BOOST_STATE_FILE.unlink()
        try:
            r1 = should_toggle_engagement_boost()
            r2 = should_toggle_engagement_boost()
            r3 = should_toggle_engagement_boost()
            r4 = should_toggle_engagement_boost()
            self.assertEqual([r1, r2, r3, r4], [True, False, True, False])
        finally:
            if BOOST_STATE_FILE.exists():
                BOOST_STATE_FILE.unlink()


if __name__ == "__main__":
    unittest.main()
