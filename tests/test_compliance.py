import unittest
from src.compliance_auditor import ComplianceAuditor, PLATFORM_POLICIES
from src.channels import is_strictly_gta

class TestCompliance(unittest.TestCase):
    def test_platform_policies_integrity(self):
        self.assertIn("youtube", PLATFORM_POLICIES)
        self.assertIn("tiktok", PLATFORM_POLICIES)
        self.assertIn("instagram", PLATFORM_POLICIES)

    def test_platform_eligibility_meta_shield(self):
        # 1. Instagram debe bloquear clips de streamers de alto perfil
        eligible, reason = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "IlloJuan flipa con el mapa de GTA 6"},
            creator_name="IlloJuan Clips",
            has_voiceover=False,
            mode="subs"
        )
        self.assertFalse(eligible)
        self.assertIn("streamer", reason.lower())

        # 2. Instagram debe bloquear clips sin locución en off propia (solo subs)
        eligible, reason = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "Filtración menú de armas de GTA 6"},
            creator_name="TGG",
            has_voiceover=False,
            mode="subs"
        )
        self.assertFalse(eligible)
        self.assertIn("locución", reason.lower())

        # 3. Instagram debe permitir clips que cuenten con locución/doblaje neural propio
        eligible, reason = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "Filtración menú de armas de GTA 6"},
            creator_name="TGG",
            has_voiceover=True,
            mode="dub"
        )
        self.assertTrue(eligible)

        # 4. YouTube debe permitir clips de noticias bajo Fair Use
        eligible, reason = ComplianceAuditor.is_platform_eligible(
            platform="youtube",
            metadata={"title": "Filtración menú de armas de GTA 6"},
            creator_name="TGG",
            has_voiceover=False,
            mode="subs"
        )
        self.assertTrue(eligible)

        # 5. YouTube y TikTok deben permitir clips de streamers bajo Fair Use
        eligible_yt, _ = ComplianceAuditor.is_platform_eligible(
            platform="youtube",
            metadata={"title": "IlloJuan flipa con el mapa de GTA 6"},
            creator_name="IlloJuan",
            has_voiceover=False,
            mode="subs"
        )
        self.assertTrue(eligible_yt)

        eligible_tt, _ = ComplianceAuditor.is_platform_eligible(
            platform="tiktok",
            metadata={"title": "Ibai reacciona a GTA 6"},
            creator_name="Ibai",
            has_voiceover=False,
            mode="subs"
        )
        self.assertTrue(eligible_tt)

        # 6. allowed_platforms y block_instagram deben ser respetados estrictamente
        eligible_ig, reason_ig = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"block_instagram": True, "title": "Clip oficial GTA 6"},
            creator_name="Rockstar Games",
            has_voiceover=True
        )
        self.assertFalse(eligible_ig)
        self.assertIn("block_instagram", reason_ig)

        eligible_allowed, _ = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"allowed_platforms": ["youtube", "tiktok"], "title": "Clip GTA 6"},
            creator_name="Rockstar Games",
            has_voiceover=True
        )
        self.assertFalse(eligible_allowed)

    def test_option_b_story_alternative_on_blocked_instagram(self):
        from pathlib import Path
        from src.social_publisher import SocialPublisher
        import tempfile

        publisher = SocialPublisher(dry_run=True)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            dummy_path = Path(f.name)
            results = publisher.publish_all(
                video_path=dummy_path,
                metadata={
                    "title": "IlloJuan flipa con el trailer de GTA 6",
                    "description": "Clip de IlloJuan. Fuente: https://youtube.com/watch?v=123. FAIR USE y Uso Legítimo.",
                    "block_instagram": True,
                    "allowed_platforms": ["youtube", "tiktok", "instagram"]
                },
                creator_name="IlloJuan",
                stagger_delay_minutes=0
            )
            # YouTube y TikTok deben procesarse
            self.assertIn("youtube", results)
            self.assertIn("tiktok", results)
            # Instagram debe haber disparado la Opción B (Story alternativa)
            self.assertIn("instagram", results)
            self.assertTrue(
                "Story Alternativa Publicada" in str(results["instagram"]) or
                "Bloqueado por Compliance Shield" in str(results["instagram"])
            )

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
        self.assertTrue(is_strictly_gta("GTA Series Videos: GTA 6 New Screenshots Breakdown"))

        # Vídeos de GTA 5, GTA Online, GTA 4, Mors Mutual o Parodias (DEBEN SER RECHAZADOS)
        self.assertFalse(is_strictly_gta("Mors Mutual: GTA 6 is unplayable..."))
        self.assertFalse(is_strictly_gta("SOUTH PARK GTA 6 PARODY VIRAL"))
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

        # Casos válidos de GTA 6 y comparativas técnicas de físicas
        self.assertTrue(is_strictly_gta("GTA 6 RAGE 9 Vehicle Physics Breakdown"))
        self.assertTrue(is_strictly_gta("GTA 5 vs GTA 6 Water Physics Comparison"))
        self.assertTrue(is_strictly_gta("Lucia and Jason criminal duo explained in GTA 6"))
        self.assertTrue(is_strictly_gta("Jason Schreier reveals GTA 6 internal release date"))

        # Descartar parodias de South Park
        self.assertFalse(is_strictly_gta("South Park GTA 6 Parody Scene"))

        # Descartar talking-heads, cháchara de ex-empleados, podcasts y tertulias sin gameplay
        self.assertFalse(is_strictly_gta("Ex-Rockstar Animator Reacts to GTA 6"))
        self.assertFalse(is_strictly_gta("¡ROCKSTAR SE PRONUNCIA SOBRE GTA 6!"))
        self.assertFalse(is_strictly_gta("GTA 6 Podcast: Declaraciones y rumores"))
        self.assertFalse(is_strictly_gta("Entrevista exclusiva sobre el despido en GTA 6"))
        self.assertFalse(is_strictly_gta("Mi opinión sobre el futuro de GTA 6"))
        self.assertFalse(is_strictly_gta("Video-ensayo sobre la industria de GTA 6"))

    def test_to_unicode_bold(self):
        from src.translator import to_unicode_bold
        self.assertEqual(to_unicode_bold("GTA 6"), "𝗚𝗧𝗔 𝟲")
        self.assertEqual(to_unicode_bold("DEBATE"), "𝗗𝗘𝗕𝗔𝗧𝗘")
        self.assertEqual(to_unicode_bold("Test 123"), "𝗧𝗲𝘀𝘁 𝟭𝟮𝟯")

    def test_purge_audio_descriptors(self):
        from src.translator import purge_audio_descriptors, sanitize_srt_content
        sample1 = "Imagine escaping the police while a massive [music] tornado destroys the"
        self.assertEqual(purge_audio_descriptors(sample1), "Imagine escaping the police while a massive tornado destroys the")

        sample2 = "Tornado police car, Rockstar hasn't [music] confirmed it yet"
        self.assertEqual(purge_audio_descriptors(sample2), "Rockstar hasn't confirmed it yet")

        sample3 = "Would [music] you want to see tornadoes in GTA 6? Video game."
        self.assertEqual(purge_audio_descriptors(sample3), "Would you want to see tornadoes in GTA 6?")

        sample_srt = (
            "1\n00:00:00,000 --> 00:00:02,000\n[música] Bienvenido a Leonida\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nTornado, coche de policía. Rockstar prepara GTA 6\n"
        )
        cleaned_srt = sanitize_srt_content(sample_srt)
        self.assertNotIn("[música]", cleaned_srt)
        self.assertNotIn("coche de policía", cleaned_srt)
        self.assertIn("Bienvenido a Leonida", cleaned_srt)
        self.assertIn("Rockstar prepara GTA 6", cleaned_srt)

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

    def test_is_safe_rrss_candidate_anti_leak_and_fair_use(self):
        from src.compliance_auditor import is_safe_rrss_candidate

        # 1. Leaks o material robado deben ser rechazados tajantemente
        safe, reason, _ = is_safe_rrss_candidate("GTA 6 Gameplay Leaks WON'T STOP (BANNED EVERYWHERE)", uploader="dkdynamite", duration_sec=30)
        self.assertFalse(safe)
        self.assertIn("anti-leak", reason.lower())

        safe, reason, _ = is_safe_rrss_candidate("Filtración del código fuente de GTA 6 en desarrollo", uploader="Random", duration_sec=25)
        self.assertFalse(safe)
        self.assertIn("anti-leak", reason.lower())

        # 2. Tráilers oficiales directos de Rockstar deben ser rechazados
        safe, reason, _ = is_safe_rrss_candidate("Grand Theft Auto VI Trailer 1 Official", uploader="Rockstar Games", duration_sec=90)
        self.assertFalse(safe)

        # 3. Duraciones no compatibles con Shorts deben ser rechazadas
        safe, reason, _ = is_safe_rrss_candidate("GTA 6 Evolución Gráfica Comparativa", uploader="ElAnalistaDeBits", duration_sec=120)
        self.assertFalse(safe)
        self.assertIn("excede", reason.lower())

        # 4. Medios competidores con logotipos quemados (Vandal, 3DJuegos) deben ser rechazados por Anti-Plagio
        safe_vandal, reason_vandal, _ = is_safe_rrss_candidate(
            "¡Menuda EVOLUCIÓN! Comparan los gráficos de GTA San Andreas con los de GTA 6 😱",
            uploader="Vandal",
            duration_sec=16
        )
        self.assertFalse(safe_vandal)
        self.assertIn("anti-plagio", reason_vandal.lower())

        # 5. Candidatos de análisis técnico limpio (ElAnalistaDeBits / GTA Series) deben ser APROBADOS al 100%
        safe, _, meta = is_safe_rrss_candidate(
            "¡Menuda EVOLUCIÓN! Comparan los gráficos de GTA San Andreas con los de GTA 6 😱",
            uploader="ElAnalistaDeBits",
            duration_sec=16
        )
        self.assertTrue(safe)
        self.assertGreaterEqual(meta["safety_score"], 90)
        self.assertEqual(meta["archetype"], "Comparativa Gráfica en Loop")
        self.assertEqual(meta["recommended_mode"], "gameplay")

        # 5. Descubrimiento geográfico de TGG debe ser APROBADO
        safe_tgg, _, meta_tgg = is_safe_rrss_candidate(
            "A Viewer Found GTA 6's Hotel in Real Life",
            uploader="TGG",
            duration_sec=13
        )
        self.assertTrue(safe_tgg)
        self.assertGreaterEqual(meta_tgg["safety_score"], 85)

        # 6. Fuentes 16:9 limpias (228s) con allow_long_clipping=True deben ser APROBADAS para auto-recorte
        safe_ws, _, meta_ws = is_safe_rrss_candidate(
            "GTA 6 Launch Screenshots - All 39 New Images Released",
            uploader="GTA Series Videos",
            duration_sec=228,
            allow_long_clipping=True
        )
        self.assertTrue(safe_ws)
        self.assertGreaterEqual(meta_ws["safety_score"], 90)

        # 7. Conceptos CGI / formatos lentos de podcast deben ser rechazados, pero reacciones frescas y tráilers nuevos transformados deben APROBARSE
        safe_podcast, reason_pod, _ = is_safe_rrss_candidate(
            "The 6 Confirmed Radio Stations in Grand Theft Auto VI",
            uploader="EssayChannel",
            duration_sec=385,
            allow_long_clipping=True
        )
        self.assertFalse(safe_podcast)
        self.assertIn("quality shield", reason_pod.lower())

        safe_react, _, _ = is_safe_rrss_candidate(
            "Grand Theft Auto VI: Pre-Load Now Trailer - Reaction!",
            uploader="Tyrone Magnus",
            duration_sec=126,
            allow_long_clipping=True
        )
        self.assertTrue(safe_react)

        safe_new_rockstar, _, _ = is_safe_rrss_candidate(
            "Grand Theft Auto VI: Pre-Load Now",
            uploader="Rockstar Games",
            duration_sec=30,
            allow_official_commentary=True
        )
        self.assertTrue(safe_new_rockstar)

    def test_filter_repetitive_candidates(self):
        from src.channels import filter_repetitive_candidates
        mock_history = [
            {
                "id": "old_1",
                "title": "GTA 6 Launch Screenshots - All 39 New Images",
                "creator": "GTA Series Videos",
                "status": "completed"
            },
            {
                "id": "rej_1",
                "title": "Lucia gets nervous when asked about GTA 6",
                "creator": "MemeUploader",
                "status": "rejected_by_operator"
            }
        ]
        cands = [
            {"id": "dup_exact_topic", "title": "GTA 6 Launch Screenshots All 39 New Images Released", "score": 95, "source_name": "GTA Series Videos"},
            {"id": "dup_rejected_topic", "title": "Lucia gets very nervous asked about GTA 6!", "score": 92, "source_name": "AnotherChannel"},
            {"id": "fresh_1a", "title": "GTA 6 RAGE 9 Water Physics Comparison in Vice Beach", "score": 88, "source_name": "ElAnalistaDeBits"},
            {"id": "fresh_1b", "title": "GTA 6 RAGE 9 Water Physics Comparison in Vice Beach (Reupload)", "score": 85, "source_name": "CloneChannel"},
            {"id": "cooldown_src", "title": "GTA 6 Hidden Easter Eggs in Port Gellhorn", "score": 90, "source_name": "GTA Series Videos"},
        ]
        res = filter_repetitive_candidates(cands, processed_entries=mock_history)
        ids = [c["id"] for c in res]
        self.assertNotIn("dup_exact_topic", ids)
        self.assertNotIn("dup_rejected_topic", ids)
        self.assertIn("fresh_1a", ids)
        self.assertNotIn("fresh_1b", ids)
        cooldown_item = next(c for c in res if c["id"] == "cooldown_src")
        self.assertTrue(cooldown_item.get("cooldown_applied"))
        self.assertEqual(cooldown_item["score"], 70)

    def test_filter_repetitive_allows_distinct_rockstar_and_reactions(self):
        from src.channels import filter_repetitive_candidates
        mock_history = [
            {
                "id": "rz1B4B2yBZY",
                "title": "Grand Theft Auto VI Launch Trailer",
                "creator": "Rockstar Games (Oficial)",
                "status": "discarded",
            }
        ]
        cands = [
            {"id": "_yl5ELcmugI", "title": "Grand Theft Auto VI: Pre-Load Now", "score": 95, "source_name": "Rockstar Games"},
            {"id": "fest1234567", "title": "Grand Theft Auto VI: The Festival", "score": 92, "source_name": "Rockstar Games"},
            {"id": "react123456", "title": "GTA 6 LAUNCH TRAILER REACTION - ITS SO PEAK!", "score": 90, "source_name": "SomeCreator"},
            {"id": "analys12345", "title": "GTA 6 Launch Trailer - Analysis + Full Thoughts!", "score": 89, "source_name": "BreakdownYT"},
            {"id": "dup_same123", "title": "Grand Theft Auto VI: Launch Trailer (4K)", "score": 80, "source_name": "ReuploadYT"},
        ]
        res = filter_repetitive_candidates(cands, processed_entries=mock_history)
        ids = [c["id"] for c in res]
        self.assertIn("_yl5ELcmugI", ids)
        self.assertIn("fest1234567", ids)
        self.assertIn("react123456", ids)
        self.assertIn("analys12345", ids)
        self.assertNotIn("dup_same123", ids)

    def test_clickbait_blacklist_and_split_ig_eligibility(self):
        from src.compliance_auditor import is_safe_rrss_candidate
        safe_mb, _, _ = is_safe_rrss_candidate(
            "This Is HUGE For GTA 6 - NEW Pre Load Trailer!",
            uploader="MrBossFTW",
            duration_sec=498,
            allow_long_clipping=True
        )
        self.assertFalse(safe_mb)

        elig_split, _ = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "GTA 6 30 FPS VS 60 FPS", "is_transformed_visual": True},
            creator_name="Enigma Gaming",
            has_voiceover=False,
            mode="gameplay"
        )
        self.assertTrue(elig_split)

    def test_instagram_session_account_isolation(self):
        import os
        import sys
        import types
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import src.social_publisher as sp

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_profile = Path(tmpdir)
            session_file = tmp_profile / "instagrapi_session.json"
            session_file.write_text('{"authorization_data": {"ds_user_id": "123"}}')
            vid_file = tmp_profile / "clip.mp4"
            vid_file.write_bytes(b"fake")

            old_client = MagicMock()
            old_client.account_info.return_value = MagicMock(username="gtavihubspain")
            fresh_client = MagicMock()
            fresh_client.account_info.return_value = MagicMock(username="gtavihubextra")
            fresh_client.clip_upload.return_value = MagicMock(code="ABC123xyz")

            fake_mod = types.ModuleType("instagrapi")
            fake_mod.Client = MagicMock(side_effect=[old_client, fresh_client])

            pub = sp.SocialPublisher(dry_run=False)
            with patch.object(pub, "_notify_telegram"), \
                 patch.object(sp, "BROWSER_PROFILE_DIR", tmp_profile), \
                 patch.dict(sys.modules, {"instagrapi": fake_mod}), \
                 patch.dict(os.environ, {"INSTAGRAM_USERNAME": "gtavihubextra", "INSTAGRAM_PASSWORD": "secret"}):
                url = pub.publish_to_instagram(vid_file, "Test caption")

            self.assertEqual(url, "https://www.instagram.com/reel/ABC123xyz/")
            old_client.clip_upload.assert_not_called()
            fresh_client.login.assert_called_once_with("gtavihubextra", "secret")
            fresh_client.clip_upload.assert_called_once()

            # Si CAA devuelve la cuenta antigua (@gtavihubspain) al pedir @gtavihubextra, debe abortar
            wrong_client = MagicMock()
            wrong_client.account_info.return_value = MagicMock(username="gtavihubspain")
            fake_mod2 = types.ModuleType("instagrapi")
            fake_mod2.Client = MagicMock(return_value=wrong_client)
            with patch.object(pub, "_notify_telegram") as mock_tg_mismatch, \
                 patch.object(sp, "BROWSER_PROFILE_DIR", tmp_profile), \
                 patch.dict(sys.modules, {"instagrapi": fake_mod2}), \
                 patch.dict(os.environ, {"INSTAGRAM_USERNAME": "gtavihubextra", "INSTAGRAM_PASSWORD": "secret"}, clear=False):
                os.environ.pop("ALLOW_LEGACY_INSTAGRAM", None)
                mismatch_url = pub.publish_to_instagram(vid_file, "Test caption")
            self.assertIsNone(mismatch_url)
            wrong_client.clip_upload.assert_not_called()
            mock_tg_mismatch.assert_called_once()

            # Uso automatico de cookie web (storage_state.json -> login_by_sessionid)
            (tmp_profile / "storage_state.json").write_text(
                '{"cookies": [{"name": "sessionid", "value": "56974781759%3Aabc123456789012345678901234567890", "domain": ".instagram.com"}]}'
            )
            sid_client = MagicMock()
            sid_client.account_info.return_value = MagicMock(username="gtavihubextra")
            sid_client.clip_upload.return_value = MagicMock(code="SID999ok")
            fake_mod3 = types.ModuleType("instagrapi")
            fake_mod3.Client = MagicMock(side_effect=[old_client, sid_client])
            with patch.object(pub, "_notify_telegram"), \
                 patch.object(sp, "BROWSER_PROFILE_DIR", tmp_profile), \
                 patch.dict(sys.modules, {"instagrapi": fake_mod3}), \
                 patch.dict(os.environ, {"INSTAGRAM_USERNAME": "gtavihubextra", "INSTAGRAM_PASSWORD": "secret"}):
                sid_url = pub.publish_to_instagram(vid_file, "Test caption")
            self.assertEqual(sid_url, "https://www.instagram.com/reel/SID999ok/")
            sid_client.login_by_sessionid.assert_called_once()
            sid_client.login.assert_not_called()

            # Bloqueo Anti-Ban si .env sigue apuntando a cuenta heredada gtavihubspain
            with patch.object(pub, "_notify_telegram") as mock_tg, \
                 patch.object(sp, "BROWSER_PROFILE_DIR", tmp_profile), \
                 patch.dict(os.environ, {"INSTAGRAM_USERNAME": "gtavihubspain", "INSTAGRAM_PASSWORD": "secret"}, clear=False):
                os.environ.pop("ALLOW_LEGACY_INSTAGRAM", None)
                blocked_url = pub.publish_to_instagram(vid_file, "Test caption")
            self.assertIsNone(blocked_url)
            mock_tg.assert_called_once()

    def test_tiktok_storage_state_and_legacy_guard(self):
        import os
        import sys
        import types
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import src.social_publisher as sp

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_profile = Path(tmpdir)
            (tmp_profile / "storage_state.json").write_text('{"cookies": [{"name": "sid", "value": "x", "domain": ".tiktok.com"}]}')
            vid_file = tmp_profile / "clip.mp4"
            vid_file.write_bytes(b"fake")

            fake_page = MagicMock()
            fake_page.url = "https://www.tiktok.com/tiktokstudio"
            fake_page.inner_text.return_value = "Panel @gtavihubspain Analytics"
            fake_ctx = MagicMock()
            fake_ctx.new_page.return_value = fake_page
            fake_browser = MagicMock()
            fake_browser.new_context.return_value = fake_ctx
            fake_pw = MagicMock()
            fake_pw.chromium.launch.return_value = fake_browser
            fake_cm = MagicMock()
            fake_cm.__enter__.return_value = fake_pw
            fake_cm.__exit__.return_value = False

            fake_pw_mod = types.ModuleType("playwright")
            fake_pw_sync = types.ModuleType("playwright.sync_api")
            fake_pw_sync.sync_playwright = MagicMock(return_value=fake_cm)

            pub = sp.SocialPublisher(dry_run=False)
            with patch.object(pub, "_notify_telegram") as mock_tg, \
                 patch.object(sp, "BROWSER_PROFILE_DIR", tmp_profile), \
                 patch.dict(sys.modules, {"playwright": fake_pw_mod, "playwright.sync_api": fake_pw_sync}), \
                 patch.dict(os.environ, {"HEADLESS_BROWSER": "true"}, clear=False):
                os.environ.pop("ALLOW_LEGACY_TIKTOK", None)
                res_url = pub.publish_to_tiktok(vid_file, "Título GTA 6", ["GTA6"])

            self.assertIsNone(res_url)
            fake_pw.chromium.launch.assert_called_once()
            fake_browser.new_context.assert_called_once()
            fake_ctx.close.assert_called_once()
            fake_browser.close.assert_called_once()
            mock_tg.assert_called_once()

    def test_pipeline_english_speech_guard_switches_gameplay_to_dub(self):
        import subprocess
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import src.pipeline as pl

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            t_dir = tmp_root / "temp"
            o_dir = tmp_root / "output"
            t_dir.mkdir()
            o_dir.mkdir()

            fake_vid = t_dir / "talk123.mp4"
            fake_vid.write_bytes(b"video")
            fake_en_srt = t_dir / "talk123.en.srt"
            fake_en_srt.write_text(
                "1\n00:00:00,500 --> 00:00:04,000\n[Music]\n\n"
                "2\n00:00:04,100 --> 00:00:12,000\nLook at this insane NPC density in Grand Theft Auto Six right now in Vice City\n",
                encoding="utf-8",
            )
            self.assertEqual(pl._count_spoken_words_in_srt(fake_en_srt), 16)

            def _fake_translate(src_p, dst_p, source_lang="en"):
                dst_p.write_text("1\n00:00:04,100 --> 00:00:12,000\nMira esta increíble densidad de NPCs en GTA 6\n", encoding="utf-8")
                return True

            def _fake_voiceover(srt_p, out_p, **kwargs):
                out_p.write_bytes(b"mp3")
                return True

            def _fake_render(*args, **kwargs):
                Path(kwargs["output_video"]).write_bytes(b"mp4")
                return True

            fake_sub_res = MagicMock(
                stdout="22.0\n",
                stderr="pts_time:1.0\npts_time:4.0\npts_time:8.0\npts_time:12.0\n",
            )

            with patch.object(pl, "TEMP_DIR", t_dir), \
                 patch.object(pl, "OUTPUT_DIR", o_dir), \
                 patch.object(pl, "AUTO_DUB_ENGLISH", True), \
                 patch.object(pl, "download_video_and_subtitles", return_value=(fake_vid, fake_en_srt, "en")), \
                 patch.object(pl, "get_video_dimensions", return_value=(1080, 1920)), \
                 patch.object(pl, "detect_horizontal_split_screen", return_value=False), \
                 patch.object(pl, "translate_srt", side_effect=_fake_translate) as mock_trans, \
                 patch.object(pl, "generate_voiceover", side_effect=_fake_voiceover) as mock_dub, \
                 patch.object(pl, "generate_video_metadata", return_value={"title": "DENSIDAD NPC GTA 6", "description": "D", "tags": ["GTA6"], "hook": "BRUTAL"}), \
                 patch.object(pl, "render_final_video", side_effect=_fake_render), \
                 patch.object(pl, "create_video_thumbnail"), \
                 patch.object(pl, "clean_temp_directory"), \
                 patch.object(pl, "enforce_storage_limits"), \
                 patch.object(pl, "mark_video_processed"), \
                 patch("src.audio_shield.validate_audio_and_speech_vitality", return_value=(True, "OK", {})), \
                 patch.object(subprocess, "run", return_value=fake_sub_res):
                res = pl.process_single_video(
                    url="https://youtube.com/shorts/talk123",
                    video_id="talk123",
                    original_title="GTA 6 NPC density is MINDBLOWING",
                    creator_name="TalkingHeadCreator",
                    source_lang="en",
                    mode="gameplay",
                    dry_run=True,
                    copilot_mode=False,
                    is_manual_ingest=False,
                )

            self.assertIsNotNone(res)
            self.assertEqual(res["mode"], "dub")
            mock_trans.assert_called_once()
            mock_dub.assert_called_once()

            # Comparativa split-screen sí debe respetar el modo gameplay sin doblar
            with patch.object(pl, "TEMP_DIR", t_dir), \
                 patch.object(pl, "OUTPUT_DIR", o_dir), \
                 patch.object(pl, "AUTO_DUB_ENGLISH", True), \
                 patch.object(pl, "download_video_and_subtitles", return_value=(fake_vid, fake_en_srt, "en")), \
                 patch.object(pl, "get_video_dimensions", return_value=(1920, 1080)), \
                 patch.object(pl, "detect_horizontal_split_screen", return_value=True), \
                 patch.object(pl, "translate_srt") as mock_trans_split, \
                 patch.object(pl, "generate_voiceover") as mock_dub_split, \
                 patch.object(pl, "generate_video_metadata", return_value={"title": "30 VS 60 FPS GTA 6", "description": "D", "tags": ["GTA6"], "hook": "FPS"}), \
                 patch.object(pl, "render_final_video", side_effect=_fake_render), \
                 patch.object(pl, "create_video_thumbnail"), \
                 patch.object(pl, "clean_temp_directory"), \
                 patch.object(pl, "enforce_storage_limits"), \
                 patch.object(pl, "mark_video_processed"), \
                 patch("src.audio_shield.validate_audio_and_speech_vitality", return_value=(True, "OK", {})), \
                 patch.object(subprocess, "run", return_value=fake_sub_res):
                res_split = pl.process_single_video(
                    url="https://youtube.com/watch?v=split123",
                    video_id="split123",
                    original_title="GTA 6 30 FPS vs 60 FPS Comparison",
                    creator_name="Enigma Gaming",
                    source_lang="en",
                    mode="gameplay",
                    dry_run=True,
                    copilot_mode=False,
                    is_manual_ingest=False,
                )
            self.assertIsNotNone(res_split)
            self.assertEqual(res_split["mode"], "gameplay")
            mock_trans_split.assert_not_called()
            mock_dub_split.assert_not_called()

    def test_quality_shield_and_gray_frame_retention(self):
        import src.pipeline as pl
        from src.compliance_auditor import is_safe_rrss_candidate

        s_ign, r_ign, _ = is_safe_rrss_candidate(
            "Rockstar Confirms GTA 6 Will Run at 30fps - IGN Daily Fix",
            uploader="IGN",
            duration_sec=289,
            allow_long_clipping=True,
            allow_official_commentary=True,
        )
        self.assertFalse(s_ign)
        self.assertIn("quality shield", r_ign.lower())

        s_fest, r_fest, _ = is_safe_rrss_candidate(
            "Grand Theft Auto VI: The Festival",
            uploader="Rockstar Games",
            duration_sec=15,
            allow_official_commentary=True,
        )
        self.assertFalse(s_fest)
        self.assertIn("quality shield", r_fest.lower())

        w, h = 160, 90
        n_px = w * h
        bright_slide = bytes([245] * n_px)
        ok_slide, reason_slide = pl._evaluate_gray_frames_retention([bright_slide, bright_slide, bright_slide, bright_slide])
        self.assertFalse(ok_slide)
        self.assertIn("diapositivas", reason_slide.lower())

        static_frame = bytes((i % 150) for i in range(n_px))
        ok_static, reason_static = pl._evaluate_gray_frames_retention([static_frame] * 5)
        self.assertFalse(ok_static)
        self.assertIn("plano fijo", reason_static.lower())

        moving_frames = [bytes(((i * 7 + step * 55) % 190) for i in range(n_px)) for step in range(5)]
        ok_move, _ = pl._evaluate_gray_frames_retention(moving_frames)
        self.assertTrue(ok_move)

    def test_portuguese_and_clickbait_rejection_and_prelaunch_flags(self):
        import os
        from datetime import datetime
        from unittest.mock import patch
        import src.config as cfg

        # Idiomas no objetivo (PT/FR) y checklists falsos pre-lanzamiento deben bloquearse
        self.assertFalse(is_strictly_gta("10 coisas que vou fazer quando GTA 6 lançar", "GamerBR"))
        self.assertFalse(is_strictly_gta("GTA 6 bande-annonce officielle en français", "JeuxFR"))
        self.assertFalse(is_strictly_gta("NO avances la HISTORIA de GTA 6 sin hacer estas 10 COSAS", "2 PLAYER MX"))

        # audit_all debe existir para el comando /audit de Telegram
        self.assertIsInstance(ComplianceAuditor.audit_all(), int)

        # is_gameplay_enabled debe respetar la fecha de lanzamiento (False antes de 2026-11-19 si no se fuerza)
        with patch.dict(os.environ, {"FORCE_ENABLE_GAMEPLAY": ""}, clear=False), \
             patch.object(cfg, "FORCE_ENABLE_GAMEPLAY", False), \
             patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 17, 22, 0, 0)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            self.assertFalse(cfg.is_gameplay_enabled())
            mock_dt.now.return_value = datetime(2026, 11, 19, 0, 5, 0)
            self.assertTrue(cfg.is_gameplay_enabled())

if __name__ == "__main__":
    unittest.main()
