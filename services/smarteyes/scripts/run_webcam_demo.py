#!/usr/bin/env python3
"""Run SmartEyes readiness demo on webcam or video source."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

# MediaPipe + newer protobuf: GetPrototype() warns on every inference call
warnings.filterwarnings(
    "ignore",
    message=r".*GetPrototype\(\) is deprecated.*",
    category=UserWarning,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _require_deps() -> None:
    missing = []
    for mod, pkg in [
        ("yaml", "pyyaml"),
        ("cv2", "opencv-python"),
        ("ultralytics", "ultralytics"),
        ("mediapipe", "mediapipe"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("Missing packages:", ", ".join(missing))
        print()
        print("Use the conda env (not system python3):")
        print("  conda activate smarteyes")
        print("  python scripts/run_webcam_demo.py")
        print()
        print("First time: conda env create -f environment.yml")
        sys.exit(1)


_require_deps()

from src.camera_utils import print_camera_list
from src.config_loader import load_config, project_root
from src.pipeline import SmartEyesPipeline, run_capture_loop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SmartEyes webcam / video demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Check filters (if any of --eyes/--stand/--headphone is set, only those run).\n"
            "  --eyes         eye cover / under-test side (desk sitting OK)\n"
            "  --stand        floor stand-zone ankles\n"
            "  --headphone    headphones on head\n"
            "  --hp-backend   yolo / custom (closed-set over_ear)\n"
            "  --spell        Vietnamese Sloan letter STT (alone = spell-only, no zone/HP)\n"
            "  --list-mics    list input microphones and exit\n"
            "  --micro IDX|NAME  pick mic + full demo (stand/HP/eyes + spell)\n"
            "\nExamples:\n"
            "  python scripts/run_webcam_demo.py --source macbook --spell\n"
            "  python scripts/run_webcam_demo.py --list-mics\n"
            "  python scripts/run_webcam_demo.py --source macbook --micro 6\n"
            "  python scripts/run_webcam_demo.py --source macbook --hp-backend yolo\n"
            "  python scripts/run_webcam_demo.py --source macbook --hp-backend custom\n"
            "  python scripts/run_webcam_demo.py --source macbook --eyes --headphone\n"
        ),
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--source",
        default=None,
        help="macbook | facetime | camera index | path/to/video.mp4",
    )
    parser.add_argument("--list-cameras", action="store_true")
    parser.add_argument(
        "--list-mics",
        action="store_true",
        help="List available microphones (sounddevice) and exit",
    )
    parser.add_argument(
        "--micro",
        default=None,
        metavar="IDX|NAME",
        help='Mic + full demo: index (e.g. 6) or name substring (e.g. "MacBook Air")',
    )
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument(
        "--eyes",
        action="store_true",
        help="Enable eye-cover / under-test check (alone = vision-only desk mode)",
    )
    parser.add_argument(
        "--stand",
        action="store_true",
        help="Enable stand-zone (floor) check",
    )
    parser.add_argument(
        "--headphone",
        "--headphones",
        action="store_true",
        dest="headphone",
        help="Enable headphones-on-head check",
    )
    parser.add_argument(
        "--hp-backend",
        "--headphones-backend",
        dest="hp_backend",
        default=None,
        choices=["yolo", "custom", "closed_set"],
        help="Headphones detector: closed-set weights/headphones_over_ear.pt",
    )
    parser.add_argument(
        "--hp-weights",
        default=None,
        metavar="PATH",
        help="Override headphones weights path (with --hp-backend custom/yolo)",
    )
    parser.add_argument(
        "--spell",
        action="store_true",
        help="Sloan letter spelling via mic. Alone = spell-only (no stand/headphones/eyes gate)",
    )
    return parser.parse_args()


def apply_headphones_backend(cfg: dict, args: argparse.Namespace) -> dict:
    """Apply --hp-backend / --hp-weights onto headphones config."""
    if args.hp_backend is None and args.hp_weights is None:
        return cfg
    cfg = dict(cfg)
    hp = dict(cfg.get("headphones") or {})
    choice = (args.hp_backend or "yolo").lower()
    if choice in ("yolo", "custom", "closed_set"):
        hp["backend"] = "yolo"
        weights = args.hp_weights or hp.get(
            "closed_set_weights", "weights/headphones_over_ear.pt"
        )
        hp["weights"] = str(weights)
        hp["conf_threshold"] = float(hp.get("closed_set_conf", 0.30))
        hp["full_frame_fallback"] = False
        hp["require_center_in_head"] = True
        hp["max_head_cover"] = float(hp.get("max_head_cover", 0.42))
    else:
        raise SystemExit(f"Unknown --hp-backend {choice!r}")
    cfg["headphones"] = hp
    return cfg


def apply_check_flags(cfg: dict, args: argparse.Namespace) -> dict:
    """CLI filters which checks run.

    --spell alone → spell-only (no stand / headphones / eyes)
    --micro set   → full demo (config defaults) + spell with that mic
    --eyes/--stand/--headphone → only those checks (+ spell if --spell/--micro)
    """
    check_flag = bool(args.eyes or args.stand or args.headphone)
    micro_set = getattr(args, "micro", None) is not None
    cfg = dict(cfg)
    if args.spell and not check_flag and not micro_set:
        # --spell alone: skip stand / headphones / eyes — go straight to spelling
        cfg["checks"] = {
            "stand": False,
            "headphones": False,
            "eyes": False,
        }
    elif check_flag:
        cfg["checks"] = {
            "stand": bool(args.stand),
            "headphones": bool(args.headphone),
            "eyes": bool(args.eyes),
        }
    else:
        # Default config checks, or --micro (full demo)
        checks = dict(cfg.get("checks") or {})
        cfg["checks"] = {
            "stand": bool(checks.get("stand", True)),
            "headphones": bool(checks.get("headphones", True)),
            "eyes": bool(checks.get("eyes", True)),
        }
    spell = dict(cfg.get("spell") or {})
    if args.spell or micro_set:
        spell["enabled"] = True
        # Spell-only desk mode: turn mic on quickly after person appears
        if args.spell and not check_flag and not micro_set:
            spell["ready_delay_seconds"] = 0.3
    if micro_set:
        spell["mic_device"] = str(args.micro).strip()
    cfg["spell"] = spell
    return cfg


def _checks_summary(checks: dict, spell_on: bool, hp_backend: str | None = None) -> str:
    parts = []
    for key, label in (("stand", "stand"), ("headphones", "headphone"), ("eyes", "eyes")):
        parts.append(f"{label}={'ON' if checks.get(key) else 'off'}")
    parts.append(f"spell={'ON' if spell_on else 'off'}")
    if hp_backend:
        parts.append(f"hp={hp_backend}")
    return ", ".join(parts)


def main() -> None:
    args = parse_args()
    if args.list_cameras:
        print_camera_list()
        return
    if args.list_mics:
        from src.sloan_stt import print_microphone_list

        print_microphone_list()
        return
    if args.micro is not None and not args.spell:
        # Selecting a mic implies spell + full demo
        args.spell = True

    root = project_root()
    cfg = load_config(root / args.config)
    cfg = apply_check_flags(cfg, args)
    cfg = apply_headphones_backend(cfg, args)

    source = args.source
    if source is None:
        source = cfg["pipeline"]["source"]
    if source != 0 and str(source).isdigit():
        source = int(source)

    max_frames = args.max_frames
    if max_frames is None and args.no_display:
        max_frames = int(cfg["pipeline"].get("max_smoke_frames", 60))

    pipeline = SmartEyesPipeline(cfg=cfg)
    spell_on = bool((cfg.get("spell") or {}).get("enabled")) and (
        pipeline.spell is not None and pipeline.spell.enabled
    )
    hp_backend = str((cfg.get("headphones") or {}).get("backend", "?"))
    print(f"SmartEyes checks: {_checks_summary(cfg['checks'], spell_on, hp_backend)}")
    if bool(cfg["checks"].get("headphones")):
        hp_w = (cfg.get("headphones") or {}).get("weights", "")
        print(f"Headphones weights: {hp_w}")
    if spell_on:
        print("Spell keys: n=new board  m=mute mic  r=retry trial  q=quit")
    else:
        print("Click the video window, then press q (or Esc) to quit.")

    try:
        run_capture_loop(
            source=source,
            pipeline=pipeline,
            display=not args.no_display,
            max_frames=max_frames,
        )
    finally:
        pipeline.close()
        print("Done.")


if __name__ == "__main__":
    main()
