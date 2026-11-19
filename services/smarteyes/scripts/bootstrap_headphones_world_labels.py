#!/usr/bin/env python3
"""Bootstrap over_ear labels via YOLO-World on downloaded stock photos (no Roboflow key).

Produces datasets/headphones/raw/bootstrap/ in YOLO layout, then you can:
  python scripts/prepare_headphones_dataset.py
  python scripts/train_headphones_yolo.py --epochs 40
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "datasets" / "headphones" / "raw" / "bootstrap"

# Public-domain / freely usable headphone images (Unsplash source URLs)
IMAGE_URLS = [
    "https://images.unsplash.com/photo-1546435770-a3e426b57623?w=800&q=80",  # over-ear
    "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=800&q=80",
    "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&q=80",
    "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=800&q=80",
    "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=800&q=80",
    "https://images.unsplash.com/photo-1524678606650-16943686777e?w=800&q=80",
    "https://images.unsplash.com/photo-1613040809024-b4ef7ba99bc3?w=800&q=80",
    "https://images.unsplash.com/photo-1577174881650-0111d18817d1?w=800&q=80",
    "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=800&q=80",
    "https://images.unsplash.com/photo-1487215078519-e21cc028cb29?w=800&q=80",
    "https://images.unsplash.com/photo-1545127398-14699f92334b?w=800&q=80",
    "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=900&q=80",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--weights", default="yolov8s-world.pt")
    args = parser.parse_args()

    from ultralytics import YOLO

    raw = OUT / "images_dl"
    train_img = OUT / "train" / "images"
    train_lab = OUT / "train" / "labels"
    for d in (raw, train_img, train_lab):
        d.mkdir(parents=True, exist_ok=True)

    print("Downloading sample headphone images…")
    paths: list[Path] = []
    for i, url in enumerate(IMAGE_URLS):
        dest = raw / f"stock_{i:02d}.jpg"
        if not dest.is_file():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SmartEyes/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    dest.write_bytes(resp.read())
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {i}: {exc}")
                continue
        paths.append(dest)

    if not paths:
        print("No images downloaded")
        sys.exit(1)

    model = YOLO(args.weights)
    model.set_classes(
        ["headphones", "headset", "over-ear headphones", "ear muffs"]
    )

    n_ok = 0
    for src in paths:
        im = cv2.imread(str(src))
        if im is None:
            continue
        h, w = im.shape[:2]
        results = model.predict(im, conf=args.conf, imgsz=args.imgsz, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            print(f"  no det: {src.name}")
            continue
        lines: list[str] = []
        xyxy = boxes.xyxy.cpu().numpy()
        for x1, y1, x2, y2 in xyxy:
            cx = ((x1 + x2) / 2) / w
            cy = ((y1 + y2) / 2) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        stem = f"boot_{n_ok:04d}"
        cv2.imwrite(str(train_img / f"{stem}.jpg"), im)
        (train_lab / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        n_ok += 1
        print(f"  labeled {src.name} → {stem} ({len(lines)} boxes)")

    if n_ok < 3:
        print("Too few labeled images for a meaningful train")
        sys.exit(1)

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
    print(f"Wrote {n_ok} samples under {OUT}")
    print("Next: python scripts/prepare_headphones_dataset.py && python scripts/train_headphones_yolo.py --epochs 50 --batch 4")


if __name__ == "__main__":
    main()
