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
MAX_STORED_REPLIED_IDS = 1000

_SPAM_PATTERNS = (
    "http://",
    "https://",
    "www.",
    "t.me/",
    "wa.me/",
    "crypto",
    "forex",
    "whatsapp",
    "telegram",
    "onlyfans",
    "sub4sub",
    "check my profile",
    "mira mi perfil",
)

_FALLBACK_REPLIES = [
    "¡Totalmente! En Vice City cada detalle cuenta 🔥 ¿Qué es lo que más ganas tienes de probar?",
    "¡Gracias por pasarte, crack! 🙌 ¿Crees que Rockstar superará las expectativas con esto?",
    "¡Buen punto! 👀 Este nivel de detalle en GTA 6 va a dar mucho que hablar en Leonida.",
    "¡Tal cual! 🔥 ¿Tú qué opinas: lo veremos tal cual el día de salida?",
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


def run_autonomous_community_cycle(yt_max: int = 6, ig_max: int = 4) -> Dict[str, Any]:
    """Ejecuta un ciclo completo de interacción autónoma con seguidores."""
    yt_res = reply_youtube_comments(max_replies=yt_max)
    ig_res = reply_instagram_comments(max_replies=ig_max)
    return {
        "timestamp": datetime.now().isoformat(),
        "youtube": yt_res,
        "instagram": ig_res,
        "total_replied": yt_res["replied"] + ig_res["replied"],
    }
