import re
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Tuple
from google import genai
from .config import GEMINI_API_KEY, GEMINI_MODEL, BUSINESS_EMAIL, MONETIZATION_AFFILIATE_URL

_client = None

FALLBACK_GEMINI_MODELS = list(dict.fromkeys([
    GEMINI_MODEL,
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]))

def generate_content_with_retry(client, contents, models=None):
    """Ejecuta generate_content con rotación automática a modelos Flash-Lite si hay límite 429 de cuota."""
    if models is None:
        models = FALLBACK_GEMINI_MODELS
    last_err = None
    for model_name in models:
        try:
            return client.models.generate_content(model=model_name, contents=contents)
        except Exception as e:
            last_err = e
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "404" in err_msg or "503" in err_msg:
                print(f"[*] Modelo '{model_name}' con limitación ({err_msg[:45]}...). Rotando a modelo alternativo...")
                continue
            raise e
    raise last_err

def to_unicode_bold(text: str) -> str:
    """
    Convierte texto alfanumérico ASCII a caracteres Unicode Mathematical Sans-Serif Bold.
    Permite resaltar títulos, preguntas de debate y llamadas a la acción directamente
    en descripciones, comentarios de YouTube, TikTok y pies de foto de Instagram sin usar Markdown.
    """
    res = []
    for ch in text:
        code = ord(ch)
        if 65 <= code <= 90:  # A-Z
            res.append(chr(0x1D5D4 + (code - 65)))
        elif 97 <= code <= 122:  # a-z
            res.append(chr(0x1D5EE + (code - 97)))
        elif 48 <= code <= 57:  # 0-9
            res.append(chr(0x1D7EC + (code - 48)))
        else:
            res.append(ch)
    return "".join(res)

def get_gemini_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY no está configurada en .env")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

AUDIO_TAG_REGEX = re.compile(
    r"\[(?i:music|música|musica|applause|aplausos|cheering|laughter|risas|sound|audio|gasp|sigh|cough|groan|screaming|bell|siren|silence|whispering|instrumental|intro music|outro music|background music|noise)[^\]]*\]|"
    r"\((?i:music|música|musica|applause|laughter|risas|sound)[^\)]*\)|"
    r"\[[\w\s\.\,\-\'\"]*\]",
    re.UNICODE
)

ASR_HALLUCINATIONS = re.compile(
    r"(?i)\b(video game|tornado police car|tornado, coche de policía|coche de policía|police siren|sound effect)\b[\.\,\:]?",
    re.UNICODE
)

def purge_audio_descriptors(text: str) -> str:
    """
    Elimina etiquetas de efectos sonoros de YouTube ASR ([music], [música], etc.)
    y descripciones acústicas automáticas para que el guion hablado y los subtítulos
    sean 100% narración humana natural y fluida.
    """
    cleaned = AUDIO_TAG_REGEX.sub("", text)
    cleaned = ASR_HALLUCINATIONS.sub("", cleaned)
    return " ".join(cleaned.split()).strip()

