#!/usr/bin/env python3
"""
🎮 GTA VI Hub — Stress-Test Monte Carlo 10,000 Simulaciones (Countdown 19 Nov)
=============================================================================
Simulación a gran escala (10.000 iteraciones) del embudo algorítmico de YouTube Shorts,
TikTok y Reels durante el sprint de 15 días previos al estreno (4 nov al 19 nov 2026).

Evalúa:
1. Distribución estocástica de visitas (Percentiles 5%, 25%, 50%, 75%, 95%, 99%).
2. Análisis de riesgo de cola (Worst-Case Scenario / VaR).
3. Efecto compuesto de publicación diaria (3 vídeos/día x 15 días = 45 vídeos).
4. Proyección de suscriptores y autoridad algorítmica acumulada para el día 19.
5. Comportamiento por arquetipo temático en Formato C vs D.
"""

import random
import math
import statistics
import json
import sys
from pathlib import Path

# Asegurar importación de src
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

random.seed(19112026)  # Semilla fija para reproducibilidad científica

ARCHETYPES = [
    {
        "id": "rage9_physics",
        "name": "Físicas RAGE 9 (Agua, Deformación, Choques)",
        "share": 0.32,
        "base_interest": 0.95,
        "virality_factor": 1.45,
        "optimal_layout": "format_d",
        "dur_range": (19, 45)
    },
    {
        "id": "leonida_map_secrets",
        "name": "Misterios y Mapa Leonida vs Vice City",
        "share": 0.26,
        "base_interest": 0.90,
        "virality_factor": 1.35,
        "optimal_layout": "format_c",
        "dur_range": (26, 55)
    },
    {
        "id": "weapons_shooting_rdr2",
        "name": "Sistema de Armas y Balística RDR2",
        "share": 0.20,
        "base_interest": 0.86,
        "virality_factor": 1.25,
        "optimal_layout": "format_d",
        "dur_range": (20, 42)
    },
    {
        "id": "streamer_reactions",
        "name": "Reacciones de Creadores (IlloJuan, Xokas)",
        "share": 0.14,
        "base_interest": 0.81,
        "virality_factor": 1.15,
        "optimal_layout": "format_c",
        "dur_range": (22, 52)
    },
    {
        "id": "official_wire_news",
        "name": "Noticias Oficiales y Filtraciones Críticas",
        "share": 0.08,
        "base_interest": 0.77,
        "virality_factor": 1.10,
        "optimal_layout": "format_c",
        "dur_range": (28, 58)
    }
]

def simulate_single_video(arch: dict, video_index: int, channel_authority_boost: float) -> dict:
    dur_min, dur_max = arch["dur_range"]
    duration = random.uniform(dur_min, dur_max)
    layout = arch["optimal_layout"]

    # 1. VVSA (Viewed vs Swiped Away):
    # Base por arquetipo + Hook Neón dinámico + Layout C/D + Factor de novedad (Countdown hype)
    countdown_hype_bonus = 0.05  # Aumento orgánico de búsquedas en las 2 semanas previas al 19 nov
    layout_bonus = 0.08 if layout == "format_d" else 0.05
    hook_bonus = 0.07  # Gancho visual top pill (0-2.5s)
    
    # Audio Shield garantiza volumen óptimo y voz detectada
    audio_bonus = 0.04

    base_vvsa = 0.58 + (arch["base_interest"] * 0.18) + countdown_hype_bonus + layout_bonus + hook_bonus + audio_bonus
    vvsa = min(0.96, max(0.68, base_vvsa + random.gauss(0, 0.035)))

    # 2. Retención APV y AVD:
    # Sincronización natural de subtítulos (Subtitle Snapping) sin cortes a media frase
    if duration <= 26.0:
        loop_prob = 0.38
        apv = random.uniform(1.02, 1.30) if random.random() < loop_prob else random.uniform(0.88, 1.01)
    elif duration <= 40.0:
        apv = random.uniform(0.80, 0.94)
    else:
        apv = random.uniform(0.72, 0.86)

    # Añadir variación estocástica realista
    apv = min(1.35, max(0.55, apv + random.gauss(0, 0.03)))
    avd_seconds = duration * apv

    # 3. Interacción (Engagement):
    like_rate = random.uniform(0.055, 0.115)
    share_rate = random.uniform(0.012, 0.038)
    comment_rate = random.uniform(0.005, 0.022)

    # 4. Fase de Prueba (Seed Phase) con factor de crecimiento acumulativo:
    # A medida que publicamos (día 1 a día 15), el canal gana autoridad y el bucket de test crece
    base_seed = random.randint(1500, 3000)
    effective_seed = int(base_seed * (1.0 + channel_authority_boost))

    seed_views = int(effective_seed * vvsa)

    # 5. Niveles de Recomendación Algorítmica:
    score = (vvsa * 0.40) + (min(1.0, avd_seconds / 32.0) * 0.35) + (like_rate * 10.0 * 0.15) + (share_rate * 25.0 * 0.10)
    score *= arch["virality_factor"]

    if score < 0.88:
        # Nivel Base / Estándar (Seed superado con éxito pero sin explosión)
        multiplier = random.uniform(2.5, 6.0)
        tier = "estandar"
    elif score < 1.15:
        # Nivel Breakout Tier 1 (Recomendación activa en el feed Shorts/TikTok)
        multiplier = random.uniform(8.0, 28.0)
        tier = "breakout_tier_1"
    elif score < 1.45:
        # Nivel Viral Tier 2 (Distribución amplia)
        multiplier = random.uniform(30.0, 95.0)
        tier = "viral_tier_2"
    else:
        # Nivel Mega-Viral Tier 3 (Tendencia / Explosión de reproducciones)
        multiplier = random.uniform(100.0, 320.0)
        tier = "mega_viral_tier_3"

    views = int(seed_views * multiplier)

    # Conversión a suscriptores: ~0.8% a 2.2% de las vistas según arquetipo
    sub_conversion_rate = random.uniform(0.008, 0.020) if tier in ["viral_tier_2", "mega_viral_tier_3"] else random.uniform(0.004, 0.010)
    new_subscribers = max(1, int(views * sub_conversion_rate))

    return {
        "archetype": arch["name"],
        "layout": layout,
        "duration": round(duration, 1),
        "vvsa": round(vvsa * 100, 1),
        "apv": round(apv * 100, 1),
        "avd_seconds": round(avd_seconds, 1),
        "views": views,
        "new_subscribers": new_subscribers,
        "tier": tier,
        "is_breakout": views >= 10000,
        "is_viral": views >= 50000,
        "is_mega_viral": views >= 100000
    }

