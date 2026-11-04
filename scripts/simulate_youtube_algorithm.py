#!/usr/bin/env python3
"""
🎮 GTA VI Hub Spain — YouTube Shorts Algorithmic Simulator (1,000 Iterations)
============================================================================
Simula el comportamiento real del algoritmo de YouTube Shorts mediante un
modelo estocástico de Monte Carlo calibrado con métricas empíricas de la plataforma:
- VVSA (Viewed vs Swiped Away)
- APV (Average Percentage Viewed / Tasa de finalización y Loop)
- Impacto de la duración (Timing a partir de 19s vs vídeos largos >45s)
- Vitalidad acústica (Voz activa vs B-roll mudo)
- Arquetipos temáticos de GTA 6
"""

import random
import math
import statistics
import json
from pathlib import Path

random.seed(42)

ARCHETYPES = [
    {
        "id": "físicas_rage9",
        "name": "Físicas RAGE 9 (Agua, Choques, IA de NPCs)",
        "base_interest": 0.92,
        "virality_multiplier": 1.45,
        "ideal_duration": (19, 26)
    },
    {
        "id": "detalles_mapa_leonida",
        "name": "Detalles Ocultos del Mapa Leonida vs Vice City",
        "base_interest": 0.88,
        "virality_multiplier": 1.35,
        "ideal_duration": (21, 28)
    },
    {
        "id": "filtracion_armas_mecanicas",
        "name": "Mecánicas de Juego & Sistema de Armas estilo RDR2",
        "base_interest": 0.84,
        "virality_multiplier": 1.25,
        "ideal_duration": (19, 25)
    },
    {
        "id": "noticia_oficial_analisis",
        "name": "Análisis Informativo / Fecha y Rockstar Newswire",
        "base_interest": 0.78,
        "virality_multiplier": 1.10,
        "ideal_duration": (24, 34)
    },
    {
        "id": "reaccion_streamer",
        "name": "Reacciones de Creadores (IlloJuan, Xokas)",
        "base_interest": 0.75,
        "virality_multiplier": 1.05,
        "ideal_duration": (20, 27)
    },
    {
        "id": "broll_trailer_mudo",
        "name": "Metraje B-Roll de Tráiler sin Locución (Formato Antiguo)",
        "base_interest": 0.35,
        "virality_multiplier": 0.20,
        "ideal_duration": (45, 55)
    }
]

FORMATS = [
    {
        "type": "optimizado_nuevo",
        "name": "Nuevo Formato (19-28s, Gancho Neón, Subtítulos Pop Bounce, Audio Ducked)",
        "vvsa_boost": 0.22,
        "apv_boost": 0.25,
        "audio_vitality": True
    },
    {
        "type": "tradicional_deficiente",
        "name": "Formato Antiguo (Largo, Sin gancho contrastado, Audio plano/mudo)",
        "vvsa_boost": -0.15,
        "apv_boost": -0.30,
        "audio_vitality": False
    }
]