def clean_srt_response(text: str) -> str:
    """Elimina delimitadores markdown si el modelo los devuelve y purga etiquetas de sonido."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()

def sanitize_srt_content(srt_text: str) -> str:
    """Limpia línea por línea el contenido de un SRT purgando etiquetas acústicas."""
    lines = srt_text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Si es número de índice o línea de tiempo '-->', mantener intacta
        if re.match(r"^\d+$", stripped) or "-->" in stripped:
            cleaned_lines.append(line)
        else:
            purged = purge_audio_descriptors(line)
            cleaned_lines.append(purged)
    return "\n".join(cleaned_lines)

def translate_srt(
    input_srt_path: Path,
    output_srt_path: Path,
    source_lang: str = "en"
) -> bool:
    """
    Traduce un archivo SRT al español si viene de inglés, o lo copia/limpia
    directamente si ya está en español (ahorrando tiempo y tokens).
    """
    if not input_srt_path.exists():
        print(f"[!] No existe el archivo SRT: {input_srt_path}")
        return False

    # Si ya está en español, copia directa limpia sin alterar nada
    if source_lang == "es":
        print(f"[*] El contenido ya está en español. Limpiando y preparando...")
        with open(input_srt_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_es = f.read()
        cleaned_es = sanitize_srt_content(raw_es)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(cleaned_es)
        return True

    with open(input_srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        print("[!] El archivo SRT está vacío.")
        return False

    # Purgar previamente tags de sonido en el contenido antes de enviarlo a la IA
    sanitized_input = sanitize_srt_content(content)
    try:
        from .downloader import deroll_and_clean_srt_content
        sanitized_input = deroll_and_clean_srt_content(sanitized_input)
    except Exception:
        pass

    client = get_gemini_client()

    prompt = (
        "Eres un traductor y guionista experto en la saga Grand Theft Auto (GTA VI), videojuegos y viralidad en Shorts.\n"
        "Traduce y adapta el siguiente archivo de subtítulos en formato SRT al español.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Conserva EXACTAMENTE la estructura de bloques numéricos y marcas de tiempo (ej. 00:00:01,200 --> 00:00:03,500).\n"
        "2. ELIMINA TOTALMENTE cualquier etiqueta de sonido, efecto acústico o música entre corchetes o paréntesis (ej. [music], [música], [applause], [sound]), así como descriptores de escena generados por error de reconocimiento de voz (ej. 'police siren', 'tornado police car', 'video game').\n"
        "3. Traduce ÚNICAMENTE el diálogo y la narración real hablada. Debe sonar como una locución humana impecable, natural y fluida, perfectamente concebida para ser doblada por voz en off en español.\n"
        "4. Si un bloque contenía únicamente música o un efecto sonoro, déjalo con texto en blanco para no generar subtítulos ni locución artificial sobre la música.\n"
        "5. Traduce y sintetiza de forma concisa y directa para que encaje con el ritmo de locución original (evita rodeos que alarguen artificialmente la frase).\n"
        "6. Usa un español dinámico, fresco y actual (apto para YouTube Shorts / TikTok).\n"
        "7. Respeta nombres canónicos (Vice City, Lucia, Jason, Leonida, Rockstar Games, etc.).\n"
        "8. CERO TARTAMUDEO / CERO REPETICIÓN: Los subtítulos de entrada pueden contener líneas rodantes o correcciones de YouTube ASR. NUNCA repitas una misma frase o cláusula dos veces consecutivas. Traduce la idea una sola vez con fluidez profesional continua.\n"
        "9. Devuelve ÚNICAMENTE el texto SRT resultante, sin explicaciones ni bloques markdown extra."
    )

    try:
        response = generate_content_with_retry(
            client=client,
            contents=f"{prompt}\n\n{sanitized_input}"
        )
        translated_srt = clean_srt_response(response.text)
        translated_srt = sanitize_srt_content(translated_srt)
        try:
            from .downloader import deroll_and_clean_srt_content
            translated_srt = deroll_and_clean_srt_content(translated_srt)
        except Exception:
            pass

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(translated_srt)

        print(f"[✓] Subtítulos traducidos con éxito -> {output_srt_path.name}")
        return True
    except Exception as e:
        print(f"[!] Error traduciendo subtítulos con Gemini: {e}")
        # Si el idioma de origen no es español, no podemos pretender que los subtítulos en inglés son españoles
        return False

def transcribe_and_translate_audio_gemini(
    audio_path: Path,
    output_srt_path: Path,
    target_lang: str = "es"
) -> Tuple[bool, bool]:
    """
    Transcribe un archivo de audio en cualquier idioma (especialmente inglés)
    y lo traduce directamente al español generando un archivo SRT sincronizado
    y desduplicado apto para subtítulos dinámicos y doblaje neural con Gemini Flash.

    Retorna: (éxito: bool, tiene_voz_humana: bool)
    - Si detecta solo sonido de juego/físicas/música sin narrador: (True, False).
    - Si detecta y traduce locución humana con cues válidos: (True, True).
    - Si ocurre un error irrecuperable: (False, False).
    """
    if not audio_path or not audio_path.exists():
        print(f"[!] Archivo de audio para transcribir no existe: {audio_path}")
        return False, False

    try:
        from google.genai import types
        client = get_gemini_client()

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        if len(audio_bytes) < 1000:
            print("[*] Archivo de audio casi vacío (<1KB). Sin voz perceptible.")
            return True, False

        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type="audio/mp3"
        )

        prompt = (
            "Eres un transcriptor y subtitulador profesional especializado en contenido viral de videojuegos y GTA 6 para YouTube Shorts, TikTok y Reels.\n"
            "Escucha atentamente el audio adjunto:\n\n"
            "1. Si el audio contiene ÚNICAMENTE efectos de sonido (ruido de coches, disparos, explosiones, música de fondo o silencio) y NO hay ninguna persona hablando, responde EXACTAMENTE y ÚNICAMENTE con la palabra: NO_SPEECH.\n\n"
            "2. Si el audio contiene voz humana, diálogo, comentarios o narración (incluso en inglés o cualquier otro idioma):\n"
            "   - Transcribe cada frase y TRADÚCELA directamente al español (España / neutro) de forma natural, dinámica y con gancho.\n"
            "   - Genera un archivo con formato estándar SubRip (.srt) con numeración secuencial (1, 2, 3...) y marcas de tiempo exactas (00:00:01,200 --> 00:00:03,800).\n"
            "   - Mantén cada bloque de subtítulo muy conciso: entre 2 y 5 palabras por bloque para un ritmo dinámico de lectura.\n"
            "   - Elimina cualquier muletilla, tartamudeo o etiqueta de sonido como [música], [risas], etc.\n"
            "   - Respeta nombres canónicos de GTA 6 (Lucia, Jason, Vice City, Leonida, Rockstar Games).\n"
            "   - Devuelve ÚNICAMENTE el texto SRT puro, sin explicaciones ni bloques de código markdown extra (sin ```srt)."
        )

        print("[*] Enviando audio a Gemini Flash para transcripción y traducción al español...")
        response = generate_content_with_retry(
            client=client,
            contents=[audio_part, prompt]
        )

        resp_text = (response.text or "").strip()
        if "NO_SPEECH" in resp_text.upper():
            print("[*] Gemini Flash determinó que el clip no contiene narración o voz humana (solo sonido de juego/ambiente).")
            return True, False

        cleaned_srt = clean_srt_response(resp_text)
        cleaned_srt = sanitize_srt_content(cleaned_srt)
        try:
            from .downloader import deroll_and_clean_srt_content
            cleaned_srt = deroll_and_clean_srt_content(cleaned_srt)
        except Exception:
            pass

        # Verificar que el SRT tiene al menos un cue válido
        if "-->" not in cleaned_srt:
            print("[*] La respuesta de Gemini no contiene marcas de tiempo SRT válidas.")
            return True, False

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(cleaned_srt)

        print(f"[✓] Transcripción y traducción de audio generada con éxito -> {output_srt_path.name}")
        return True, True
    except Exception as e:
        print(f"[!] Error transcribiendo/traduciendo audio con Gemini Flash: {e}")
        return False, False

def generate_video_metadata(
    original_title: str,
    original_url: str = "",
    is_short: bool = False,
    creator_name: str = "",
    source_lang: str = "en",
    clip_transcript: str = ""
) -> Dict[str, str]:
    """
    Genera metadatos profesionales de alto impacto para YouTube siguiendo
    las últimas tendencias de YouTube Gaming / GTA 6:
    - Título TODO EN MAYÚSCULAS con ganchos psicológicos (CTR alto).
    - Gancho superior de intriga (0-2.5s).
    - Pregunta polarizante de debate para multiplicar comentarios en los primeros 30 min.
    - Descripción ensamblada programáticamente con créditos exactos y Fair Use.
    """
    client = get_gemini_client()
    tipo = "un YouTube Short vertical de máximo impacto" if is_short else "un vídeo de YouTube Gaming"

    from .config import is_gameplay_enabled
    is_launched = is_gameplay_enabled()

    try:
        from .learning_engine import get_playbook_context_for_prompt
        playbook_rules = get_playbook_context_for_prompt()
    except Exception:
        playbook_rules = ""

    clean_excerpt = ""
    if clip_transcript:
        excerpt_lines = [
            ln.strip() for ln in clip_transcript.splitlines()
            if ln.strip() and not ln.strip().isdigit() and "-->" not in ln
        ]
        clean_excerpt = " ".join(excerpt_lines)[:550].strip()

    clip_context_block = (
        f'\nCONTENIDO REAL HABLADO EN ESTE FRAGMENTO RECORTADO:\n"{clean_excerpt}"\n'
        f'(MUY IMPORTANTE: El "viral_title", "hook" y "debate_question" DEBEN reflejar específicamente lo que se dice/muestra en este fragmento concreto, no generalidades vagas del vídeo completo).\n'
        if clean_excerpt else ""
    )

    context_phase = (
        "FASE: LANZAMIENTO OFICIAL & GAMEPLAY REAL (GTA 6 ya está disponible). "
        "Enfócate estrictamente en el tema REAL descrito en el Título Original y en el fragmento recortado."
        if is_launched else
        "FASE: PRE-LANZAMIENTO. Enfócate estrictamente en el tema REAL descrito en el Título Original."
    )

    prompt = f"""Actúa como el mejor estratega de YouTube Gaming y viralidad en español.
