"""
src/x_scout.py — Scout de X (Twitter) para detectar vídeos virales de GTA6 en tu cuenta.

Usa Playwright con sesión persistente para:
1. Escanear tus Likes (/likes) de X en busca de publicaciones de GTA6 (vídeos nativos de X, YouTube y TikTok).
2. Extraer un patrón de gustos persistente en data/x_taste_profile.json (temas, creadores y queries).
3. Escanear el timeline autenticado (/home) aplicando el patrón de gustos aprendido.

Setup previo (una sola vez, en local con pantalla):
    .venv/bin/python3 scripts/setup_x_session.py --sync
"""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .config import BASE_DIR
from .viral_discovery import calculate_virality_score

X_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles" / "x_user_data"
X_STORAGE_STATE_FILE = BASE_DIR / "assets" / ".browser_profiles" / "x_storage_state.json"
X_TASTE_PROFILE_FILE = BASE_DIR / "data" / "x_taste_profile.json"

GTA6_KEYWORDS = [
    "gta 6", "gta vi", "grand theft auto 6", "grand theft auto vi",
    "gta6", "gtavi", "rockstar", "vice city", "lucia", "jason",
    "leonida", "rage 9", "#gta6", "#gtavi",
]

TASTE_TOPIC_MAP = {
    "fisicas": ["physics", "fisica", "física", "rage 9", "water", "agua", "destruction", "ragdoll"],
    "comparativa": ["vs", "comparison", "comparativa", "gta 5", "gta v", "rdr2", "ps5 pro", "graphics", "graficos"],
    "gameplay": ["gameplay", "free roam", "mundo abierto", "mission", "mision", "combate", "driving"],
    "misterios": ["secret", "secreto", "easter egg", "mystery", "misterio", "map", "mapa", "leak", "hidden"],
    "personajes": ["lucia", "jason", "npc", "character", "protagonist", "trailer"],
    "humor_reaccion": ["funny", "caos", "chaos", "reaction", "reaccion", "fail", "wtf", "crazy"],
}

YOUTUBE_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)
TIKTOK_RE = re.compile(
    r'https?://(?:www\.)?tiktok\.com/@[\w.]+/video/(\d+)'
)
X_STATUS_RE = re.compile(
    r'(?:https?://(?:www\.)?(?:x\.com|twitter\.com))?/([A-Za-z0-9_]+)/status/(\d+)'
)
VIEWS_RE = re.compile(r'([\d,.]+)\s*([KMB]?)\s*(?:views|visualizaciones)', re.IGNORECASE)

LIKED_BONUS = 15


def _is_gta6_tweet(text: str) -> bool:
    tl = (text or "").lower()
    return any(kw in tl for kw in GTA6_KEYWORDS)


def _parse_views(text: str) -> int:
    m = VIEWS_RE.search(text or "")
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


