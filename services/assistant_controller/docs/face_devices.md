# Dual Face ID devices (production stub)

MVP uses **one** panel with `bridges.face.role: combined` (front door + vision room).

## Config

See [`configs/default.yaml`](../configs/default.yaml):

```yaml
bridges:
  face:
    host: 192.168.1.18
    device_id: panel-01
    role: combined   # combined | front_door | vision_room

face_devices:
  - id: front-door
    host: 192.168.1.22
    role: front_door
  - id: vision-room
    host: 192.168.1.18
    role: vision_room
```

## Intended roles (later)

| Role | Behavior |
|------|----------|
| `front_door` | Identify → welcome / queue number only; no exam |
| `vision_room` | Identify → service menu → Vision Test → SmartEyes + chart |
| `combined` | MVP: identify → register prompt if needed → service menu → exam |

Hospital DB (`Patient.aiface_enroll_id`) is shared. Sync enrollments to both panels with AiFace `setuserinfo` when multi-device ships.

Gallery source: **Face VectorDB API** (placeholder) — see [face_vectordb.md](face_vectordb.md). AC loads faces onto the panel so verification runs **on device** at scan time.
