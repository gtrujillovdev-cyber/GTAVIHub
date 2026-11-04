#!/usr/bin/env python3
"""
🎮 GTA VI Hub — Algorithmic Views & Retention Forecast Simulator
================================================================
Simula el rendimiento y las visitas estimadas en YouTube Shorts y TikTok
comparando 4 arquitecturas de publicación:
1. Formato Antiguo (Letterbox 31.6%, audio no verificado, recortes rígidos)
2. Formato C: Smart Frame 4:5 (70.3% pantalla, Audio Shield, AVD Engine)
3. Formato D: Pro-Cinema 83.3% (83.3% pantalla, Audio Shield, AVD Engine)
4. Sistema Adaptativo Completo (Elección dinámica C/D + AVD + Audio Shield)
"""

import random
import math
import statistics
import json
from pathlib import Path

random.seed(2026)

# 1. Definición de Arquetipos de Contenido y su Potencial Orgánico
CONTENT_ARCHETYPES = [
    {
        "id": "rage9_physics",
        "name": "Físicas RAGE 9 (Agua, Deformación, Colisiones)",
        "share_of_content": 0.30,
        "base_interest": 0.94,
        "best_layout": "format_d",  # Pro-Cinema 83.3% maximiza inmersión
        "natural_duration_range": (20, 48)
    },
    {
        "id": "leonida_map_details",
        "name": "Detalles Ocultos del Mapa Leonida vs Vice City",
        "share_of_content": 0.25,
        "base_interest": 0.89,
        "best_layout": "format_c",  # Smart Frame 4:5 protege HUD y comparativa
        "natural_duration_range": (28, 55)
    },
    {
        "id": "weapons_rdr2_mechanics",
        "name": "Armas, Inventario y Físicas Estilo RDR2",
        "share_of_content": 0.20,
        "base_interest": 0.85,
        "best_layout": "format_d",
        "natural_duration_range": (22, 45)
    },
    {
        "id": "streamer_reactions",
        "name": "Reacciones de Creadores (IlloJuan, Xokas, Rubius)",
        "share_of_content": 0.15,
        "base_interest": 0.80,
        "best_layout": "format_c",  # Smart Frame 4:5 protege cam del streamer
        "natural_duration_range": (24, 52)
    },
    {
        "id": "official_news_analysis",
        "name": "Noticias Oficiales Rockstar / Fecha y Lanzamiento",
        "share_of_content": 0.10,
        "base_interest": 0.76,
        "best_layout": "format_c",
        "natural_duration_range": (30, 58)
    }
]

