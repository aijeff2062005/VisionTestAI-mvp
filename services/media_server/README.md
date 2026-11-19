# Media server (Mac)

Lean patient **audio / image** store for VisionTestAI.

- **Bytes:** HTTP PUT/GET on `:9010`
- **Control:** MQTT grants + ready events (Mosquitto on Mac)
- Hospital API stays JSON-only (object refs, not base64)

Architecture: [`../docs/MEDIA_ARCHITECTURE.md`](../docs/MEDIA_ARCHITECTURE.md)

## Quick start (Mac)

```bash
# Mosquitto must already listen on LAN (same as hospital)
cd VisionTestAI/media_server
./run.sh
# health: http://192.168.1.78:9010/health
```

Optional env:

| Variable | Default | Meaning |
|----------|---------|---------|
| `MEDIA_ROOT` | `./data` | On-disk object root |
| `MEDIA_HOST` | `0.0.0.0` | Bind |
| `MEDIA_PORT` | `9010` | HTTP port |
| `MEDIA_PUBLIC_BASE` | `http://192.168.1.78:9010` | URLs put in MQTT grants |
| `MQTT_HOST` | `127.0.0.1` | Broker (Mac) |
| `MQTT_PORT` | `1883` | |
| `MEDIA_TOKEN` | `dev-media-token` | Shared `X-Media-Token` |
| `MEDIA_STATIONS` | `station-01` | Comma list to subscribe |
| `MEDIA_TENANTS` | (empty) | Several hospitals: `main:station-01;qdymd:qdymd-01,qdymd-02`. Replaces `MEDIA_TOKEN` and `MEDIA_STATIONS`; each token reaches only its own stations' objects |
| `MEDIA_TENANT_TOKENS_DIR` | (empty) | Directory with one file per tenant (`<dir>/<tenant>`) holding that tenant's `X-Media-Token` |

## Optional Garage (real S3)

```bash
docker compose up -d
# S3 API: http://127.0.0.1:3900  — wire gateway later via MEDIA_S3_*
```

## MQTT example

```bash
# After AC uploads, subscribers see:
mosquitto_sub -h 127.0.0.1 -t 'qlbn/media/+/object/ready' -v
```