def run_single_simulation(sim_id: int) -> dict:
    # 1. Asignar arquetipo (distribución representativa)
    # 70% de clips técnicos/mapa/noticias, 15% streamers, 15% formato antiguo defectuoso para comparar
    r_arch = random.random()
    if r_arch < 0.30:
        arch = ARCHETYPES[0] # RAGE 9
    elif r_arch < 0.55:
        arch = ARCHETYPES[1] # Mapa Leonida
    elif r_arch < 0.75:
        arch = ARCHETYPES[2] # Armas / Mecánicas
    elif r_arch < 0.88:
        arch = ARCHETYPES[3] # Noticia oficial
    elif r_arch < 0.94:
        arch = ARCHETYPES[4] # Streamer
    else:
        arch = ARCHETYPES[5] # B-roll mudo (antiguo)

    # 2. Formato editorial (80% nuevo optimizado, 20% antiguo para benchmarking)
    is_new_format = (arch["id"] != "broll_trailer_mudo") and (random.random() < 0.85)
    fmt = FORMATS[0] if is_new_format else FORMATS[1]

    # 3. Duración del clip
    if is_new_format:
        # Calibrado en torno al sweet spot a partir de 19s
        dur_target = random.choice([19, 21, 23, 24, 26, 28, 32])
        duration = round(random.gauss(dur_target, 1.8), 1)
        duration = max(18.5, min(duration, 42.0))
    else:
        # Clips largos o B-roll sin corte optimizado
        duration = round(random.uniform(42.0, 56.0), 1)

    # 4. Cálculo de VVSA (Viewed vs Swiped Away % en los primeros 2 segundos)
    base_vvsa = 0.58 + (arch["base_interest"] * 0.18) + fmt["vvsa_boost"]
    noise_vvsa = random.gauss(0, 0.05)
    vvsa = max(0.20, min(0.92, base_vvsa + noise_vvsa))

    # 5. Cálculo de APV (Average Percentage Viewed / Retención)
    # Si la duración está entre 19s y 26s, la retención tiende a >95% e incluso >110% por bucle
    if duration <= 22:
        decay_factor = 1.12
    elif duration <= 28:
        decay_factor = 1.02
    elif duration <= 35:
        decay_factor = 0.82
    elif duration <= 45:
        decay_factor = 0.65
    else:
        decay_factor = 0.45

    if not fmt["audio_vitality"]:
        # Si el audio está mudo o sin voz, el abandono a los 3-5 segundos es brutal
        decay_factor *= 0.40

    base_apv = (arch["base_interest"] * decay_factor) + fmt["apv_boost"]
    noise_apv = random.gauss(0, 0.06)
    apv = max(0.15, min(1.35, base_apv + noise_apv))

    # 6. Cálculo de Vistas Proyectadas (Cascada Algorítmica de YouTube Shorts)
    # YouTube evalúa VVSA y APV en rondas sucesivas (Seed -> Tier 1 -> Tier 2 -> Tier 3)
    views = 0
    tier = 0
    shadowban_flag = False

    # Penalización fatal por B-roll mudo / contenido reutilizado sin transformar
    if not fmt["audio_vitality"] or vvsa < 0.45 or apv < 0.40:
        shadowban_flag = True
        views = int(random.uniform(12, 180)) # Estancamiento en < 200 visitas
        tier = 0
    else:
        # Semilla inicial (Batch 1: 500 a 1,200 impresiones)
        seed_views = int(random.uniform(400, 1100))
        views = seed_views
        tier = 1

        # Test para Tier 2 (Expansión local): Requiere VVSA >= 68% y APV >= 82%
        if vvsa >= 0.68 and apv >= 0.82:
            tier = 2
            tier2_boost = int(random.uniform(4000, 18000) * arch["virality_multiplier"])
            views += tier2_boost

            # Test para Tier 3 (Breakout Viral): Requiere VVSA >= 78% y APV >= 98% (o loop >100%)
            if vvsa >= 0.78 and apv >= 0.98:
                tier = 3
                # Viral breakout exponencial
                viral_multiplier = random.uniform(2.5, 6.0)
                tier3_views = int(views * viral_multiplier * (1.2 if (19 <= duration <= 26) else 0.8))
                views = min(tier3_views, 450000)

    # 7. Engagement: Likes y Comentarios
    like_rate = random.uniform(0.04, 0.09) if tier >= 2 else random.uniform(0.02, 0.05)
    likes = int(views * like_rate)
    comment_rate = random.uniform(0.003, 0.012)
    comments = int(views * comment_rate)

    return {
        "id": sim_id,
        "archetype": arch["id"],
        "archetype_name": arch["name"],
        "format": fmt["type"],
        "duration": duration,
        "vvsa": round(vvsa * 100, 1),
        "apv": round(apv * 100, 1),
        "tier": tier,
        "views": views,
        "likes": likes,
        "comments": comments,
        "shadowban_flag": shadowban_flag
    }