def _extract_video_url(href: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Devuelve (video_id, canonical_url, platform) para enlaces externos o (None, None, None)."""
    yt = YOUTUBE_RE.search(href or "")
    if yt:
        vid = yt.group(1)
        return vid, f"https://www.youtube.com/watch?v={vid}", "youtube"
    tt = TIKTOK_RE.search(href or "")
    if tt:
        vid = tt.group(1)
        url = href if href.startswith("http") else f"https://www.tiktok.com{href}"
        return vid, url, "tiktok"
    return None, None, None


def _extract_native_x_status(tweet_el: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Si el tweet contiene un vídeo nativo de X, devuelve (status_id, canonical_x_url, 'x')."""
    try:
        has_video = (
            tweet_el.query_selector('[data-testid="videoPlayer"]') is not None
            or tweet_el.query_selector("video") is not None
        )
        if not has_video:
            return None, None, None
        for link in tweet_el.query_selector_all("a[href*='/status/']"):
            href = link.get_attribute("href") or ""
            m = X_STATUS_RE.search(href)
            if m:
                user, status_id = m.group(1), m.group(2)
                return f"x_{status_id}", f"https://x.com/{user}/status/{status_id}", "x"
    except Exception:
        pass
    return None, None, None


def load_x_taste_profile() -> Dict[str, Any]:
    if not X_TASTE_PROFILE_FILE.exists():
        return {"preferred_topics": [], "preferred_creators": [], "dynamic_queries": [], "liked_samples": 0}
    try:
        data = json.loads(X_TASTE_PROFILE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"preferred_topics": [], "preferred_creators": [], "dynamic_queries": [], "liked_samples": 0}


def update_x_taste_profile(liked_tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analiza tweets con like de GTA6 para marcar un patrón persistente de gustos y queries."""
    existing = load_x_taste_profile()
    if not liked_tweets:
        return existing

    topic_counts: Counter = Counter()
    creator_counts: Counter = Counter()
    for t in liked_tweets:
        txt = (t.get("title") or "").lower()
        for topic, kws in TASTE_TOPIC_MAP.items():
            if any(kw in txt for kw in kws):
                topic_counts[topic] += 1
        creator = (t.get("uploader") or "").strip()
        if creator and creator not in ("X Timeline", "X Likes"):
            creator_counts[creator] += 1

    top_topics = [t for t, _ in topic_counts.most_common(4)]
    top_creators = [c for c, _ in creator_counts.most_common(8)]
    dynamic_queries = [f"GTA 6 {topic}" for topic in top_topics[:3]]

    profile = {
        "updated_at": datetime.now().isoformat(),
        "liked_samples": len(liked_tweets),
        "preferred_topics": top_topics or existing.get("preferred_topics", []),
        "preferred_creators": top_creators or existing.get("preferred_creators", []),
        "dynamic_queries": dynamic_queries or existing.get("dynamic_queries", []),
        "topic_weights": dict(topic_counts),
    }
    X_TASTE_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    X_TASTE_PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile


def get_x_taste_boost(title: str, uploader: str = "") -> int:
    """Devuelve un bonus de 0 a 15 pts si el candidato encaja con el patrón de Likes en X."""
    profile = load_x_taste_profile()
    boost = 0
    low_title = (title or "").lower()
    for topic in profile.get("preferred_topics", []):
        kws = TASTE_TOPIC_MAP.get(topic, [])
        if any(kw in low_title for kw in kws):
            boost += 5
    if uploader and uploader in profile.get("preferred_creators", []):
        boost += 5
    return min(15, boost)


def ingest_x_likes_as_sources(liked_candidates: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Ingesta clips y creadores de tus Likes de X como fuentes para futura selección:
    1) Añade los clips a data/curated_queue.json (cola prioritaria de channels.py).
    2) Registra los creadores/canales mediante auto_register_source_from_metadata.
    """
    stats = {"queued_clips": 0, "registered_sources": 0}
    if not liked_candidates:
        return stats

    try:
        from .channels import (
            CURATED_QUEUE_FILE,
            auto_register_source_from_metadata,
            get_processed_ids,
        )
    except Exception:
        return stats

    processed_ids = get_processed_ids()
    existing_queue: List[Dict[str, Any]] = []
    if CURATED_QUEUE_FILE.exists():
        try:
            loaded = json.loads(CURATED_QUEUE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_queue = loaded
        except Exception:
            existing_queue = []

    queued_ids = {str(item.get("id", "")) for item in existing_queue}
    plat_map = {"youtube": "YouTube", "tiktok": "TikTok", "x": "X"}

    for cand in liked_candidates:
        if not cand.get("is_liked"):
            continue
        cid = str(cand.get("id", "")).strip()
        if cid and cid not in processed_ids and cid not in queued_ids:
            existing_queue.append({
                "id": cid,
                "url": cand.get("url", ""),
                "title": cand.get("title", "GTA 6 X Like"),
                "uploader": cand.get("uploader", "X Likes"),
                "source_name": "X Likes",
                "platform": cand.get("platform", "x"),
                "score": cand.get("score", 75),
                "is_short": True,
                "lang": cand.get("lang", "en"),
                "source": "x_likes",
            })
            queued_ids.add(cid)
            stats["queued_clips"] += 1

        plat_name = plat_map.get(str(cand.get("platform", "")).lower(), "X")
        reg = auto_register_source_from_metadata({
            "uploader": cand.get("uploader", ""),
            "platform": plat_name,
            "url": cand.get("url", ""),
            "title": cand.get("title", ""),
        })
        if reg.get("success"):
            stats["registered_sources"] += 1

    if stats["queued_clips"] > 0:
        CURATED_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURATED_QUEUE_FILE.write_text(
            json.dumps(existing_queue[-50:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return stats


def _dismiss_cookie_banner(page: Any) -> None:
    """Cierra el banner modal de cookies de X si aparece tapando la pantalla."""
    try:
        # Botones típicos: "Refuse non-essential cookies", "Accept all cookies", etc.
        selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Refuse non-essential")',
            'button:has-text("Aceptar todas")',
            'button:has-text("Rechazar")',
            '[data-testid="sheetDialog"] button',
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_timeout(1000)
                break
    except Exception:
        pass


def _collect_tweets_from_current_page(
    page: Any,
    max_candidates: int,
    max_scrolls: int,
    seen_ids: set,
    force_liked: bool = False,
    source_label: str = "X Timeline",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extrae candidatos de vídeo y metadatos de tweets GTA6 de la página actual de X."""
    _dismiss_cookie_banner(page)
    candidates: List[Dict[str, Any]] = []
    liked_texts: List[Dict[str, Any]] = []

    for _ in range(max_scrolls):
        tweets = page.query_selector_all('[data-testid="tweet"]')
        for tweet_el in tweets:
            try:
                tweet_text = tweet_el.inner_text() or ""
                if not _is_gta6_tweet(tweet_text):
                    continue

                is_liked = force_liked
                if not is_liked:
                    try:
                        is_liked = tweet_el.query_selector('[data-testid="unlike"]') is not None
                    except Exception:
                        pass

                uploader = source_label
                try:
                    user_el = tweet_el.query_selector('[data-testid="User-Name"]')
                    if user_el:
                        uploader = user_el.inner_text().split("\n")[0].strip() or source_label
                except Exception:
                    pass

                if is_liked:
                    liked_texts.append({"title": tweet_text[:180], "uploader": uploader})

                tweet_views = _parse_views(tweet_text)
                extracted: List[Tuple[str, str, str]] = []

                for link in tweet_el.query_selector_all("a[href]"):
                    href = link.get_attribute("href") or ""
                    vid, vurl, plat = _extract_video_url(href)
                    if vid and vurl and plat:
                        extracted.append((vid, vurl, plat))

                if not extracted:
                    n_vid, n_url, n_plat = _extract_native_x_status(tweet_el)
                    if n_vid and n_url and n_plat:
                        extracted.append((n_vid, n_url, n_plat))

                for video_id, video_url, platform in extracted:
                    if video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)

                    score_data = calculate_virality_score(
                        title=tweet_text[:120],
                        duration=28,
                        views=tweet_views,
                        days_old=1,
                    )
                    base_score = score_data.get("score", 40)
                    taste_bonus = get_x_taste_boost(tweet_text, uploader)
                    final_score = min(100, base_score + (LIKED_BONUS if is_liked else 0) + taste_bonus)

                    candidates.append({
                        "id": video_id,
                        "url": video_url,
                        "title": tweet_text[:120].strip().replace("\n", " "),
                        "uploader": uploader,
                        "source_name": source_label,
                        "platform": platform,
                        "score": final_score,
                        "is_liked": is_liked,
                        "views": tweet_views,
                        "lang": "en",
                        "is_short": True,
                        "source": "x_scout",
                    })
                    if len(candidates) >= max_candidates:
                        return candidates, liked_texts
            except Exception:
                continue

        page.evaluate("window.scrollBy(0, 1800)")
        page.wait_for_timeout(2200)

    return candidates, liked_texts


def scan_x_timeline(
    max_candidates: int = 20,
    max_scrolls: int = 8,
    include_likes: bool = True,
) -> List[Dict[str, Any]]:
    """
    Navega tus Likes de X (para marcar patrón de gustos y extraer clips) y tu Timeline,
    devolviendo candidatos de vídeo GTA6 (YouTube, TikTok y vídeos nativos de X).
    """
    if not X_PROFILE_DIR.exists() and not X_STORAGE_STATE_FILE.exists():
        print("[X Scout] Sin perfil de sesión ni storage_state. Ejecuta: python3 scripts/setup_x_session.py --sync")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[X Scout] playwright no instalado en el entorno.")
        return []

    all_candidates: List[Dict[str, Any]] = []
    all_liked_meta: List[Dict[str, Any]] = []
    seen_ids: set = set()

    print("[X Scout] Iniciando navegador headless con sesión de X...")
    with sync_playwright() as p:
        try:
            browser = None
            if X_STORAGE_STATE_FILE.exists():
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = browser.new_context(
                    storage_state=str(X_STORAGE_STATE_FILE),
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
            else:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(X_PROFILE_DIR),
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                )
        except Exception as e:
            print(f"[X Scout] Error lanzando navegador: {e}")
            return []

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(3500)

            if "login" in page.url.lower():
                print("[X Scout] Sesión caducada. Ejecuta: .venv/bin/python3 scripts/setup_x_session.py --fresh --sync")
                context.close()
                return []

            # 1) Escanear Likes del usuario para extraer clips y marcar patrón de gustos
            if include_likes:
                try:
                    profile_link = page.query_selector('a[data-testid="AppTabBar_Profile_Link"]')
                    profile_href = profile_link.get_attribute("href") if profile_link else ""
                    likes_url = f"https://x.com{profile_href.rstrip('/')}/likes" if profile_href else "https://x.com/i/history/likes"
                    print(f"[X Scout] Escaneando tus Likes en {likes_url}...")
                    page.goto(likes_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3500)
                    liked_cands, liked_meta = _collect_tweets_from_current_page(
                        page,
                        max_candidates=max(5, max_candidates // 2),
                        max_scrolls=max(3, max_scrolls // 2),
                        seen_ids=seen_ids,
                        force_liked=True,
                        source_label="X Likes",
                    )
                    all_candidates.extend(liked_cands)
                    all_liked_meta.extend(liked_meta)
                    if liked_meta:
                        prof = update_x_taste_profile(liked_meta)
                        print(f"[X Taste] Patrón actualizado: temas={prof.get('preferred_topics')} ({len(liked_meta)} likes GTA6)")
                    if liked_cands:
                        ing = ingest_x_likes_as_sources(liked_cands)
                        print(f"[X Likes -> Fuentes] Cola={ing['queued_clips']} clips nuevos, Fuentes={ing['registered_sources']} creadores.")
                except Exception as e:
                    print(f"[X Scout] Aviso escaneando Likes: {e}")

            # 2) Escanear Timeline principal
            remaining = max_candidates - len(all_candidates)
            if remaining > 0:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3500)
                home_cands, home_liked = _collect_tweets_from_current_page(
                    page,
                    max_candidates=remaining,
                    max_scrolls=max_scrolls,
                    seen_ids=seen_ids,
                    force_liked=False,
                    source_label="X Timeline",
                )
                all_candidates.extend(home_cands)
                all_liked_meta.extend(home_liked)
                if home_liked and not include_likes:
                    update_x_taste_profile(home_liked)

        except Exception as e:
            print(f"[X Scout] Error durante el escaneo: {e}")

        context.close()

    all_candidates.sort(key=lambda c: (c.get("is_liked", False), c.get("score", 0)), reverse=True)
    liked = sum(1 for c in all_candidates if c.get("is_liked"))
    print(f"[X Scout] {len(all_candidates)} candidatos GTA6 encontrados ({liked} con like tuyo).")
    return all_candidates


def print_x_leaderboard(candidates: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 68)
    print(" X (TWITTER) SCOUT — VIDEOS GTA6 (LIKES & TIMELINE)")
    print("=" * 68)
    if not candidates:
        print("  Sin candidatos encontrados.")
        return
    for i, c in enumerate(candidates, 1):
        liked_tag = " [LIKED]" if c.get("is_liked") else ""
        print(f"  {i:2}. [{c['score']:3}/100]{liked_tag}  {c['title'][:55]}")
        print(f"      -> {c['uploader']} | {c['platform'].upper()} | URL: {c['url']}")
    print("=" * 68)
