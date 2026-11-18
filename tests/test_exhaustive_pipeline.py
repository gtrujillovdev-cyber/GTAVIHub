import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import src.pipeline as pl
from src.adaptive_scheduler import get_daily_schedule, LAUNCH_NIGHT_WINDOWS
from src.audio_shield import detect_audio_levels, validate_audio_and_speech_vitality
from src.channels import is_strictly_gta6, mark_video_processed, get_processed_ids
from src.cleaner import clean_temp_directory, clean_uploaded_video_file
from src.compliance_auditor import ComplianceAuditor
from src.config import BASE_DIR, OUTPUT_DIR, TEMP_DIR, is_quant_busy, is_gameplay_enabled
from src.social_publisher import SocialPublisher
from src.translator import generate_content_with_retry, generate_video_metadata


class TestExhaustivePipeline(unittest.TestCase):
    """
    Batería de pruebas exhaustivas y críticas para el pipeline completo de GTA VI Hub Spain.
    Valida:
      1. Filtrado y defensa en profundidad (Anti-OffTopic / Anti-Leak / Anti-Fake).
      2. Síntesis y transformación real de vídeo con FFmpeg (Formato vertical 9:16, Audio Shield, Karaoke).
      3. Doblaje neural automático ante locución en inglés (Guardia Anti-Inglés).
      4. Cumplimiento legal y Fair Use multiplataforma (YouTube, TikTok, Instagram Shield).
      5. Coexistencia con GaTDSEQ (Thread-capping de CPU y recolección de memoria).
      6. Protocolo de Disco 0 Bytes en temp/ y output/.
      7. Calendario de estreno 19-N y ventanas nocturnas (midnight_drop / late_night_wave).
      8. Inferencia estructurada con Gemini 4 Hydrogen.
    """

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.test_dir.name)
        self.mock_temp = self.test_path / "temp"
        self.mock_output = self.test_path / "output"
        self.mock_temp.mkdir(parents=True, exist_ok=True)
        self.mock_output.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.test_dir.cleanup()

    def _create_synthetic_video(
        self,
        filename: str = "synth_test.mp4",
        duration: int = 3,
        width: int = 1920,
        height: int = 1080,
        with_audio: bool = True,
        audio_frequency: int = 440,
        volume: str = "1.0"
    ) -> Path:
        """Genera un archivo MP4 real sintético usando FFmpeg para pruebas E2E."""
        out_file = self.mock_temp / filename
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=navy:s={width}x{height}:d={duration}:r=30"]
        if with_audio:
            cmd.extend([
                "-f", "lavfi",
                "-i", f"sine=frequency={audio_frequency}:duration={duration}",
                "-af", f"volume={volume}",
                "-c:a", "aac", "-b:a", "128k"
            ])
        else:
            cmd.extend(["-an"])

        cmd.extend([
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(duration),
            str(out_file)
        ])
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Error creando vídeo sintético: {res.stderr}")
        self.assertTrue(out_file.exists())
        self.assertGreater(out_file.stat().st_size, 1000)
        return out_file

    def _create_synthetic_srt(self, filename: str = "synth.srt", text: str = "GTA 6 gameplay impresionante") -> Path:
        srt_file = self.mock_temp / filename
        content = f"1\n00:00:00,500 --> 00:00:02,500\n{text}\n\n"
        srt_file.write_text(content, encoding="utf-8")
        return srt_file

    # -------------------------------------------------------------------------
    # 1. FILTRADO Y DEFENSA EN PROFUNDIDAD (Gatekeeper)
    # -------------------------------------------------------------------------
    def test_gatekeeper_rejects_non_gta_content(self):
        """El pipeline debe rechazar de inmediato contenidos no relacionados con GTA 6."""
        off_topic_titles = [
            "Cyberpunk 2077 Update 2.3 Gameplay Walkthrough",
            "Fortnite Chapter 6 Season 1 Battle Pass Trailer",
            "Minecraft 1.22 New Biomes Revealed",
            "Call of Duty Warzone Season 2 Patch Notes"
        ]
        with patch("src.telegram_bot.send_telegram_alert"):
            for title in off_topic_titles:
                self.assertFalse(is_strictly_gta6(title), f"Debería rechazar '{title}'")
                res = pl.process_single_video(
                    url=f"https://youtube.com/watch?v=mock_{hash(title)}",
                    video_id=f"off_{abs(hash(title)) % 10000}",
                    original_title=title,
                    creator_name="Random Gaming",
                    dry_run=True,
                    copilot_mode=False
                )
                self.assertIsNone(res, f"El pipeline debió abortar inmediatamente con '{title}'")

    def test_gatekeeper_accepts_valid_gta6_content(self):
        """El filtro debe permitir títulos legítimos de GTA 6."""
        valid_titles = [
            "Grand Theft Auto VI: Official Launch Gameplay",
            "GTA 6 RAGE 9 Water Physics and Vehicle Damage",
            "Lucia and Jason Vice City Night Mission GTA 6",
            "GTA 6 Graphics Comparison PS5 Pro vs Xbox Series X"
        ]
        for title in valid_titles:
            self.assertTrue(is_strictly_gta6(title), f"Debería aceptar '{title}'")

    # -------------------------------------------------------------------------
    # 2. AUDIO SHIELD & RECHAZO DE VÍDEOS MUDOS / B-ROLL
    # -------------------------------------------------------------------------
    def test_audio_shield_aborts_silent_video(self):
        """Un vídeo sin pista de audio o con volumen inaudible debe ser rechazado por Audio Shield."""
        silent_video = self._create_synthetic_video(
            filename="silent_clip.mp4",
            duration=3,
            with_audio=False
        )
        audio_info = detect_audio_levels(silent_video)
        self.assertFalse(audio_info["has_audio"])

        is_vital, reason, _ = validate_audio_and_speech_vitality(
            video_path=silent_video,
            srt_path=None,
            has_voiceover=False,
            mode="subs",
            is_manual=False,
            allow_gameplay_sound=False
        )
        self.assertFalse(is_vital)
        self.assertTrue("carece" in reason.lower() or "mudo" in reason.lower() or "silencio" in reason.lower())

    # -------------------------------------------------------------------------
    # 3. GUARDIA ANTI-INGLÉS & AUTO-DOBLAJE NEURAL
    # -------------------------------------------------------------------------
    def test_anti_english_guard_activates_dubbing(self):
        """Vídeo en inglés con >12 palabras habladas debe forzar modo dub y generar locución."""
        english_text = (
            "Rockstar Games has just released the official details on how the new Vice City police system "
            "tracks suspects across different districts using AI and facial recognition technology."
        )
        srt_file = self._create_synthetic_srt("english_dense.srt", english_text)

        fake_video = self.mock_temp / "fake_eng.mp4"
        fake_video.write_bytes(b"dummy_mp4_bytes")

        def _mock_dub(srt, out, max_duration=None):
            out.write_bytes(b"mock_voiceover_mp3_data")
            return True

        def _mock_trans(src, dst, source_lang="en"):
            dst.write_text("1\n00:00:00,500 --> 00:00:02,500\nRockstar Games acaba de revelar el sistema policial.\n\n", encoding="utf-8")
            return True

        def _mock_render(input_video, output_video, **kwargs):
            output_video.write_bytes(b"rendered_mp4_data")
            return True

        fake_sub_res = MagicMock(
            stdout="22.0",
            stderr="pts_time: 1.2\npts_time: 5.4\npts_time: 9.8\npts_time: 14.1\n",
            returncode=0
        )

        with patch.object(pl, "TEMP_DIR", self.mock_temp), \
             patch.object(pl, "OUTPUT_DIR", self.mock_output), \
             patch.object(pl, "AUTO_DUB_ENGLISH", True), \
             patch.object(pl, "download_video_and_subtitles", return_value=(fake_video, srt_file, "en")), \
             patch.object(pl, "get_video_dimensions", return_value=(1080, 1920)), \
             patch.object(pl, "detect_horizontal_split_screen", return_value=False), \
             patch.object(pl, "translate_srt", side_effect=_mock_trans) as mock_trans, \
             patch.object(pl, "generate_voiceover", side_effect=_mock_dub) as mock_dub, \
             patch.object(pl, "generate_video_metadata", return_value={
                 "title": "NUEVO SISTEMA POLICIAL GTA 6",
                 "description": "Detalles oficiales",
                 "tags": ["GTA6"],
                 "hook": "¡POLICÍA CON IA!"
             }), \
             patch.object(pl, "render_final_video", side_effect=_mock_render), \
             patch.object(pl, "create_video_thumbnail"), \
             patch.object(pl, "clean_temp_directory"), \
             patch.object(pl, "enforce_storage_limits"), \
             patch.object(pl, "mark_video_processed"), \
             patch("src.audio_shield.validate_audio_and_speech_vitality", return_value=(True, "OK", {})), \
             patch("src.telegram_bot.send_telegram_alert"), \
             patch.object(subprocess, "run", return_value=fake_sub_res):

            res = pl.process_single_video(
                url="https://youtube.com/watch?v=police_ai",
                video_id="police_ai",
                original_title="GTA 6 Next Gen Police AI System Breakdown",
                creator_name="Technical Gaming",
                source_lang="en",
                mode="gameplay",  # Intentaba pasar como gameplay
                dry_run=True,
                copilot_mode=False
            )

            self.assertIsNotNone(res)
            # La guardia anti-inglés debe haber cambiado el modo a 'dub'
            self.assertEqual(res["mode"], "dub")
            mock_trans.assert_called_once()
            mock_dub.assert_called_once()

    # -------------------------------------------------------------------------
    # 4. TRANSFROMACIÓN REAL DE VÍDEO CON FFMPEG (E2E Render & 9:16 Vertical)
    # -------------------------------------------------------------------------
    def test_e2e_video_transformation_and_render(self):
        """Renderiza un vídeo sintético 16:9 real a 9:16 vertical con hook y subtítulos."""
        input_vid = self._create_synthetic_video(
            filename="input_16_9.mp4",
            duration=3,
            width=1920,
            height=1080,
            with_audio=True
        )
        srt_file = self._create_synthetic_srt("es_sub.srt", "¡FÍSICAS BRUTALES EN GTA 6!")
        output_vid = self.mock_output / "final_vertical.mp4"

        # Importar render_final_video real
        from src.video_editor import render_final_video

        success = render_final_video(
            input_video=input_vid,
            output_video=output_vid,
            srt_subtitles=srt_file,
            force_short_format=True,
            hook_text="FÍSICAS RAGE 9\nDETALLE INCREÍBLE",
            archetype="gameplay_puro",
            format_preset="D"
        )
        self.assertTrue(success, "El renderizado FFmpeg debe completarse con éxito")
        self.assertTrue(output_vid.exists(), "El archivo de salida debe existir")
        self.assertGreater(output_vid.stat().st_size, 5000, "El vídeo final debe tener contenido real")

        # Verificar dimensiones y SAR 1:1 del vídeo de salida vía ffprobe (debe ser 1080x1920 vertical)
        p = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,sample_aspect_ratio", "-of", "csv=p=0", str(output_vid)],
            capture_output=True, text=True
        )
        probe_out = p.stdout.strip()
        self.assertTrue(probe_out.startswith("1080,1920"), f"El formato final debe ser 1080x1920, se obtuvo '{probe_out}'")
        self.assertIn("1:1", probe_out, f"SAR debe normalizarse a 1:1 para TikTok/Shorts, se obtuvo '{probe_out}'")

    # -------------------------------------------------------------------------
    # 5. CUMPLIMIENTO LEGAL & FAIR USE MULTIPLATAFORMA
    # -------------------------------------------------------------------------
    def test_fair_use_and_attribution_generation(self):
        """Los metadatos deben incluir mención obligatoria de autor y cláusula Fair Use."""
        meta = generate_video_metadata(
            original_title="GTA 6 Water Physics and Boat Crash",
            original_url="https://youtube.com/watch?v=water_phys",
            is_short=True,
            creator_name="Enigma Gaming",
            clip_transcript="Las físicas de fluidos reaccionan con gran realismo."
        )
        self.assertIn("title", meta)
        self.assertIn("description", meta)
        desc = meta["description"]

        # 1. Atribución transparente al autor original
        self.assertTrue(
            "POR: @Enigma Gaming" in desc or "@Enigma Gaming" in desc or "Enigma Gaming" in desc,
            "La descripción debe contener mención al creador original"
        )
        # 2. Descargo estatutario de Fair Use (Art. 107)
        self.assertIn("107", desc, "Debe contener referencia al Artículo 107 de la Ley de Propiedad Intelectual")
        self.assertIn("fair use", desc.lower())

    def test_instagram_meta_shield_blocks_unauthorized_content(self):
        """Instagram debe rechazar clips de streamers o clips sin locución propia."""
        # Caso 1: Streamer conocido (ej: IlloJuan)
        eligible_streamer, reason_streamer = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "IlloJuan flipa con el nuevo tráiler de GTA 6"},
            creator_name="IlloJuan",
            has_voiceover=False,
            mode="subs"
        )
        self.assertFalse(eligible_streamer)
        self.assertIn("streamer", reason_streamer.lower())

        # Caso 2: Clip oficial con block_instagram: True
        eligible_blocked, _ = ComplianceAuditor.is_platform_eligible(
            platform="instagram",
            metadata={"title": "GTA 6 Official Clip", "block_instagram": True},
            creator_name="Rockstar Games",
            has_voiceover=True
        )
        self.assertFalse(eligible_blocked)

    # -------------------------------------------------------------------------
    # 6. COEXISTENCIA CON GATDSEQ (Hardware Throttling)
    # -------------------------------------------------------------------------
    def test_gatdseq_coexistence_cpu_throttling(self):
        """Si GaTDSEQ está activo, FFmpeg debe reducirse estrictamente a 1 hilo."""
        from src.config import get_ffmpeg_threads

        with patch("src.config.is_quant_busy", return_value=True):
            self.assertEqual(get_ffmpeg_threads(), 1, "Cuando GaTDSEQ calcula, FFmpeg debe limitarse a 1 hilo")

        with patch("src.config.is_quant_busy", return_value=False):
            self.assertEqual(get_ffmpeg_threads(), 2, "En reposo, FFmpeg debe usar su límite estándar de 2 hilos")

    # -------------------------------------------------------------------------
    # 7. PROTOCOLO DE HIGIENE DE DISCO (Regla 0 Bytes)
    # -------------------------------------------------------------------------
    def test_strict_disk_hygiene_removes_temp_and_mp4(self):
        """Comprueba que temp/ se purga totalmente y los .mp4 se eliminan tras subida."""
        dummy_temp_file = self.mock_temp / "leftover_chunk.ts"
        dummy_temp_file.write_bytes(b"temp_garbage_data")
        dummy_mp4 = self.mock_output / "uploaded_video.mp4"
        dummy_mp4.write_bytes(b"heavy_video_payload")

        # 1. Limpieza de archivo subido
        clean_uploaded_video_file(dummy_mp4)
        self.assertFalse(dummy_mp4.exists(), "El archivo .mp4 pesado debió ser eliminado del disco tras la subida")

        # 2. Limpieza total de carpeta temp
        with patch("src.cleaner.TEMP_DIR", self.mock_temp):
            clean_temp_directory()
            files_left = list(self.mock_temp.iterdir())
            self.assertEqual(len(files_left), 0, f"temp/ debe quedar en 0 bytes/archivos. Quedaron: {files_left}")

    # -------------------------------------------------------------------------
    # 8. CALENDARIO DE ESTRENO 19-N Y VENTANAS NOCTURNAS
    # -------------------------------------------------------------------------
    def test_launch_night_schedule_and_phase_transition(self):
        """Verifica la inyección automática de midnight_drop y late_night_wave para el 19-N."""
        sched_19 = get_daily_schedule(date(2026, 11, 19))
        windows = sched_19.get("windows", [])
        win_ids = [w["id"] for w in windows]

        self.assertIn("midnight_drop", win_ids, "Debe incluir la ventana de medianoche (00:00 CET)")
        self.assertIn("late_night_wave", win_ids, "Debe incluir la ventana de madrugada (01:30 CET)")

        # Comprobación de estado de fase antes y después de la fecha de estreno
        with patch("src.config.GAMEPLAY_RELEASE_DATE", "2099-01-01"):
            with patch("src.config.FORCE_ENABLE_GAMEPLAY", False):
                self.assertFalse(is_gameplay_enabled(), "Antes de la fecha de estreno, gameplay debe estar deshabilitado")

        with patch("src.config.GAMEPLAY_RELEASE_DATE", "2020-01-01"):
            self.assertTrue(is_gameplay_enabled(), "A partir de la fecha de estreno, gameplay debe estar habilitado")

    # -------------------------------------------------------------------------
    # 9. INFERENCIA Y SALIDA ESTRUCTURADA CON GEMINI 4 HYDROGEN
    # -------------------------------------------------------------------------
    def test_hydrogen_model_invocation_and_json_parsing(self):
        """Prueba de llamada controlada con JSON estructurado en Hydrogen / Fallbacks."""
        from src.translator import get_gemini_client
        client = get_gemini_client()
        prompt = "Devuelve exclusivamente este JSON: {\"status\": \"ready\", \"model\": \"hydrogen\"}"
        res = generate_content_with_retry(
            client=client,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        self.assertIsNotNone(res)
        text = res.text if hasattr(res, "text") else str(res)
        data = json.loads(text)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ready")

    # -------------------------------------------------------------------------
    # 10. PIPELINE DE GAMEPLAY REAL (Gameplays Largos, Sin Directos y Formato D)
    # -------------------------------------------------------------------------
    def test_gameplay_safety_allows_long_and_blocks_livestreams(self):
        """Acepta gameplays largos (45m) para recorte por sección y bloquea directos 🔴."""
        from src.compliance_auditor import is_safe_rrss_candidate
        safe_long, reason_long, meta = is_safe_rrss_candidate(
            "GTA 6 Gameplay Walkthrough Part 1 - INTRO (PS5 PRO 4K)",
            uploader="GameRiot",
            duration_sec=2990.0,
            allow_long_clipping=True
        )
        self.assertTrue(safe_long, f"Debió aprobar gameplay de 50m con clipping: {reason_long}")
        self.assertEqual(meta.get("recommended_mode"), "gameplay")

        safe_live, reason_live, _ = is_safe_rrss_candidate(
            "🔴 GTA VI GAMEPLAY EN DIRECTO (primeras horas de juego)",
            uploader="Sinapsis",
            duration_sec=0.0,
            allow_long_clipping=True
        )
        self.assertFalse(safe_live, "Debe bloquear emisiones en directo para no colgar yt-dlp")
        self.assertIn("directo", reason_live.lower())

    def test_pure_gameplay_preserves_game_audio_and_uses_preset_d(self):
        """Gameplay real (ej. IGN Primera Misión) conserva audio auténtico y usa Formato D 83.3%."""
        en_dialogue = (
            "Hey Lucia keep your head down while we cross the bridge near Vice Beach, "
            "cops are blocking every exit across Leonida right now."
        )
        srt_file = self._create_synthetic_srt("mission_dialogue.srt", en_dialogue)
        fake_video = self.mock_temp / "ign_mission.mp4"
        fake_video.write_bytes(b"dummy_mp4_bytes")

        captured_render = {}

        def _mock_trans(src, dst, source_lang="en"):
            dst.write_text("1\n00:00:00,500 --> 00:00:02,500\nEh Lucía agacha la cabeza al cruzar el puente.\n\n", encoding="utf-8")
            return True

        def _mock_render(input_video, output_video, **kwargs):
            captured_render.update(kwargs)
            output_video.write_bytes(b"rendered_mp4_data")
            return True

        fake_sub_res = MagicMock(
            stdout="22.0",
            stderr="pts_time: 1.2\npts_time: 5.4\npts_time: 9.8\npts_time: 14.1\n",
            returncode=0
        )

        with patch.object(pl, "TEMP_DIR", self.mock_temp), \
             patch.object(pl, "OUTPUT_DIR", self.mock_output), \
             patch.object(pl, "AUTO_DUB_ENGLISH", True), \
             patch.object(pl, "download_video_and_subtitles", return_value=(fake_video, srt_file, "en")), \
             patch.object(pl, "get_video_dimensions", return_value=(1920, 1080)), \
             patch.object(pl, "detect_horizontal_split_screen", return_value=False), \
             patch.object(pl, "translate_srt", side_effect=_mock_trans), \
             patch.object(pl, "generate_voiceover") as mock_dub, \
             patch.object(pl, "generate_video_metadata", return_value={
                 "title": "PRIMERA MISION GTA 6 EN PS5 PRO",
                 "description": "Gameplay real",
                 "tags": ["GTA6"],
                 "hook": "¡PRIMER GAMEPLAY!"
             }), \
             patch.object(pl, "render_final_video", side_effect=_mock_render), \
             patch.object(pl, "create_video_thumbnail"), \
             patch.object(pl, "clean_temp_directory"), \
             patch.object(pl, "enforce_storage_limits"), \
             patch.object(pl, "mark_video_processed"), \
             patch("src.audio_shield.validate_audio_and_speech_vitality", return_value=(True, "OK", {})), \
             patch("src.telegram_bot.send_telegram_alert"), \
             patch.object(subprocess, "run", return_value=fake_sub_res):

            res = pl.process_single_video(
                url="https://youtube.com/watch?v=3PiR0G3rVw8",
                video_id="3PiR0G3rVw8",
                original_title="GTA 6 PS5 Pro Gameplay - 15 Minutes of The First Mission",
                creator_name="IGN",
                source_lang="en",
                mode="gameplay",
                dry_run=True,
                copilot_mode=False
            )

            self.assertIsNotNone(res)
            self.assertEqual(res["mode"], "subs", "Gameplay con diálogo de misión debe usar subs en ES y audio auténtico")
            mock_dub.assert_not_called()
            self.assertEqual(captured_render.get("format_preset"), "D", "Gameplay real debe usar Formato D 83.3% incluso si viene de IGN")

    def test_early_gameplay_wave_injected_on_nov18(self):
        """Hoy 18-N debe incluir la franja de captura inmediata de gameplay."""
        sched_18 = get_daily_schedule(date(2026, 11, 18))
        ids_18 = [w["id"] for w in sched_18.get("windows", [])]
        self.assertIn("early_gameplay_wave", ids_18)

    def test_chapter_selection_skips_intro_and_picks_action(self):
        """Debe ignorar capítulos de intro/menú y extraer el tramo de persecución policial."""
        from src.downloader import _select_action_chapter_window
        chapters = [
            {"title": "Intro & Settings Menu", "start_time": 0.0, "end_time": 90.0},
            {"title": "Sponsor Message", "start_time": 90.0, "end_time": 140.0},
            {"title": "Vice City Police Chase Combat", "start_time": 140.0, "end_time": 260.0},
            {"title": "Outro & Subscribe", "start_time": 260.0, "end_time": 300.0},
        ]
        win = _select_action_chapter_window(chapters, duration=300.0, target_duration=24)
        self.assertIsNotNone(win)
        self.assertGreaterEqual(win[0], 140.0)
        self.assertLessEqual(win[1], 260.0)
        self.assertGreaterEqual(win[1] - win[0], 18.0)

    def test_clean_title_no_shorts_spam_and_upload_cooldown(self):
        """Los títulos de YouTube no deben llevar #Shorts spam y cooldown debe frenar subidas <45m."""
        meta = generate_video_metadata(
            original_title="GTA 6 Police Chase Free Roam Gameplay PS5 Pro",
            original_url="https://youtube.com/watch?v=9TLwyuGDSmI",
            is_short=True,
            creator_name="GameV"
        )
        self.assertNotIn("#shorts", meta["title"].lower())
        self.assertIn("#shorts", meta["description"].lower())

        import src.uploader as up
        cooldown_tmp = self.mock_temp / "test_cooldown.json"
        with patch.object(up, "UPLOAD_COOLDOWN_FILE", cooldown_tmp):
            up._record_youtube_upload("yt123", meta["title"], "public")
            blocked, reason = up._is_youtube_upload_blocked_by_cooldown("Otro título nuevo de GTA 6", "public")
            self.assertTrue(blocked, "Debe bloquear subidas en menos de 45 minutos")
            self.assertIn("cooldown", reason.lower())

    def test_tiktok_anti_saturation_cooldown(self):
        """TikTok debe respetar el enfriamiento anti-saturación entre subidas consecutivas."""
        import src.social_publisher as sp
        tt_cd = self.mock_temp / "test_tt_cooldown.json"
        with patch.object(sp, "TIKTOK_COOLDOWN_FILE", tt_cd):
            sp._record_tiktok_upload("GTA 6 Gameplay en PS5 Pro")
            blocked, reason = sp._is_tiktok_blocked_by_cooldown(cooldown_minutes=90)
            self.assertTrue(blocked, "Debe espaciar subidas en TikTok <90 min para evitar saturación")
            self.assertIn("tiktok", reason.lower())


if __name__ == "__main__":
    unittest.main()
