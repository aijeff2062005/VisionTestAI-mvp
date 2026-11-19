#!/usr/bin/env python3
"""Calibrate stand-zone HSV / fixed polygon for SmartEyes.

Click white floor (or tape) pixels; press:
  s  — print suggested floor_hsv / tape hsv
  p  — add current click as fixed_polygon vertex (normalized)
  d  — dump fixed_polygon YAML
  q  — quit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera_utils import open_video_capture, resolve_source
from src.config_loader import load_config
from src.line_detector import FloorLineDetector

_samples: list[np.ndarray] = []
_poly_pts: list[tuple[float, float]] = []
_last_click: tuple[int, int] | None = None


def _on_mouse(event, x, y, _flags, param) -> None:
    global _last_click
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    frame = param["frame"]
    h, w = frame.shape[:2]
    _last_click = (x, y)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    patch = hsv[max(0, y - 2) : y + 3, max(0, x - 2) : x + 3]
    if patch.size == 0:
        return
    mean = patch.reshape(-1, 3).mean(axis=0)
    _samples.append(mean)
    print(
        f"Sample @({x},{y}) HSV: H={mean[0]:.0f} S={mean[1]:.0f} V={mean[2]:.0f}  "
        f"norm=({x / w:.3f}, {y / h:.3f})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="macbook")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args()

    source = args.source
    if str(source).isdigit():
        source = int(source)

    cfg = load_config(ROOT / args.config)
    detector = FloorLineDetector(cfg)

    cap = open_video_capture(source)
    print(f"Opened {resolve_source(source)!r}")
    print("Click floor | s=HSV summary | p=add polygon point | d=dump polygon | q=quit")
    cv2.namedWindow("calibrate_zone")
    state: dict = {"frame": None}

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            state["frame"] = frame
            cv2.setMouseCallback("calibrate_zone", _on_mouse, state)
            band = detector.detect(frame)
            vis = frame.copy()
            if band.found and band.polygon is not None:
                cv2.polylines(vis, [band.polygon], True, (0, 255, 255), 2)
                x, y, bw, bh = cv2.boundingRect(band.polygon)
                cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 200, 255), 1)
                cv2.putText(
                    vis,
                    band.label,
                    (x, max(24, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
            for nx, ny in _poly_pts:
                px, py = int(nx * frame.shape[1]), int(ny * frame.shape[0])
                cv2.circle(vis, (px, py), 5, (255, 80, 255), -1)
            if _last_click:
                cv2.circle(vis, _last_click, 6, (0, 0, 255), 2)
            cv2.putText(
                vis,
                "click floor | s=HSV | p=poly pt | d=dump | q=quit",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
            )
            cv2.imshow("calibrate_zone", vis)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("p") and _last_click is not None:
                h, w = frame.shape[:2]
                nx, ny = _last_click[0] / w, _last_click[1] / h
                _poly_pts.append((nx, ny))
                print(f"Polygon point {_poly_pts[-1]}")
            if key == ord("d") and _poly_pts:
                print("fixed_polygon:")
                for nx, ny in _poly_pts:
                    print(f"  - [{nx:.3f}, {ny:.3f}]")
            if key == ord("s") and _samples:
                arr = np.array(_samples)
                # Floor suggestion: expand S upward a bit, keep V low bound
                s_hi = int(min(255, arr[:, 1].max() + 25))
                v_lo = int(max(0, arr[:, 2].min() - 20))
                print("Suggested floor HSV (configs/default.yaml):")
                print(f"  floor_hsv_low: [0, 0, {v_lo}]")
                print(f"  floor_hsv_high: [179, {max(s_hi, 40)}, 255]")
                lo = np.clip(arr.min(axis=0) - [8, 40, 40], [0, 0, 0], [179, 255, 255])
                hi = np.clip(arr.max(axis=0) + [8, 40, 40], [0, 0, 0], [179, 255, 255])
                print("If using tape mode instead:")
                print(f"  hsv_low: [{int(lo[0])}, {int(lo[1])}, {int(lo[2])}]")
                print(f"  hsv_high: [{int(hi[0])}, {int(hi[1])}, {int(hi[2])}]")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
