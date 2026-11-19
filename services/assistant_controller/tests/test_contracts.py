"""Contract sample validation against JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_session_start_schema() -> None:
    schema = _load_schema("session_start.schema.json")
    sample = {
        "schema_version": "0.1.0",
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "patient_id": "P001",
        "patient_name": "Nguyễn Văn A",
        "dob": "1990-01-01",
        "sex": "Male",
        "queue_number": "A012",
        "exam_type": "distance_acuity_5m",
        "eyes": "both",
        "callback_url": "https://qlbn.example/api/v1/vision/results",
        "correlation_id": "corr-1",
        "locale": "vi-VN",
    }
    Draft202012Validator(schema).validate(sample)


def test_session_status_schema() -> None:
    schema = _load_schema("session_status.schema.json")
    sample = {
        "schema_version": "0.1.0",
        "session_id": "s1",
        "station_id": "station-01",
        "state": "measuring",
        "step_id": "b7_stt",
        "message_vi": "Đang đo",
        "ts": "2026-07-23T03:00:00Z",
    }
    Draft202012Validator(schema).validate(sample)


def test_results_callback_schema() -> None:
    schema = _load_schema("results_callback.schema.json")
    sample = {
        "schema_version": "0.1.0",
        "session_id": "s1",
        "patient_id": "P001",
        "station_id": "station-01",
        "exam_type": "distance_acuity_5m",
        "completed_at": "2026-07-23T03:00:00Z",
        "acuity": {
            "right": {
                "logmar": 0.1,
                "decimal": 0.8,
                "snellen_approx": "6/7.5",
                "vn_over_10": "8/10",
                "correct": 4,
                "total": 5,
            },
            "left": {
                "logmar": 0.0,
                "decimal": 1.0,
                "snellen_approx": None,
                "vn_over_10": "10/10",
                "correct": 3,
                "total": 5,
                "row_passed": True,
            },
        },
        "protocol": {
            "passes_per_eye": 3,
            "distance_m": 5.0,
            "letter_uncertain_threshold": 0.45,
            "letter_accept_threshold": 0.75,
            "max_misses": 1,
            "letter_timeout_seconds": 10,
            "letter_chunk_seconds": 3,
            "letter_protocol": "model_a_threshold_band",
        },
        "raw_trials": [],
    }
    Draft202012Validator(schema).validate(sample)


def test_pydantic_roundtrip() -> None:
    from ac.models import ResultsCallback, SessionStart

    start = SessionStart(
        session_id="s1",
        patient_id="P001",
        callback_url="http://127.0.0.1:9/results",
    )
    assert start.schema_version == "0.1.0"
    with_patient = SessionStart(
        session_id="s2",
        patient_id="PAT-001",
        patient_name="Nguyễn Văn A",
        dob="1990-01-01",
        sex="Male",
        callback_url="http://127.0.0.1:9/results",
    )
    assert with_patient.patient_name == "Nguyễn Văn A"
    assert with_patient.dob == "1990-01-01"
