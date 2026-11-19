# Light / lux calibration (for chart setup)

Vietnam BQP procedure targets roughly **400–700 lux** at the chart (ambient illuminance), no glare into the patient’s eyes.

## What to buy

- A cheap **lux meter** (illuminance meter). Phone lux apps are approximate only — OK for rough setup, not for audit.
- Optional (better for self-lit screens): **luminance meter** (cd/m²). Research charts often target **~80–320 cd/m²** chart luminance (ETDRS-style ~160 cd/m²).

## Method A — Wall / ambient chart (matches BQP lux wording)

1. Place patient mark at **5 m**.
2. Put the lux meter **on the chart surface** (or flush against the monitor bezel facing the room lights the way the chart is lit).
3. Adjust room lights / blinds until reading is **400–700 lx**.
4. Avoid:
   - Spotlights into the patient’s eyes
   - Strong reflections / glare on the screen
   - Mixing very bright window + dark room
5. Record: date, lux reading, screen brightness %, room lamp settings → station log.

Ref: [Fiat Lux — illuminance & VA](https://pmc.ncbi.nlm.nih.gov/articles/PMC4884565/) suggests keeping community/clinic illuminance around **400–600 lx** to limit score drift.

## Method B — Self-lit monitor / tablet chart

1. Disable auto-brightness; set a fixed brightness (e.g. 70–100%).
2. Warm up display **≥15 minutes**.
3. Ideally measure **luminance (cd/m²)** on the white chart background with a luminance meter perpendicular to the screen.
4. Also note ambient lux at the patient (reflections). High ambient + glossy screen → washout.

Ref: [PLOS One photometric tablet/ETDRS compliance](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0150676).

## Demo station checklist (no meter automation yet)

| Step | Action | Target |
|------|--------|--------|
| 1 | Fixed monitor brightness | Note % in journal |
| 2 | Lux on chart face | 400–700 lx |
| 3 | Patient view: no glare | Visual check |
| 4 | Re-check after moving lights | Same band |

Future AC: optional `POST /api/station/lux` or MQTT status field `illuminance_lux` from a USB lux sensor — not implemented in this demo.

## Related

- Size calibration (px/mm): 100 mm bar in chart UI  
- Distance: TCVN 4470 / BQP **5 m**
