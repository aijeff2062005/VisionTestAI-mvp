#!/usr/bin/env python3
"""Generate a minimal synthetic over_ear YOLO set for smoke training / packaging.

Replace with real Roboflow + clinic data for production (see datasets/headphones/README.md).
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "datasets" / "headphones" / "raw" / "synthetic"


def draw_headset(canvas: np.ndarray, rng: random.Random) -> tuple[int, int, int, int]:
    """Draw crude over-ear cups + band; return xyxy bbox."""
    h, w = canvas.shape[:2]
    cx = rng.randint(w // 4, 3 * w // 4)
    cy = rng.randint(h // 4, h // 2)
    cup_r = rng.randint(18, 40)
    gap = rng.randint(50, 110)
    color = (
        rng.randint(20, 80),
        rng.randint(20, 80),
        rng.randint(20, 200),
    )
    left = (cx - gap // 2, cy)
    right = (cx + gap // 2, cy)
    cv2.circle(canvas, left, cup_r, color, -1)
    cv2.circle(canvas, right, cup_r, color, -1)
    cv2.ellipse(canvas, (cx, cy - cup_r // 2), (gap // 2 + 4, cup_r), 0, 200, 340, color, 5)
    x1 = max(0, left[0] - cup_r - 4)
    y1 = max(0, cy - cup_r - gap // 4 - 8)
    x2 = min(w - 1, right[0] + cup_r + 4)
    y2 = min(h - 1, cy + cup_r + 4)
    return x1, y1, x2, y2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=640)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    train_img = OUT / "train" / "images"
    train_lab = OUT / "train" / "labels"
    for d in (train_img, train_lab):
        d.mkdir(parents=True, exist_ok=True)

    for i in range(args.n):
        canvas = np.zeros((args.size, args.size, 3), dtype=np.uint8)
        canvas[:] = (
            rng.randint(40, 180),
            rng.randint(40, 180),
            rng.randint(40, 180),
        )
        # noise blobs
        for _ in range(rng.randint(3, 12)):
            cv2.circle(
                canvas,
                (rng.randint(0, args.size - 1), rng.randint(0, args.size - 1)),
                rng.randint(5, 40),
                (
                    rng.randint(0, 255),
                    rng.randint(0, 255),
                    rng.randint(0, 255),
                ),
                -1,
            )
        x1, y1, x2, y2 = draw_headset(canvas, rng)
        cx = ((x1 + x2) / 2) / args.size
        cy = ((y1 + y2) / 2) / args.size
        bw = (x2 - x1) / args.size
        bh = (y2 - y1) / args.size
        stem = f"syn_{i:04d}"
        cv2.imwrite(str(train_img / f"{stem}.jpg"), canvas)
        (train_lab / f"{stem}.txt").write_text(
            f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n", encoding="utf-8"
        )

    (OUT / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {OUT.resolve()}",
                "train: train/images",
                "val: train/images",
                "names:",
                "  0: over_ear",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Synthetic {args.n} images → {OUT}")
    print("Next: python scripts/prepare_headphones_dataset.py")


if __name__ == "__main__":
    main()
