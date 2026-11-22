"""
src/community_manager.py — Gestor autónomo de comunidad e interacción con seguidores.

Responde de forma natural, segura y con límite de tasa a comentarios reales
de seguidores en YouTube e Instagram Reels, evitando spam y auto-respuestas.
"""

import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

from .config import BASE_DIR, GEMINI_API_KEY

REPLIED_COMMENTS_FILE = BASE_DIR / "data" / "replied_comments.json"
FOLLOWED_USERS_FILE = BASE_DIR / "data" / "followed_users.json"
BROWSER_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles"
MAX_STORED_REPLIED_IDS = 1000
MAX_STORED_FOLLOWED_IDS = 500

_SPAM_PATTERNS = (
    "http://",
    "https://",
    "www.",
    "t.me/",
    "wa.me/",
    "bit.ly",
    "tinyurl",
    "is.gd",
    "crypto",
    "forex",
    "whatsapp",
    "telegram",
    "onlyfans",
    "sub4sub",
    "check my profile",
    "mira mi perfil",
    "airdrop",
    "nft",
    "trust wallet",
    "dm me",
    "dm for",
    "invest",
    "trading",
    "casino",
    "follow me",
    "sigueme",
    "sígueme",
)

_FALLBACK_REPLIES = [
    # Estructura variada: afirmaciones, preguntas, reacciones cortas
    "¡Totalmente! En Vice City cada detalle cuenta 🔥 ¿Qué es lo que más ganas tienes de probar?",
    "¡Gracias por pasarte, crack! 🙌 ¿Crees que Rockstar superará las expectativas con esto?",
    "¡Buen punto! 👀 Este nivel de detalle en GTA 6 va a dar mucho que hablar en Leonida.",
    "¡Tal cual! 🔥 ¿Tú qué opinas: lo veremos tal cual el día de salida?",
    "Rockstar no para de sorprender con estos detalles 🤯",
    "Leonida va a ser una locura total 🌴",
    "Justo lo que pensaba, esto es otro nivel 👀",
    "Eso mismo digo yo, menudo nivelazo 🔥",
    "GTA 6 tiene pinta de que va a cambiar el juego para siempre 🎮",
    "Qué bueno que alguien más se fijó en esto 👏",
    "Vice City 2.0 va a ser una pasada, ¿no? 🌅",
    "Eso no lo había visto, buen ojo 👁️",
    "Se nota que Rockstar se lo ha currado 💯",
    "Pues sí, esto pinta increíble 🫡",
    "El hype está justificado con estos detalles, la verdad 🚀",
    "Me pregunto qué más tendrán escondido por ahí 🤔",
]


