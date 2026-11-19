#!/usr/bin/env python3
"""Train closed-set YOLOv8n over_ear detector and export ONNX."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "datasets" / "headphones" / "merged" / "data.yaml"
DEFAULT_OUT_PT = ROOT / "weights" / "headphones_over_ear.pt"
DEFAULT_OUT_ONNX = ROOT / "weights" / "headphones_over_ear.onnx"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--model", default="yolov8n.pt", help="Base Ultralytics weights")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--device", default="", help="cuda / mps / cpu (empty = auto)")
    p.add_argument("--project", type=Path, default=ROOT / "runs" / "headphones")
    p.add_argument("--name", default="over_ear_n")
    p.add_argument("--skip-export", action="store_true")
    p.add_argument(
        "--out-pt",
        type=Path,
        default=DEFAULT_OUT_PT,
        help="Copy best.pt here for SmartEyes config",
    )
    p.add_argument("--out-onnx", type=Path, default=DEFAULT_OUT_ONNX)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.data.is_file():
        print(f"Missing {args.data}")
        print("Run: python scripts/prepare_headphones_dataset.py")
        print("See datasets/headphones/README.md")
        sys.exit(1)

    from ultralytics import YOLO

    model = YOLO(args.model)
    train_kwargs = dict(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(args.project),
        name=args.name,
        exist_ok=True,
    )
    if args.device:
        train_kwargs["device"] = args.device

    print("Training:", train_kwargs)
    results = model.train(**train_kwargs)
    best = Path(results.save_dir) / "weights" / "best.pt"
    if not best.is_file():
        # Fallback path layout
        best = args.project / args.name / "weights" / "best.pt"
    if not best.is_file():
        print("Training finished but best.pt not found")
        sys.exit(1)

    args.out_pt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, args.out_pt)
    print(f"Copied {best} → {args.out_pt}")

    if not args.skip_export:
        exp = YOLO(str(args.out_pt))
        exported = exp.export(format="onnx", imgsz=args.imgsz)
        onnx_path = Path(exported) if exported else args.out_pt.with_suffix(".onnx")
        if onnx_path.is_file():
            args.out_onnx.parent.mkdir(parents=True, exist_ok=True)
            if onnx_path.resolve() != args.out_onnx.resolve():
                shutil.copy2(onnx_path, args.out_onnx)
            print(f"ONNX → {args.out_onnx}")
        else:
            print("WARN: ONNX export path not found:", exported)

    print()
    print("Next: set configs/default.yaml headphones.backend: yolo")
    print(f"      headphones.weights: {args.out_pt.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
