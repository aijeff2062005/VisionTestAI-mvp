# Provisional QLBN ↔ AC contracts (v0.1.0)

These schemas are **provisional**. When real QLBN docs arrive, keep adapters thin and update topic names / field mappings here first.

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `MQTT_HOST` | `127.0.0.1` | Broker host |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_USER` | _(empty)_ | Optional auth |
| `MQTT_PASS` | _(empty)_ | Optional auth |
| `STATION_ID` | `station-01` | Exam station id in topics |

## MQTT topics

| Direction | Topic | Payload schema |
|-----------|-------|----------------|
| QLBN → AC | `qlbn/station/{station_id}/session/start` | [`session_start.schema.json`](../contracts/session_start.schema.json) |
| AC → QLBN | `qlbn/station/{station_id}/session/status` | [`session_status.schema.json`](../contracts/session_status.schema.json) |
| QLBN → AC | `qlbn/station/{station_id}/session/cancel` | [`session_cancel.schema.json`](../contracts/session_cancel.schema.json) |

### Session states

`accepted` → `preparing` → `guiding` → `measuring` → `confirming` → `completed`  
Terminal also: `failed`, `cancelled`.

## Face ID (demo AiFace)

- Panel host: `bridges.face.host` (lab: `192.168.1.18`); Server IP → Jetson AiFace BS
- Hospital DB: Mac `hospital.base_url` lookup/register by `aiface_enroll_id`
- Patient media (audio/images): Mac media gateway — MQTT + HTTP PUT, see [`MEDIA_ARCHITECTURE.md`](../../docs/MEDIA_ARCHITECTURE.md)
- Face gallery VectorDB → AiFace on-device sync: [`face_vectordb.md`](face_vectordb.md)
- Chart screens: welcome / register_prompt / service_menu (Vision Test)
- Dual panels: see [face_devices.md](face_devices.md)
- Lab topology: [`../docs/LAB_TOPOLOGY.md`](../../docs/LAB_TOPOLOGY.md)

## HTTP results callback

`POST {callback_url}` with header `X-Correlation-Id: {correlation_id}`.

Body: [`results_callback.schema.json`](../contracts/results_callback.schema.json)

OpenAPI stub: [`openapi.yaml`](../contracts/openapi.yaml)

## Acuity scoring rule (v0.2 — VN-aligned pass)

- **Pass a row:** ≤ **1** miss on the row (`max_misses: 1`, typically 4/5 or 5/5) — matches BQP fine-row idea.
- **Letter timeout:** `letter_timeout_seconds: 10` — no full answer in time → miss that letter, continue.
- **Staircase:** pass → **smaller** letters; fail → **same size once**; fail again → **bigger**.
- **Results:** `vn_over_10` (e.g. `8/10`) **and** logMAR/decimal. Font unchanged (Sloan / Optician Sans).

See [demo_flow.md](demo_flow.md), [lux_calibration.md](lux_calibration.md), [occluder_diy.md](occluder_diy.md), [vn_standard_compliance.md](vn_standard_compliance.md).
