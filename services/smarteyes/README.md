# SmartEyes — Patient readiness MVP

Detect whether a patient is ready to start a distance vision test:

1. **Standing in the stand zone** (white ceramic floor region by default; tape optional)
2. **Wearing over-ear headphones on the head** (near ears — not just detected in frame)
3. **Eye under test** from cover state (SmartClass-style Face Mesh iris / EAR):
   - cover **left** → test **RIGHT**
   - cover **right** → test **LEFT**
   - cover neither → test **BOTH**
   - partial cover (peek between fingers) → not counted as covered; coaching to cover fully

When zone + headphones-on-head pass for a short hold → **READY** (eye side shown live).

Optional **`--spell`**: after READY, show a 5-letter Sloan board on screen and listen for Vietnamese letter names via sibling [`sloan-stt_v2`](../sloan-stt_v2) (in-process ONNX).

Stack: MacBook camera → YOLOv8n person → MediaPipe Pose (ankles/ears) → floor stand-zone → closed-set `over_ear` YOLO → Face Mesh eye cover → temporal rules → HUD → (optional) mic Sloan STT.

## Prerequisites

- **Conda** (Miniconda/Anaconda) — do not use macOS system `python3` (MediaPipe needs 3.11)
- MacBook FaceTime camera for the live demo
- **White / light floor** in the camera corridor (MVP), or optional colored tape (`line.mode: tape`)
- **Over-ear headphones** (earbuds are unreliable without custom training)
- For `--spell`: microphone + keep `VisionTestAI/sloan-stt_v2` next to this folder (ONNX models included there)

## Setup

```bash
cd VisionTestAI/SmartEyes
conda env create -f environment.yml
conda activate smarteyes
# if env already exists and you need spell deps:
pip install onnxruntime sounddevice soundfile librosa torchaudio
python scripts/make_smoke_video.py
```

Model weights (`yolov8n.pt`, `yolov8s-world.pt`) download automatically on first run.

## Run

```bash
conda activate smarteyes

# Or use Make shortcuts (from this folder):
make help
make demo                  # closed-set headphones
make demo-custom           # closed-set over_ear weights
make demo-micro MICRO=6    # full demo + spell on mic 6
make list-mics
make clean-clinic && make prepare-hp && make train-hp
```

```bash
# All checks (default)
python scripts/run_webcam_demo.py --source macbook

# Vision / eye-cover only (desk sitting — no stand/headphones required)
python scripts/run_webcam_demo.py --source macbook --eyes

# Closed-set headphone detector (CLI: --hp-backend)
python scripts/run_webcam_demo.py --source macbook --hp-backend yolo
python scripts/run_webcam_demo.py --source macbook --hp-backend custom

# After READY: on-screen Sloan letters + Vietnamese mic spelling
# --spell alone = spell-only (ZONE/HP/EYES off so mic turns on at the desk)
python scripts/run_webcam_demo.py --source macbook --spell
python scripts/run_webcam_demo.py --source macbook --eyes --spell
python scripts/run_webcam_demo.py --source macbook --eyes --headphone --spell

# List mics / pick one → full demo (zone + headphones + eyes + spell)
python scripts/run_webcam_demo.py --list-mics
python scripts/run_webcam_demo.py --source macbook --micro 6
python scripts/run_webcam_demo.py --source macbook --micro "MacBook Air"

# Spell-only desk mode (no zone/HP/eyes gate)
python scripts/run_webcam_demo.py --source macbook --spell
python scripts/run_webcam_demo.py --source macbook --eyes --spell

# Offline smoke
python scripts/run_webcam_demo.py --source data/sample/smoke.mp4 --no-display --eyes
```

Press `q` in the window to quit. With `--spell`: `n` new board, `m` mute mic, `r` retry trial.

## What you should see

