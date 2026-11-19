# Station demo runbook (full Face → SmartEyes → Chart)

## Prerequisites

- Conda env **`smarteyes`** (not `.venv`)
- Mosquitto on `127.0.0.1:1883` (or use `--mqtt-optional` with `--demo-session`)
- AiFace panel at `192.168.1.96` (admin password via config / `FACE_PASSWORD`)
- Webcam for SmartEyes readiness

```bash
conda activate smarteyes
cd VisionTestAI/assistant_controller
pip install -r requirements.txt
pip install -e .
```

## One-command full demo

```bash
conda activate smarteyes
cd VisionTestAI/assistant_controller
python -m ac.main --demo-session --mqtt-optional
```

1. Open http://127.0.0.1:8088/
2. Look at Face ID → greet with name (or register on panel if stranger)
3. SmartEyes OpenCV window + chart coaching until READY
4. Chart rows run (mock STT by default)
5. Results overlay on chart + `data/journals/<session_id>_results.json`

Optional HTTP sink:

```bash
python scripts/results_sink.py
# listens on http://127.0.0.1:8099/api/v1/vision/results
```

## MQTT path

```bash
# Mosquitto
/usr/local/opt/mosquitto/sbin/mosquitto -c /usr/local/etc/mosquitto/mosquitto.conf -d

python -m ac.main
python scripts/demo_start_session.py --callback http://127.0.0.1:8099/api/v1/vision/results
mosquitto_sub -h 127.0.0.1 -t 'qlbn/station/station-01/session/status' -v
```

## Face-only

```bash
python scripts/demo_face_wait.py --timeout 60
```

## Cancel

```bash
mosquitto_pub -h 127.0.0.1 -t 'qlbn/station/station-01/session/cancel' -m '{"schema_version":"0.1.0","session_id":"<id>","reason":"operator"}'
```
