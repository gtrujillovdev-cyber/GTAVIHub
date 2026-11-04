#!/usr/bin/env python3
"""
🎨 GTA VI Hub Spain — Simulador y Calibrador de Formatos Visuales
================================================================
Compara y evalúa matemáticamente 3 variantes de encuadre vertical para Shorts/TikTok/Reels:
1. Formato A: Cinema Clásico 16:9 (1080x608, 31.6% cobertura de pantalla)
2. Formato B: Full Crop 9:16 (1080x1920, 100% cobertura pero recorta 66% de los laterales)
3. Formato C: Inmersivo 4:5 Smart Frame (1080x1440, 75.0% cobertura de pantalla - EQUILIBRIO PERFECTO)
4. Formato D: Pro-Cinema 83.3% (1080x1600, 83.3% cobertura según Regla 5 del canal)
"""

import subprocess
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
SAMPLE_VIDEO = OUTPUT_DIR / "GTA_6_REACCIÓN_Y_ANÁLISIS_DE_GTA_6_GTA_6_GAMEPLAY_DETAILS_WE_HQA7fxZ-_r0.mp4"
if not SAMPLE_VIDEO.exists():
    # Buscar cualquier otro mp4
    mp4s = list(OUTPUT_DIR.glob("*.mp4"))
    if mp4s:
        SAMPLE_VIDEO = mp4s[0]

LAB_DIR = BASE_DIR / "output" / "lab"
LAB_DIR.mkdir(parents=True, exist_ok=True)
SIM_DIR = LAB_DIR / "format_simulations"
SIM_DIR.mkdir(parents=True, exist_ok=True)

# Parámetros de safe zones para TikTok y YouTube Shorts:
# Altura total: 1920px. Ancho: 1080px.
# Zona superior de riesgo: 0 a 160px (Header del feed, botones de búsqueda).
# Zona inferior de riesgo: 1580px a 1920px (Título de cuenta, audio track, botones de navegación).
# Zona lateral derecha de riesgo: X > 930px (Botones de Like, Comentarios, Compartir, Guardar).

LAYOUTS = [
    {
        "id": "A_cinema_clasico",
        "name": "Cinema Clásico 16:9 (608px)",
        "fg_w": 1080,
        "fg_h": 608,
        "fg_y": 656,
        "coverage_pct": 31.6,
        "side_crop_pct": 0.0,
        "hook_y": 520,
        "subs_y": 1350,
        "desc": "Conserva el 100% de los laterales pero el vídeo ocupa solo un tercio de la pantalla (demasiado pequeño en móvil)."
    },
    {
        "id": "B_full_crop",
        "name": "Full Crop 9:16 (1920px)",
        "fg_w": 1080,
        "fg_h": 1920,
        "fg_y": 0,
        "coverage_pct": 100.0,
        "side_crop_pct": 66.7,
        "hook_y": 140,
        "subs_y": 1250,
        "desc": "Llena el 100% de la pantalla pero mutila el 66% de la información lateral (pierde HUD, minimapa y elementos clave)."
    },
    {
        "id": "C_smart_frame_4_5",
        "name": "Smart Frame Inmersivo 4:5 (1350px)",
        "fg_w": 1080,
        "fg_h": 1350,
        "fg_y": 285,
        "coverage_pct": 70.3,
        "side_crop_pct": 25.0,
        "hook_y": 120,
        "subs_y": 1420,
        "desc": "El vídeo ocupa el 70.3% de la pantalla. Mantiene la mayor parte del encuadre y deja franjas limpias arriba y abajo para Gancho y Subtítulos."
    },
    {
        "id": "D_pro_cinema_83",
        "name": "Pro-Cinema 83.3% (1600px - Regla 5 Oficial)",
        "fg_w": 1080,
        "fg_h": 1600,
        "fg_y": 160,
        "coverage_pct": 83.3,
        "side_crop_pct": 38.0,
        "hook_y": 50,
        "subs_y": 1440,
        "desc": "Enfoque cinemático de alto impacto establecido en las reglas operativas. Máxima inmersión visual sin llegar al recorte agresivo del 9:16 puro."
    }
]


