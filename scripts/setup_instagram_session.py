"""
Login interactivo de Instagram con instagrapi para @gtavihubextra.
Resuelve challenge / 2FA si aplica, verifica el usuario real autenticado,
actualiza .env y guarda assets/.browser_profiles/instagrapi_session.json.

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_instagram_session.py --user gtavihubextra --fresh --sync
"""

import argparse
import getpass
import os
import shlex
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
SESSION_FILE = BASE_DIR / "assets" / ".browser_profiles" / "instagrapi_session.json"
REMOTE_HOST = os.getenv("GTA_HOST", "gabrieltrujillovallejo@100.108.212.124")
REMOTE_DIR = os.getenv("GTA_REMOTE_DIR", "~/GTAVIHub")


def _update_env_file(env_path: Path, updates: dict) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    new_lines = []
    for ln in lines:
        key = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(ln)
    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(ENV_FILE)
    parser = argparse.ArgumentParser(description="Configura sesión de Instagram (instagrapi)")
    parser.add_argument("--user", default="", help="Usuario de Instagram (por defecto gtavihubextra)")
    parser.add_argument("--fresh", action="store_true", help="Borra caché previo de instagrapi antes de autenticar")
    parser.add_argument("--sync", action="store_true", help="Sincroniza sesión y credenciales a mbp1 por scp/ssh")
    parser.add_argument("--use-env-password", action="store_true", help="Usa INSTAGRAM_PASSWORD de .env sin pedir por TTY")
    parser.add_argument("--from-browser-state", action="store_true", help="Convierte la cookie sessionid de storage_state.json a instagrapi_session.json")
    parser.add_argument("--code", default="", help="Código 2FA o challenge si se conoce de antemano")
    args = parser.parse_args()

    env_user = (os.getenv("INSTAGRAM_USERNAME") or "").strip()
    env_pass = os.getenv("INSTAGRAM_PASSWORD") or ""
    default_user = env_user if (env_user and env_user.lower() != "gtavihubspain") else "gtavihubextra"
    username = (args.user or "").strip().lstrip("@")
    if not username:
        if args.from_browser_state:
            username = default_user
        else:
            entered = input(f"Usuario de Instagram [{default_user}]: ").strip().lstrip("@")
            username = entered or default_user

    password = env_pass
    if not args.from_browser_state:
        if env_pass and (args.use_env_password or username.lower() == env_user.lower()):
            password = env_pass
        elif env_pass:
            typed = getpass.getpass(f"Contraseña para @{username} (Enter para probar la actual de .env): ").strip()
            password = typed or env_pass
        else:
            password = getpass.getpass(f"Contraseña para @{username}: ").strip()

        if not password:
            print("[!] Contraseña vacía — cancelando.")
            return 1

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh and SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print("[*] Caché anterior instagrapi_session.json eliminado (--fresh).")

    print(f"\n[*] Iniciando sesión como @{username}...")

    try:
        from instagrapi import Client

        cl = Client()
        cl.delay_range = [2, 5]

        if args.from_browser_state:
            import json as _json
            from urllib.parse import unquote
            st_path = BASE_DIR / "assets" / ".browser_profiles" / "storage_state.json"
            if not st_path.exists():
                print(f"[!] No existe {st_path}")
                return 1
            st_data = _json.loads(st_path.read_text(encoding="utf-8"))
            ig_sid = next(
                (unquote(c.get("value", "")) for c in st_data.get("cookies", [])
                 if "instagram" in c.get("domain", "") and c.get("name") == "sessionid" and c.get("value")),
                "",
            )
            if not ig_sid:
                print("[!] No hay cookie sessionid de Instagram en storage_state.json.")
                return 1
            cl.login_by_sessionid(ig_sid)
        else:
            def challenge_handler(u: str, choice: int = 0) -> str:
                if args.code:
                    return args.code.strip()
                print(f"\n[!] CHALLENGE_REQUIRED para @{u}: Instagram envió un código de verificación por email/SMS.")
                return input("    Introduce el código de 6 dígitos: ").strip()

            def two_factor_handler() -> str:
                if args.code:
                    return args.code.strip()
                return input("    Código 2FA de Instagram: ").strip()

            cl.challenge_code_handler = challenge_handler

            try:
                cl.login(username, password, verification_code=args.code.strip() if args.code else "")
            except Exception as e:
                err = str(e)
                if "two-factor" in err.lower() or "2fa" in err.lower():
                    code = two_factor_handler()
                    cl.login(username, password, verification_code=code)
                elif any(x in err.lower() for x in ["572", "timeline", "feed"]):
                    print(f"[!] Advertencia post-login (ignorada): {err[:80]}")
                else:
                    raise

        info = cl.account_info()
        actual_user = getattr(info, "username", username)
        if actual_user.strip().lower() != username.strip().lower():
            print(f"[!] ADVERTENCIA: Instagram devolvió @{actual_user} (pk={getattr(info, 'pk', 'N/A')}) en lugar de @{username}.")
            return 1
        print(f"[✓] Autenticado correctamente como @{actual_user} (pk={getattr(info, 'pk', 'N/A')}).")

        cl.dump_settings(str(SESSION_FILE))
        env_upd = {"INSTAGRAM_USERNAME": actual_user}
        if password:
            env_upd["INSTAGRAM_PASSWORD"] = password
        _update_env_file(ENV_FILE, env_upd)
        print(f"[OK] Sesión guardada en {SESSION_FILE} y .env actualizado.")

        if args.sync:
            import json as _json
            print(f"\n→ Sincronizando sesión y credenciales IG a {REMOTE_HOST} ...")
            subprocess.run(
                ["scp", "-q", str(SESSION_FILE), f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/instagrapi_session.json"],
                check=True,
            )
            payload_json = _json.dumps(env_upd)
            remote_script = (
                "import json, sys\n"
                "from pathlib import Path\n"
                "updates = json.loads(sys.stdin.read())\n"
                "ep = Path('.env')\n"
                "lines = ep.read_text(encoding='utf-8').splitlines() if ep.exists() else []\n"
                "seen, out = set(), []\n"
                "for ln in lines:\n"
                "    k = ln.split('=', 1)[0].strip() if '=' in ln and not ln.lstrip().startswith('#') else None\n"
                "    if k in updates:\n"
                "        out.append(f'{k}={updates[k]}')\n"
                "        seen.add(k)\n"
                "    else:\n"
                "        out.append(ln)\n"
                "for k, v in updates.items():\n"
                "    if k not in seen:\n"
                "        out.append(f'{k}={v}')\n"
                "ep.write_text('\\n'.join(out) + '\\n', encoding='utf-8')\n"
            )
            subprocess.run(
                ["ssh", REMOTE_HOST, f"cd {REMOTE_DIR} && .venv/bin/python3 -c {shlex.quote(remote_script)}"],
                input=payload_json,
                text=True,
                check=True,
            )
            print("[✓] Instagram sincronizado en mbp1.")
        else:
            print(
                "\nAhora sincroniza al Mac remoto:\n"
                f"  scp assets/.browser_profiles/instagrapi_session.json "
                f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/instagrapi_session.json"
            )
        return 0
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