Estamos analizando contenido sobre Grand Theft Auto VI (GTA 6).
{context_phase}
Tipo de formato: {tipo}.
Título original: "{original_title}"
Creador/Fuente original: "{creator_name or 'Rockstar Games'}"
{clip_context_block}
{playbook_rules}

REGLA ESTRICTA ANTI-ALUCINACIÓN Y GRAMÁTICA PERFECTA:
- Basa el título, resumen, hook y pregunta de debate EXCLUSIVAMENTE en el tema real del Título Original ("{original_title}") y su fragmento hablado.
- PROHIBIDO inventar elementos que NO aparecen (no inventes streamers, persecuciones policiales, atracos ni caimanes si el clip trata sobre FPS, tanques de agua, radios o comparativas).
- Cuida la ortografía, los géneros ("la pre-descarga", nunca "el pre-descarga") y la concordancia gramatical en español. Jamás uses 'CONCEPTO', 'CGI', 'FAN-MADE' o 'UNREAL ENGINE'.

Tu tarea es ADAPTAR EL TONO Y FORMATO AL CONTENIDO REAL:
1. "archetype": Clasifica el contenido exactamente en uno de estos 6 arquetipos:
   - "humor_parodia" (parodias, sketches, humor)
   - "analisis_tecnico" (físicas RAGE 9, gráficos, comparativas técnicas, iluminación, FPS)
   - "filtracion_misterio" (secretos del mapa, easter eggs, detalles ocultos)
   - "noticia_oficial" (comunicados de Rockstar, capturas oficiales, portadas, fechas)
   - "reaccion_streamer" (momentos de streamers)
   - "gameplay_puro" (misiones, jugabilidad real, capturas in-game, mundo abierto)
