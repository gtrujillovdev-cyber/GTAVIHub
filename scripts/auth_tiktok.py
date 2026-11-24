#!/usr/bin/env python3
"""
scripts/auth_tiktok.py
======================
Flujo OAuth 2.0 oficial para TikTok Content Posting API v2.
Guarda las credenciales en `tiktok_token.json` en la raíz del proyecto.

Requisitos en .env:
  TIKTOK_CLIENT_KEY=...
  TIKTOK_CLIENT_SECRET=...
  TIKTOK_REDIRECT_URI=http://localhost:8089/callback  (opcional)

Uso:
  python3 scripts/auth_tiktok.py
"""

import os
import sys
import json
import time
import base64
import hashlib
import secrets
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TOKEN_FILE = BASE_DIR / "tiktok_token.json"
DEFAULT_REDIRECT = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8089/callback")
SCOPES = "user.info.basic,video.upload,video.publish"


def refresh_tiktok_token(token_data: dict) -> dict:
    """Renueva el access_token oficial usando refresh_token."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    refresh_token = token_data.get("refresh_token", "")
    if not client_key or not client_secret or not refresh_token:
        raise ValueError("Faltan TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET o refresh_token.")

    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Error renovando token TikTok: {data}")
    data["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def authenticate_tiktok():
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    if not client_key or not client_secret:
        print("=" * 64)
        print("[!] Faltan TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET en .env")
        print("=" * 64)
        print("Pasos para obtenerlos en TikTok for Developers:")
        print("1. Entra en https://developers.tiktok.com/ y crea una app.")
        print("2. Añade los productos: 'Login Kit' y 'Content Posting API'.")
        print("3. En Redirect URI añade: http://localhost:8089/callback")
        print("4. Copia Client Key y Client Secret en tu .env:")
        print("   TIKTOK_CLIENT_KEY=tu_client_key")
        print("   TIKTOK_CLIENT_SECRET=tu_client_secret")
        sys.exit(1)

    state = secrets.token_urlsafe(16)
    code_verifier = "".join(
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        for _ in range(64)
    )
    code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).hexdigest()
    auth_params = urllib.parse.urlencode({
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": DEFAULT_REDIRECT,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{auth_params}"

    received = {}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            received["code"] = qs.get("code", [None])[0]
            received["state"] = qs.get("state", [None])[0]
            received["error"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>TikTok autorizado correctamente. Ya puedes cerrar esta ventana.</h2>")

        def log_message(self, format, *args):
            return

    parsed_redir = urllib.parse.urlparse(DEFAULT_REDIRECT)
    port = parsed_redir.port or 8089
    server = HTTPServer(("localhost", port), _CallbackHandler)

    print("=" * 64)
    print("🔐 AUTENTICACIÓN OFICIAL TIKTOK CONTENT POSTING API v2")
    print("=" * 64)
    print(f"Abre esta URL si no se abre automáticamente:\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server.handle_request()
    server.server_close()

    if received.get("error") or not received.get("code"):
        raise RuntimeError(f"Autorización cancelada o fallida: {received}")
    if received.get("state") != state:
        raise RuntimeError("State OAuth no coincide.")

    token_resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": received["code"],
            "grant_type": "authorization_code",
            "redirect_uri": DEFAULT_REDIRECT,
            "code_verifier": code_verifier,
        },
        timeout=20,
    )
    token_data = token_resp.json()
    if "access_token" not in token_data:
        raise RuntimeError(f"Error obteniendo access_token de TikTok: {token_data}")

    token_data["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[✓] Token oficial guardado en {TOKEN_FILE.name}")


if __name__ == "__main__":
    authenticate_tiktok()
