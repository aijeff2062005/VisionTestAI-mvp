# Future: Earbuds guided setup (draft — not implemented)

Face-on earbuds are hard to see once seated in the canal. Do **not** rely on
“worn earbuds” detection from a frontal camera for readiness.

Instead, treat setup as a **guided hold → insert** sequence for **both** ears,
using pose wrists + ear landmarks already in `src/pose_body.py`.

## Planned detector classes (later)

| Class | Role |
|-------|------|
| `over_ear` | Current milestone (closed-set YOLO) |
| `earbud` | Bud body / stem visible |
| `earbud_in_hand` | Optional — bud overlapping wrist |

## Phase machine

```text
WaitingDevice
  → LeftInHand   (earbud near left wrist, brief hold)
  → LeftInEar    (same track moves to left ear landmark, hold ~0.5–1s)
  → RightInHand
  → RightInEar
  → EarbudsReady (both sides latched)
```

Order may be left-first or right-first via independent latch flags; readiness
requires **both** sides.

## Constraints

- Hold timers so a single frame near the ear does not pass.
- Abort / reset if person leaves frame or READY zone lost for too long.
- Vision “earbuds ready” is separate from `--micro` audio device choice.
- Prefer **over-ear** for Orange Pi MVP until this ships.

## Config stub (not wired)

```yaml
headphones:
  earbuds_setup:
    enabled: false
    hold_seconds: 0.7
    require_both_sides: true
    classes: [earbud, earbud_in_hand]
```

No runtime path in `SpellSession` / `ReadinessRules` yet.