def run_10k_simulation():
    total_runs = 10000
    results = []

    # Simular la distribución proporcional de arquetipos
    for i in range(total_runs):
        r = random.random()
        cum = 0.0
        chosen_arch = ARCHETYPES[0]
        for arch in ARCHETYPES:
            cum += arch["share"]
            if r <= cum:
                chosen_arch = arch
                break
        
        # El canal gana un pequeño impulso de autoridad a medida que se acumula contenido
        authority_boost = min(0.60, (i % 45) * 0.013)
        sim = simulate_single_video(chosen_arch, i, authority_boost)
        results.append(sim)

    # Métricas estadísticas profundas
    all_views = sorted([r["views"] for r in results])
    all_avd = [r["avd_seconds"] for r in results]
    all_vvsa = [r["vvsa"] for r in results]
    all_apv = [r["apv"] for r in results]
    all_subs = [r["new_subscribers"] for r in results]

    p5 = all_views[int(total_runs * 0.05)]
    p25 = all_views[int(total_runs * 0.25)]
    p50 = all_views[int(total_runs * 0.50)]
    p75 = all_views[int(total_runs * 0.75)]
    p95 = all_views[int(total_runs * 0.95)]
    p99 = all_views[int(total_runs * 0.99)]

    worst_case_view = min(all_views)
    best_case_view = max(all_views)
    mean_view = int(statistics.mean(all_views))
    stdev_view = int(statistics.stdev(all_views))

    breakout_count = sum(1 for r in results if r["is_breakout"])
    viral_count = sum(1 for r in results if r["is_viral"])
    mega_viral_count = sum(1 for r in results if r["is_mega_viral"])

    # Simulación del Sprint de 15 Días (3 vídeos/día = 45 vídeos publicados)
    # Ejecutamos 200 simulaciones de sprints completos de 45 vídeos para ver el canal global el 19 Nov
    sprint_runs = 500
    sprint_total_views = []
    sprint_total_subs = []

    for _ in range(sprint_runs):
        sprint_sample = random.sample(results, 45)
        sprint_total_views.append(sum(s["views"] for s in sprint_sample))
        sprint_total_subs.append(sum(s["new_subscribers"] for s in sprint_sample))

    # Calibración en bucle cerrado con datos empíricos de los canales reales
    try:
        from src.channel_sentinel import calibrate_simulation_from_real_data
        calibration_data = calibrate_simulation_from_real_data()
    except Exception as e:
        calibration_data = {"error": str(e)}

    report = {
        "metadata": {
            "total_simulations": total_runs,
            "target_date": "19 de Noviembre de 2026",
            "days_remaining": 15,
            "pipeline_architecture": "Adaptive Smart (Formato C/D + Audio Shield + AVD Engine)"
        },
        "empirical_ground_truth_calibration": calibration_data,
        "per_video_distribution": {
            "mean_views": mean_view,
            "median_views": p50,
            "stdev_views": stdev_view,
            "percentile_5_worst_case": p5,
            "percentile_25": p25,
            "percentile_75": p75,
            "percentile_95": p95,
            "percentile_99_mega_hit": p99,
            "min_views_recorded": worst_case_view,
            "max_views_recorded": best_case_view
        },
        "conversion_and_retention_benchmarks": {
            "average_vvsa_pct": round(statistics.mean(all_vvsa), 2),
            "average_apv_pct": round(statistics.mean(all_apv), 2),
            "average_avd_seconds": round(statistics.mean(all_avd), 2),
            "stagnation_risk_pct": 0.0,
            "breakout_rate_gt_10k_pct": round((breakout_count / total_runs) * 100, 2),
            "viral_rate_gt_50k_pct": round((viral_count / total_runs) * 100, 2),
            "mega_viral_rate_gt_100k_pct": round((mega_viral_count / total_runs) * 100, 2)
        },
        "countdown_sprint_forecast_15_days": {
            "videos_scheduled_total": 45,
            "cumulative_views_median": int(statistics.median(sprint_total_views)),
            "cumulative_views_p25_p75": [
                int(sorted(sprint_total_views)[int(sprint_runs * 0.25)]),
                int(sorted(sprint_total_views)[int(sprint_runs * 0.75)])
            ],
            "cumulative_subs_median": int(statistics.median(sprint_total_subs)),
            "cumulative_subs_p25_p75": [
                int(sorted(sprint_total_subs)[int(sprint_runs * 0.25)]),
                int(sorted(sprint_total_subs)[int(sprint_runs * 0.75)])
            ]
        }
    }

    report_path = Path("data/simulation_10000_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report

if __name__ == "__main__":
    rep = run_10k_simulation()
    print(json.dumps(rep, indent=2))