2. "viral_title": Un título ULTRA LLAMATIVO en ESPAÑOL completamente en MAYÚSCULAS acorde al clip real, con emojis y #GTA6 (máx 78 caracteres).
3. "summary": Un resumen apasionante de 2 párrafos en español fiel al contenido real del vídeo.
4. "hook": Titular visual en ESPAÑOL de 2 líneas cortas separado por '\\n' (máx 18 chars por línea, en MAYÚSCULAS, SIN '¿' ni '?') que revele EL DATO CONCRETO del clip en los primeros segundos (ej. "GTA 6 A 30 FPS\\nINCLUSO EN PS5 PRO" o "PRE-CARGA ACTIVA\\nYA SE DESCARGA"). PROHIBIDO hooks genéricos vacíos como "IMPRESIONANTE" o "GRÁFICOS TOP".
5. "debate_question": Una pregunta directa para comentarios sobre este tema específico.

Devuelve tu respuesta EXACTAMENTE en este formato JSON (sin texto extra):
{{
  "archetype": "humor_parodia | analisis_tecnico | filtracion_misterio | noticia_oficial | reaccion_streamer | gameplay_puro",
  "viral_title": "TITULO EN MAYUSCULAS CON EMOJIS Y #GTA6",
  "summary": "Resumen en español...",
  "hook": "GANCHO EN MAYUSCULAS",
  "debate_question": "¿Pregunta de debate polarizante para comentarios? 👇"
}}
"""
    try:
        response = generate_content_with_retry(
            client=client,
            contents=prompt
        )
        cleaned = clean_srt_response(response.text)
        data = json.loads(cleaned)
        archetype = data.get("archetype", "filtracion_misterio").strip().lower()
        viral_title = data.get("viral_title", "").strip().upper()
        summary = data.get("summary", "").strip()
        hook = data.get("hook", "¡INCREÍBLE!").strip().upper()
        debate_question = data.get("debate_question", "¿Qué opinas tú de esta filtración de GTA 6? ¡Te leemos abajo! 👇").strip()
    except Exception as e:
        print(f"[Warning] Error consultando IA para metadatos: {e}")
        # Inferencia heurística de arquetipo si falla la IA
        orig_lower = (original_title or "").lower()
        if any(k in orig_lower for k in ["south park", "parodia", "meme", "sketch", "fails", "humor"]):
            archetype = "humor_parodia"
            fallback_hook = "¡NO PUEDE SER! 😂"
        elif any(k in orig_lower for k in ["físicas", "fisicas", "motor", "rage", "gráfico", "grafico", "digital foundry"]):
            archetype = "analisis_tecnico"
            fallback_hook = "¡FÍSICAS NUNCA VISTAS! 🌊"
        elif any(k in orig_lower for k in ["trailer", "tráiler", "oficial", "rockstar", "comunicado"]):
            archetype = "noticia_oficial"
            fallback_hook = "¡ANUNCIO OFICIAL! 🔥"
        elif any(k in orig_lower for k in ["ibai", "xokas", "rubius", "knekro", "reaccion", "reacción"]):
            archetype = "reaccion_streamer"
            fallback_hook = "¡REACCIÓN BRUTAL! 😱"
        else:
            archetype = "gameplay_puro" if is_launched else "filtracion_misterio"
            fallback_hook = "¡GAMEPLAY BRUTAL!" if is_launched else "¡DETALLE ÉPICO!"
        viral_title = f"¡BRUTAL! 🔥 MOMENTO ÉPICO EN GTA 6: {original_title[:40].upper()} #GTA6" if is_launched else f"¡BRUTAL! 🔥 REACCIÓN Y ANÁLISIS DE GTA 6: {original_title[:40].upper()} #GTA6"
        summary = f"Cobertura y mejores momentos de Grand Theft Auto VI a partir del contenido de {creator_name or 'la comunidad'}."
        hook = fallback_hook
        debate_question = "¿Qué os parece este gameplay de GTA 6? ¿Cumple con lo esperado? ¡Comenta abajo! 👇" if is_launched else "¿Crees que GTA 6 cumplirá todas las expectativas? ¡Comenta abajo! 👇"

    # Asegurar que el título siempre esté en mayúsculas y contenga #Shorts para el crawler
    if not viral_title:
        viral_title = f"¡IMPACTANTE! 😱 DETALLES DE GTA 6: {original_title[:40].upper()} #GTA6 #Shorts"
    else:
        viral_title = viral_title.upper()
        if "#SHORTS" not in viral_title and len(viral_title) <= 90:
            viral_title = f"{viral_title} #Shorts"

    # Desduplicación Estricta de Títulos (Anti-Spam Shield: CERO títulos repetidos)
    try:
        from .config import PROCESSED_FILE
        if PROCESSED_FILE.exists():
            with open(PROCESSED_FILE, "r", encoding="utf-8") as pf:
                recent_processed = json.load(pf)
                recent_titles = [
                    v.get("youtube_title", "").upper().replace("#SHORTS", "").replace("#GTA6", "").strip()
                    for v in recent_processed[-30:]
                    if v.get("youtube_title")
                ]
                clean_candidate = viral_title.upper().replace("#SHORTS", "").replace("#GTA6", "").strip()
                if clean_candidate in recent_titles or any(len(clean_candidate) > 12 and clean_candidate == t for t in recent_titles):
                    print(f"[Anti-Duplicate] Título '{viral_title}' ya publicado en los últimos 30 clips. Diferenciando variante...")
                    short_tag = re.sub(r'[^A-Z0-9 ]', '', original_title.upper()).strip()
                    short_tag = short_tag.split()[0] if short_tag else "NUEVO"
                    base_vt = viral_title.replace("#SHORTS", "").strip()
                    viral_title = f"{base_vt} ({short_tag}) #Shorts"
    except Exception as e:
        print(f"[Anti-Duplicate] Nota: {e}")

    # Ensamblar descripción PROGRAMÁTICAMENTE (garantiza cero placeholders y cumplimiento legal)
    creator_clean = creator_name or "Rockstar Games"
    url_line = f"🔗 Vídeo Original: {original_url}\n" if original_url else ""
    creator_line = f"👤 Creador / Fuente Original: {creator_clean}\n"

    # Detección de música del tráiler de GTA 6
    is_trailer_content = any(k in original_title.lower() for k in ["trailer", "tráiler", "rockstar", "official"])
    if is_trailer_content:
        music_disclaimer = (
            "🎵 CRÉDITOS DE LA MÚSICA:\n"
            "- Canción: 'Love Is a Long Road'\n"
            "- Artista: Tom Petty (Álbum: Full Moon Fever, 1989)\n"
            "- Compositores: Tom Petty, Mike Campbell\n"
            "- Sello / Licencias: Geffen Records / Universal Music Group (UMG).\n"
            "Todos los derechos fonográficos y de autor pertenecen a sus legítimos propietarios.\n"
        )
    else:
        music_disclaimer = (
            "🎵 MÚSICA Y AUDIO:\n"
            "Pistas musicales y efectos pertenecen a sus respectivos autores y licenciatarios de YouTube Audio Library / Take-Two Interactive.\n"
        )

    try:
        from .affiliates import (
            format_description_affiliate_block,
            format_pinned_comment_affiliates,
            format_pinned_comment_clean,
            is_affiliates_enabled
        )
        if is_affiliates_enabled():
            affiliate_block = format_description_affiliate_block()
            pinned_comment = format_pinned_comment_affiliates(debate_question)
        else:
            affiliate_block = ""
            pinned_comment = format_pinned_comment_clean(debate_question)
    except Exception as e:
        affiliate_block = ""
        pinned_comment = f"🌴 💬 DEBATE GTA 6:\n{debate_question}\n👇 ¡Déjanos tu teoría en los comentarios!"

    if is_short:
        # Formato optimizado para YouTube Shorts: limpio, natural y libre de spam de enlaces
        # (Las ofertas y enlaces de afiliados se ubican en el COMENTARIO FIJADO para no disparar el filtro anti-spam)
        short_summary = summary[:600].rsplit(".", 1)[0] + "." if len(summary) > 600 else summary
        full_description = f"""{short_summary}

