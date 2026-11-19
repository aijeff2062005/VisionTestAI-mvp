#!/usr/bin/env python3
"""Merge Roboflow YOLO exports into a single-class over_ear dataset."""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "datasets" / "headphones" / "raw"
DEFAULT_OUT = ROOT / "datasets" / "headphones" / "merged"

# Class-name substrings mapped to over_ear (case-insensitive)
OVER_EAR_HINTS = (
    "over_ear",
    "over-ear",
    "overear",
    "headphone",
    "headphones",
    "headset",
    "earphone",
    "earphones",
    "ear muff",
    "earmuff",
)

# Skip these labels in v1 (earbud track is future)
SKIP_HINTS = (
    "earbud",
    "earbuds",
    "airpod",
    "airpods",
    "inear",
    "in-ear",
    "in_ear",
    "iem",
)


def _load_names(data_yaml: Path) -> list[str]:
    import yaml

    with open(data_yaml, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    names = cfg.get("names")
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names, key=lambda x: int(x))]
    if isinstance(names, list):
        return [str(n) for n in names]
    return []


def _class_keep(name: str) -> bool | None:
    """True = over_ear, False = skip frame label, None = unknown → skip."""
    n = name.lower().strip()
    if any(h in n for h in SKIP_HINTS):
        return False
    if any(h in n for h in OVER_EAR_HINTS):
        return True
    return None


def _find_split_dirs(root: Path) -> list[tuple[Path, Path]]:
    """Return list of (images_dir, labels_dir) under a Roboflow export."""
    pairs: list[tuple[Path, Path]] = []
    for split in ("train", "valid", "val", "test"):
        img = root / split / "images"
        lab = root / split / "labels"
        if img.is_dir() and lab.is_dir():
            pairs.append((img, lab))
        # Flat: train/ with images beside labels
        img2 = root / split
        if img2.is_dir() and (img2 / "images").is_dir():
            continue
    # Also: images/train + labels/train
    for split in ("train", "valid", "val", "test"):
        img = root / "images" / split
        lab = root / "labels" / split
        if img.is_dir() and lab.is_dir():
            pairs.append((img, lab))
    return pairs


def _discover_sources(raw_root: Path) -> list[Path]:
    """Each direct child that looks like a YOLO export (or zip extracted root)."""
    if not raw_root.is_dir():
        return []
    sources: list[Path] = []

    def _try_add(p: Path) -> None:
        if not p.is_dir() or p.name.startswith("."):
            return
        if not (p / "data.yaml").is_file() and not list(p.glob("**/data.yaml")):
            return
        if _find_split_dirs(p):
            sources.append(p)
            return
        for sub in p.iterdir():
            if sub.is_dir() and _find_split_dirs(sub) and (
                (sub / "data.yaml").is_file() or (p / "data.yaml").is_file()
            ):
                sources.append(sub)

    for child in sorted(raw_root.iterdir()):
        _try_add(child)
    return sources


