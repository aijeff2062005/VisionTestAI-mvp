"""Lean hospital API for VisionTestAI (VPS Docker hospital simulation).

Implements Patient ↔ AiFace enroll_id lookup/register and acuity callback.
Runs on :8000. Media bytes live on the separate media gateway (:9010).

Lab: VPS = this API + Mosquitto + media + face_vectordb; Jetson = clinic AC.
See mvp_platform/docs/QUICKSTART.md.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

import os

DB_PATH = Path(os.environ.get("HOSPITAL_DB", Path(__file__).resolve().parent / "data" / "hospital.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="VisionTestAI Hospital API", version="0.1.0")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
              id TEXT PRIMARY KEY,
              full_name TEXT NOT NULL,
              uid TEXT,
              mobile TEXT,
              aiface_enroll_id INTEGER UNIQUE,
              aiface_display_name TEXT,
              aiface_enrolled_at TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vision_measurements (
              id TEXT PRIMARY KEY,
              patient_id TEXT NOT NULL,
              station_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS visual_acuity (
              id TEXT PRIMARY KEY,
              vision_measurement_id TEXT NOT NULL,
              right_score TEXT,
              left_score TEXT,
              both_score TEXT,
              payload_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(vision_measurement_id) REFERENCES vision_measurements(id)
            );
            """
        )


init_db()


class RegisterFaceBody(BaseModel):
    enroll_id: int
    full_name: str
    uid: str | None = None
    mobile: str | None = None


class StartMeasurementBody(BaseModel):
    patient_id: str
    station_id: str = "station-01"


class AcuityEye(BaseModel):
    logmar: float | None = None
    decimal: float | None = None
    snellen_approx: str | None = None
    vn_over_10: str | None = None
    correct: int | None = None
    total: int | None = None
    row_passed: bool | None = None


class ResultsCallbackBody(BaseModel):
    schema_version: str = "0.1.0"
    session_id: str
    patient_id: str
    patient_name: str | None = None
    face_enroll_id: int | None = None
    station_id: str = "station-01"
    exam_type: str = "distance_acuity_5m"
    completed_at: str | None = None
    acuity: dict[str, Any] = Field(default_factory=dict)
    protocol: dict[str, Any] = Field(default_factory=dict)
    raw_trials: list[dict[str, Any]] = Field(default_factory=list)
    vision_measurement: str | None = None


def _acuity_score(eye: dict[str, Any]) -> str:
    score = str(eye.get("vn_over_10") or eye.get("logmar") or "").strip()
    if eye.get("row_passed") is False and score and not score.startswith("<"):
        return f"<{score}"
    return score


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hospital_api"}


@app.get("/api/method/smart_hospital.api.face_identity.lookup_by_enroll_id")
@app.get("/api/face/lookup")
def lookup_by_enroll_id(enroll_id: int) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE aiface_enroll_id = ?",
            (enroll_id,),
        ).fetchone()
    if not row:
        return {"found": False, "enroll_id": enroll_id}
    return {
        "found": True,
        "patient": {
            "name": row["id"],
            "patient_name": row["full_name"],
            "uid": row["uid"],
            "mobile": row["mobile"],
            "aiface_enroll_id": row["aiface_enroll_id"],
            "aiface_display_name": row["aiface_display_name"],
        },
    }


