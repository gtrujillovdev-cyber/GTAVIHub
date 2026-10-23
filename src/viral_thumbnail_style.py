"""
Analizador de estilo de miniaturas virales para GTA 6.

Flujo:
1. Busca los 10 vídeos más virales de GTA 6 en YouTube (última semana).
2. Descarga sus miniaturas.
3. Las analiza con Gemini Vision para extraer parámetros de estilo dominante.
4. Guarda el perfil en data/thumbnail_style.json (cache 24h).

El thumbnail_generator.py consume este perfil para adaptar su estilo
automáticamente a las tendencias del momento.
"""

import json
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from .config import BASE_DIR

STYLE_CACHE_FILE = BASE_DIR / "data" / "thumbnail_style.json"
STYLE_CACHE_HOURS = 24

DEFAULT_STYLE: Dict[str, Any] = {
    "last_updated": None,
    "saturation": 1.35,
    "contrast": 1.25,
    "brightness": 1.05,
    "top_bar": False,
    "bottom_gradient": True,
    "text_hook": True,
    "text_color": [255, 230, 0],
    "text_stroke": [0, 0, 0],
    "text_stroke_width": 6,
    "font_size_ratio": 0.07,
    "color_tone": "neon_miami",
    "vignette_alpha": 120,
    "analysis_source": "default",
}


def _load_cached_style() -> Optional[Dict[str, Any]]:
    if not STYLE_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(STYLE_CACHE_FILE.read_text())
        last = data.get("last_updated")
        if last:
            age = datetime.now() - datetime.fromisoformat(last)
            if age < timedelta(hours=STYLE_CACHE_HOURS):
                return data
    except Exception:
        pass
    return None


def _save_style(style: Dict[str, Any]) -> None:
    STYLE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    style["last_updated"] = datetime.now().isoformat()
    STYLE_CACHE_FILE.write_text(json.dumps(style, indent=2, ensure_ascii=False))


def _analyze_with_gemini(thumbnail_urls: list) -> Dict[str, Any]:
    """Usa Gemini Vision para analizar el estilo dominante de las miniaturas virales."""
    try:
        import google.generativeai as genai
        import os, base64

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return {}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Descargar y codificar miniaturas (máx 5)
        parts = []
        for url in thumbnail_urls[:5]:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    img_bytes = r.read()
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(img_bytes).decode()
                    }
                })
            except Exception:
                continue

        if not parts:
            return {}

        prompt = (
            "Analiza estas miniaturas de YouTube de vídeos virales de GTA 6. "
            "Identifica el estilo visual dominante y responde SOLO con un JSON con estos campos:\n"
            "{\n"
            '  "saturation": <float 1.0-1.8>,\n'
            '  "contrast": <float 1.0-1.5>,\n'
            '  "brightness": <float 0.9-1.2>,\n'
            '  "text_color": [R, G, B],\n'
            '  "text_stroke": [R, G, B],\n'
            '  "text_stroke_width": <int 3-12>,\n'
            '  "font_size_ratio": <float 0.05-0.12>,\n'
            '  "bottom_gradient": <bool>,\n'
            '  "vignette_alpha": <int 60-180>,\n'
            '  "color_tone": "<neon_miami|dark_cinematic|bright_pop|orange_fire>"\n'
            "}"
        )

        response = model.generate_content([prompt] + parts)
        raw = response.text.strip()
        # Extraer JSON del texto
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(raw[start:end])
            parsed["analysis_source"] = "gemini_vision"
            return parsed
    except Exception as e:
        print(f"[ViralStyle] Error en análisis Gemini: {e}")
    return {}


def _fetch_viral_thumbnails() -> list:
    """Obtiene las URLs de las miniaturas de los vídeos más virales de GTA 6."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_file = BASE_DIR / "token.json"
        if not token_file.exists():
            return []

        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        yt = build("youtube", "v3", credentials=creds)
        resp = yt.search().list(
            q="GTA 6 Shorts",
            part="snippet",
            type="video",
            order="viewCount",
            publishedAfter=(datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            maxResults=10,
            videoDuration="short",
            regionCode="ES"
        ).execute()

        urls = []
        for item in resp.get("items", []):
            thumbs = item["snippet"].get("thumbnails", {})
            url = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium", {})).get("url")
            if url:
                urls.append(url)
        return urls
    except Exception as e:
        print(f"[ViralStyle] Error obteniendo miniaturas virales: {e}")
        return []


def get_viral_style() -> Dict[str, Any]:
    """
    Devuelve el perfil de estilo viral activo.
    Usa la cache si es reciente (< 24h), si no, analiza y actualiza.
    """
    cached = _load_cached_style()
    if cached:
        age_h = (datetime.now() - datetime.fromisoformat(cached["last_updated"])).seconds // 3600
        print(f"[ViralStyle] Usando perfil cacheado ({age_h}h de antiguedad): {cached.get('color_tone','?')}")
        return cached

    print("[ViralStyle] Cache expirada — analizando tendencias virales actuales...")
    urls = _fetch_viral_thumbnails()
    style = DEFAULT_STYLE.copy()

    if urls:
        analyzed = _analyze_with_gemini(urls)
        if analyzed:
            style.update(analyzed)
            print(f"[ViralStyle] Perfil actualizado por Gemini Vision: {style.get('color_tone','?')}")
        else:
            print("[ViralStyle] Gemini no disponible — usando perfil neon_miami por defecto")
    else:
        print("[ViralStyle] Sin miniaturas virales encontradas — perfil por defecto")

    _save_style(style)
    return style