def simulate_clip_performance(archetype: dict, strategy: str, channel_type: str = "new_channel") -> dict:
    """
    Simula una subida individual a través del embudo algorítmico de YouTube Shorts / TikTok.
    """
    dur_min, dur_max = archetype["natural_duration_range"]
    
    # Determinación de Duración según la Estrategia:
    if strategy == "legacy_old":
        # En el sistema antiguo se forzaba un corte rígido artificial
        duration = random.uniform(16.0, 24.0)
        has_audio_shield = False
        is_silent_risk = random.random() < 0.22  # 22% riesgo de meter B-roll plano o mudo
        layout = "format_a"
    elif strategy == "format_c_only":
        duration = random.uniform(dur_min, dur_max)
        has_audio_shield = True
        is_silent_risk = False
        layout = "format_c"
    elif strategy == "format_d_only":
        duration = random.uniform(dur_min, dur_max)
        has_audio_shield = True
        is_silent_risk = False
        layout = "format_d"
    elif strategy == "adaptive_smart":
        duration = random.uniform(dur_min, dur_max)
        has_audio_shield = True
        is_silent_risk = False
        # Elige el mejor layout según el tipo de contenido
        layout = archetype["best_layout"]
    else:
        raise ValueError(f"Estrategia desconocida: {strategy}")

    # 1. VVSA (Viewed vs Swiped Away) — La compuerta de los primeros 2 segundos:
    # Influenciado por: Gancho Neón, Cobertura visual y Atractivo del arquetipo
    base_vvsa = 0.55 + (archetype["base_interest"] * 0.20)  # 0.70 a 0.74 base
    
    if layout == "format_a":
        # Formato A: Letterbox 31.6% con fondo borroso enorme provoca swipe inmediato en móvil
        vvsa_layout_mod = -0.16
    elif layout == "format_c":
        # Formato C: Smart Frame 4:5 (70.3%) buen impacto con zonas de seguridad limpias
        vvsa_layout_mod = 0.05
    elif layout == "format_d":
        # Formato D: Pro-Cinema 83.3% impacto visual superior para acción/físicas
        if archetype["id"] in ["rage9_physics", "weapons_rdr2_mechanics"]:
            vvsa_layout_mod = 0.09
        else:
            vvsa_layout_mod = 0.04
    else:
        vvsa_layout_mod = 0.0

    if strategy != "legacy_old":
        # Gancho Neón Superior + Subtítulo Pop de alta visibilidad
        vvsa_hook_mod = 0.08
    else:
        vvsa_hook_mod = -0.05

    if is_silent_risk:
        # Vídeo sin audio o con música plana: el usuario lo descarta al instante
        vvsa_audio_mod = -0.35
    else:
        vvsa_audio_mod = 0.03

    vvsa = min(0.95, max(0.20, base_vvsa + vvsa_layout_mod + vvsa_hook_mod + vvsa_audio_mod + random.gauss(0, 0.04)))

    # 2. APV (Average Percentage Viewed) y AVD (Average View Duration):
    # La retención a lo largo del vídeo
    if is_silent_risk:
        apv = random.uniform(0.15, 0.35)
    else:
        # Clips más cortos tienen mayor % por loop; clips más largos acumulan más segundos netos
        if duration <= 25.0:
            # Posibilidad de ver > 100% (loop replay)
            loop_chance = 0.35 if strategy != "legacy_old" else 0.10
            base_apv = 1.05 if random.random() < loop_chance else 0.88
        elif duration <= 40.0:
            base_apv = 0.82
        else:
            base_apv = 0.74

        # Modificador por corte natural (Subtitle Snapping):
        # En el sistema antiguo se cortaban frases a la mitad (-18% retención)
        if strategy == "legacy_old":
            snapping_mod = -0.18
        else:
            snapping_mod = 0.06

        apv = min(1.40, max(0.25, base_apv + snapping_mod + random.gauss(0, 0.05)))

    # AVD en segundos absolutos:
    avd_seconds = duration * apv

    # 3. Tasa de Engagement (Likes, Comentarios, Compartidos):
    if is_silent_risk or vvsa < 0.50:
        like_rate = random.uniform(0.01, 0.03)
        share_rate = random.uniform(0.001, 0.005)
    else:
        like_rate = random.uniform(0.05, 0.11)
        share_rate = random.uniform(0.01, 0.035)

    # 4. Simulación del Embudo de Impresiones Algorítmico:
    # YouTube Shorts / TikTok Seed Phase:
    if channel_type == "new_channel":
        seed_impressions = random.randint(1200, 2500)
    else:
        seed_impressions = random.randint(3500, 7500)

    # Nivel 1: Vistas en fase de prueba (Seed Phase)
    seed_views = int(seed_impressions * vvsa)

    # Nivel 2: Algoritmo evalúa métricas de salida del seed:
    # Condiciones de Breakout:
    # - VVSA >= 70%
    # - Y (APV >= 85% para clips cortos O AVD >= 24s para clips de 30-55s)
    # - Y Like Rate >= 4.5%
    is_breakout_candidate = (
        vvsa >= 0.70 and
        (apv >= 0.85 or avd_seconds >= 24.0) and
        like_rate >= 0.045
    )

    is_viral_candidate = (
        vvsa >= 0.77 and
        (apv >= 0.98 or avd_seconds >= 32.0) and
        like_rate >= 0.065 and
        share_rate >= 0.015
    )

    if is_silent_risk or vvsa < 0.60:
        # Fiasco / Flatline: el algoritmo detiene la distribución casi inmediatamente
        multiplier = random.uniform(1.0, 1.4)
        tier = "flop_stagnant"
    elif not is_breakout_candidate:
        # Rendimiento moderado estándar
        multiplier = random.uniform(1.8, 3.8)
        tier = "standard_tier"
    elif not is_viral_candidate:
        # Breakout Tier 1 (Recomendación activa en el feed Shorts)
        multiplier = random.uniform(8.0, 25.0)
        tier = "breakout_tier"
    else:
        # Mega Viral Tier 2 (Distribución masiva continua)
        multiplier = random.uniform(35.0, 150.0)
        tier = "viral_hit"

    total_views = int(seed_views * multiplier)

    return {
        "archetype": archetype["name"],
        "strategy": strategy,
        "layout": layout,
        "duration": round(duration, 1),
        "vvsa": round(vvsa * 100, 1),
        "apv": round(apv * 100, 1),
        "avd_seconds": round(avd_seconds, 1),
        "views": total_views,
        "tier": tier,
        "is_breakout": total_views >= 10000,
        "is_viral": total_views >= 50000
    }

def run_comparative_forecast(runs_per_strategy: int = 1000):
    strategies = ["legacy_old", "format_c_only", "format_d_only", "adaptive_smart"]
    results = {s: [] for s in strategies}

    for s in strategies:
        for _ in range(runs_per_strategy):
            # Selección ponderada del arquetipo
            r = random.random()
            cum = 0.0
            chosen_arch = CONTENT_ARCHETYPES[0]
            for arch in CONTENT_ARCHETYPES:
                cum += arch["share_of_content"]
                if r <= cum:
                    chosen_arch = arch
                    break
            sim = simulate_clip_performance(chosen_arch, s, channel_type="new_channel")
            results[s].append(sim)

    # Análisis estadístico comparativo
    summary = {}
    for s, data in results.items():
        views_list = [d["views"] for d in data]
        vvsa_list = [d["vvsa"] for d in data]
        apv_list = [d["apv"] for d in data]
        avd_list = [d["avd_seconds"] for d in data]

        breakout_count = sum(1 for d in data if d["is_breakout"])
        viral_count = sum(1 for d in data if d["is_viral"])
        flop_count = sum(1 for d in data if d["tier"] == "flop_stagnant")

        summary[s] = {
            "total_simulations": runs_per_strategy,
            "median_views": int(statistics.median(views_list)),
            "mean_views": int(statistics.mean(views_list)),
            "min_views": min(views_list),
            "max_views": max(views_list),
            "avg_vvsa_pct": round(statistics.mean(vvsa_list), 1),
            "avg_apv_pct": round(statistics.mean(apv_list), 1),
            "avg_avd_seconds": round(statistics.mean(avd_list), 1),
            "flop_rate_pct": round((flop_count / runs_per_strategy) * 100, 1),
            "breakout_rate_gt_10k_pct": round((breakout_count / runs_per_strategy) * 100, 1),
            "viral_rate_gt_50k_pct": round((viral_count / runs_per_strategy) * 100, 1)
        }

    # Guardar reporte detallado
    report_path = Path("data/views_forecast_simulation.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary

if __name__ == "__main__":
    summary = run_comparative_forecast(1000)
    print(json.dumps(summary, indent=2))
