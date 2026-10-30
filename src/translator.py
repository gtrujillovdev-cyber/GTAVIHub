import re
import shutil
from pathlib import Path
from typing import Optional, Dict
from google import genai
from .config import GEMINI_API_KEY, GEMINI_MODEL, BUSINESS_EMAIL, MONETIZATION_AFFILIATE_URL

_client = None

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

def clean_srt_response(text: str) -> str:
    """Elimina delimitadores markdown si el modelo los devuelve."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()

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

    # Si ya está en español, copia directa intacta sin alterar nada
    if source_lang == "es":
        print(f"[*] El contenido ya está en español. Saltando traducción...")
        shutil.copyfile(input_srt_path, output_srt_path)
        return True

    with open(input_srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        print("[!] El archivo SRT está vacío.")
        return False

    client = get_gemini_client()

    prompt = (
        "Eres un traductor y guionista experto en la saga Grand Theft Auto (GTA VI), videojuegos y viralidad en Shorts.\n"
        "Traduce y adapta el siguiente archivo de subtítulos en formato SRT al español.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Conserva EXACTAMENTE la estructura de bloques numéricos y marcas de tiempo (ej. 00:00:01,200 --> 00:00:03,500).\n"
        "2. Traduce y sintetiza únicamente las líneas de texto hablado.\n"
        "3. Usa un español dinámico, fresco y actual (apto para YouTube Shorts / TikTok).\n"
        "4. Respeta nombres canónicos (Vice City, Lucia, Jason, Leonida, Rockstar Games, etc.).\n"
        "5. Devuelve ÚNICAMENTE el texto SRT resultante, sin explicaciones ni bloques markdown extra."
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{prompt}\n\n{content}"
        )
        translated_srt = clean_srt_response(response.text)

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(translated_srt)

        print(f"[✓] Subtítulos traducidos con éxito -> {output_srt_path.name}")
        return True
    except Exception as e:
        print(f"[!] Error traduciendo subtítulos con Gemini: {e}")
        print("[*] Fallback de seguridad: conservando subtítulos originales para mantener el karaoke dinámico...")
        try:
            shutil.copyfile(input_srt_path, output_srt_path)
            return True
        except Exception as copy_err:
            print(f"[!] Error en fallback de subtítulos: {copy_err}")
            return False

def generate_video_metadata(
    original_title: str,
    original_url: str = "",
    is_short: bool = False,
    creator_name: str = "",
    source_lang: str = "en"
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

    context_phase = (
        "FASE: LANZAMIENTO OFICIAL & GAMEPLAY REAL (GTA 6 ya está disponible). "
        "Enfócate en jugabilidad real, misiones, mundo abierto de Vice City, persecuciones policiales, físicas extremas, "
        "reacciones en directo de streamers y momentos graciosos o impactantes."
        if is_launched else
        "FASE: PRE-LANZAMIENTO. Enfócate en novedades, comparativas, filtraciones reales y anticipación de GTA 6."
    )

    prompt = f"""Actúa como el mejor estratega de YouTube Gaming y viralidad en español.
Estamos analizando contenido sobre Grand Theft Auto VI (GTA 6).
{context_phase}
Tipo de formato: {tipo}.
Título original: "{original_title}"
Creador/Fuente original: "{creator_name or 'Rockstar Games'}"

{playbook_rules}

Usa terminología del GLOSARIO OFICIAL Y VIRAL DE GTA 6 cuando sea pertinente:
- Protagonistas: Lucía (primera protagonista femenina), Jason (pareja criminal), Stefanie (consejera), Mud Girl, Florida Joker.
- Ubicaciones de Leonida: Vice City, Port Gellhorn, Ocean Drive, Grassrivers (Everglades), Los Cayos (Keys), Vice Beach.
- Físicas & Jugabilidad: Físicas de agua realistas, IA de peatones/multitudes, motor RAGE 9, sistema de saqueo, animaciones al agacharse, interiores explorables, atracos a restaurantes, caimanes.
- Gameplay & Reacciones: Misiones, tiroteos, conducción, persecuciones 5 estrellas, easter eggs, streamers jugando en directo.