def _load_replied_ids() -> List[str]:
    if not REPLIED_COMMENTS_FILE.exists():
        return []
    try:
        data = json.loads(REPLIED_COMMENTS_FILE.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _save_replied_ids(ids: List[str]) -> None:
    REPLIED_COMMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    trimmed = ids[-MAX_STORED_REPLIED_IDS:]
    REPLIED_COMMENTS_FILE.write_text(
        json.dumps(trimmed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_safe_follower_comment(text: str) -> bool:
    """Filtra comentarios vacíos, spam con enlaces o bots promocionales."""
    cleaned = (text or "").strip()
    if len(cleaned) < 3:
        return False
    low = cleaned.lower()
    return not any(pat in low for pat in _SPAM_PATTERNS)


def generate_community_reply(
    comment_text: str,
    video_title: str = "",
    author_name: str = "",
    platform: str = "youtube",
) -> str:
    """Genera una respuesta breve, cercana y gamer en español usando Gemini con fallback 0-API."""
    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                "Eres el community manager del canal en español 'GTA VI Hub'. "
                f"Un seguidor ({author_name or 'usuario'}) comentó en {platform} "
                f"sobre el vídeo '{video_title[:80]}':\n"
                f"\"{comment_text[:280]}\"\n\n"
                "Responde en español de España/LatAm neutro, tono cercano gamer, "
                "máximo 2 frases cortas (<170 caracteres), incluye 1 emoji relevante y "
                "haz una pregunta breve si encaja para fomentar debate. "
                "Sin hashtags, sin enlaces, sin sonar robótico. Devuelve solo el texto."
            )
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = (getattr(resp, "text", "") or "").strip().strip('"')
            text = re.sub(r"\s+", " ", text)
            if 8 <= len(text) <= 220 and "http" not in text.lower():
                return text
        except Exception:
            pass
    return random.choice(_FALLBACK_REPLIES)


def reply_youtube_comments(max_replies: int = 6) -> Dict[str, Any]:
    """Responde a comentarios recientes sin respuesta en el canal de YouTube."""
    summary: Dict[str, Any] = {"platform": "youtube", "replied": 0, "checked": 0, "errors": []}
    token_extra = BASE_DIR / "token_extra.json"
    token_file = token_extra if token_extra.exists() else (BASE_DIR / "token.json")
    if not token_file.exists():
        return summary

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)

        ch_resp = yt.channels().list(part="id", mine=True).execute()
        items = ch_resp.get("items", [])
        if not items:
            return summary
        my_channel_id = items[0]["id"]

        threads_resp = yt.commentThreads().list(
            part="snippet,replies",
            allThreadsRelatedToChannelId=my_channel_id,
            maxResults=20,
            order="time",
        ).execute()

        replied_list = _load_replied_ids()
        replied_set: Set[str] = set(replied_list)

        for thread in threads_resp.get("items", []):
            if summary["replied"] >= max_replies:
                break
            summary["checked"] += 1
            thread_id = thread.get("id", "")
            key = f"yt:{thread_id}"
            if not thread_id or key in replied_set:
                continue

            top_snippet = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            author_ch = top_snippet.get("authorChannelId", {}).get("value", "")
            if author_ch == my_channel_id:
                continue

            existing_replies = thread.get("replies", {}).get("comments", [])
            already_replied_by_us = any(
                r.get("snippet", {}).get("authorChannelId", {}).get("value") == my_channel_id
                for r in existing_replies
            )
            if already_replied_by_us:
                replied_list.append(key)
                replied_set.add(key)
                continue

            comment_text = top_snippet.get("textDisplay", "") or top_snippet.get("textOriginal", "")
            if not is_safe_follower_comment(comment_text):
                continue

            author_name = top_snippet.get("authorDisplayName", "")
            reply_text = generate_community_reply(
                comment_text=comment_text,
                video_title="Short de GTA 6",
                author_name=author_name,
                platform="YouTube Shorts",
            )

            yt.comments().insert(
                part="snippet",
                body={
                    "snippet": {
                        "parentId": thread_id,
                        "textOriginal": reply_text,
                    }
                },
            ).execute()

            replied_list.append(key)
            replied_set.add(key)
            summary["replied"] += 1
            print(f"[Community YT] Respuesta a {author_name}: {reply_text}")
            time.sleep(random.uniform(1.5, 3.0))

        _save_replied_ids(replied_list)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[Community YT] Aviso: {e}")

    return summary


def reply_instagram_comments(max_replies: int = 4) -> Dict[str, Any]:
    """Da like y responde a comentarios recientes en Instagram Reels."""
    summary: Dict[str, Any] = {"platform": "instagram", "replied": 0, "checked": 0, "errors": []}
    ig_user = os.getenv("INSTAGRAM_USERNAME", "gtavihubextra").strip().lstrip("@")
    session_file = BASE_DIR / "assets" / ".browser_profiles" / f"instagrapi_session_{ig_user}.json"
    if not session_file.exists():
        return summary

    try:
        from instagrapi import Client
        cl = Client()
        cl.load_settings(str(session_file))
        my_pk = str(cl.user_id)

        medias = cl.user_medias(int(my_pk), amount=5)
        replied_list = _load_replied_ids()
        replied_set: Set[str] = set(replied_list)

        for media in medias:
            if summary["replied"] >= max_replies:
                break
            comments = cl.media_comments(media.id, amount=15)
            for c in comments:
                if summary["replied"] >= max_replies:
                    break
                summary["checked"] += 1
                cid = str(getattr(c, "pk", ""))
                key = f"ig:{cid}"
                if not cid or key in replied_set:
                    continue
                c_user = getattr(c, "user", None)
                if c_user and str(getattr(c_user, "pk", "")) == my_pk:
                    continue
                c_text = getattr(c, "text", "") or ""
                if not is_safe_follower_comment(c_text):
                    continue

                author_name = getattr(c_user, "username", "") if c_user else ""
                reply_text = generate_community_reply(
                    comment_text=c_text,
                    video_title=getattr(media, "caption_text", "")[:60],
                    author_name=author_name,
                    platform="Instagram Reels",
                )
                try:
                    cl.comment_like(cid)
                except Exception:
                    pass
                cl.media_comment(media.id, reply_text, replied_to_comment_id=int(cid))
                replied_list.append(key)
                replied_set.add(key)
                summary["replied"] += 1
                print(f"[Community IG] Respuesta a @{author_name}: {reply_text}")
                time.sleep(random.uniform(2.0, 4.0))

        _save_replied_ids(replied_list)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[Community IG] Aviso: {e}")

    return summary


def _load_followed_ids() -> List[str]:
    if not FOLLOWED_USERS_FILE.exists():
        return []
    try:
        data = json.loads(FOLLOWED_USERS_FILE.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _save_followed_ids(ids: List[str]) -> None:
    FOLLOWED_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    trimmed = ids[-MAX_STORED_FOLLOWED_IDS:]
    FOLLOWED_USERS_FILE.write_text(
        json.dumps(trimmed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def followback_instagram_commenters(max_follows: int = 3) -> Dict[str, Any]:
    """
    Follow selectivo de usuarios que comentan en nuestros Reels.
    Solo sigue cuentas reales (>5 posts, >20 followers, no privadas),
    con delays humanos aleatorios para evitar detección.
    """
    summary: Dict[str, Any] = {"platform": "instagram_followback", "followed": 0, "skipped": 0, "errors": []}
    ig_user = os.getenv("INSTAGRAM_USERNAME", "gtavihubextra").strip().lstrip("@")
    session_file = BROWSER_PROFILE_DIR / f"instagrapi_session_{ig_user}.json"
    if not session_file.exists():
        return summary

    try:
        from instagrapi import Client
        cl = Client()
        cl.load_settings(str(session_file))
        my_pk = str(cl.user_id)

        followed_list = _load_followed_ids()
        followed_set: Set[str] = set(followed_list)

        medias = cl.user_medias(int(my_pk), amount=5)
        candidates: List[str] = []

        for media in medias:
            comments = cl.media_comments(media.id, amount=20)
            for c in comments:
                c_user = getattr(c, "user", None)
                if not c_user:
                    continue
                uid = str(getattr(c_user, "pk", ""))
                if uid and uid != my_pk and uid not in followed_set and uid not in candidates:
                    candidates.append(uid)

        random.shuffle(candidates)

        for uid in candidates[:max_follows * 3]:
            if summary["followed"] >= max_follows:
                break
            try:
                info = cl.user_info(int(uid))
                # Filtros anti-bot: cuenta real con actividad mínima
                if info.is_private:
                    summary["skipped"] += 1
                    continue
                if info.media_count < 5:
                    summary["skipped"] += 1
                    continue
                if info.follower_count < 20:
                    summary["skipped"] += 1
                    continue
                # No seguir cuentas masivas (probablemente no recíproco)
                if info.follower_count > 50000:
                    summary["skipped"] += 1
                    continue

                cl.user_follow(int(uid))
                followed_list.append(uid)
                followed_set.add(uid)
                summary["followed"] += 1
                print(f"[Followback IG] Seguido @{info.username} ({info.follower_count} followers)")
                # Delay humano largo entre follows (4-8s) para no saltar alarmas
                time.sleep(random.uniform(4.0, 8.0))

            except Exception as e:
                summary["errors"].append(f"user {uid}: {e}")
                time.sleep(random.uniform(2.0, 4.0))

        _save_followed_ids(followed_list)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[Followback IG] Aviso: {e}")

    return summary


def reply_tiktok_comments(max_replies: int = 3) -> Dict[str, Any]:
    """
    Responde a comentarios en TikTok vía Playwright (TikTok Studio).
    Usa perfil persistente + storage_state.json existente.
    Delays humanos largos (5-10s) entre acciones para evitar detección.
    """
    summary: Dict[str, Any] = {"platform": "tiktok", "replied": 0, "checked": 0, "errors": []}
    tiktok_profile = BROWSER_PROFILE_DIR / "tiktok_user_data"
    storage_state_file = BROWSER_PROFILE_DIR / "storage_state.json"

    if not tiktok_profile.exists() and not storage_state_file.exists():
        return summary

    replied_list = _load_replied_ids()
    replied_set: Set[str] = set(replied_list)

    try:
        from playwright.sync_api import sync_playwright
        headless = os.getenv("HEADLESS_BROWSER", "true").lower() in ("1", "true", "yes")

        with sync_playwright() as p:
            browser = None
            try:
                if tiktok_profile.exists():
                    browser = p.chromium.launch_persistent_context(
                        str(tiktok_profile),
                        headless=headless,
                        args=["--disable-blink-features=AutomationControlled"],
                    )
                    page = browser.new_page()
                elif storage_state_file.exists():
                    b = p.chromium.launch(headless=headless)
                    browser = b
                    page = b.new_page(storage_state=str(storage_state_file))
                else:
                    return summary

                # Navegar a TikTok Studio > Comentarios
                page.goto("https://www.tiktok.com/creator#/comment", wait_until="domcontentloaded", timeout=20000)
                time.sleep(random.uniform(3.0, 5.0))

                # Buscar los contenedores de comentarios
                comment_items = page.query_selector_all('[class*="DivCommentItemWrapper"], [class*="comment-item"]')
                if not comment_items:
                    # Fallback: intentar listado genérico
                    comment_items = page.query_selector_all('[data-e2e="comment-item"]')

                for item in comment_items[:20]:
                    if summary["replied"] >= max_replies:
                        break
                    summary["checked"] += 1

                    try:
                        # Extraer texto del comentario y un ID único
                        text_el = item.query_selector('[class*="comment-text"], [class*="DivCommentText"], p')
                        c_text = text_el.inner_text().strip() if text_el else ""
                        # Usar hash del texto como ID (TikTok no expone IDs en DOM fácilmente)
                        c_hash = f"tk:{hash(c_text) & 0xFFFFFFFF:08x}"

                        if not c_text or c_hash in replied_set or not is_safe_follower_comment(c_text):
                            continue

                        author_el = item.query_selector('[class*="user-name"], [class*="DivUserName"], a[class*="user"]')
                        author_name = author_el.inner_text().strip() if author_el else ""

                        reply_text = generate_community_reply(
                            comment_text=c_text,
                            video_title="Short de GTA 6",
                            author_name=author_name,
                            platform="TikTok",
                        )

                        # Click en botón de responder
                        reply_btn = item.query_selector('[class*="reply"], button[class*="Reply"]')
                        if not reply_btn:
                            continue
                        reply_btn.click()
                        time.sleep(random.uniform(1.0, 2.0))

                        # Escribir la respuesta en el input que aparece
                        reply_input = page.query_selector(
                            '[class*="DivReplyInput"] [contenteditable], '
                            '[class*="reply-input"] textarea, '
                            '[data-e2e="comment-input"] [contenteditable]'
                        )
                        if not reply_input:
                            continue
                        reply_input.click()
                        time.sleep(random.uniform(0.3, 0.7))
                        reply_input.type(reply_text, delay=random.randint(30, 80))
                        time.sleep(random.uniform(0.5, 1.0))

                        # Enviar con Enter o botón Post
                        send_btn = page.query_selector(
                            '[class*="DivPostButton"], button[class*="post-btn"], '
                            '[data-e2e="comment-post"]'
                        )
                        if send_btn:
                            send_btn.click()
                        else:
                            reply_input.press("Enter")

                        replied_list.append(c_hash)
                        replied_set.add(c_hash)
                        summary["replied"] += 1
                        print(f"[Community TK] Respuesta a @{author_name}: {reply_text}")
                        # Delay humano largo entre respuestas (5-10s)
                        time.sleep(random.uniform(5.0, 10.0))

                    except Exception as e:
                        summary["errors"].append(f"comment: {e}")

            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass

    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[Community TK] Aviso: {e}")

    _save_replied_ids(replied_list)
    return summary


COMMENT_INSIGHTS_FILE = BASE_DIR / "data" / "comment_insights.json"

# Temas que los viewers mencionan → señal de demanda de contenido
_INSIGHT_TOPICS = {
    "tips_guias": ["tip", "tips", "guide", "guia", "guía", "how to", "como", "cómo", "donde", "where"],
    "armas": ["arma", "weapon", "gun", "pistol", "rifle", "escopeta", "legendaria", "legendary"],
    "coches": ["coche", "car", "vehicle", "vehiculo", "moto", "bike", "mclaren", "lambo"],
    "mapa": ["mapa", "map", "ubicacion", "ubicación", "location", "leonida", "vice city", "zona"],
    "misiones": ["mision", "misión", "mission", "historia", "story", "prologo", "prólogo"],
    "policia": ["policia", "policía", "police", "persecucion", "chase", "estrella", "wanted"],
    "secretos": ["secreto", "secret", "easter egg", "oculto", "hidden", "detalle"],
    "dinero": ["dinero", "money", "cash", "millones", "grind", "farm"],
    "mas_contenido": ["mas", "más", "more", "sigue", "keep", "continue", "otro", "another"],
    "comparativa": ["comparativa", "comparison", "vs", "ps5", "xbox", "fps", "grafico"],
}


def extract_comment_insights(max_comments: int = 50) -> Dict[str, Any]:
    """
    Analiza los comentarios recientes del canal para extraer temas demandados.
    Usa keyword matching (0 coste API). Persiste en data/comment_insights.json.
    """
    token_extra = BASE_DIR / "token_extra.json"
    token_file = token_extra if token_extra.exists() else (BASE_DIR / "token.json")
    if not token_file.exists():
        return {"ok": False, "reason": "No token.json"}

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)

        ch_resp = yt.channels().list(part="id", mine=True).execute()
        items = ch_resp.get("items", [])
        if not items:
            return {"ok": False, "reason": "No channel found"}
        my_channel_id = items[0]["id"]

        threads_resp = yt.commentThreads().list(
            part="snippet",
            allThreadsRelatedToChannelId=my_channel_id,
            maxResults=min(max_comments, 100),
            order="time",
        ).execute()

        # Contar menciones de temas
        topic_counts: Dict[str, int] = {t: 0 for t in _INSIGHT_TOPICS}
        total_comments = 0
        sample_requests: List[str] = []

        for thread in threads_resp.get("items", []):
            snippet = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = (snippet.get("textDisplay", "") or "").lower()
            if not text or len(text) < 5:
                continue
            total_comments += 1

            for topic, keywords in _INSIGHT_TOPICS.items():
                if any(kw in text for kw in keywords):
                    topic_counts[topic] += 1

            # Detectar peticiones directas
            if any(w in text for w in ["haz", "hace", "make", "quiero ver", "want to see", "puedes", "podrias", "podrías"]):
                sample_requests.append(text[:100])

        # Ordenar por demanda
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        top_demanded = [t for t, c in sorted_topics if c > 0]

        result = {
            "ok": True,
            "analyzed_at": datetime.now().isoformat(),
            "total_comments": total_comments,
            "topic_demand": {t: c for t, c in sorted_topics if c > 0},
            "top_demanded_topics": top_demanded[:5],
            "sample_requests": sample_requests[:5],
        }

        # Persistir
        COMMENT_INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        COMMENT_INSIGHTS_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Community Insights] Analizados {total_comments} comentarios. Top demanda: {top_demanded[:3]}")
        return result

    except Exception as e:
        print(f"[Community Insights] Error: {e}")
        return {"ok": False, "reason": str(e)}


X_ENGAGEMENT_FILE = BASE_DIR / "data" / "x_engagement.json"
X_FOLLOWED_FILE = BASE_DIR / "data" / "x_followed_users.json"

# Cuentas GTA6 de referencia para buscar contenido relevante y hacer engagement
X_GTA6_CREATORS = [
    "GTA6Intel", "GTAVInewz", "GTAVI_Countdown", "RockstarGames",
    "GTA6News_", "GTASeries", "TezFunz2", "GTA6Videos",
]

MAX_X_LIKES_PER_DAY = int(os.getenv("MAX_X_LIKES_PER_DAY", "20"))
MAX_X_FOLLOWS_PER_DAY = int(os.getenv("MAX_X_FOLLOWS_PER_DAY", "10"))


def _load_x_engagement_state() -> Dict[str, Any]:
    if not X_ENGAGEMENT_FILE.exists():
        return {"today_date": "", "likes_today": 0, "follows_today": 0}
    try:
        return json.loads(X_ENGAGEMENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"today_date": "", "likes_today": 0, "follows_today": 0}


def _save_x_engagement_state(state: Dict[str, Any]) -> None:
    X_ENGAGEMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    X_ENGAGEMENT_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_x_followed_ids() -> List[str]:
    if not X_FOLLOWED_FILE.exists():
        return []
    try:
        data = json.loads(X_FOLLOWED_FILE.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _save_x_followed_ids(ids: List[str]) -> None:
    X_FOLLOWED_FILE.parent.mkdir(parents=True, exist_ok=True)
    trimmed = ids[-MAX_STORED_FOLLOWED_IDS:]
    X_FOLLOWED_FILE.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_x_browser_context():
    """Crea un contexto de Playwright con la sesion persistente de X."""
    from playwright.sync_api import sync_playwright
    browser_profile_dir = BASE_DIR / "assets" / ".browser_profiles"
    x_storage_state = browser_profile_dir / "x_storage_state.json"
    x_profile = browser_profile_dir / "x_user_data"

    headless = os.getenv("HEADLESS_BROWSER", "false").lower() in ["true", "1", "yes"]

    pw = sync_playwright().start()
    if x_storage_state.exists():
        raw_browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = raw_browser.new_context(
            storage_state=str(x_storage_state),
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1280, "height": 900},
        )
        return pw, raw_browser, ctx
    elif x_profile.exists():
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(x_profile),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1280, "height": 900},
        )
        return pw, None, ctx
    else:
        pw.stop()
        raise FileNotFoundError("No hay sesion de X configurada. Ejecuta scripts/setup_x_session.py primero.")


def like_relevant_gta6_tweets(max_likes: int = 10) -> Dict[str, Any]:
    """
    Da like a tweets recientes de creadores GTA6 de referencia.
    Conservador: max 20 likes/dia con delays humanos largos.
    """
    summary: Dict[str, Any] = {"platform": "x_likes", "liked": 0, "skipped": 0, "errors": []}
    today_str = datetime.now().strftime("%Y-%m-%d")
    state = _load_x_engagement_state()
    if state.get("today_date") != today_str:
        state = {"today_date": today_str, "likes_today": 0, "follows_today": 0}
    if state["likes_today"] >= MAX_X_LIKES_PER_DAY:
        print(f"[X Engagement] Limite diario de likes alcanzado ({MAX_X_LIKES_PER_DAY}).")
        return summary

    remaining_likes = min(max_likes, MAX_X_LIKES_PER_DAY - state["likes_today"])

    try:
        pw, raw_browser, ctx = _get_x_browser_context()
    except (ImportError, FileNotFoundError) as e:
        summary["errors"].append(str(e))
        return summary

    try:
        page = ctx.new_page()
        # Buscar tweets GTA6 recientes
        page.goto("https://x.com/search?q=GTA%206%20OR%20GTA6%20OR%20%22Grand%20Theft%20Auto%206%22&src=typed_query&f=live", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3.0, 5.0))

        if "login" in page.url.lower():
            summary["errors"].append("Sesion de X caducada")
            return summary

        # Buscar botones de like en los tweets visibles
        like_buttons = page.locator('[data-testid="like"]')
        count = like_buttons.count()

        for i in range(min(count, remaining_likes * 2)):
            if summary["liked"] >= remaining_likes:
                break
            try:
                btn = like_buttons.nth(i)
                if btn.is_visible():
                    btn.click()
                    summary["liked"] += 1
                    state["likes_today"] += 1
                    print(f"[X Engagement] Like #{summary['liked']} dado.")
                    time.sleep(random.uniform(3.0, 8.0))
            except Exception:
                summary["skipped"] += 1
                time.sleep(random.uniform(1.0, 3.0))

        _save_x_engagement_state(state)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[X Engagement] Error en likes: {e}")
    finally:
        try:
            ctx.close()
            if raw_browser:
                raw_browser.close()
            pw.stop()
        except Exception:
            pass

    return summary