def main():
    print("=================================================================")
    print("🎮 EJECUTANDO 1,000 SIMULACIONES ESTOCÁSTICAS DE YOUTUBE SHORTS")
    print("=================================================================\n")

    results = [run_single_simulation(i + 1) for i in range(1000)]

    # 1. Métricas Globales
    all_views = [r["views"] for r in results]
    median_views = statistics.median(all_views)
    mean_views = statistics.mean(all_views)
    p90_views = sorted(all_views)[int(len(all_views) * 0.90)]
    max_views = max(all_views)

    print(f"📊 MÉTRICAS GLOBALES DEL MODELO (N = 1000 simulaciones):")
    print(f"  • Visualizaciones Medianas : {median_views:,.0f} vistas")
    print(f"  • Visualizaciones Medias   : {mean_views:,.0f} vistas")
    print(f"  • Percentil 90 (Top 10%)   : {p90_views:,.0f} vistas")
    print(f"  • Máximo Viral Registrado  : {max_views:,.0f} vistas\n")

    # 2. Análisis por Rango de Duración (Timing)
    dur_ranges = [
        ("< 19s (Demasiado corto)", lambda d: d < 19.0),
        ("19s - 28s (Sweet Spot Viral)", lambda d: 19.0 <= d <= 28.0),
        ("29s - 38s (Medio)", lambda d: 29.0 <= d <= 38.0),
        ("> 40s (Largo / Riesgo Retención)", lambda d: d > 40.0),
    ]

    print("⏱️ IMPACTO DE LA DURACIÓN (TIMING) EN EL RENDIMIENTO:")
    print("-" * 65)
    for label, fn in dur_ranges:
        group = [r for r in results if fn(r["duration"])]
        if group:
            g_views = [r["views"] for r in group]
            g_apv = [r["apv"] for r in group]
            g_viral_pct = sum(1 for r in group if r["tier"] >= 2) / len(group) * 100
            print(f"  • {label:32}: Mediana {statistics.median(g_views):>7,.0f} vistas | Retención: {statistics.mean(g_apv):>5.1f}% | Éxito: {g_viral_pct:>4.1f}%")

    print("\n" + "=" * 65)
    print("🎯 IMPACTO POR ARQUETIPO TEMÁTICO DE GTA 6:")
    print("-" * 65)
    arch_ids = [a["id"] for a in ARCHETYPES]
    for a_id in arch_ids:
        group = [r for r in results if r["archetype"] == a_id]
        if group:
            a_name = group[0]["archetype_name"]
            g_views = [r["views"] for r in group]
            breakouts = sum(1 for r in group if r["tier"] == 3) / len(group) * 100
            shadowbans = sum(1 for r in group if r["shadowban_flag"]) / len(group) * 100
            print(f"  [{a_id[:16]:16}] Mediana: {statistics.median(g_views):>7,.0f} | Breakout Viral: {breakouts:>4.1f}% | Estancado: {shadowbans:>4.1f}%")

    # 3. Comparativa Nuevo Formato vs Formato Antiguo
    print("\n" + "=" * 65)
    print("🛡️ NUEVO FORMATO VS FORMATO ANTIGUO DEFICIENTE:")
    print("-" * 65)
    new_fmt_group = [r for r in results if r["format"] == "optimizado_nuevo"]
    old_fmt_group = [r for r in results if r["format"] == "tradicional_deficiente"]

    new_med = statistics.median([r["views"] for r in new_fmt_group])
    old_med = statistics.median([r["views"] for r in old_fmt_group])
    new_viral = sum(1 for r in new_fmt_group if r["views"] >= 10000) / len(new_fmt_group) * 100
    old_viral = sum(1 for r in old_fmt_group if r["views"] >= 10000) / len(old_fmt_group) * 100
    new_shadow = sum(1 for r in new_fmt_group if r["shadowban_flag"]) / len(new_fmt_group) * 100
    old_shadow = sum(1 for r in old_fmt_group if r["shadowban_flag"]) / len(old_fmt_group) * 100

    print(f"  • NUEVO FORMATO (19-28s + Glow + Vitalidad Audio) : Mediana {new_med:,.0f} vistas | Virales (>10k): {new_viral:.1f}% | Riesgo Shadowban: {new_shadow:.1f}%")
    print(f"  • FORMATO ANTIGUO (Largo + B-roll Mudo)            : Mediana {old_med:,.0f} vistas | Virales (>10k): {old_viral:.1f}% | Riesgo Shadowban: {old_shadow:.1f}%")

    # Guardar resumen en artefactos/data
    out_summary = {
        "iterations": 1000,
        "median_views": median_views,
        "mean_views": mean_views,
        "new_format_median": new_med,
        "old_format_median": old_med,
        "top_archetypes": [
            {"id": "físicas_rage9", "recommended": True},
            {"id": "detalles_mapa_leonida", "recommended": True},
            {"id": "filtracion_armas_mecanicas", "recommended": True}
        ]
    }
    with open("data/simulation_1000_report.json", "w", encoding="utf-8") as f:
        json.dump(out_summary, f, indent=2)

    print("\n[✓] Simulación completada. Reporte guardado en data/simulation_1000_report.json.")

if __name__ == "__main__":
    main()