Tu tarea es ADAPTAR EL TONO Y FORMATO AL CONTENIDO REAL:
1. "archetype": Clasifica el contenido exactamente en uno de estos 6 arquetipos:
   - "humor_parodia" (parodias como South Park, sketches, memes, risas, situaciones absurdas)
   - "analisis_tecnico" (físicas de agua/vehículos, motor RAGE 9, gráficos, comparativas de frames/resolución)
   - "filtracion_misterio" (secretos del mapa, easter eggs, patentes, archivos ocultos)
   - "noticia_oficial" (comunicados de Rockstar, trailers, fechas oficiales, novedades de Take-Two)
   - "reaccion_streamer" (momentos de streamers, hype, sorpresa o incredulidad en directo)
   - "gameplay_puro" (misiones, persecuciones policiales, tiroteos, mundo abierto)
2. "viral_title": Un título ULTRA LLAMATIVO completamente en MAYÚSCULAS con emojis acordes al arquetipo y etiqueta #GTA6 (máx 80 caracteres). El tono debe adaptarse: cómico para parodias, riguroso/asombro para técnica, misterio para filtraciones, épico para noticias. REGLA DE ORO: Jamás uses palabras como 'CONCEPTO', 'CGI', 'FAN-MADE' o 'UNREAL ENGINE'.
3. "summary": Un resumen apasionante de 2 párrafos en español explicando qué ocurre en el clip y por qué la comunidad de GTA 6 está reaccionando.
4. "hook": Una frase o pregunta corta de MÁXIMA INTRIGA O SINTONÍA CON EL ARQUETIPO para los primeros 2 segundos (máx 4-5 palabras en MAYÚSCULAS, máx 24 caracteres) para la píldora superior.
5. "debate_question": Una pregunta directa, polarizante y picante para la comunidad adaptada al arquetipo que genere aluvión de comentarios en los primeros minutos.

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
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        cleaned = clean_srt_response(response.text)
        import json
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

    # Asegurar que el título siempre esté en mayúsculas y bien formateado
    if not viral_title:
        viral_title = f"¡IMPACTANTE! 😱 DETALLES DE GTA 6: {original_title[:40].upper()} #GTA6"
    else:
        viral_title = viral_title.upper()

    # Ensamblar descripción PROGRAMÁTICAMENTE (garantiza cero placeholders y cumplimiento legal)
    url_line = f"🔗 Vídeo Original: {original_url}\n" if original_url else ""
    creator_line = f"👤 Creador / Fuente Original: {creator_name}\n" if creator_name else "👤 Fuente Original: Rockstar Games\n"

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
        from .affiliates import format_description_affiliate_block, format_pinned_comment_affiliates
        affiliate_block = format_description_affiliate_block()
        pinned_comment = format_pinned_comment_affiliates(debate_question)
    except Exception as e:
        affiliate_block = (
            f"🎮 {to_unicode_bold('RESERVA OFICIAL GTA VI & ACCESORIOS:')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 Reserva oficial garantizada y mejores ofertas de consolas PS5 / Xbox:\n"
            f"{MONETIZATION_AFFILIATE_URL}"
        )
        pinned_comment = (
            f"🌴 💬 {to_unicode_bold('DEBATE GTA 6:')}\n"
            f"{debate_question}\n"
            f"👇 ¡Déjanos tu teoría en los comentarios!\n\n"
            f"🌐 𝗧𝗢𝗗𝗔𝗦 𝗡𝗨𝗘𝗦𝗧𝗥𝗔𝗦 𝗥𝗘𝗗𝗘𝗦 👉 https://linktr.ee/gtavihubspain\n"
            f"🎮 𝗥𝗘𝗦𝗘𝗥𝗩𝗔 𝗢𝗙𝗜𝗖𝗜𝗔𝗟 𝗚𝗧𝗔 𝟲 👉 {MONETIZATION_AFFILIATE_URL}\n"
            f"📩 Contacto Business: {BUSINESS_EMAIL}"
        )

    full_description = f"""{summary}

💬 {to_unicode_bold("DEBATE DE LA COMUNIDAD:")}
{debate_question}
👇 ¿Cuál es tu teoría? ¡Te leemos en los comentarios!

🌴 {to_unicode_bold("GTA VI HUB ESPAÑA | REDES OFICIALES:")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 Hub Central & Enlaces: https://linktr.ee/gtavihubspain
🎬 TikTok Oficial: https://tiktok.com/@gtavihubspain
📸 Instagram Reels: https://instagram.com/gtavihubspain
🔴 Suscríbete al Canal: https://youtube.com/@GTAVIHubSpain?sub_confirmation=1

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

    return {
        "title": viral_title[:100],
        "description": full_description[:5000],
        "hook": hook,
        "debate_question": debate_question,
        "pinned_comment": pinned_comment,
        "archetype": archetype
    }
