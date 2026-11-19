# Demo vs Vietnam clinical standards — compliance check

Date: 2026-07-23  
Scope: VisionTestAI Assistant Controller + Sloan chart display demo vs standards found for VN clinic / facility / health-check practice.

## Standards referenced

| Ref | Document | What it governs |
|-----|----------|-----------------|
| **A** | [TCVN 4470:2012](https://vanbanphapluat.co/tcvn-4470-2012-benh-vien-da-khoa-tieu-chuan-thiet-ke) §6.3.8.2 | Hospital design: chỗ đo thị lực length **≥ 5 m** |
| **B** | [Thông tư 105/2023/TT-BQP](https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/chinh-sach-moi/96589/quy-trinh-kham-mat-di-nghia-vu-quan-su-2026-theo-quy-dinh-moi-nhat) Phụ lục I (as amended by **106/2025/TT-BQP**); lineage from **16/2016/TTLT-BYT-BQP** | Formal **thị lực** procedure (health / military exams): distance, lighting, occluder, timing, row pass rule, **/10** scoring |
| **C** | VN ophthalmology clinic practice (hospital guides) | Charts: Snellen / Landolt C / E; report **x/10** at ~5 m |

> Note: **B** is written for khám sức khỏe BQP/BYT, not a single “TCVN optotype chart” law. It is still the clearest **official VN procedure** for how thị lực is measured and scored. There is **no TCVN** that mandates Sloan letters or a fixed letter count per row.

## Verdict

**Partially aligned** with Vietnamese BQP thị lực procedure after v0.2 updates (≤1 miss, `/10` field, 10 s letter timeout, staircase).  
Still **not fully certified**: Sloan/Optician Sans (not Landolt/E), no automated lux gate, no BQP “tổng 2 mắt” points table, occluder is DIY process only.

---

## Requirement matrix

| # | Standard requirement | Source | Demo today | Status |
|---|----------------------|--------|------------|--------|
| 1 | Test distance / room length **≥ 5 m** | A, B | `distance_m: 5.0`; chart math at 5 m; **physical room not enforced** | Partial |
| 2 | Chart: black letters on white | B | White chart bg, black glyphs | OK |
| 3 | Row **7/10–8/10** hung at eye height | B | Digital screen; no physical hang / eye-height check | Gap |
| 4 | Illumination **~400–700 lux**, no glare | B | Not measured / not gated | Gap |
| 5 | Occlude with **hard card**, not hand; both eyes open | B | SmartEyes detects eye cover (hand/occluder CV); **does not enforce “bìa cứng”**; AC default readiness is **mock** | Partial / Gap |
| 6 | Point letter-by-letter; answer **&lt; 10 s** per letter | B | STT listen timeout **45 s**/letter (config); no pointer UX | Gap |
| 7 | Rows **8/10, 9/10, 10/10**: pass if **≤ 1 miss** | B | **`max_misses: 1`** (≤1 miss on row) | Aligned |
| 8 | Letters per row | B (silent) / C | Demo fixed **5** (logMAR-style). VN Snellen often **variable** | N/A / different model |
| 9 | Result scale **x/10** (decimal thập phân) | B, C | Results include **`vn_over_10`** plus logMAR | Aligned (dual) |
| 10 | Cap single-eye &gt;10/10 at 10/10 when summing 2 eyes (BQP) | B | No “tổng thị lực 2 mắt” BQP scoring | Gap |
| 11 | Chart type: Snellen / Landolt C / E common in VN | C | **Sloan** set + **Optician Sans** (kept by product choice) | Different (kept) |
| 12 | Optotype angular size at acuity | International / C | `1.4544 × D / decimalVA` (5′ at D) — sound sizing math if calibrated | OK (if calibrated) |
| 13 | Screen calibration | Best practice | 100 mm bar → px/mm | OK (manual) |
| 14 | STT confidence gate | Drawio (product) | ≥ **0.8** for acuity path | Product rule (not in B) |
| 15 | Per-letter **&lt; 10 s** | B | `letter_timeout_seconds: 10`; miss & advance | Aligned |
| 16 | Illumination 400–700 lux | B | Manual lux calibrate SOP ([lux_calibration.md](lux_calibration.md)) | Partial (manual) |
| 17 | Hard occluder | B | DIY Ø ~60 mm ([occluder_diy.md](occluder_diy.md)) | Partial (process) |

---

## Scoring comparison (critical)

### VN BQP (rows 8/10–10/10)

- Fail a row if **more than 1** letter wrong (exact row length not mandated).
- Record acuity as **n/10**.

### Demo AC (`configs/default.yaml` + `scoring.py`)

- `letters_per_row: 5`, `min_correct: 3` → allow **2** wrong and still count the row.
- Best (lowest) logMAR among eligible rows.
- HTTP results: `acuity.*.logmar` / `decimal` / `snellen_approx` — **not** `10/10`.

Example: decimal VA 0.8 → VN clinic often writes **8/10**; demo stores logMAR **0.1** and decimal **0.8**.

---

## Chart / alphabet comparison

| | VN clinic common | Demo |
|--|------------------|------|
| Alphabet | Snellen Latin / Landolt C / E | Sloan `C D H K N O R S V Z` |
| Font | Printed certified chart | Optician Sans (CDN approximation) |
| Layout | Full chart or pointed rows | One row at a time (AC), optional full chart in UI |
| AC exam rows | Often walk down to smallest readable **/10** row | Fixed logMAR set `[0.5, 0.3, 0.1]` × 3 passes/eye |

Sloan letters are scientifically acceptable (ETDRS family) but **not** the usual VN wall-chart set.

---

## Process / UX comparison

| Step | VN BQP-style | Demo AC |
|------|----------------|---------|
| Start | Staff / nurse | MQTT from QLBN |
| Guide stand at 5 m | Verbal / room marks | Audio scenario + SmartEyes zone (when not mock) |
| Cover one eye | Hard occluder | Audio + CV eye-cover (approximate) |
| Show letters | Wall chart + pointer | Remote WebSocket chart |
| Patient response | Spoken letter / direction | Sloan STT (VN names) or mock |
| End | Staff records **/10** | Confirm audio + HTTP callback |

---

## What already matches intent of standards

1. **5 m** as design distance (TCVN room length + BQP cự ly).  
2. **One eye at a time** with cover instruction.  
3. **High-contrast** black-on-white presentation.  
4. Calibratable on-screen size (supports correct angular size *if* room is actually 5 m and px/mm is correct).

## Highest-priority gaps to close for VN alignment

1. **Scoring:** switch row pass to **≤1 miss** (or map explicitly to BQP for `/10` rows); emit **`vn_over_10`** (e.g. `8/10`) in results.  
2. **Reporting:** primary clinical field = **thập phân x/10**, keep logMAR as secondary.  
3. **Timing:** enforce **≤10 s** per letter (or document STT exception).  
4. **Environment:** lux check or install checklist (400–700 lux); eye-height / fullscreen exam SOP.  
5. **Occluder:** coach + detect rigid occluder; reject bare-hand cover for “standard mode”.  
6. **Chart choice:** optional Landolt C / E / Snellen mode for VN clinics; or keep Sloan but label as “ETDRS-style screening, not BQP chart”.  
7. **Font:** replace Optician Sans with licensed Sloan/ETDRS (or VN-certified) assets for production.

---

## Compliance statement (for requirement.md ask)

> “Please review the implemented parts and compare them with the standards to see if they are truly compliant.”

**Answer:** Implemented AC + chart demo are **not truly compliant** with VN BQP/BYT thị lực procedure or typical VN clinic **/10** reporting. They are a **provisional Sloan/logMAR automation demo** that correctly targets **5 m** distance and one-eye testing, but diverge on pass rules, result notation, lighting, occluder type, letter set, and certified optotypes.

---

## Related demo files

- Protocol: [`configs/default.yaml`](../configs/default.yaml)  
- Scoring: [`src/ac/scoring.py`](../src/ac/scoring.py)  
- Contracts note: [`contracts.md`](contracts.md)  
- Chart UI: [`display/index.html`](../display/index.html)  
- Architecture ask: [`../../System Architecture/requirement.md`](../../System%20Architecture/requirement.md)
