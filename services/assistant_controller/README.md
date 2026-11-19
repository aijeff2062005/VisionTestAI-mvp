# VisionTestAI Assistant Controller (AC)

Orchestrates a distance visual-acuity exam session on the station device:

- **Face ID (B1)**: AiFace panel identify → patient name, or guide register
- **SmartEyes readiness**: stand + headphones + eyes (live webcam)
- **DMN** (`dmn/acuity_flow.dmn`): decides next chart action
- **Display**: Sloan 5 m chart UI over WebSocket (`:8088`)
- **Audio**: scenario WAVs from `scenarios/vi/`
- **Results**: JSON file under `data/journals/` + chart overlay; HTTP callback best-effort

Contracts: [docs/contracts.md](docs/contracts.md).

**Vietnam standards compliance:** [docs/vn_standard_compliance.md](docs/vn_standard_compliance.md)  
**Demo flow graph:** [docs/demo_flow.md](docs/demo_flow.md) · **Lux calibrate:** [docs/lux_calibration.md](docs/lux_calibration.md) · **DIY occluder:** [docs/occluder_diy.md](docs/occluder_diy.md)

## Setup (conda — no `.venv`)

Full demo shares the SmartEyes conda env (opencv / ultralytics / mediapipe):

```bash
conda activate smarteyes
# first time only:
#   conda env create -f ../SmartEyes/environment.yml
#   conda activate smarteyes
cd VisionTestAI/assistant_controller
pip install -r requirements.txt
pip install -e .
```

## Run (full demo)

Terminal A — Mosquitto (optional if using `--mqtt-optional`):

```bash
/usr/local/opt/mosquitto/sbin/mosquitto -c /usr/local/etc/mosquitto/mosquitto.conf -d
```

Terminal B — AC:

```bash
conda activate smarteyes
cd VisionTestAI/assistant_controller
export STATION_ID=station-01
python -m ac.main --demo-session --mqtt-optional
# open http://127.0.0.1:8088/
# look at Face ID panel → stand for SmartEyes → chart runs (mock STT)
```

Or MQTT session start:

```bash
python -m ac.main
# other terminal:
python scripts/demo_start_session.py
```

Face-only smoke:

```bash
python scripts/demo_face_wait.py --timeout 60
```

Config highlights (`configs/default.yaml`):

```yaml
bridges:
  readiness: smarteyes
  stt: mock
  face:
    mode: aiface
    host: 192.168.1.96
```

## Tests

```bash
conda activate smarteyes
cd VisionTestAI/assistant_controller
pytest -q
```

## Layout

```
assistant_controller/
  contracts/          # JSON Schema + OpenAPI stub
  docs/contracts.md
  dmn/acuity_flow.dmn
  display/index.html  # controlled chart
  scenarios/vi/       # audio + manifest
  src/ac/             # runtime
  scripts/            # demo helpers
  tests/
```