def _image_stem_map(images_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
        for p in images_dir.glob(ext):
            out[p.stem] = p
        for p in images_dir.glob(ext.upper()):
            out[p.stem] = p
    return out


def merge_sources(
    sources: list[Path],
    out_root: Path,
    *,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[int, int]:
    """Merge all sources into out_root; return (n_train, n_val)."""
    rng = random.Random(seed)
    samples: list[tuple[Path, str]] = []  # (image, label_text)

    for src_root in sources:
        yaml_path = src_root / "data.yaml"
        if not yaml_path.is_file():
            found = list(src_root.rglob("data.yaml"))
            yaml_path = found[0] if found else yaml_path
        if not yaml_path.is_file():
            print(f"Skip {src_root}: no data.yaml")
            continue
        names = _load_names(yaml_path)
        if not names:
            print(f"Skip {src_root}: empty names in {yaml_path}")
            continue
        id_map: dict[int, bool] = {}
        for i, name in enumerate(names):
            k = _class_keep(name)
            if k is True:
                id_map[i] = True
            elif k is False:
                id_map[i] = False
            else:
                id_map[i] = len(names) == 1
                if len(names) == 1:
                    print(f"  note: treating sole class {name!r} as over_ear")
                else:
                    print(f"  skip unknown class {i}:{name!r}")

        if not any(id_map.values()):
            print(f"Skip {src_root}: no over_ear-like classes in {names}")
            continue

        pairs = _find_split_dirs(src_root)
        if not pairs:
            print(f"Skip {src_root}: no train/valid image folders")
            continue

        n_added = 0
        for img_dir, lab_dir in pairs:
            stems = _image_stem_map(img_dir)
            for stem, img_path in stems.items():
                lab_path = lab_dir / f"{stem}.txt"
                if not lab_path.is_file():
                    continue
                text = lab_path.read_text(encoding="utf-8").strip()
                lines_out: list[str] = []
                if text:
                    for line in text.splitlines():
                        parts = line.split()
                        if len(parts) < 5:
                            continue
                        try:
                            cid = int(float(parts[0]))
                        except ValueError:
                            continue
                        if id_map.get(cid) is not True:
                            continue
                        lines_out.append("0 " + " ".join(parts[1:5]))
                if not lines_out:
                    continue
                samples.append((img_path, "\n".join(lines_out) + "\n"))
                n_added += 1
        print(f"{src_root.name}: +{n_added} labeled images ({names})")

    if not samples:
        raise SystemExit(
            "No images collected. Put Roboflow YOLO exports under "
            f"{DEFAULT_RAW}/roboflow_a and roboflow_b (see README)."
        )

    rng.shuffle(samples)
    n_val = max(1, int(len(samples) * val_ratio)) if len(samples) > 5 else max(
        1, len(samples) // 5
    )
    val_set = samples[:n_val]
    train_set = samples[n_val:]
    if not train_set:
        train_set, val_set = samples[1:], samples[:1]

    if out_root.exists():
        shutil.rmtree(out_root)
    for split in ("train", "val"):
        (out_root / "images" / split).mkdir(parents=True)
        (out_root / "labels" / split).mkdir(parents=True)

    def _copy(split: str, items: list[tuple[Path, str]]) -> None:
        for i, (img, lab_text) in enumerate(items):
            stem = f"{split}_{i:05d}"
            shutil.copy2(img, out_root / "images" / split / f"{stem}{img.suffix.lower()}")
            (out_root / "labels" / split / f"{stem}.txt").write_text(
                lab_text, encoding="utf-8"
            )

    _copy("train", train_set)
    _copy("val", val_set)

    data_yaml = out_root / "data.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {out_root.resolve()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: over_ear",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {data_yaml}")
    print(f"train={len(train_set)}  val={len(val_set)}")
    return len(train_set), len(val_set)


def try_download(raw_root: Path) -> None:
    """Optional Roboflow CLI download into raw/roboflow_a and raw/roboflow_b."""
    try:
        from roboflow import Roboflow
    except ImportError as exc:
        raise SystemExit(
            "pip install roboflow and set ROBOFLOW_API_KEY for --download"
        ) from exc
    import os

    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set ROBOFLOW_API_KEY for --download")

    rf = Roboflow(api_key=key)
    specs = [
        ("roboflow_a", "yolov8workspace", "headphones-detection-rx2oj", 2),
        ("roboflow_b", "tatsi-shagova-pftso", "headphones-detection", 4),
    ]
    for folder, workspace, project, version in specs:
        dest = raw_root / folder
        dest.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {workspace}/{project} v{version} → {dest}")
        try:
            proj = rf.workspace(workspace).project(project)
            ver = proj.version(version)
            ver.download("yolov8", location=str(dest))
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN: {exc}")
            print(f"  Manual: export YOLO zip into {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        default=DEFAULT_RAW,
        help="Root containing roboflow_a / roboflow_b / clinic_clean",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--sources",
        default="",
        help="Comma list of raw/* folder names to include "
        "(default: auto-discover, preferring clinic_clean over clinic_labeled)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download Roboflow sets via API (needs ROBOFLOW_API_KEY)",
    )
    args = parser.parse_args()
    args.raw.mkdir(parents=True, exist_ok=True)
    (args.raw / "roboflow_a").mkdir(exist_ok=True)
    (args.raw / "roboflow_b").mkdir(exist_ok=True)
    (args.raw / "clinic").mkdir(exist_ok=True)

    if args.download:
        try_download(args.raw)

    if args.sources.strip():
        names = [s.strip() for s in args.sources.split(",") if s.strip()]
        sources = []
        for name in names:
            p = args.raw / name
            if not p.is_dir():
                print(f"WARN: missing source {p}")
                continue
            # Allow nested export
            if (p / "data.yaml").is_file() and _find_split_dirs(p):
                sources.append(p)
            else:
                for sub in p.iterdir():
                    if sub.is_dir() and _find_split_dirs(sub):
                        yaml_ok = (sub / "data.yaml").is_file() or (
                            p / "data.yaml"
                        ).is_file()
                        if yaml_ok:
                            sources.append(sub)
                if (p / "data.yaml").is_file() and _find_split_dirs(p):
                    if p not in sources:
                        sources.append(p)
    else:
        sources = _discover_sources(args.raw)
        # Prefer clean clinic; drop noisy World-fullframe teacher set
        sources = [
            s
            for s in sources
            if "clinic_labeled" not in s.name and "synthetic" not in s.name
        ]

    if not sources:
        print(
            f"No YOLO exports under {args.raw}.\n"
            "Run: python scripts/clean_clinic_headphones_dataset.py\n"
            "  or unzip Roboflow into raw/roboflow_a (see README)."
        )
        sys.exit(1)
    print("Sources:", ", ".join(str(s) for s in sources))
    merge_sources(sources, args.out, val_ratio=args.val_ratio, seed=args.seed)


if __name__ == "__main__":
    main()
