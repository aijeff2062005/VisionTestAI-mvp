"""Static stand-zone sidecar helpers (persist + track-box crop geometry)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from src.line_detector import FloorLineDetector, LineBand


STAND_ZONE_FILENAME = "stand_zone.json"
DEFAULT_X_PAD_FRAC = 0.02
# Clinic-ish full-height corridor when no polygon is available to seed from.
DEFAULT_TRACK_BOX = [0.25, 0.0, 0.92, 1.0]


class _HasBBox(Protocol):
    bbox: tuple[int, int, int, int]


def stand_zone_path_for_config(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / STAND_ZONE_FILENAME


def default_stand_zone_path(project_root: Path) -> Path:
    return project_root / "configs" / STAND_ZONE_FILENAME


def normalize_polygon(points: list[list[float]], *, max_points: int = 8) -> list[list[float]]:
    """Clamp, convex-hull, and keep 3–max_points normalized vertices."""
    cleaned: list[list[float]] = []
    for p in points or []:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        x = float(max(0.0, min(1.0, float(p[0]))))
        y = float(max(0.0, min(1.0, float(p[1]))))
        cleaned.append([x, y])
    if len(cleaned) < 3:
        raise ValueError("stand zone needs at least 3 points")
    pts = np.array(cleaned, dtype=np.float32).reshape(-1, 1, 2)
    # convexHull expects pixel-ish ints for stability; scale then rescale
    scaled = (pts * 10000.0).astype(np.int32)
    hull = cv2.convexHull(scaled)
    if hull is None or len(hull) < 3:
        raise ValueError("convex hull failed for stand zone")
    out = [[float(p[0][0]) / 10000.0, float(p[0][1]) / 10000.0] for p in hull]
    if len(out) > max_points:
        idx = np.linspace(0, len(out) - 1, num=max_points, dtype=int)
        out = [out[i] for i in sorted(set(idx.tolist()))]
        if len(out) < 3:
            out = [[float(p[0][0]) / 10000.0, float(p[0][1]) / 10000.0] for p in hull[:max_points]]
    return out


def normalize_track_box(box: list[float] | tuple[float, ...] | None) -> list[float]:
    """Clamp axis-aligned track box to normalized [x0, y0, x1, y1] with x0<x1, y0<y1."""
    if box is None or not isinstance(box, (list, tuple)) or len(box) < 4:
        raise ValueError("track_box needs [x0, y0, x1, y1]")
    x0 = float(max(0.0, min(1.0, float(box[0]))))
    y0 = float(max(0.0, min(1.0, float(box[1]))))
    x1 = float(max(0.0, min(1.0, float(box[2]))))
    y1 = float(max(0.0, min(1.0, float(box[3]))))
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)
    top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
    if right - left < 1e-4 or bottom - top < 1e-4:
        raise ValueError("track_box is degenerate")
    return [left, top, right, bottom]


def default_track_box_from_polygon(
    polygon: list[list[float]] | None,
    *,
    x_pad_frac: float = DEFAULT_X_PAD_FRAC,
) -> list[float]:
    """
    Seed track box as full-height vertical corridor of the stand AABB
    (x from polygon ± pad, y from 0..1). Falls back to DEFAULT_TRACK_BOX.
    """
    try:
        poly = list(polygon or [])
        if len(poly) < 3:
            return list(DEFAULT_TRACK_BOX)
        xs = [float(p[0]) for p in poly if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(xs) < 3:
            return list(DEFAULT_TRACK_BOX)
        x_min = min(xs)
        x_max = max(xs)
        pad = max(0.0, float(x_pad_frac))
        return normalize_track_box([x_min - pad, 0.0, x_max + pad, 1.0])
    except (TypeError, ValueError):
        return list(DEFAULT_TRACK_BOX)


def track_box_to_pixel_roi(
    box: list[float] | tuple[float, ...] | None,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int] | None:
    """Convert normalized track_box to inclusive-exclusive pixel ROI (x0,y0,x1,y1)."""
    try:
        nb = normalize_track_box(box)
    except ValueError:
        return None
    w = max(1, int(frame_w))
    h = max(1, int(frame_h))
    x0 = int(round(nb[0] * w))
    y0 = int(round(nb[1] * h))
    x1 = int(round(nb[2] * w))
    y1 = int(round(nb[3] * h))
    x0 = max(0, min(w - 1, x0))
    y0 = max(0, min(h - 1, y0))
    x1 = max(0, min(w, x1))
    y1 = max(0, min(h, y1))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def load_stand_zone_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    return data


def save_stand_zone_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def ensure_track_box(zone: dict[str, Any]) -> list[float]:
    """Return a valid track_box from zone, seeding from polygon when missing."""
    raw = zone.get("track_box")
    if raw is None and zone.get("detect_box") is not None:
        raw = zone.get("detect_box")
    try:
        return normalize_track_box(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default_track_box_from_polygon(zone.get("polygon"))


def merge_stand_zone_into_cfg(cfg: dict[str, Any], zone: dict[str, Any] | None) -> dict[str, Any]:
    """Apply sidecar mode / polygon / detect_in_zone / track_box onto a config dict (in place)."""
    if not zone:
        return cfg
    line = dict(cfg.get("line") or {})
    model = dict(cfg.get("model") or {})
    mode = zone.get("mode")
    if mode is not None:
        line["mode"] = str(mode).lower()
    poly = zone.get("polygon")
    if poly is not None:
        try:
            line["fixed_polygon"] = normalize_polygon(list(poly))
        except ValueError:
            pass
    if "detect_in_zone" in zone:
        model["detect_in_zone"] = bool(zone.get("detect_in_zone"))
    track = ensure_track_box(zone if isinstance(zone, dict) else {})
    model["track_box"] = track
    cfg["line"] = line
    cfg["model"] = model
    return cfg


def seed_stand_zone_from_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build a sidecar payload from yaml defaults (first boot before anyone draws)."""
    line = cfg.get("line") or {}
    model = cfg.get("model") or {}
    poly = line.get("fixed_polygon") or []
    try:
        polygon = normalize_polygon(list(poly)) if len(poly) >= 3 else []
    except ValueError:
        polygon = []
    mode = str(line.get("mode") or "fixed").lower()
    detect = bool(model.get("detect_in_zone", mode == "fixed"))
    raw_box = model.get("track_box")
    try:
        track_box = normalize_track_box(raw_box) if raw_box is not None else default_track_box_from_polygon(polygon)
    except (TypeError, ValueError):
        track_box = default_track_box_from_polygon(polygon)
    return {
        "mode": mode,
        "detect_in_zone": detect,
        "tool": "seed",
        "polygon": polygon,
        "track_box": track_box,
    }


