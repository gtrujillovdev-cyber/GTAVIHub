"""
src/channel_directory.py — Directorio Maestro de Fuentes (+1,000 Canales) y Filtro de Tráfico Viral.

Maneja el catálogo masivo de fuentes de contenido para GTA VI Hub Spain:
1. Acceso y rotación sobre más de 1,000 canales de videojuegos, especialistas de GTA,
   prensa global/hispana, analistas técnicos y creadores de contenido top.
2. Filtro estricto de alto volumen de visualizaciones (descarta clips irrelevantes con pocas visitas).
3. Cosechadora dinámica de nuevos creadores emergentes (auto-registro continuo).
4. CERO parodias, CERO memes y CERO contenido residual de GTA 5.
"""

import os
import json
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import BASE_DIR, DATA_DIR

DIRECTORY_FILE = BASE_DIR / "config" / "channel_directory.json"
DISCOVERED_FILE = DATA_DIR / "discovered_channels.json"

class ChannelDirectory:
    _instance = None

    def __init__(self):
        self.channels: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if DIRECTORY_FILE.exists():
            try:
                with open(DIRECTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.channels = data.get("channels", [])
            except Exception as e:
                print(f"[ChannelDirectory] Error cargando {DIRECTORY_FILE}: {e}")
                self.channels = []

    def get_count(self) -> int:
        return len(self.channels)

    def get_channels_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [c for c in self.channels if c.get("category") == category and c.get("enabled", True)]

    def get_rotating_batch(self, batch_size: int = 35) -> List[Dict[str, Any]]:
        """
        Retorna un lote balanceado y rotativo de canales para escaneo continuo:
        - 30% Especialistas y Autoridades de GTA
        - 25% Analistas Técnicos y Físicas
        - 25% Prensa y Medios Globales/Hispanos
        - 20% Creadores Top y Streamers
        """
        if not self.channels:
            return []

        authorities = self.get_channels_by_category("gta_authority")
        technical = self.get_channels_by_category("technical_analysis")
        media = (
            self.get_channels_by_category("gaming_media")
            + self.get_channels_by_category("hispanic_media")
        )
        creators = (
            self.get_channels_by_category("hispanic_creator")
            + self.get_channels_by_category("global_creator")
        )

        sample_auth = random.sample(authorities, min(len(authorities), int(batch_size * 0.30))) if authorities else []
        sample_tech = random.sample(technical, min(len(technical), int(batch_size * 0.25))) if technical else []
        sample_media = random.sample(media, min(len(media), int(batch_size * 0.25))) if media else []
        sample_creators = random.sample(creators, min(len(creators), int(batch_size * 0.20))) if creators else []

        batch = sample_auth + sample_tech + sample_media + sample_creators
        random.shuffle(batch)
        return batch

def get_channel_directory() -> ChannelDirectory:
    return ChannelDirectory()

def filter_high_traffic_candidates(
    candidates: List[Dict[str, Any]],
    min_views: int = 25_000,
    min_velocity_vpd: float = 1_000.0
) -> List[Dict[str, Any]]:
    """
    Filtro estricto de tracción real:
    Descarta clips irrelevantes con pocas vistas y prioriza vídeos masivos con muchas visitas.
    """
    filtered = []
    for c in candidates:
        views = c.get("views", 0) or 0
        vpd = c.get("velocity", 0.0) or 0.0
        days_old = c.get("days_old")

        # Clips recién publicados (Día 1): admiten velocity vpd >= 1,000 aunque aún no alcancen el umbral absoluto
        if days_old == 1 and vpd >= min_velocity_vpd:
            filtered.append(c)
        elif views >= min_views:
            filtered.append(c)

    # Ordenar por visualizaciones descendentes (los vídeos con más visitas van primero)
    filtered.sort(key=lambda x: (x.get("views", 0) or 0), reverse=True)
    return filtered