@app.post("/api/method/smart_hospital.api.face_identity.register_face_patient")
@app.post("/api/face/register")
def register_face_patient(body: RegisterFaceBody) -> dict[str, Any]:
    if body.enroll_id == 99999999:
        raise HTTPException(400, "Cannot register stranger enroll id")
    with _db() as conn:
        existing = conn.execute(
            "SELECT * FROM patients WHERE aiface_enroll_id = ?",
            (body.enroll_id,),
        ).fetchone()
        if body.uid:
            by_uid = conn.execute(
                "SELECT * FROM patients WHERE uid = ?",
                (body.uid,),
            ).fetchone()
        else:
            by_uid = None

        if existing:
            conn.execute(
                """
                UPDATE patients SET full_name=?, uid=COALESCE(?, uid),
                  mobile=COALESCE(?, mobile), aiface_display_name=?,
                  aiface_enrolled_at=COALESCE(aiface_enrolled_at, ?)
                WHERE aiface_enroll_id=?
                """,
                (
                    body.full_name,
                    body.uid,
                    body.mobile,
                    body.full_name,
                    _now(),
                    body.enroll_id,
                ),
            )
            pid = existing["id"]
        elif by_uid:
            conn.execute(
                """
                UPDATE patients SET aiface_enroll_id=?, aiface_display_name=?,
                  aiface_enrolled_at=?, full_name=COALESCE(?, full_name),
                  mobile=COALESCE(?, mobile)
                WHERE id=?
                """,
                (
                    body.enroll_id,
                    body.full_name,
                    _now(),
                    body.full_name,
                    body.mobile,
                    by_uid["id"],
                ),
            )
            pid = by_uid["id"]
        else:
            pid = f"PAT-{uuid.uuid4().hex[:10].upper()}"
            conn.execute(
                """
                INSERT INTO patients
                (id, full_name, uid, mobile, aiface_enroll_id,
                 aiface_display_name, aiface_enrolled_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    body.full_name,
                    body.uid,
                    body.mobile,
                    body.enroll_id,
                    body.full_name,
                    _now(),
                    _now(),
                ),
            )
        row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    return {
        "success": True,
        "patient": {
            "name": row["id"],
            "patient_name": row["full_name"],
            "aiface_enroll_id": row["aiface_enroll_id"],
        },
    }


@app.post("/api/method/smart_hospital.api.vision.start_measurement")
@app.post("/api/vision/start")
def start_measurement(body: StartMeasurementBody) -> dict[str, Any]:
    with _db() as conn:
        pat = conn.execute(
            "SELECT id FROM patients WHERE id=?",
            (body.patient_id,),
        ).fetchone()
        if not pat:
            raise HTTPException(404, f"Patient not found: {body.patient_id}")
        mid = f"MEA-{datetime.now().strftime('%d-%m-%Y')}-{uuid.uuid4().hex[:6].upper()}"
        conn.execute(
            """
            INSERT INTO vision_measurements (id, patient_id, station_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (mid, body.patient_id, body.station_id, _now()),
        )
    return {"success": True, "vision_measurement": mid, "patient_id": body.patient_id}


@app.post("/api/method/smart_hospital.api.receive_visual_acuity.receive_visual_acuity")
@app.post("/api/method/smart_hospital.api.vision.receive_results")
@app.post("/api/vision/results")
async def receive_results(request: Request) -> dict[str, Any]:
    """Accept AC results_callback JSON or legacy form fields."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        raw = await request.json()
    else:
        form = await request.form()
        raw = dict(form)

    # Legacy simple scores
    if "right_score" in raw and "vision_measurement" in raw:
        vm = str(raw["vision_measurement"])
        with _db() as conn:
            if not conn.execute(
                "SELECT 1 FROM vision_measurements WHERE id=?", (vm,)
            ).fetchone():
                raise HTTPException(404, f"Vision Measurement not found: {vm}")
            existing = conn.execute(
                "SELECT id FROM visual_acuity WHERE vision_measurement_id=? LIMIT 1",
                (vm,),
            ).fetchone()
            if existing:
                aid = existing["id"]
                conn.execute(
                    """
                    UPDATE visual_acuity
                    SET right_score=?, left_score=?, both_score=?, payload_json=?
                    WHERE id=?
                    """,
                    (
                        str(raw.get("right_score")),
                        str(raw.get("left_score")),
                        str(raw.get("both_score")),
                        json.dumps(raw),
                        aid,
                    ),
                )
            else:
                aid = f"VA-{uuid.uuid4().hex[:8].upper()}"
                conn.execute(
                    """
                    INSERT INTO visual_acuity
                    (id, vision_measurement_id, right_score, left_score, both_score,
                     payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        aid,
                        vm,
                        str(raw.get("right_score")),
                        str(raw.get("left_score")),
                        str(raw.get("both_score")),
                        json.dumps(raw),
                        _now(),
                    ),
                )
        return {
            "success": True,
            "visual_acuity": aid,
            "vision_measurement": vm,
        }

    body = ResultsCallbackBody.model_validate(raw)
    right = (body.acuity or {}).get("right") or {}
    left = (body.acuity or {}).get("left") or {}
    both = (body.acuity or {}).get("both") or {}
    right_score = _acuity_score(right)
    left_score = _acuity_score(left)
    both_score = _acuity_score(both)

    with _db() as conn:
        patient = conn.execute(
            "SELECT id FROM patients WHERE id=?",
            (body.patient_id,),
        ).fetchone()
        if not patient and body.face_enroll_id:
            patient = conn.execute(
                "SELECT id FROM patients WHERE aiface_enroll_id=?",
                (body.face_enroll_id,),
            ).fetchone()
        if not patient:
            # Auto-create shell patient so results are not lost
            pid = body.patient_id or f"PAT-{uuid.uuid4().hex[:10].upper()}"
            conn.execute(
                """
                INSERT INTO patients
                (id, full_name, uid, mobile, aiface_enroll_id,
                 aiface_display_name, aiface_enrolled_at, created_at)
                VALUES (?, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    pid,
                    body.patient_name or pid,
                    body.face_enroll_id,
                    body.patient_name,
                    _now(),
                    _now(),
                ),
            )
        else:
            pid = patient["id"]

        vm = body.vision_measurement or body.session_id
        if not conn.execute(
            "SELECT 1 FROM vision_measurements WHERE id=?", (vm,)
        ).fetchone():
            conn.execute(
                """
                INSERT INTO vision_measurements (id, patient_id, station_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (vm, pid, body.station_id, _now()),
            )
        existing = conn.execute(
            "SELECT id FROM visual_acuity WHERE vision_measurement_id=? LIMIT 1",
            (vm,),
        ).fetchone()
        if existing:
            aid = existing["id"]
            conn.execute(
                """
                UPDATE visual_acuity
                SET right_score=?, left_score=?, both_score=?, payload_json=?
                WHERE id=?
                """,
                (right_score, left_score, both_score, json.dumps(raw), aid),
            )
        else:
            aid = f"VA-{uuid.uuid4().hex[:8].upper()}"
            conn.execute(
                """
                INSERT INTO visual_acuity
                (id, vision_measurement_id, right_score, left_score, both_score,
                 payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    vm,
                    right_score,
                    left_score,
                    both_score,
                    json.dumps(raw),
                    _now(),
                ),
            )
    return {
        "success": True,
        "visual_acuity": aid,
        "vision_measurement": vm,
        "patient_id": pid,
        "right_score": right_score,
        "left_score": left_score,
        "both_score": both_score,
    }


@app.get("/api/patients")
def list_patients() -> dict[str, Any]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return {
        "patients": [
            {
                "name": r["id"],
                "patient_name": r["full_name"],
                "aiface_enroll_id": r["aiface_enroll_id"],
                "uid": r["uid"],
            }
            for r in rows
        ]
    }


@app.post("/api/method/smart_hospital.api.clinic_desk.apply_cccd_scan")
async def apply_cccd_scan(request: Request) -> dict[str, Any]:
    """Legacy FastAPI stub — stores CCCD uid on patient when provided."""
    raw = await request.json()
    enroll_id = raw.get("enroll_id")
    patient_id = raw.get("patient")
    uid = None
    payload = raw.get("raw_payload") or ""
    if payload and "|" in str(payload):
        uid = str(payload).split("|", 1)[0].strip()
    with _db() as conn:
        row = None
        if patient_id:
            row = conn.execute(
                "SELECT * FROM patients WHERE id=?", (patient_id,)
            ).fetchone()
        if not row and enroll_id is not None:
            row = conn.execute(
                "SELECT * FROM patients WHERE aiface_enroll_id=?",
                (int(enroll_id),),
            ).fetchone()
        if not row:
            return {"success": False, "error": "patient_not_found", "note": "legacy_stub"}
        if uid:
            conn.execute(
                "UPDATE patients SET uid=? WHERE id=?",
                (uid, row["id"]),
            )
        return {
            "success": True,
            "patient": row["id"],
            "uid": uid,
            "note": "legacy_hospital_api_stub",
            "media_url": raw.get("media_url"),
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
