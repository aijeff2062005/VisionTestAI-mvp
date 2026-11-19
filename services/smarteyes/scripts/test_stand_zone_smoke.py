"""Unit checks for static stand-zone helpers (no YOLO)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.line_detector import FloorLineDetector, LineBand  # noqa: E402
from src.stand_zone import (  # noqa: E402
    corridor_roi,
    default_track_box_from_polygon,
    ensure_track_box,
    filter_detections_in_zone,
    legacy_stand_zone_payload,
    merge_stand_zone_into_cfg,
    normalize_polygon,
    normalize_track_box,
    pick_largest,
    save_stand_zone_file,
    load_stand_zone_file,
    track_box_to_pixel_roi,
)


@dataclass
class FakeDet:
    bbox: tuple[int, int, int, int]
    confidence: float = 1.0


def test_normalize_polygon_hull() -> None:
    pts = [[0.2, 0.9], [0.8, 0.9], [0.7, 0.5], [0.5, 0.7], [0.3, 0.5]]
    hull = normalize_polygon(pts)
    assert 3 <= len(hull) <= 8
    assert all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in hull)


def test_corridor_roi_expands_to_top() -> None:
    """Legacy helper still works; YOLO crop uses track_box instead."""
    poly = np.array(
        [[[200, 400]], [[600, 400]], [[550, 300]], [[250, 300]]],
        dtype=np.int32,
    )
    band = LineBand(found=True, polygon=poly, mode="fixed")
    roi = corridor_roi(band, 800, 600, x_pad_frac=0.0)
    assert roi is not None
    x0, y0, x1, y1 = roi
    assert y0 == 0
    assert x0 == 200
    assert x1 == 600
    assert y1 >= 400


def test_track_box_independent_of_hull() -> None:
    box = normalize_track_box([0.9, 0.8, 0.1, 0.2])
    assert box == [0.1, 0.2, 0.9, 0.8]
    roi = track_box_to_pixel_roi(box, 1000, 500)
    assert roi == (100, 100, 900, 400)
    seeded = default_track_box_from_polygon(
        [[0.28, 0.98], [0.90, 0.98], [0.78, 0.48], [0.36, 0.48]],
        x_pad_frac=0.0,
    )
    assert seeded[0] == 0.28
    assert seeded[1] == 0.0
    assert seeded[2] == 0.90
    assert seeded[3] == 1.0
    # Missing track_box seeds from polygon corridor, not coupled at runtime
    zone = {"polygon": [[0.2, 0.9], [0.8, 0.9], [0.7, 0.5], [0.3, 0.5]]}
    tb = ensure_track_box(zone)
    assert len(tb) == 4
    assert tb[1] == 0.0 and tb[3] == 1.0


def test_filter_and_pick_in_zone() -> None:
    poly = np.array(
        [[[100, 100]], [[300, 100]], [[300, 300]], [[100, 300]]],
        dtype=np.int32,
    )
    band = LineBand(found=True, polygon=poly, mode="fixed")
    inside = FakeDet(bbox=(150, 50, 200, 200))  # feet at (175, 200)
    outside = FakeDet(bbox=(400, 50, 500, 200))  # feet at (450, 200)
    kept = filter_detections_in_zone([inside, outside], band)
    assert kept == [inside]
    assert pick_largest([inside, FakeDet(bbox=(120, 40, 280, 280))]) is not None


def test_fixed_mode_detector() -> None:
    cfg = {
        "line": {
            "mode": "fixed",
            "fixed_polygon": [[0.1, 0.9], [0.9, 0.9], [0.8, 0.5], [0.2, 0.5]],
        }
    }
    det = FloorLineDetector(cfg)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    band = det.detect(frame)
    assert band.found
    assert band.mode == "fixed"
    # floor / tape paths still callable
    assert hasattr(det, "_detect_floor")
    assert hasattr(det, "_detect_tape")
    det.apply_stand_zone(mode="floor")
    assert det.mode == "floor"


def test_merge_and_legacy_sidecar(tmp_path: Path | None = None) -> None:
    cfg = {
        "line": {"mode": "fixed", "fixed_polygon": [[0.2, 0.8], [0.8, 0.8], [0.7, 0.4], [0.3, 0.4]]},
        "model": {"detect_in_zone": True},
    }
    zone = {
        "mode": "floor",
        "detect_in_zone": False,
        "polygon": [[0.2, 0.8], [0.8, 0.8], [0.7, 0.4], [0.3, 0.4]],
        "track_box": [0.15, 0.0, 0.85, 1.0],
        "tool": "legacy",
    }
    merge_stand_zone_into_cfg(cfg, zone)
    assert cfg["line"]["mode"] == "floor"
    assert cfg["model"]["detect_in_zone"] is False
    assert cfg["model"]["track_box"] == [0.15, 0.0, 0.85, 1.0]
    legacy = legacy_stand_zone_payload(zone)
    assert legacy["mode"] == "floor"
    assert legacy["detect_in_zone"] is False
    assert legacy["track_box"] == [0.15, 0.0, 0.85, 1.0]

    path = (tmp_path or Path("/tmp")) / "stand_zone.json"
    if tmp_path is None:
        path = Path("/tmp/stand_zone_smoke.json")
    save_stand_zone_file(path, legacy)
    loaded = load_stand_zone_file(path)
    assert loaded is not None
    assert loaded["tool"] == "legacy"
    assert json.loads(path.read_text())["detect_in_zone"] is False
    assert json.loads(path.read_text())["track_box"] == [0.15, 0.0, 0.85, 1.0]


if __name__ == "__main__":
    test_normalize_polygon_hull()
    test_corridor_roi_expands_to_top()
    test_track_box_independent_of_hull()
    test_filter_and_pick_in_zone()
    test_fixed_mode_detector()
    test_merge_and_legacy_sidecar()
    # config_loader merge smoke
    from src.config_loader import load_config, project_root

    cfg = load_config(project_root() / "configs" / "clinic_jetson.yaml")
    assert cfg["line"]["mode"] in ("fixed", "floor", "tape")
    assert "detect_in_zone" in cfg["model"]
    assert "track_box" in cfg["model"]
    assert len(cfg["model"]["track_box"]) == 4
    print(
        "stand_zone smoke OK",
        cfg["line"]["mode"],
        cfg["model"]["detect_in_zone"],
        cfg["model"]["track_box"],
    )
