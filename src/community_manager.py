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


def run_autonomous_community_cycle(
    yt_max: int = 6, ig_max: int = 4,
    tk_max: int = 3, ig_followback_max: int = 3,
) -> Dict[str, Any]:
    """Ejecuta un ciclo completo de interacción autónoma con seguidores."""
    yt_res = reply_youtube_comments(max_replies=yt_max)
    ig_res = reply_instagram_comments(max_replies=ig_max)
    tk_res = reply_tiktok_comments(max_replies=tk_max)
    fb_res = followback_instagram_commenters(max_follows=ig_followback_max)
    return {
        "timestamp": datetime.now().isoformat(),
        "youtube": yt_res,
        "instagram": ig_res,
        "tiktok": tk_res,
        "instagram_followback": fb_res,
        "total_replied": yt_res["replied"] + ig_res["replied"] + tk_res["replied"],
        "total_followed": fb_res["followed"],
    }
