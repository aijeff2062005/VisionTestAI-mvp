# Headphones closed-set dataset (Orange Pi / edge)

**MVP demo keeps `backend: yolo_world`** (open-vocab + CLIP).  
Closed-set YOLOv8n is for packing later (~6 MB `.pt` / ~12 MB ONNX, no CLIP).

## Layout

```text
datasets/headphones/
  raw/roboflow_a/      # optional public YOLOv8 export
  raw/roboflow_b/
  raw/clinic/          # capture_headphones_frames.py dumps
  raw/clinic_clean/    # head-crop teacher + hard negatives (preferred)
  raw/clinic_labeled/  # DO NOT USE — noisy full-frame teacher (chairs/faces)
  merged/              # prepare_headphones_dataset.py output
```

## MVP (now)

Leave config as:

```yaml
headphones:
  backend: yolo_world
  weights: yolov8s-world.pt
```

On-head / held-in-hand is geometric (ears, wrists) — not the detector alone.

## Edge dataset (clinic-ready)

### A. Capture more corridor / desk / worn / held / bare-head

```bash
python scripts/capture_headphones_frames.py --source macbook --every 5
```

Include frames where you:

- wear over-ears (fluffy hair OK)
- hold headphones in hand (must become hard-negatives for head crop)
- sit with **no** headphones (bare head + chair visible)

### B. Clean labels (head crop only — no chair)

```bash
python scripts/clean_clinic_headphones_dataset.py
# → raw/clinic_clean/  (positives + empty-label hard negatives)
```

Teacher = YOLO-World **inside the pose head box only**. Full-frame chair cups are never labeled `over_ear`.

### C. Optional public Roboflow

Unzip YOLOv8 exports into `raw/roboflow_a` / `raw/roboflow_b`.

### D. Merge + train

```bash
python scripts/prepare_headphones_dataset.py --sources clinic_clean,roboflow_a,roboflow_b
# or auto (skips clinic_labeled / synthetic):
python scripts/prepare_headphones_dataset.py

python scripts/train_headphones_yolo.py --epochs 80 --batch 8
```

### E. Switch demo to closed-set when val looks sane

```yaml
headphones:
  backend: yolo
  weights: weights/headphones_over_ear.pt
  conf_threshold: 0.35
  full_frame_fallback: false
  require_center_in_head: true
  max_head_cover: 0.42
```

## Why the previous clinic model failed

`clinic_labeled` used World on the **full frame** → chairs and whole heads became `over_ear`, then READY flipped ON HEAD while cups were in-hand. That set is quarantined; prefer `clinic_clean`.
