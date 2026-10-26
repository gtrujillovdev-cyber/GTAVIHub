import re
import shutil
from pathlib import Path
from typing import Optional, Dict
from google import genai
from .config import GEMINI_API_KEY, GEMINI_MODEL, BUSINESS_EMAIL, MONETIZATION_AFFILIATE_URL

_client = None

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
    source_lang: str = "en",
    enable_seamless_loop: bool = False
) -> bool:
    """
    Traduce un archivo SRT al español si viene de inglés, o lo copia/limpia
    directamente si ya está en español (ahorrando tiempo y tokens).
    Si enable_seamless_loop=True, formula la frase final para conectar con el inicio.
    """
    if not input_srt_path.exists():
        print(f"[!] No existe el archivo SRT: {input_srt_path}")
        return False

    # Si ya está en español y no requiere bucle, copia directa
    if source_lang == "es" and not enable_seamless_loop:
        print(f"[*] El contenido ya está en español. Saltando traducción...")
        shutil.copyfile(input_srt_path, output_srt_path)
        return True

    with open(input_srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        print("[!] El archivo SRT está vacío.")
        return False

    client = get_gemini_client()

    loop_rule = ""
    if enable_seamless_loop:
        loop_rule = (
            "6. BUCLE INFINITO (SEAMLESS LOOP): Adapta la última frase del subtítulo para que quede como una frase abierta "
            "o intrigante que conecte de forma natural e imperceptible con la primera frase del vídeo al reiniciar la reproducción.\n"
        )

    prompt = (
        "Eres un traductor y guionista experto en la saga Grand Theft Auto (GTA VI), videojuegos y viralidad en Shorts.\n"
        "Traduce y adapta el siguiente archivo de subtítulos en formato SRT al español.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Conserva EXACTAMENTE la estructura de bloques numéricos y marcas de tiempo (ej. 00:00:01,200 --> 00:00:03,500).\n"
        "2. Traduce y sintetiza únicamente las líneas de texto hablado.\n"
        "3. Usa un español dinámico, fresco y actual (apto para YouTube Shorts / TikTok).\n"
        "4. Respeta nombres canónicos (Vice City, Lucia, Jason, Leonida, Rockstar Games, etc.).\n"
        f"{loop_rule}"
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
    source_lang: str = "en",
    enable_seamless_loop: bool = False
) -> Dict[str, str]:
    """
    Genera metadatos profesionales de alto impacto para YouTube siguiendo
    las últimas tendencias de YouTube Gaming / GTA 6:
    - Título TODO EN MAYÚSCULAS con ganchos psicológicos (CTR alto).
    - Gancho superior de intriga (0-2.5s).
    - Pregunta polarizante de debate para multiplicar comentarios en los primeros 30 min.
    - Soporte de Bucle Infinito (Seamless Loop) en 2 de cada 5 vídeos.
    - Descripción ensamblada programáticamente con créditos exactos y Fair Use.
    """
    client = get_gemini_client()
    tipo = "un YouTube Short vertical de máximo impacto" if is_short else "un vídeo de YouTube Gaming"
    
    loop_prompt_extra = ""
    if enable_seamless_loop:
        loop_prompt_extra = (
            "\nIMPORTANTE BUCLE INFINITO: Como este vídeo está configurado para bucle continuo, "
            "diseña el 'hook' inicial de modo que cuando el espectador llegue al final del vídeo y vuelva a empezar, "
            "la transición sea un bucle de curiosidad invisible y adictivo."
        )

    prompt = f"""Actúa como el mejor estratega de YouTube Gaming y viralidad en español.
Estamos analizando contenido sobre Grand Theft Auto VI (GTA 6).
Tipo de formato: {tipo}.
Título original: "{original_title}"
Creador/Fuente original: "{creator_name or 'Rockstar Games'}"{loop_prompt_extra}

Usa terminología del GLOSARIO OFICIAL Y VIRAL DE GTA 6 cuando sea pertinente:
- Protagonistas: Lucía (primera protagonista femenina), Jason (pareja criminal), Stefanie (consejera), Mud Girl, Florida Joker.
- Ubicaciones de Leonida: Vice City, Port Gellhorn, Ocean Drive, Grassrivers (Everglades), Los Cayos (Keys), Vice Beach.
- Físicas & Jugabilidad: Físicas de agua realistas, IA de peatones/multitudes, motor RAGE 9, sistema de saqueo, animaciones al agacharse, interiores explorables, atracos a restaurantes, caimanes.
- Expectación: Tráiler 1, Tráiler 2, Easter eggs, comparativa GTA 5 vs GTA 6, vida real vs Vice City.

Tu tarea es generar:
1. "viral_title": Un título ULTRA LLAMATIVO completamente en MAYÚSCULAS con emojis gaming y etiqueta #GTA6 (máx 80 caracteres). Debe apelar a la curiosidad, misterio o impacto extremo (ej: "¡NO PUEDE SER! 😱 REVELAN SECRETOS DE GTA 6 [DETALLES BRUTALES] 🔥🌴 #GTA6"). REGLA DE ORO: Jamás uses palabras como 'CONCEPTO', 'CGI', 'FAN-MADE' o 'UNREAL ENGINE'. Enfócate en filtraciones, secretos, comparativas y jugabilidad real.
2. "summary": Un resumen apasionante de 2 párrafos en español explicando qué ocurre en el vídeo, teorías y por qué la comunidad de GTA está impactada.
3. "hook": Una frase o pregunta corta de MÁXIMA INTRIGA O POLÉMICA para los primeros 2 segundos (máx 4-5 palabras en MAYÚSCULAS) para evitar que deslicen la pantalla (ej: "¿NOTASTE ESTE SECRETO? 🤯", "¿POR QUÉ OCULTARON ESTO? 🚨", "¡ESTO CAMBIA TODO! 🔥", "EL DETALLE QUE NADIE VIO 😱").
4. "debate_question": Una pregunta directa, polarizante y picante para la comunidad que genere un aluvión de comentarios inmediatos (ej: "¿Creéis que Lucía traicionará a Jason al final del juego o será al revés?", "¿Preferís 60 FPS estables o gráficos ultra a 30 FPS en PS5?").

Devuelve tu respuesta EXACTAMENTE en este formato JSON (sin texto extra):
{{
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
        viral_title = data.get("viral_title", "").strip().upper()
        summary = data.get("summary", "").strip()
        hook = data.get("hook", "¡INCREÍBLE!").strip().upper()
        debate_question = data.get("debate_question", "¿Qué opinas tú de esta filtración de GTA 6? ¡Te leemos abajo! 👇").strip()
    except Exception as e:
        print(f"[Warning] Error consultando IA para metadatos: {e}")
        viral_title = f"¡BRUTAL! 🔥 REACCIÓN Y ANÁLISIS DE GTA 6: {original_title[:40].upper()} #GTA6"
        summary = f"Análisis y cobertura exclusiva de las novedades y detalles de Grand Theft Auto VI a partir del material de {creator_name or 'la comunidad'}."
        hook = "¡NUEVO LEAK!"
        debate_question = "¿Crees que GTA 6 cumplirá todas las expectativas o habrá decepción? ¡Comenta abajo! 👇"

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

    full_description = f"""{summary}

💬 DEBATE DE LA COMUNIDAD:
{debate_question}

🔔 ¡SUSCRÍBETE a GTA VI Hub España para no perderte ninguna noticia, tráiler y filtración del juego más esperado de la historia!

═══════════════════════════════════════
🎮 RESERVA OFICIAL GTA VI & ACCESORIOS RECOMENDADOS:
═══════════════════════════════════════
👉 Consigue las mejores ofertas de consolas PS5/Xbox y reserva de GTA VI aquí:
{MONETIZATION_AFFILIATE_URL}

═══════════════════════════════════════
📌 CRÉDITOS DEL CONTENIDO ORIGINAL:
═══════════════════════════════════════
{creator_line}{url_line}
Todo el reconocimiento a los creadores originales por su gran trabajo. ¡Apoya el canal original en el enlace superior!

═══════════════════════════════════════
💼 CONTACTO COMERCIAL Y RETIRADA DE CONTENIDO:
═══════════════════════════════════════
📩 Email de contacto / Business: {BUSINESS_EMAIL}
🛡️ Retirada inmediata de contenido / Copyright inquiry:
Si eres el autor o propietario de algún fragmento y deseas su retirada o modificación, por favor escríbenos al email arriba indicado y lo resolveremos inmediatamente de forma amistosa en menos de 2 horas.

═══════════════════════════════════════
{music_disclaimer}
═══════════════════════════════════════
⚖️ AVISO LEGAL Y USO LEGÍTIMO (FAIR USE):
═══════════════════════════════════════
Este vídeo contiene material transformado con fines estrictamente informativos, de divulgación comunitaria, comentario crítico y traducción para la comunidad hispanohablante.

De conformidad con el Artículo 107 de la Ley de Propiedad Intelectual (Copyright Act de 1976 / Doctrina de 'Fair Use'), se autoriza el uso de material protegido por derechos de autor con fines de crítica, comentarios, noticias, enseñanza y análisis. 

Grand Theft Auto VI, GTA VI, Vice City y los logotipos asociados son marcas registradas de Rockstar Games y Take-Two Interactive Software, Inc. Ninguna infracción de derechos es pretendida.

#GTA6 #GrandTheftAutoVI #RockstarGames #GTAVI #ViceCity #Gaming #Shorts #Videojuegos
"""

    pinned_comment = (
        f"🌴 {debate_question}\n¡Déjanos tu teoría en los comentarios! 👇\n\n"
        f"🎮 Reserva oficial de GTA VI y accesorios gaming recomendados 👉 {MONETIZATION_AFFILIATE_URL}\n"
        f"📩 Contacto comercial / Colaboraciones: {BUSINESS_EMAIL}"
    )

    return {
        "title": viral_title[:100],
        "description": full_description[:5000],
        "hook": hook,
        "debate_question": debate_question,
        "pinned_comment": pinned_comment
    }
