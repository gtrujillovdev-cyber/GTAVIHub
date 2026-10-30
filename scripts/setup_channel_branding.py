#!/usr/bin/env python3
"""
scripts/setup_channel_branding.py — Asistente de Configuración de Canales y Afiliados
Muestra las descripciones oficiales, los enlaces de afiliados de Amazon y la estructura de Linktree.
"""
import sys
import argparse
from pathlib import Path

# Asegurar path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.affiliates import (
    get_channel_branding_kit,
    get_amazon_tag,
    get_hub_linktree,
    get_all_affiliate_products
)

def main():
    parser = argparse.ArgumentParser(description="Kit de Branding, Enlaces de Afiliados y Perfiles para GTA VI Hub Spain")
    parser.add_argument("--platform", choices=["youtube", "tiktok", "instagram", "linktree", "all"], default="all",
                        help="Plataforma a mostrar (default: all)")
    parser.add_argument("--tag", type=str, default=None,
                        help="Etiqueta de asociado de Amazon (ej: gtavihub-21)")
    args = parser.parse_args()

    kit = get_channel_branding_kit()
    active_tag = args.tag or get_amazon_tag()
    hub = get_hub_linktree()

    print("\n" + "═" * 70)
    print("🌴 GTA VI HUB SPAIN — KIT DE BRANDING, REDES Y AFILIADOS AMAZON 🎮")
    print("═" * 70)
    print(f"📌 Etiqueta Amazon Asociados: {active_tag}")
    print(f"🌐 Hub de Enlaces Central:    {hub}")
    print("═" * 70)

    if args.platform in ["youtube", "all"]:
        yt = kit["youtube"]
        print("\n" + "─" * 70)
        print("🔴 1. PERFIL OFICIAL DE YOUTUBE")
        print("─" * 70)
        print(f"• Nombre del Canal: {yt['channel_name']}")
        print(f"• Identificador (@): {yt['handle']}")
        print(f"• Eslogan:          {yt['tagline']}\n")
        print("📝 DESCRIPCIÓN DEL CANAL (Copiar y pegar en YouTube Studio > Personalización > Información básica):")
        print("┌" + "─" * 68 + "┐")
        for line in yt["description"].split("\n"):
            print(f"│ {line}")
        print("└" + "─" * 68 + "┘")
        print("\n🔗 ENLACES DEL BANNER DE YOUTUBE:")
        for idx, l in enumerate(yt["links"], 1):
            print(f"  [{idx}] {l['title']}: {l['url']}")

    if args.platform in ["tiktok", "all"]:
        tt = kit["tiktok"]
        print("\n" + "─" * 70)
        print("🎵 2. PERFIL OFICIAL DE TIKTOK")
        print("─" * 70)
        print(f"• Nombre para mostrar: {tt['display_name']}")
        print(f"• Nombre de usuario:   {tt['username']}")
        print(f"• Categoría:           {tt['category']}")
        print(f"• Enlace del sitio web: {tt['bio_link']}\n")
        print("📝 BIOGRAFÍA TIKTOK (máx 80 caracteres con saltos):")
        print("┌" + "─" * 68 + "┐")
        for line in tt["bio"].split("\n"):
            print(f"│ {line}")
        print("└" + "─" * 68 + "┘")

    if args.platform in ["instagram", "all"]:
        ig = kit["instagram"]
        print("\n" + "─" * 70)
        print("📸 3. PERFIL OFICIAL DE INSTAGRAM REELS")
        print("─" * 70)
        print(f"• Nombre:        {ig['name']}")
        print(f"• Nombre de usuario: {ig['username']}")
        print(f"• Categoría:     {ig['category']}")
        print(f"• Enlace externo: {ig['bio_link']}\n")
        print("📝 BIOGRAFÍA INSTAGRAM (Lista para pegar):")
        print("┌" + "─" * 68 + "┐")
        for line in ig["bio"].split("\n"):
            print(f"│ {line}")
        print("└" + "─" * 68 + "┘")

    if args.platform in ["linktree", "all"]:
        lt = kit["linktree_buttons"]
        print("\n" + "─" * 70)
        print("🌐 4. ESTRUCTURA RECOMENDADA DE LINKTREE / LINK IN BIO")
        print("─" * 70)
        print("Agrega estos 7 botones en tu panel de Linktree en este orden de prioridad:\n")
        for b in lt:
            print(f"  [{b['order']}] {b['badge']} ──► {b['title']}")
            print(f"      Subtítulo: {b['subtitle']}")
            print(f"      Enlace:    {b['url']}\n")

    print("─" * 70)
    print("🎨 5. ESPECIFICACIONES DE AVATAR Y BANNER OFICIAL (assets/)")
    print("─" * 70)
    print("• Avatar: 800x800 px (Relación 1:1, centrado circular)")
    print("  Ubicación: assets/avatar.jpg")
    print("• Banner YouTube: 2560x1440 px (Zona segura central: 1546x423 px)")
    print("  Ubicación: assets/banner.jpg")
    print("• Paleta Oficial Vice City:")
    print("  - Magenta Neón:  #FF007F / #FF1493")
    print("  - Cian Eléctrico: #00F0FF / #00FFFF")
    print("  - Amarillo Sol:  #FFD700 / #FFE600")
    print("  - Azul Noche:    #0B0E14")
    print("═" * 70 + "\n")

if __name__ == "__main__":
    main()
