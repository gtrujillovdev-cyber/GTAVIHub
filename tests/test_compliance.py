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

        # Vídeos no relacionados con videojuegos / ajenos
        self.assertFalse(is_strictly_gta("Senior Offering, May 3, 2007"))
        self.assertFalse(is_strictly_gta("Jazz Combo, April 29, 2007"))
        self.assertFalse(is_strictly_gta("Banda tocando música en directo"))
        self.assertFalse(is_strictly_gta("Receta de cocina con Gordon Ramsay"))
        self.assertFalse(is_strictly_gta("Concierto de coro escolar"))

if __name__ == "__main__":
    unittest.main()