💬 {to_unicode_bold("DEBATE:")} {debate_question}

📌 Creador / Fuente: {creator_clean}
🔗 Original: {original_url}

⚖️ Uso Legítimo / Fair Use (Art. 107 Copyright Act) con fines informativos y comentario para la comunidad hispanohablante.
📩 Contacto: {BUSINESS_EMAIL}

#GTA6 #GTAVI #RockstarGames #Gaming #Shorts
"""
    else:
        full_description = f"""{summary}

💬 {to_unicode_bold("DEBATE DE LA COMUNIDAD:")}
{debate_question}
👇 ¿Cuál es tu teoría? ¡Te leemos en los comentarios!

🌴 {to_unicode_bold("GTA VI HUB EXTRA | REDES OFICIALES:")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 Hub Central & Enlaces: https://linktr.ee/gtavihubextra
🎬 TikTok Oficial: https://tiktok.com/@gtavihubextra
📸 Instagram Reels: https://instagram.com/gtavihubextra
🔴 Suscríbete al Canal: https://youtube.com/@GTAVIHubExtra?sub_confirmation=1

{affiliate_block}

📌 {to_unicode_bold("CRÉDITOS DEL AUTOR & FUENTE OFICIAL:")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{creator_line}{url_line}
Todo el reconocimiento al creador original por su excelente cobertura. ¡Apoya el canal original en el enlace superior!

💼 {to_unicode_bold("CONTACTO COMERCIAL & COPYRIGHT:")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📩 Email de contacto / Business: {BUSINESS_EMAIL}
🛡️ Retirada inmediata o atribución personalizada: Si eres el autor o titular de derechos y deseas alguna modificación o retirada amistosa, contáctanos a nuestro email y atenderemos tu solicitud en menos de 2 horas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{music_disclaimer}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚖️ {to_unicode_bold("AVISO LEGAL & USO LEGÍTIMO (FAIR USE):")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Este vídeo contiene material transformado con fines estrictamente informativos, de divulgación comunitaria, comentario crítico y traducción para la comunidad hispanohablante.

De conformidad con el Artículo 107 de la Ley de Propiedad Intelectual (Copyright Act de 1976 / Doctrina de 'Fair Use'), se autoriza el uso de material protegido por derechos de autor con fines de crítica, comentarios, noticias, enseñanza y análisis. 

Grand Theft Auto VI, GTA VI, Vice City y los logotipos asociados son marcas registradas de Rockstar Games y Take-Two Interactive Software, Inc. Ninguna infracción de derechos es pretendida.

#GTA6 #GrandTheftAutoVI #RockstarGames #GTAVI #ViceCity #Gaming #Shorts #Videojuegos
"""

    # Tags dinámicos: base común + específicos por archetype para mejorar indexación SEO
    base_tags = ["GTA 6", "GTA VI", "Grand Theft Auto VI", "Rockstar Games", "Vice City", "Gaming"]
    if is_short:
        base_tags.append("Shorts")
    archetype_tags = {
        "humor_parodia": ["GTA 6 Memes", "GTA 6 Divertido", "Parodia GTA 6", "South Park GTA"],
        "analisis_tecnico": ["RAGE 9", "Físicas GTA 6", "Gráficos GTA 6", "Digital Foundry", "PS5 Pro"],
        "filtracion_misterio": ["GTA 6 Secretos", "Easter Eggs GTA 6", "Mapa GTA 6", "Leonida"],
        "noticia_oficial": ["GTA 6 Noticias", "Tráiler GTA 6", "Rockstar Anuncio", "GTA 6 Fecha"],
        "reaccion_streamer": ["Reacciones GTA 6", "Streamers GTA 6", "Gameplay en Vivo"],
        "gameplay_puro": ["GTA 6 Gameplay", "Misiones GTA 6", "Tiroteos GTA 6", "Mundo Abierto"],
    }
    entity_tags = []
    title_lower = (original_title or "").lower()
    if any(k in title_lower for k in ["lucia", "lucía"]):
        entity_tags.append("Lucia GTA 6")
    if "jason" in title_lower:
        entity_tags.append("Jason GTA 6")
    if any(k in title_lower for k in ["vice city", "leonida"]):
        entity_tags.append("Leonida")
    tags = base_tags + archetype_tags.get(archetype, ["GTA 6 Viral"]) + entity_tags

    return {
        "title": viral_title[:100],
        "description": full_description[:5000],
        "hook": hook,
        "debate_question": debate_question,
        "pinned_comment": pinned_comment,
        "archetype": archetype,
        "tags": tags
    }


def generate_editorial_commentary_srt(
    video_path: Path,
    original_title: str,
    creator_name: str,
    output_srt: Path,
    duration_sec: float = 30.0
) -> bool:
    """
    Para clips visuales puros de gameplay/capturas sin narración hablada (ej. comparativas o galerías 4K),
    extrae 3 fotogramas clave y usa Gemini Flash multimodal para redactar un comentario analítico original
    en español sincronizado en bloques SRT cortos (0.4s hasta fin del clip).
    Aporta valor editorial real bajo Fair Use en lugar de publicar metraje sin voz.
    """
    import subprocess
    if not video_path or not video_path.exists():
        return False

    extracted_frames = []
    try:
        from google.genai import types
        client = get_gemini_client()

        eff_dur = max(12.0, min(float(duration_sec or 28.0), 45.0))
        sample_times = [max(0.5, eff_dur * 0.15), eff_dur * 0.50, max(1.0, eff_dur * 0.80)]
        contents = []

        for idx, t in enumerate(sample_times):
            tmp_jpg = video_path.parent / f"_editorial_frame_{video_path.stem}_{idx}.jpg"
            cmd = [
                "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
                "-vframes", "1", "-q:v", "4", "-vf", "scale=720:-1", str(tmp_jpg)
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and tmp_jpg.exists():
                extracted_frames.append(tmp_jpg)
                contents.append(types.Part.from_bytes(data=tmp_jpg.read_bytes(), mime_type="image/jpeg"))

        target_speech_end = round(min(eff_dur - 1.5, 26.0), 1)
        prompt = (
            f"Eres el presentador y analista técnico experto en Rockstar Games de 'GTA VI Hub Extra'.\n"
            f"Estás viendo fotogramas reales de un clip de gameplay/imágenes de '{original_title}' (créditos a {creator_name}).\n"
            f"Duración del clip: {eff_dur:.1f} segundos.\n\n"
            f"TAREA:\n"
            f"Redacta un comentario editorial original, informativo y con alto gancho de retención en ESPAÑOL para locutarlo sobre estas imágenes.\n"
            f"- Describe lo que realmente se ve en las escenas y analiza su iluminación, detalles gráficos o ambientación en Vice City / Leonida (SIN inventar historias falsas de streamers ni mentir sobre lo que aparece en pantalla).\n"
            f"- Empieza en 00:00:00,400 con un gancho potente en la primera frase.\n"
            f"- Distribuye entre 6 y 9 bloques SRT desde 00:00:00,400 hasta 00:00:{int(target_speech_end):02d},000 (aprox 3-5 palabras por bloque, lectura natural y ágil ~2.5 palabras/segundo).\n"
            f"- Formato ESTRICTO SubRip (.srt) puro (1, 2, 3... con 'HH:MM:SS,mmm --> HH:MM:SS,mmm').\n"
            f"- Devuelve ÚNICAMENTE el texto SRT puro, sin markdown (```) ni comentarios."
        )
        contents.append(prompt)

        print(f"[*] Generando guion de análisis original en español para metraje visual ({len(extracted_frames)} frames)...")
        response = generate_content_with_retry(client=client, contents=contents)
        cleaned = clean_srt_response(response.text or "")
        cleaned = sanitize_srt_content(cleaned)

        if not cleaned or "-->" not in cleaned:
            return False

        output_srt.write_text(cleaned.strip() + "\n", encoding="utf-8")
        print(f"[✓] Guion editorial SRT generado con éxito -> {output_srt.name}")
        return True
    except Exception as e:
        print(f"[Warning] No se pudo generar comentario editorial visual: {e}")
        return False
    finally:
        for f in extracted_frames:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