def render_layout_frame(layout: dict, source_video: Path, output_png: Path):
    """Genera un fotograma representativo del layout con fondo ambient blur y overlay."""
    fg_w = layout["fg_w"]
    fg_h = layout["fg_h"]
    fg_y = layout["fg_y"]

    filter_complex = (
        "[0:v]split[v1][v2];"
        "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:5,eq=brightness=-0.16:contrast=1.08:saturation=1.20[bg];"
        f"[v2]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,crop={fg_w}:{fg_h},unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
        f"[bg][fg]overlay=0:{fg_y}[v_out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", "00:00:04",
        "-i", str(source_video),
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-vframes", "1",
        str(output_png)
    ]
    subprocess.run(cmd, capture_output=True, check=False)


def evaluate_layout_score(layout: dict) -> dict:
    """Calcula una puntuación objetiva de retención, estética y cumplimiento."""
    # 1. Puntuación de Cobertura Visual (0 a 40): los usuarios móviles odian los vídeos que parecen sellos
    cov = layout["coverage_pct"]
    if cov < 40:
        cov_score = 10  # Penalización por letterboxing excesivo
    elif cov <= 60:
        cov_score = 25
    elif cov <= 85:
        cov_score = 40  # Óptimo: 70-85% llena la pantalla sin asfixiar
    else:
        cov_score = 35

    # 2. Puntuación de Preservación de Información (0 a 30): evitar recortar demasiado los laterales
    side_crop = layout["side_crop_pct"]
    if side_crop == 0:
        crop_score = 30  # 100% visible
    elif side_crop <= 25:
        crop_score = 28  # Muy poco recorte
    elif side_crop <= 40:
        crop_score = 24  # Recorte moderado aceptable
    else:
        crop_score = 12  # Recorte salvaje (66% perdido)

    # 3. Safe Zones para Gancho y Subtítulos (0 a 30):
    # ¿Tiene espacio para el gancho arriba sin tapar y para subtítulos abajo sin tapar UI?
    if layout["fg_y"] >= 200:
        safe_score = 30 # Franjas perfectas de respiro
    elif layout["fg_y"] >= 140:
        safe_score = 27
    elif layout["fg_y"] > 0:
        safe_score = 22
    else:
        safe_score = 15 # Pantalla completa: colisiona con HUD y UI

    total_score = cov_score + crop_score + safe_score

    return {
        "layout_id": layout["id"],
        "name": layout["name"],
        "coverage_score": cov_score,
        "crop_score": crop_score,
        "safe_zone_score": safe_score,
        "total_score": total_score,
        "verdict": "GANADOR DEFINITIVO" if total_score >= 90 else ("MUY BUENO" if total_score >= 80 else "DEFICIENTE")
    }


def main():
    print("=================================================================")
    print("🔬 SIMULADOR DE FORMATOS Y LAYOUTS VISUALES — GTA VI HUB")
    print("=================================================================\n")

    if not SAMPLE_VIDEO.exists():
        print(f"[!] No se encontró vídeo de muestra en {SAMPLE_VIDEO}.")
        return

    print(f"[*] Vídeo base para simulaciones: {SAMPLE_VIDEO.name}\n")

    evaluations = []
    for lay in LAYOUTS:
        out_png = SIM_DIR / f"frame_{lay['id']}.png"
        render_layout_frame(lay, SAMPLE_VIDEO, out_png)
        score_info = evaluate_layout_score(lay)
        evaluations.append({**lay, **score_info, "frame_path": str(out_png)})

        print(f"▶ {lay['name'].upper()}:")
        print(f"  • Cobertura de Pantalla    : {lay['coverage_pct']}% (Y={lay['fg_y']}px a Y={lay['fg_y']+lay['fg_h']}px)")
        print(f"  • Recorte Lateral          : {lay['side_crop_pct']}%")
        print(f"  • Puntuación Total         : {score_info['total_score']}/100 ➔ [{score_info['verdict']}]")
        print(f"  • Diagnóstico              : {lay['desc']}")
        if out_png.exists():
            print(f"  • Frame generado           : {out_png.name} ({out_png.stat().st_size // 1024} KB)")
        print()

    # Ordenar por puntuación
    evaluations.sort(key=lambda x: x["total_score"], reverse=True)
    winner = evaluations[0]

    print("=" * 65)
    print(f"🏆 FORMATO GANADOR SELECCIONADO: {winner['name']}")
    print(f"   Puntuación: {winner['total_score']}/100 | Veredicto: {winner['verdict']}")
    print("=" * 65)

    with open(LAB_DIR / "layout_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(evaluations, f, indent=2)

if __name__ == "__main__":
    main()
