import unittest
from src.affiliates import (
    build_amazon_url,
    get_amazon_tag,
    get_hub_linktree,
    get_all_affiliate_products,
    format_description_affiliate_block,
    format_pinned_comment_affiliates,
    get_channel_branding_kit
)

class TestAffiliates(unittest.TestCase):
    def test_build_amazon_url(self):
        url = build_amazon_url("https://www.amazon.es/dp/B0CL5J6T9N", tag="testtag-21")
        self.assertIn("tag=testtag-21", url)
        self.assertTrue(url.startswith("https://www.amazon.es/dp/B0CL5J6T9N"))

    def test_build_amazon_url_search_query(self):
        url = build_amazon_url("gta 6 ps5", tag="testtag-21")
        self.assertIn("tag=testtag-21", url)
        self.assertIn("amazon.es/s?k=", url)

    def test_get_all_affiliate_products(self):
        prods = get_all_affiliate_products()
        self.assertGreaterEqual(len(prods), 5)
        for p in prods:
            self.assertIn("title", p)
            self.assertIn("url", p)
            self.assertIn("badge", p)
            self.assertIn("amazon.es", p["url"])

    def test_format_description_affiliate_block(self):
        block = format_description_affiliate_block()
        self.assertIn("Reserva GTA 6", block)
        self.assertIn("PS5 Pro", block)
        self.assertIn("SSD M.2", block)
        self.assertIn("En calidad de Afiliado de Amazon", block)

    def test_format_pinned_comment_affiliates(self):
        comment = format_pinned_comment_affiliates("¿Qué personaje prefieres?")
        self.assertIn("¿Qué personaje prefieres?", comment)
        self.assertIn("Amazon", comment)
        self.assertIn("linktr.ee", comment)

    def test_channel_branding_kit(self):
        kit = get_channel_branding_kit()
        self.assertIn("youtube", kit)
        self.assertIn("tiktok", kit)
        self.assertIn("instagram", kit)
        self.assertIn("linktree_buttons", kit)
        self.assertGreaterEqual(len(kit["linktree_buttons"]), 5)

if __name__ == "__main__":
    unittest.main()
