from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.stand_zone import (
    ensure_track_box,
    load_stand_zone_file,
    merge_stand_zone_into_cfg,
    seed_stand_zone_from_cfg,
    stand_zone_path_for_config,
    save_stand_zone_file,
)


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    zone_path = stand_zone_path_for_config(path)
    zone = load_stand_zone_file(zone_path)
    if zone is None:
        # Seed sidecar from yaml fixed_polygon so first boot has a zone.
        seeded = seed_stand_zone_from_cfg(cfg)
        if seeded.get("polygon"):
            try:
                save_stand_zone_file(zone_path, seeded)
                zone = seeded
            except OSError:
                zone = seeded
    elif isinstance(zone, dict) and zone.get("track_box") is None and zone.get("detect_box") is None:
        # Backfill track_box on older sidecars so YOLO crop stays independent of stand hull.
        zone = dict(zone)
        zone["track_box"] = ensure_track_box(zone)
        try:
            save_stand_zone_file(zone_path, zone)
        except OSError:
            pass
    merge_stand_zone_into_cfg(cfg, zone)
    return cfg


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent
