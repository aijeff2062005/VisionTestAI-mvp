#!/usr/bin/env python3
"""Capture corridor frames for headphones labeling (clinic domain)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera_utils import open_video_capture, resolve_source


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Save webcam frames for over-ear headphones labeling",
    )
    p.add_argument("--source", default="macbook", help="macbook | index | video path")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "datasets" / "headphones" / "raw" / "clinic",
        help="Output folder for JPEG frames",
    )
    p.add_argument("--every", type=int, default=5, help="Save every Nth frame")
    p.add_argument("--max-frames", type=int, default=0, help="Stop after N saves (0=unlimited)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--no-display", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = args.out / stamp
    session.mkdir(parents=True, exist_ok=True)

    source = resolve_source(args.source)
    cap = open_video_capture(source)
    if not cap.isOpened():
        print(f"Failed to open source: {source}")
        sys.exit(1)
    if args.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    if args.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    print(f"Saving every {args.every} frames → {session}")
    print("Wear / hold over-ears in the stand zone. Press q to quit, s to force-save.")
    idx = 0
    saved = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            idx += 1
            force = False
            if not args.no_display:
                vis = frame.copy()
                cv2.putText(
                    vis,
                    f"clinic capture  saved={saved}  [s]=save [q]=quit",
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("SmartEyes headphones capture", vis)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key in (ord("s"), ord("S")):
                    force = True

            if force or (args.every > 0 and idx % args.every == 0):
                path = session / f"frame_{saved:05d}.jpg"
                cv2.imwrite(str(path), frame)
                saved += 1
                if args.max_frames and saved >= args.max_frames:
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"Done. Saved {saved} frames under {session}")
    print("Label over_ear boxes (YOLO), then re-run prepare_headphones_dataset.py")


if __name__ == "__main__":
    main()
