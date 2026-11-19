# Demo flow graph (full AC setup)

Font stays **Optician Sans / Sloan letters**. Scoring: **≤1 miss** → pass row; results include **`vn_over_10`** (e.g. `8/10`). Letter timeout **10 s** → miss that letter and continue. After a row: pass → smaller; fail → same size once; fail again → bigger.

Runtime: **`conda activate smarteyes`** (shared with SmartEyes — no `.venv` for full demo).

```mermaid
flowchart TD
  Start[MQTT_or_demo_session] --> Face[B1_AiFace_identify]
  Face -->|matched_name| Queue[SHOW_QUEUE]
  Face -->|stranger| Reg[must_register_on_panel]
  Reg -->|match_after_enroll| Queue
  Reg -->|timeout| Fail[FAILED]
  Queue --> Ready[WAIT_READY_SmartEyes]
  Ready -->|ready| Cover[PLAY_AUDIO_B4_cover]
  Cover --> Show[SHOW_ROW_Sloan]
  Show --> Listen[LISTEN_letter]
  Listen -->|within_10s_and_match| NextL{more_letters?}
  Listen -->|timeout_or_wrong| Miss[count_miss_?]
  Miss --> NextL
  NextL -->|yes| Listen
  NextL -->|row_done| Score{misses_le_1?}
  Score -->|yes_pass| Smaller{smaller_size?}
  Score -->|no_fail| Retry{same_size_retry_left?}
  Retry -->|yes| Show
  Retry -->|no| Bigger{bigger_size?}
  Smaller -->|yes| Show
  Smaller -->|no_finest| EyeDone[eye_complete]
  Bigger -->|yes| Show
  Bigger -->|no_coarsest| EyeDone
  EyeDone --> Other{other_eye?}
  Other -->|yes| Cover
  Other -->|no| Confirm[CONFIRM_B10]
  Confirm --> Results[UI_plus_JSON_file]
  Results --> HttpOpt[HTTP_callback_best_effort]
```

## Size staircase (one eye)

```mermaid
flowchart LR
  S05["logMAR 0.5\n~3/10"] -->|pass| S04["0.4"]
  S04 -->|pass| S03["0.3"]
  S03 -->|pass| S02["0.2"]
  S02 -->|pass| S01["0.1\n~8/10"]
  S01 -->|pass| S00["0.0\n10/10"]
  S03 -->|fail_once| S03
  S03 -->|fail_again| S04
```

## Station setup reminders

- Distance **5 m** + screen **px/mm** bar  
- Light: see [lux_calibration.md](lux_calibration.md) (400–700 lux)  
- Occluder Ø **~60 mm**: [occluder_diy.md](occluder_diy.md)
- Face panel: `192.168.1.96` · SmartEyes webcam readiness
