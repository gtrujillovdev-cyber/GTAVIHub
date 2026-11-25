#!/usr/bin/env python3
"""
scripts/clean_telegram_media.py
===============================
Registra y purga automáticamente vídeos y fotos antiguos enviados por el bot
de Telegram (dentro de la ventana de 48h permitida por Telegram Bot API).

Uso:
  python3 scripts/clean_telegram_media.py --hours 12
  python3 scripts/clean_telegram_media.py --all
  python3 scripts/clean_telegram_media.py --hours 6 --keep-last 2 --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MEDIA_LOG_FILE = DATA_DIR / "telegram_media_log.json"
TELEGRAM_MAX_DELETE_AGE_SEC = 47.5 * 3600  # Margen seguro bajo límite estricto de 48h


def _load_media_log(log_file: Path = MEDIA_LOG_FILE) -> List[Dict[str, Any]]:
    if not log_file.exists():
        return []
    try:
        data = json.loads(log_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_media_log(entries: List[Dict[str, Any]], log_file: Path = MEDIA_LOG_FILE) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    trimmed = entries[-500:]
    tmp_file = log_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_file.replace(log_file)


def log_telegram_media_message(
    chat_id: Any,
    message_id: Any,
    kind: str = "video",
    label: str = "",
    log_file: Path = MEDIA_LOG_FILE,
) -> None:
    """Registra un mensaje multimedia enviado por el bot para su limpieza programada."""
    if not chat_id or not message_id:
        return
    entries = _load_media_log(log_file)
    entries.append({
        "chat_id": str(chat_id),
        "message_id": int(message_id),
        "kind": str(kind),
        "label": str(label)[:100],
        "sent_at": time.time(),
    })
    _save_media_log(entries, log_file)


def clean_telegram_media(
    hours: float = 12.0,
    delete_all: bool = False,
    keep_last: int = 0,
    dry_run: bool = False,
    log_file: Path = MEDIA_LOG_FILE,
) -> Dict[str, int]:
    """
    Elimina del chat los mensajes multimedia registrados que superen `hours`
    (o todos si `delete_all=True`), respetando el límite de 48h de Telegram Bot API.
    """
    load_dotenv(BASE_DIR / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and not dry_run:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en .env")

    entries = _load_media_log(log_file)
    now = time.time()
    min_age_sec = 0.0 if delete_all else max(0.0, float(hours) * 3600.0)

    # Proteger los últimos `keep_last` mensajes si se solicita
    protected_ids = set()
    if keep_last > 0 and entries:
        for item in entries[-keep_last:]:
            protected_ids.add((str(item.get("chat_id")), int(item.get("message_id", 0))))

    stats = {"deleted": 0, "kept": 0, "expired_48h": 0, "failed": 0}
    remaining: List[Dict[str, Any]] = []
    api_url = f"https://api.telegram.org/bot{token}/deleteMessage"

    for item in entries:
        cid = str(item.get("chat_id", ""))
        mid = int(item.get("message_id", 0) or 0)
        sent_at = float(item.get("sent_at", 0) or 0)
        age = max(0.0, now - sent_at)

        if not cid or not mid:
            continue

        if age >= TELEGRAM_MAX_DELETE_AGE_SEC:
            stats["expired_48h"] += 1
            continue  # Purgar del log: Telegram ya no permite borrar >48h

        if (cid, mid) in protected_ids or age < min_age_sec:
            stats["kept"] += 1
            remaining.append(item)
            continue

        if dry_run:
            print(f"[DRY-RUN] Borraría {item.get('kind')} msg_id={mid} ({item.get('label')})")
            stats["deleted"] += 1
            remaining.append(item)
            continue

        try:
            resp = requests.post(
                api_url,
                json={"chat_id": cid, "message_id": mid},
                timeout=10,
            )
            ok = resp.status_code == 200 and resp.json().get("ok") is True
            if ok:
                stats["deleted"] += 1
            else:
                # Si ya fue borrado manualmente, no reintentar
                desc = (resp.text or "").lower()
                if "message to delete not found" in desc or "message can't be deleted" in desc:
                    stats["expired_48h"] += 1
                else:
                    stats["failed"] += 1
                    remaining.append(item)
        except Exception as exc:
            print(f"[Telegram Clean] Error borrando msg_id={mid}: {exc}")
            stats["failed"] += 1
            remaining.append(item)

    if not dry_run:
        _save_media_log(remaining, log_file)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpieza de vídeos/fotos enviados por el bot de Telegram.")
    parser.add_argument("--hours", type=float, default=12.0, help="Borrar media con más de N horas (default: 12).")
    parser.add_argument("--all", action="store_true", help="Borrar toda la media registrada (<48h) sin esperar.")
    parser.add_argument("--keep-last", type=int, default=0, help="Conservar los últimos N mensajes multimedia.")
    parser.add_argument("--dry-run", action="store_true", help="Simular sin borrar mensajes reales.")
    args = parser.parse_args()

    res = clean_telegram_media(
        hours=args.hours,
        delete_all=args.all,
        keep_last=args.keep_last,
        dry_run=args.dry_run,
    )
    print(
        f"[Telegram Clean] borrados={res['deleted']} | conservados={res['kept']} "
        f"| expirados_48h={res['expired_48h']} | fallidos={res['failed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
