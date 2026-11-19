"""Pydantic models for provisional QLBN ↔ AC contracts (v0.1.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


SCHEMA_VERSION = "0.1.0"


class ExamType(str, Enum):
    DISTANCE_ACUITY_5M = "distance_acuity_5m"


class EyesMode(str, Enum):
    BOTH = "both"
    LEFT = "left"
    RIGHT = "right"


class SessionState(str, Enum):
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    GUIDING = "guiding"
    MEASURING = "measuring"
    RESULTS = "results"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionStart(BaseModel):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    patient_id: str
    patient_name: str | None = None
    sex: str | None = None
    queue_number: str | None = None
    exam_type: ExamType = ExamType.DISTANCE_ACUITY_5M
    eyes: EyesMode = EyesMode.BOTH
    callback_url: HttpUrl
    correlation_id: str | None = None
    locale: str = "vi-VN"
    face_image_ref: str | None = None
    # Walk-in from AiFace: skip welcome / service menu and go to the chart test.
    auto_enter_test: bool = False
    dob: str | None = None


class SessionCancel(BaseModel):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    reason: str | None = None
    correlation_id: str | None = None


class SessionStatus(BaseModel):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    station_id: str | None = None
    state: SessionState
    step_id: str | None = None
    message_vi: str | None = None
    queue_number: str | None = None
    error_code: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EyeAcuity(BaseModel):
    logmar: float
    decimal: float
    snellen_approx: str | None = None
    vn_over_10: str | None = None  # e.g. "8/10" — VN clinic scale
    correct: int
    total: int
    row_passed: bool | None = None


class ProtocolInfo(BaseModel):
    passes_per_eye: int
    distance_m: float
    letter_uncertain_threshold: float
    letter_accept_threshold: float
    max_misses: int = 1
    letter_timeout_seconds: float = 10.0
    letter_chunk_seconds: float | None = None
    scoring: str = "vn_bqp_max_1_miss"
    letter_protocol: str = "model_a_threshold_band"


class ResultsCallback(BaseModel):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    patient_id: str
    patient_name: str | None = None
    face_enroll_id: int | None = None
    station_id: str
    exam_type: ExamType = ExamType.DISTANCE_ACUITY_5M
    completed_at: datetime
    acuity: dict[str, EyeAcuity]
    protocol: ProtocolInfo
    raw_trials: list[dict[str, Any]] = Field(default_factory=list)
    vision_measurement: str | None = None


class ActionName(str, Enum):
    PLAY_AUDIO = "PLAY_AUDIO"
    SHOW_ROW = "SHOW_ROW"
    SHOW_QUEUE = "SHOW_QUEUE"
    LISTEN = "LISTEN"
    COMPARE = "COMPARE"
    RECORD = "RECORD"
    SWITCH_EYE = "SWITCH_EYE"
    SHOW_RESULTS = "SHOW_RESULTS"
    SUBMIT = "SUBMIT"
    RETRY = "RETRY"
    ABORT = "ABORT"
    WAIT_READY = "WAIT_READY"
    IDLE = "IDLE"


class DecisionResult(BaseModel):
    action: ActionName
    step_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