def corridor_roi(
    band: LineBand,
    frame_w: int,
    frame_h: int,
    *,
    x_pad_frac: float = DEFAULT_X_PAD_FRAC,
) -> tuple[int, int, int, int] | None:
    """
    Legacy helper: AABB of stand polygon expanded to frame top (+ x pad).
    Prefer track_box_to_pixel_roi for YOLO crop; kept for tests / migration.
    """
    if not band.found or band.polygon is None or len(band.polygon) < 3:
        return None
    pts = band.polygon.reshape(-1, 2)
    x_min = int(np.min(pts[:, 0]))
    x_max = int(np.max(pts[:, 0]))
    y_max = int(np.max(pts[:, 1]))
    frac = float(x_pad_frac)
    if frac <= 0:
        pad = 0
    else:
        pad = max(2, int(round(frame_w * frac)))
    x0 = max(0, x_min - pad)
    x1 = min(frame_w, x_max + pad)
    y0 = 0
    y1 = min(frame_h, max(y_max + max(pad, 1), y0 + 1))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def feet_point(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    x1, _y1, x2, y2 = bbox
    return (int((x1 + x2) / 2), int(y2))


def filter_detections_in_zone(detections: list[_HasBBox], band: LineBand) -> list[_HasBBox]:
    if not band.found:
        return []
    kept: list[_HasBBox] = []
    for det in detections:
        if FloorLineDetector.point_in_zone(band, feet_point(det.bbox)):
            kept.append(det)
    return kept


def pick_largest(detections: list[_HasBBox]) -> _HasBBox | None:
    if not detections:
        return None
    return max(
        detections,
        key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]),
    )


def legacy_stand_zone_payload(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Rollback snapshot: HSV auto-floor + full-frame YOLO; keep polygon/track_box for later."""
    base = dict(existing or {})
    track = ensure_track_box(base)
    return {
        "mode": "floor",
        "detect_in_zone": False,
        "tool": "legacy",
        "polygon": list(base.get("polygon") or []),
        "track_box": track,
    }