def follow_gta6_creators(max_follows: int = 5) -> Dict[str, Any]:
    """
    Sigue cuentas relevantes del nicho GTA6 en X.
    Conservador: max 10 follows/dia con delays humanos.
    """
    summary: Dict[str, Any] = {"platform": "x_follows", "followed": 0, "skipped": 0, "errors": []}
    today_str = datetime.now().strftime("%Y-%m-%d")
    state = _load_x_engagement_state()
    if state.get("today_date") != today_str:
        state = {"today_date": today_str, "likes_today": 0, "follows_today": 0}
    if state["follows_today"] >= MAX_X_FOLLOWS_PER_DAY:
        print(f"[X Engagement] Limite diario de follows alcanzado ({MAX_X_FOLLOWS_PER_DAY}).")
        return summary

    remaining_follows = min(max_follows, MAX_X_FOLLOWS_PER_DAY - state["follows_today"])
    followed_list = _load_x_followed_ids()
    followed_set: Set[str] = set(followed_list)

    try:
        pw, raw_browser, ctx = _get_x_browser_context()
    except (ImportError, FileNotFoundError) as e:
        summary["errors"].append(str(e))
        return summary

    try:
        page = ctx.new_page()
        # Buscar creadores GTA6 en la busqueda de personas
        page.goto("https://x.com/search?q=GTA%206%20gaming&src=typed_query&f=user", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3.0, 5.0))

        if "login" in page.url.lower():
            summary["errors"].append("Sesion de X caducada")
            return summary

        # Buscar botones de follow
        follow_buttons = page.locator('[data-testid$="-follow"]')
        count = follow_buttons.count()

        for i in range(min(count, remaining_follows * 3)):
            if summary["followed"] >= remaining_follows:
                break
            try:
                btn = follow_buttons.nth(i)
                # Extraer username del contenedor padre
                parent = btn.locator("xpath=ancestor::div[@data-testid='UserCell']")
                username_el = parent.locator("a[href^='/']").first
                username = ""
                if username_el.count() > 0:
                    href = username_el.get_attribute("href") or ""
                    username = href.strip("/").lower()

                if username in followed_set or not username:
                    summary["skipped"] += 1
                    continue

                if btn.is_visible():
                    btn.click()
                    summary["followed"] += 1
                    state["follows_today"] += 1
                    followed_list.append(username)
                    followed_set.add(username)
                    print(f"[X Engagement] Seguido @{username}")
                    time.sleep(random.uniform(5.0, 10.0))
            except Exception:
                summary["skipped"] += 1
                time.sleep(random.uniform(2.0, 4.0))

        _save_x_engagement_state(state)
        _save_x_followed_ids(followed_list)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[X Engagement] Error en follows: {e}")
    finally:
        try:
            ctx.close()
            if raw_browser:
                raw_browser.close()
            pw.stop()
        except Exception:
            pass

    return summary


