#!/usr/bin/env python3
"""Create synthetic smoke.mp4 with white ceramic stand zone + stick figure."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample" / "smoke.mp4"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    w, h, fps, n = 640, 480, 20, 60
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(OUT), fourcc, fps, (w, h))

    for i in range(n):
        frame = np.full((h, w, 3), 45, dtype=np.uint8)
        # Dark far room
        frame[0:220, 180:460] = (35, 30, 28)

        # White ceramic stand zone (trapezoid corridor)
        zone = np.array(
            [[160, h - 5], [520, h - 5], [430, 230], [220, 230]],
            dtype=np.int32,
        )
        cv2.fillPoly(frame, [zone], (235, 235, 232))
        # Tile grid hint
        for yy in range(240, h, 40):
            cv2.line(frame, (180, yy), (500, yy), (210, 210, 210), 1)

        # Stick person with ankles in zone
        cx = int(w * 0.5 + 15 * np.sin(i * 0.08))
        head_y = 140
        ankle_y = 400
        cv2.circle(frame, (cx, head_y), 28, (200, 180, 160), -1)
        cv2.ellipse(frame, (cx - 32, head_y), (10, 18), 0, 0, 360, (20, 20, 20), -1)
        cv2.ellipse(frame, (cx + 32, head_y), (10, 18), 0, 0, 360, (20, 20, 20), -1)
        cv2.line(frame, (cx - 28, head_y - 18), (cx + 28, head_y - 18), (30, 30, 30), 4)
        hip_y = 280
        cv2.line(frame, (cx, head_y + 28), (cx, hip_y), (180, 160, 140), 8)
        cv2.line(frame, (cx, hip_y), (cx - 25, ankle_y), (180, 160, 140), 6)
        cv2.line(frame, (cx, hip_y), (cx + 25, ankle_y), (180, 160, 140), 6)
        cv2.circle(frame, (cx - 25, ankle_y), 6, (100, 100, 220), -1)
        cv2.circle(frame, (cx + 25, ankle_y), 6, (100, 100, 220), -1)

        writer.write(frame)

    writer.release()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
