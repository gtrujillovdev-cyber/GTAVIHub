import unittest
from src.compliance_auditor import ComplianceAuditor, PLATFORM_POLICIES
from src.channels import is_strictly_gta

class TestCompliance(unittest.TestCase):
    def test_platform_policies_integrity(self):
        self.assertIn("youtube", PLATFORM_POLICIES)
        self.assertIn("tiktok", PLATFORM_POLICIES)
        self.assertIn("instagram", PLATFORM_POLICIES)

    def test_auditor_metadata_validation(self):
        metadata = {
            "title": "GTA 6 Nueva Filtración de Vice City",
            "description": "Análisis del nuevo mapa. Creador: DaniRep. Fuente: https://youtube.com/watch?v=123. FAIR USE y Uso Legítimo."
        }
        is_safe, issues = ComplianceAuditor.audit_clip_metadata(
            metadata=metadata,
            creator_name="DaniRep",
            original_url="https://youtube.com/watch?v=123"
        )
        self.assertTrue(is_safe)
        self.assertEqual(len(issues), 0)

    def test_auditor_rejects_missing_attribution(self):
        metadata = {
            "title": "Vídeo sin créditos",
            "description": "Sin enlace ni autor."
        }
        is_safe, issues = ComplianceAuditor.audit_clip_metadata(
            metadata=metadata,
            creator_name="",
            original_url=""
        )
        self.assertFalse(is_safe)
        self.assertGreater(len(issues), 0)

    def test_gta6_exclusive_content_filter(self):
        # Vídeos legítimos EXCLUSIVOS de GTA 6 / GTA VI
        self.assertTrue(is_strictly_gta("GTA 6: Inside the Development of Vice City"))
        self.assertTrue(is_strictly_gta("Detalles ocultos de Lucía y Jason en el trailer"))
        self.assertTrue(is_strictly_gta("Esto es GTA VI (GAMEPLAY + EXCLUSIVA)"))
        self.assertTrue(is_strictly_gta("Grand Theft Auto VI - Nuevos Detalles Filtrados de Leonida"))
        self.assertTrue(is_strictly_gta("Mors Mutual: GTA 6 is unplayable..."))

        # Vídeos de GTA 5, GTA Online, GTA 4 u otras entregas (DEBEN SER RECHAZADOS)
        self.assertFalse(is_strictly_gta("CORRE O TE ATROPELLO ESPECIAL GTA 6 - GTA 5 ONLINE"))
        self.assertFalse(is_strictly_gta("GTA Online Wants Me to Grind FOREVER - 100% Career Progress #48"))
        self.assertFalse(is_strictly_gta("TRIPLE MONEY & DISCOUNTS | GTA Online Weekly Update"))
        self.assertFalse(is_strictly_gta("MI ÚLTIMO CARA A CARA EN GTA 5 ONLINE"))
        self.assertFalse(is_strictly_gta("GTA IV Enhanced Is Better Than I Expected - Final"))
        self.assertFalse(is_strictly_gta("GTA San Andreas Definitive Edition Gameplay"))
        self.assertFalse(is_strictly_gta("GTA Vice City The definitive edition Easter egg #shorts"))
        self.assertFalse(is_strictly_gta("GTA Vice City Definitive Edition Remaster"))
        self.assertFalse(is_strictly_gta("Vice City Stories Gameplay Walkthrough"))

        # Vídeos no relacionados con videojuegos / ajenos
        self.assertFalse(is_strictly_gta("Senior Offering, May 3, 2007"))
        self.assertFalse(is_strictly_gta("Jazz Combo, April 29, 2007"))
        self.assertFalse(is_strictly_gta("Banda tocando música en directo"))
        self.assertFalse(is_strictly_gta("Receta de cocina con Gordon Ramsay"))
        self.assertFalse(is_strictly_gta("Concierto de coro escolar"))

        # OTROS VIDEOJUEGOS O NOTICIAS AJENAS (DEBEN SER ESTRICTAMENTE DESCARTADOS)
        self.assertFalse(is_strictly_gta("Red Dead Redemption 2 Secret Easter Egg in 2026"))
        self.assertFalse(is_strictly_gta("Circoloco Records Presents Anyma"))
        self.assertFalse(is_strictly_gta("Fortnite Chapter 5 Season 2 Battle Pass"))
        self.assertFalse(is_strictly_gta("Call of Duty Warzone Season 2 Patch Notes"))
        self.assertFalse(is_strictly_gta("Elden Ring Shadow of the Erdtree Gameplay"))
        self.assertFalse(is_strictly_gta("Cyberpunk 2077 Phantom Liberty Ending"))
        self.assertFalse(is_strictly_gta("Jason Schreier talks about PS6 launch window"))
        self.assertFalse(is_strictly_gta("Lucia de la Puerta reacciona a su nuevo video"))
        self.assertFalse(is_strictly_gta("Bully 2 cancellation story explained"))
        self.assertFalse(is_strictly_gta("Max Payne 1 and 2 Remake update"))

        # Casos válidos de GTA 6 con crossovers y comparativas técnicas
        self.assertTrue(is_strictly_gta("South Park GTA 6 Parody Scene"))
        self.assertTrue(is_strictly_gta("GTA 5 vs GTA 6 Water Physics Comparison"))
        self.assertTrue(is_strictly_gta("Lucia and Jason criminal duo explained in GTA 6"))
        self.assertTrue(is_strictly_gta("Jason Schreier reveals GTA 6 internal release date"))

    def test_to_unicode_bold(self):
        from src.translator import to_unicode_bold
        self.assertEqual(to_unicode_bold("GTA 6"), "𝗚𝗧𝗔 𝟲")
        self.assertEqual(to_unicode_bold("DEBATE"), "𝗗𝗘𝗕𝗔𝗧𝗘")
        self.assertEqual(to_unicode_bold("Test 123"), "𝗧𝗲𝘀𝘁 𝟭𝟮𝟯")

    def test_channel_catalog_integrity(self):
        from src.config import CHANNELS_FILE
        import json
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        channels = data.get("channels", [])
        # Catálogo optimizado de fuentes verificadas (sin podcasts de relleno ni duplicados)
        self.assertGreaterEqual(len(channels), 40)
        names = [c["name"] for c in channels]
        self.assertTrue(any("GTA VI O'Clock" in n for n in names))
        self.assertTrue(any("ElAnalistaDeBits" in n for n in names))
        self.assertTrue(any("Ray Snakeyes" in n for n in names))
        self.assertTrue(any("Strange Man" in n for n in names))
        self.assertTrue(any("Gameranx" in n for n in names))
        self.assertTrue(any("Sonny Evans" in n for n in names))
        self.assertTrue(any("Hobby Consolas" in n for n in names))
        self.assertTrue(any("CaptainEggcellent" in n for n in names))

if __name__ == "__main__":
    unittest.main()