def followback_x_followers(max_follows: int = 5) -> Dict[str, Any]:
    """
    Sigue de vuelta a nuevos seguidores en X que no estamos siguiendo.
    Conservador con delays humanos para evitar restricciones en cuenta nueva.
    """
    summary: Dict[str, Any] = {"platform": "x_followback", "followed": 0, "skipped": 0, "errors": []}
    today_str = datetime.now().strftime("%Y-%m-%d")
    state = _load_x_engagement_state()
    if state.get("today_date") != today_str:
        state = {"today_date": today_str, "likes_today": 0, "follows_today": 0}
    if state["follows_today"] >= MAX_X_FOLLOWS_PER_DAY:
        return summary

    remaining = min(max_follows, MAX_X_FOLLOWS_PER_DAY - state["follows_today"])
    x_handle = os.getenv("X_USERNAME", "gtavihubextra").strip().lstrip("@")

    try:
        pw, raw_browser, ctx = _get_x_browser_context()
    except (ImportError, FileNotFoundError) as e:
        summary["errors"].append(str(e))
        return summary

    try:
        page = ctx.new_page()
        page.goto(f"https://x.com/{x_handle}/followers", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3.0, 5.0))

        if "login" in page.url.lower():
            summary["errors"].append("Sesion de X caducada")
            return summary

        # Buscar botones "Follow" (no "Following") en la lista de seguidores
        follow_buttons = page.locator('[data-testid$="-follow"]')
        count = follow_buttons.count()

        for i in range(min(count, remaining * 2)):
            if summary["followed"] >= remaining:
                break
            try:
                btn = follow_buttons.nth(i)
                # Solo procesar botones que dicen "Follow" (no "Following")
                btn_text = (btn.inner_text() or "").strip().lower()
                if btn_text in ("following", "siguiendo"):
                    continue
                if btn.is_visible():
                    btn.click()
                    summary["followed"] += 1
                    state["follows_today"] += 1
                    print(f"[X Followback] Followback #{summary['followed']}")
                    time.sleep(random.uniform(5.0, 10.0))
            except Exception:
                summary["skipped"] += 1
                time.sleep(random.uniform(2.0, 4.0))

        _save_x_engagement_state(state)
    except Exception as e:
        summary["errors"].append(str(e))
        print(f"[X Followback] Error: {e}")
    finally:
        try:
            ctx.close()
            if raw_browser:
                raw_browser.close()
            pw.stop()
        except Exception:
            pass

    return summary


