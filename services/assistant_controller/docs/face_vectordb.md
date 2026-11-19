# Face VectorDB → AiFace on-device gallery

Hospital / cloud **VectorDB API** holds the face gallery. AC pulls it and **loads enrollments onto the AiFace panel** so scan-time match runs **on device** (not a cloud search during every look).

## Flow

```
VectorDB API (placeholder HTTP)
        │ list + image/template
        ▼
   AC face_sync
        │ setuserinfo / upsert
        ▼
 AiFace panel local DB  ──scan──►  on-device verify → enroll_id
        │
        ▼
 Hospital lookup by enroll_id
```

## Config / env

`configs/default.yaml` → `face_vectordb:`

| Env | Meaning |
|-----|---------|
| `FACE_VECTORDB_ENABLED` | `1` to turn on |
| `FACE_VECTORDB_MODE` | `mock` \| `http` \| `off` |
| `FACE_VECTORDB_BASE_URL` | API root (http mode) |
| `FACE_VECTORDB_API_KEY` | Sent as `X-Api-Key` (configurable header) |

Placeholder list contract:

`GET {base}/v1/faces?limit=N` → `{ "faces": [ { enroll_id, full_name, image_url|image_b64|device_template_b64, … } ] }`

Prefer **`device_template_b64`** / `aiface_record` (native panel `record`). Else JPEG via `image_b64` / `image_url` / media `get_url`.

## Run sync

```bash
# Dry gallery (mock) → real panel (needs FACE_MODE=aiface + panel online)
FACE_VECTORDB_ENABLED=1 FACE_VECTORDB_MODE=mock \
  python scripts/sync_faces_to_device.py --force-enable

# Real API
FACE_VECTORDB_ENABLED=1 FACE_VECTORDB_MODE=http \
FACE_VECTORDB_BASE_URL=https://vectordb.example FACE_VECTORDB_API_KEY=… \
  python scripts/sync_faces_to_device.py
```

AC also syncs on **startup** when `face_vectordb.enabled` + `sync_on_startup: true`.  
Set `sync_before_identify: true` to refresh again at each B1 scan gate.

## Note

Some panels only match faces enrolled via live `adduser`. If JPEG-only push creates “ghost” users, store **device-native templates** in VectorDB (from a prior successful on-device enroll) and sync those.