| HUD | Meaning |
|-----|---------|
| `ZONE: PASS / FAIL` | Ankles inside the boxed white-floor stand zone |
| `HEADPHONES: ON HEAD / DETECTED/OFF / FAIL` | Headset worn near ears (not merely in frame) |
| `EYE TEST: LEFT / RIGHT / BOTH` | Which eye(s) are under test from cover state |
| `L:` / `R:` | Per-eye `open` / `covered` / `partial` / `closed` |
| `STATUS: READY / WAITING` | Zone + headphones-on-head held for ~1.5s |

Yellow **STAND ZONE** overlays the floor. Iris dots are green (open), orange (covered), yellow (partial peek).

## Letter spelling (Vietnamese Sloan STT)

Opt-in with `--spell` (or `spell.enabled: true` in config). Uses the closed-set classifier in [`../sloan-stt_v2`](../sloan-stt_v2):

Letters: `C D H K N O R S V Z` (spoken Vietnamese names). Special `X` / “không thấy” → new board.

| Example spoken | Letter |
|----------------|--------|
| xê, cờ | C |
| dê, đê | D |
| hờ | H |
| ca, kay | K |
| nờ | N |
| ô | O |
| rờ | R |
| sờ, ét | S |
| vê, vờ | V |
| dét | Z |
| không thấy | X (skip / new board) |

Flow: wait until **READY** → board appears → speak one letter at a time → HEARD fills green/red → score `k/5` tagged with current eye (`LEFT` / `RIGHT` / `BOTH`). Losing READY or changing eye cover aborts the trial.

**Note:** the on-screen board is a **flow demo**, not a distance-calibrated acuity chart. Headphones remain a **visual** on-head check; they also stand in for “patient hears instructions / answers on mic.”

## Physical demo setup

1. Camera ~130 cm high, aimed so the white ceramic corridor fills the lower/center frame (patient full body).
2. Patient stands on that white floor (distance mark) with over-ear headphones.
3. Tape is **not required**; for facilities with tape, set `line.mode: tape` in config.
4. Tune zone if needed:

```bash
python scripts/calibrate_line.py --source macbook
# click white floor → s for HSV; p/d for fixed_polygon vertices
```

## Config

[`configs/default.yaml`](configs/default.yaml):

- `line.mode: floor` — white ceramic stand zone (default)
- `line.floor_hsv_*` / `search_roi` / `fixed_polygon` — zone tuning
- `line.mode: tape` — optional colored tape at some sites
- `headphones.require_on_head` — must sit near ears, not just in frame
- `eye_cover.*` — Face Mesh cover / partial / under-test side
- `rules.hold_seconds` — how long zone + headphones must stay true
- `headphones.backend: yolo` — closed-set `over_ear`; disabled clearly if weights are missing
- `headphones.weights: weights/headphones_over_ear.pt`
- `spell.*` — board length, STT thresholds, VAD, `sloan_root` path

## Closed-set headphones

Runtime: `headphones.backend: yolo`:

```bash
python scripts/capture_headphones_frames.py --source macbook --every 5
python scripts/clean_clinic_headphones_dataset.py   # head-crop labels + hard negatives
python scripts/prepare_headphones_dataset.py --sources clinic_clean
python scripts/train_headphones_yolo.py
# then set backend: yolo + weights/headphones_over_ear.pt
```

Details: [`datasets/headphones/README.md`](datasets/headphones/README.md). Earbuds hold→insert: [`docs/FUTURE_EARBUDS.md`](docs/FUTURE_EARBUDS.md).

## Orange Pi (later)

Same Python stack on Orange Pi 8GB. Prefer `weights/headphones_over_ear.onnx` + spell ONNX (~26 MB); MediaPipe Pose on CPU is fine for single-person readiness.

## Layout

```
SmartEyes/
  environment.yml
  configs/default.yaml
  src/
  scripts/                 # demo, prepare/train headphones, capture frames
  datasets/headphones/     # README + raw/merged (gitignored data)
  docs/FUTURE_EARBUDS.md
  weights/headphones_over_ear.pt   # after train
  data/sample/smoke.mp4
../sloan-stt_v2/
```
