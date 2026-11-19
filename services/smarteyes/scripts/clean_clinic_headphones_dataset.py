#!/usr/bin/env python3
"""Build a clean clinic over_ear YOLO set for Orange Pi (not for noisy MVP).

Uses YOLO-World **only inside the head crop** so cups/hair are labeled, while
chairs / hands / torso are excluded. Also writes hard-negative frames (empty
labels) when the head crop has no cups — stops the model learning “chair = cups”.

MVP demo stays on yolo_world. Edge path:

  python scripts/clean_clinic_headphones_dataset.py
  python scripts/prepare_headphones_dataset.py --sources clinic_clean,roboflow_a,roboflow_b
  python scripts/train_headphones_yolo.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config, project_root
from src.detector import YOLODetector
from src.pose_body import BodyPoseEstimator


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--clinic",
        type=Path,
        default=ROOT / "datasets" / "headphones" / "raw" / "clinic",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "datasets" / "headphones" / "raw" / "clinic_clean",
    )
    p.add_argument("--world-weights", default="yolov8s-world.pt")
    p.add_argument("--conf", type=float, default=0.10)
    p.add_argument("--max-head-cover", type=float, default=0.55)
    p.add_argument("--imgsz", type=int, default=640)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    from ultralytics import YOLO

    cfg = load_config(project_root() / "configs" / "default.yaml")
    person_det = YOLODetector(cfg)
    pose = BodyPoseEstimator(cfg)
    world = YOLO(args.world_weights)
    world.set_classes(
        [
            "headphones",
            "headset",
            "over-ear headphones",
            "ear muffs",
            "noise cancelling headphones",
        ]
    )

    img_out = args.out / "train" / "images"
    lab_out = args.out / "train" / "labels"
    for d in (img_out, lab_out):
        d.mkdir(parents=True, exist_ok=True)

    frames: list[Path] = []
    if args.clinic.is_dir():
        for sub in sorted(args.clinic.iterdir()):
            if sub.is_dir():
                frames.extend(sorted(sub.glob("*.jpg")))
            elif sub.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                frames.append(sub)
    print(f"Clinic frames: {len(frames)}")

    n_pos = 0
    n_neg = 0
    n_skip = 0

    try:
        for i, path in enumerate(frames):
            frame = cv2.imread(str(path))
            if frame is None:
                n_skip += 1
                continue
            h, w = frame.shape[:2]
            dets = person_det.detect(frame)
            if not dets:
                n_skip += 1
                continue
            person = max(dets, key=lambda d: d.confidence)
            pose_est = pose.estimate(frame, person.bbox)
            if pose_est.head_bbox is None:
                n_skip += 1
                continue
            hx1, hy1, hx2, hy2 = pose_est.head_bbox
            # Expand a bit upward for fluffy hair / headband
            pad_x = int(0.20 * (hx2 - hx1))
            pad_top = int(0.35 * (hy2 - hy1))
            pad_bot = int(0.10 * (hy2 - hy1))
            hx1 = max(0, hx1 - pad_x)
            hy1 = max(0, hy1 - pad_top)
            hx2 = min(w - 1, hx2 + pad_x)
            hy2 = min(h - 1, hy2 + pad_bot)
            head = (hx1, hy1, hx2, hy2)
            crop = frame[hy1 : hy2 + 1, hx1 : hx2 + 1]
            if crop.size == 0 or crop.shape[0] < 32 or crop.shape[1] < 32:
                n_skip += 1
                continue

            results = world.predict(
                crop, conf=args.conf, imgsz=args.imgsz, verbose=False
            )
            lines: list[str] = []
            boxes = results[0].boxes
            hh = max(hy2 - hy1, 1)
            hw = max(hx2 - hx1, 1)
            head_area = float(hw * hh)

            if boxes is not None and len(boxes):
                for x1, y1, x2, y2 in boxes.xyxy.cpu().numpy():
                    bx1 = int(x1) + hx1
                    by1 = int(y1) + hy1
                    bx2 = int(x2) + hx1
                    by2 = int(y2) + hy1
                    bw = max(bx2 - bx1, 1)
                    bh = max(by2 - by1, 1)
                    if bw * bh > args.max_head_cover * head_area:
                        continue
                    if _iou((bx1, by1, bx2, by2), head) < 0.05:
                        continue
                    cx = (bx1 + bx2) / 2
                    cy = (by1 + by2) / 2
                    # Reject obvious whole-face wrap (covers both cheeks + nose band)
                    if bw > hw * 0.85 and bh > hh * 0.70:
                        continue
                    # Keep cups / band: top + sides of head box
                    in_ear_band = cy <= hy1 + hh * 0.92
                    if not in_ear_band:
                        continue
                    lines.append(
                        "0 "
                        f"{(cx / w):.6f} {(cy / h):.6f} "
                        f"{(bw / w):.6f} {(bh / h):.6f}"
                    )

            stem = f"clean_{n_pos + n_neg:05d}"
            if lines:
                cv2.imwrite(str(img_out / f"{stem}.jpg"), frame)
                (lab_out / f"{stem}.txt").write_text(
                    "\n".join(lines) + "\n", encoding="utf-8"
                )
                n_pos += 1
            else:
                # Hard negative: person + head visible, no cup in head crop
                # (held-in-hand / bare head / chair distraction elsewhere)
                cv2.imwrite(str(img_out / f"{stem}.jpg"), frame)
                (lab_out / f"{stem}.txt").write_text("", encoding="utf-8")
                n_neg += 1

            if (n_pos + n_neg) % 40 == 0:
                print(f"  progress pos={n_pos} neg={n_neg} …")
    finally:
        pose.close()

    (args.out / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {args.out.resolve()}",
                "train: train/images",
                "val: train/images",
                "names:",
                "  0: over_ear",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Done → {args.out}")
    print(f"  positives (labeled cups): {n_pos}")
    print(f"  hard negatives (empty):   {n_neg}")
    print(f"  skipped:                  {n_skip}")
    print("Next (edge):")
    print("  python scripts/prepare_headphones_dataset.py --sources clinic_clean")
    print("  python scripts/train_headphones_yolo.py")


if __name__ == "__main__":
    main()