def run_x_engagement_cycle(
    max_likes: int = 10, max_follows: int = 5, max_followbacks: int = 3,
) -> Dict[str, Any]:
    """Ejecuta un ciclo completo de engagement en X/Twitter."""
    likes_res = like_relevant_gta6_tweets(max_likes=max_likes)
    follows_res = follow_gta6_creators(max_follows=max_follows)
    followback_res = followback_x_followers(max_follows=max_followbacks)
    return {
        "x_likes": likes_res,
        "x_follows": follows_res,
        "x_followback": followback_res,
        "total_x_likes": likes_res["liked"],
        "total_x_follows": follows_res["followed"] + followback_res["followed"],
    }


def run_autonomous_community_cycle(
    yt_max: int = 6, ig_max: int = 4,
    tk_max: int = 3, ig_followback_max: int = 3,
    x_likes_max: int = 10, x_follows_max: int = 5,
) -> Dict[str, Any]:
    """Ejecuta un ciclo completo de interacción autónoma con seguidores."""
    yt_res = reply_youtube_comments(max_replies=yt_max)
    ig_res = reply_instagram_comments(max_replies=ig_max)
    tk_res = reply_tiktok_comments(max_replies=tk_max)
    fb_res = followback_instagram_commenters(max_follows=ig_followback_max)

    # Engagement en X/Twitter (likes, follows, followbacks)
    x_res: Dict[str, Any] = {"total_x_likes": 0, "total_x_follows": 0}
    try:
        x_res = run_x_engagement_cycle(
            max_likes=x_likes_max, max_follows=x_follows_max, max_followbacks=3,
        )
    except Exception as e:
        print(f"[X Engagement] Info: {e}")

    # Extraer insights de comentarios tras responder (aprovecha la API ya autenticada)
    insights = {}
    try:
        insights = extract_comment_insights(max_comments=50)
    except Exception:
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "youtube": yt_res,
        "instagram": ig_res,
        "tiktok": tk_res,
        "instagram_followback": fb_res,
        "x_engagement": x_res,
        "total_replied": yt_res["replied"] + ig_res["replied"] + tk_res["replied"],
        "total_followed": fb_res["followed"] + x_res.get("total_x_follows", 0),
        "total_x_likes": x_res.get("total_x_likes", 0),
        "comment_insights": insights,
    }
