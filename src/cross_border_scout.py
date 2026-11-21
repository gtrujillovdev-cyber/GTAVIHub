"""
Cross-Border Scout — Motor de Arbitraje que detecta picos de traccion temprana
en Reddit (r/GTA6, r/GTA, r/gaming) y los inyecta como candidatos
en el pool de viral_discovery.

Usa el JSON API publico de Reddit (sin autenticacion) para minimizar
dependencias y rate limits.
"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .config import DATA_DIR

ENABLE_REDDIT_SCOUT = os.getenv("ENABLE_REDDIT_SCOUT", "true").lower() in ("1", "true", "yes")
REDDIT_COOLDOWN_FILE = DATA_DIR / "reddit_scout_last.txt"
REDDIT_COOLDOWN_MINUTES = int(os.getenv("REDDIT_COOLDOWN_MINUTES", "180"))  # 3h default

DEFAULT_SUBREDDITS = ["GTA6", "GTA", "gaming"]

GTA6_KEYWORDS = [
    "gta 6", "gta vi", "gta6", "gtavi", "grand theft auto vi",
    "vice city", "leonida", "lucia", "jason", "rage 9",
]

EMOTION_KEYWORDS = {
    "high": ["bug", "glitch", "physics", "ragdoll", "secret", "easter egg",
             "hidden", "wtf", "insane", "crazy", "broken", "details", "ai"],
    "medium": ["gameplay", "comparison", "graphics", "map", "weapon", "car"],
    "low": ["news", "update", "release", "trailer", "official", "leak"],
}


def _is_on_cooldown() -> bool:
    """Verifica si el scout esta en cooldown para evitar spam de requests."""
    if not REDDIT_COOLDOWN_FILE.exists():
        return False
    try:
        last_ts = float(REDDIT_COOLDOWN_FILE.read_text(encoding="utf-8").strip())
        elapsed_min = (time.time() - last_ts) / 60.0
        return elapsed_min < REDDIT_COOLDOWN_MINUTES
    except Exception:
        return False


def _mark_cooldown() -> None:
    try:
        REDDIT_COOLDOWN_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _is_gta6_post(title: str, selftext: str = "") -> bool:
    """Verifica que un post trate sobre GTA 6."""
    combined = f" {title} {selftext} ".lower()
    return any(kw in combined for kw in GTA6_KEYWORDS)


def calculate_emotion_score(title: str, selftext: str = "") -> float:
    """
    Puntua 'emocion pura' (bugs, fisicas, secretos) vs contenido generico.
    Rango: 0.0 a 10.0
    """
    combined = f" {title} {selftext} ".lower()
    score = 3.0  # Base

    for kw in EMOTION_KEYWORDS["high"]:
        if kw in combined:
            score += 1.5

    for kw in EMOTION_KEYWORDS["medium"]:
        if kw in combined:
            score += 0.7

    for kw in EMOTION_KEYWORDS["low"]:
        if kw in combined:
            score += 0.3

    # Bonus por signos de excitacion/sorpresa
    if any(c in title for c in ("!", "?!", "WTF", "INSANE")):
        score += 0.5

    return min(10.0, score)


def _calculate_upvote_velocity(score: int, created_utc: float) -> float:
    """Calcula upvotes por hora desde la creacion."""
    age_hours = max(0.25, (time.time() - created_utc) / 3600.0)
    return score / age_hours


def _extract_video_urls(selftext: str, url: str) -> List[str]:
    """Extrae URLs de YouTube/TikTok del post."""
    urls = []
    combined = f"{selftext} {url}"

    yt_pattern = re.compile(
        r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})'
    )
    for m in yt_pattern.finditer(combined):
        full_url = m.group(0)
        if full_url not in urls:
            urls.append(full_url)

    return urls


def scan_reddit_gta6(
    subreddits: Optional[List[str]] = None,
    min_upvote_velocity: float = 30.0,
    max_results: int = 10,
    force: bool = False
) -> List[Dict[str, Any]]:
    """
    Escanea posts recientes de subreddits de GTA 6 buscando contenido
    con alta velocidad de upvotes y emocion.

    Retorna candidatos compatibles con el formato de viral_discovery.
    """
    if not ENABLE_REDDIT_SCOUT:
        return []

    if not force and _is_on_cooldown():
        print(f"[Reddit Scout] En cooldown ({REDDIT_COOLDOWN_MINUTES} min). Omitiendo.")
        return []

    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    import requests

    candidates = []
    headers = {"User-Agent": "GTAVIHub/1.0 (educational research bot)"}

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                print(f"[Reddit Scout] r/{sub}: HTTP {resp.status_code}")
                continue

            data = resp.json()
            posts = data.get("data", {}).get("children", [])

            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                score = int(post.get("score", 0))
                created = float(post.get("created_utc", time.time()))
                permalink = post.get("permalink", "")
                post_url = post.get("url", "")

                if not _is_gta6_post(title, selftext):
                    continue

                velocity = _calculate_upvote_velocity(score, created)
                emotion = calculate_emotion_score(title, selftext)

                # Filtrar por velocidad minima
                if velocity < min_upvote_velocity and score < 50:
                    continue

                video_urls = _extract_video_urls(selftext, post_url)
                age_hours = max(0.25, (time.time() - created) / 3600.0)

                # Generar score compatible con viral_discovery (0-100)
                composite_score = min(100, int(
                    (velocity / 10.0) * 3  # Velocity weight
                    + emotion * 4           # Emotion weight
                    + min(30, score / 5)    # Raw upvotes capped
                ))

                candidate = {
                    "id": f"reddit_{post.get('id', '')}",
                    "title": title,
                    "url": video_urls[0] if video_urls else f"https://reddit.com{permalink}",
                    "has_video_url": bool(video_urls),
                    "score": composite_score,
                    "uploader": f"r/{sub}",
                    "source_name": f"r/{sub}",
                    "views": score,  # Upvotes as proxy
                    "views_per_hour": velocity,
                    "hours_old": round(age_hours, 1),
                    "duration": 30,  # Unknown, use default
                    "lang": "en",
                    "source": "reddit",
                    "emotion_score": emotion,
                    "reddit_permalink": f"https://reddit.com{permalink}",
                }
                candidates.append(candidate)

            # Rate limit entre subreddits
            time.sleep(1.5)

        except Exception as e:
            print(f"[Reddit Scout] Error en r/{sub}: {e}")
            continue

    _mark_cooldown()

    # Ordenar por score compuesto
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Solo candidatos con URL de video real
    with_video = [c for c in candidates if c.get("has_video_url")]
    without_video = [c for c in candidates if not c.get("has_video_url")]

    final = (with_video + without_video)[:max_results]

    if final:
        print(f"[Reddit Scout] {len(final)} candidatos GTA6 encontrados en Reddit ({len(with_video)} con video)")

    return final
