"""
src/x_scout.py — Scout de X (Twitter) para detectar vídeos virales de GTA6 en el timeline del usuario.

Usa Playwright con sesión persistente para navegar el timeline autenticado y
extraer URLs de YouTube/TikTok mencionadas en tweets sobre GTA6.

- Tweets a los que el usuario dio like reciben +15 pts de bonus (señal de calidad humana).
- Retorna candidatos en el mismo formato que fetch_channel_candidates.

Setup previo (una sola vez, en local con pantalla):
    python scripts/setup_x_session.py [--sync]
"""

import re
import time
from pathlib import Path
from typing import List, Dict, Any

from .config import BASE_DIR
from .viral_discovery import calculate_virality_score

X_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles" / "x_user_data"

GTA6_KEYWORDS = [
    "gta 6", "gta vi", "grand theft auto 6", "grand theft auto vi",
    "gta6", "gtavi", "rockstar", "vice city", "lucia", "rage 9",
    "#gta6", "#gtavi",
]

YOUTUBE_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)
TIKTOK_RE = re.compile(
    r'https?://(?:www\.)?tiktok\.com/@[\w.]+/video/(\d+)'
)
VIEWS_RE = re.compile(r'([\d,.]+)\s*([KMB]?)\s*(?:views|visualizaciones)', re.IGNORECASE)

LIKED_BONUS = 15


def _is_gta6_tweet(text: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in GTA6_KEYWORDS)


def _parse_views(text: str) -> int:
    m = VIEWS_RE.search(text)
    if not m:
        return 0
    try:
        num = float(m.group(1).replace(",", "").replace(".", ""))
        suffix = m.group(2).upper()
        if suffix == "B":
            return int(num * 1_000_000_000)
        if suffix == "M":
            return int(num * 1_000_000)
        if suffix == "K":
            return int(num * 1_000)
        return int(num)
    except Exception:
        return 0


def _extract_video_url(href: str) -> tuple:
    """Devuelve (video_id, canonical_url, platform) o (None, None, None)."""
    yt = YOUTUBE_RE.search(href)
    if yt:
        vid = yt.group(1)
        return vid, f"https://www.youtube.com/watch?v={vid}", "youtube"
    tt = TIKTOK_RE.search(href)
    if tt:
        vid = tt.group(1)
        url = href if href.startswith("http") else f"https://www.tiktok.com{href}"
        return vid, url, "tiktok"
    return None, None, None


def scan_x_timeline(
    max_candidates: int = 20,
    max_scrolls: int = 10,
) -> List[Dict[str, Any]]:
    """
    Navega el timeline de X autenticado y devuelve candidatos de vídeo GTA6.
    Los tweets con like del usuario puntúan +15 pts.
    """
    if not X_PROFILE_DIR.exists():
        print("[X Scout] Sin perfil de sesión. Ejecuta: python scripts/setup_x_session.py --sync")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[X Scout] playwright no instalado en el entorno.")
        return []

    candidates: List[Dict[str, Any]] = []
    seen_ids: set = set()

    print("[X Scout] Iniciando navegador headless con sesión de X...")
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(X_PROFILE_DIR),
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        except Exception as e:
            print(f"[X Scout] Error lanzando navegador: {e}")
            return []

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(3500)

            if "login" in page.url.lower():
                print("[X Scout] Sesión caducada. Ejecuta: python scripts/setup_x_session.py --fresh --sync")
                context.close()
                return []

            print(f"[X Scout] Timeline cargado. Escaneando ({max_scrolls} scrolls max)...")

            for scroll_i in range(max_scrolls):
                tweets = page.query_selector_all('[data-testid="tweet"]')

                for tweet_el in tweets:
                    try:
                        tweet_text = tweet_el.inner_text() or ""
                        if not _is_gta6_tweet(tweet_text):
                            continue

                        # Detectar like activo: botón unlike = ya fue likeado
                        is_liked = False
                        try:
                            is_liked = tweet_el.query_selector('[data-testid="unlike"]') is not None
                        except Exception:
                            pass

                        # Vistas del tweet (si están disponibles en el card)
                        tweet_views = _parse_views(tweet_text)

                        # Rastrear todos los hrefs del tweet buscando vídeos
                        links = tweet_el.query_selector_all("a[href]")
                        for link in links:
                            href = link.get_attribute("href") or ""
                            video_id, video_url, platform = _extract_video_url(href)

                            if not video_id or video_id in seen_ids:
                                continue
                            seen_ids.add(video_id)

                            # Scoring: virality base + bonus por like humano
                            score_data = calculate_virality_score(
                                title=tweet_text[:120],
                                duration=28,
                                views=tweet_views,
                                days_old=1,
                            )
                            base_score = score_data.get("score", 40)
                            final_score = min(100, base_score + (LIKED_BONUS if is_liked else 0))

                            # Intentar extraer autor del tweet
                            uploader = "X Timeline"
                            try:
                                user_el = tweet_el.query_selector('[data-testid="User-Name"]')
                                if user_el:
                                    uploader = user_el.inner_text().split("\n")[0].strip() or "X Timeline"
                            except Exception:
                                pass

                            candidates.append({
                                "id": video_id,
                                "url": video_url,
                                "title": tweet_text[:120].strip().replace("\n", " "),
                                "uploader": uploader,
                                "source_name": "X Timeline",
                                "platform": platform,
                                "score": final_score,
                                "is_liked": is_liked,
                                "views": tweet_views,
                                "lang": "en",
                                "is_short": True,
                                "source": "x_scout",
                            })

                            if len(candidates) >= max_candidates:
                                break

                    except Exception:
                        continue

                    if len(candidates) >= max_candidates:
                        break

                if len(candidates) >= max_candidates:
                    break

                page.evaluate("window.scrollBy(0, 1800)")
                page.wait_for_timeout(2200)

        except Exception as e:
            print(f"[X Scout] Error durante el escaneo: {e}")

        context.close()

    # Liked primero, luego por score
    candidates.sort(key=lambda c: (c.get("is_liked", False), c.get("score", 0)), reverse=True)

    liked = sum(1 for c in candidates if c.get("is_liked"))
    print(f"[X Scout] {len(candidates)} candidatos GTA6 encontrados ({liked} con like tuyo).")
    return candidates


def print_x_leaderboard(candidates: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 68)
    print(" X (TWITTER) SCOUT — VIDEOS GTA6 EN TU TIMELINE")
    print("=" * 68)
    if not candidates:
        print("  Sin candidatos encontrados.")
        return
    for i, c in enumerate(candidates, 1):
        liked_tag = " [LIKED]" if c.get("is_liked") else ""
        print(f"  {i:2}. [{c['score']:3}/100]{liked_tag}  {c['title'][:55]}")
        print(f"      -> {c['uploader']} | {c['platform'].upper()} | URL: {c['url']}")
    print("=" * 68)
