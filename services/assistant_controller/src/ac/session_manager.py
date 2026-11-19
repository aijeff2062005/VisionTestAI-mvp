"""Active exam session lifecycle and JSONL journal."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac.models import EyesMode, SessionStart, SessionState

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TrialRecord:
    eye: str
    pass_index: int
    row_index: int
    logmar: float
    target: list[str]
    heard: list[str]
    correct: int
    total: int
    confidence_mean: float
    passed: bool = False
    outcome: str = ""  # pass | fail_retry_same | fail_go_bigger | timeout_mix
    phase: str = "legacy"  # legacy | range | verify


@dataclass
class ExamSession:
    start: SessionStart
    station_id: str
    state: SessionState = SessionState.ACCEPTED
    step_id: str | None = None
    message_vi: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    # Protocol progress
    eye_side: str = "right"  # full exam: right → left (no binocular pass)
    pass_index: int = 0
    row_index: int = 0
    readiness_ok: bool = False
    under_test: str = "RIGHT"
    current_letters: list[str] = field(default_factory=list)
    shown_letter_history: list[str] = field(default_factory=list)
    current_logmar: float | None = None
    last_stt_letter: str = ""
    last_stt_confidence: float = 0.0
    last_stt_reliable: bool = False
    last_stt_match: bool | None = None
    heard_letters: list[str] = field(default_factory=list)
    letter_cursor: int = 0
    trials: list[TrialRecord] = field(default_factory=list)
    all_eyes_done: bool = False
    eye_complete: bool = False
    same_size_fail_count: int = 0
    rows_this_eye: int = 0
    verifying_smaller_row: bool = False
    abort_reason: str | None = None
    cancelled: bool = False
    speaker_flow: bool = False
    patient_dob: str | None = None
    row_search: Any = None
    zone_done: bool = False
    rules_played: bool = False
    letter_clip_index: int = 0
    letter_replacements: int = 0
    # Face ID gate (AiFace panel)
    face_ok: bool = False
    face_name: str | None = None
    face_enroll_id: int | None = None
    vision_measurement_id: str | None = None

    def eyes_order(self) -> list[str]:
        if self.start.eyes == EyesMode.LEFT:
            return ["left"]
        if self.start.eyes == EyesMode.RIGHT:
            return ["right"]
        # A full exam means both eyes measured separately, right first.
        return ["right", "left"]

    def to_journal_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.start.session_id,
            "patient_id": self.start.patient_id,
            "state": self.state.value,
            "step_id": self.step_id,
            "eye_side": self.eye_side,
            "pass_index": self.pass_index,
            "row_index": self.row_index,
            "all_eyes_done": self.all_eyes_done,
            "ts": _utc_now().isoformat(),
        }


class SessionManager:
    """One active session per station."""

    def __init__(self, station_id: str, journal_dir: Path) -> None:
        self.station_id = station_id
        self.journal_dir = journal_dir
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active: ExamSession | None = None

    @property
    def active(self) -> ExamSession | None:
        with self._lock:
            return self._active

    def is_busy(self) -> bool:
        with self._lock:
            if self._active is None:
                return False
            return self._active.state not in (
                SessionState.COMPLETED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            )

    def start(self, payload: SessionStart) -> tuple[ExamSession | None, str | None]:
        """Return (session, error_code). error_code=busy if already active."""
        with self._lock:
            if self._active is not None and self._active.state not in (
                SessionState.COMPLETED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            ):
                return None, "busy"
            order = (
                ["left"]
                if payload.eyes == EyesMode.LEFT
                else ["right"]
                if payload.eyes == EyesMode.RIGHT
                else ["right", "left"]
            )
            session = ExamSession(
                start=payload,
                station_id=self.station_id,
                state=SessionState.ACCEPTED,
                eye_side=order[0],
                under_test=order[0].upper(),
            )
            self._active = session
            self._append_journal(session, "start", payload.model_dump(mode="json"))
            return session, None

    def cancel(self, session_id: str, reason: str | None = None) -> ExamSession | None:
        """Cancel only the requested active exam, never a different walk-in session."""
        with self._lock:
            if not self._active:
                return None
            if self._active.state in (SessionState.COMPLETED, SessionState.FAILED, SessionState.CANCELLED):
                return None
            if self._active.start.session_id != session_id:
                logger.warning(
                    "cancel session_id=%s ignored; active=%s",
                    session_id,
                    self._active.start.session_id,
                )
                return None
            self._active.cancelled = True
            self._active.abort_reason = reason or "cancelled"
            self._active.state = SessionState.CANCELLED
            self._active.updated_at = _utc_now()
            self._append_journal(self._active, "cancel", {"reason": reason})
            return self._active

    def set_state(
        self,
        state: SessionState,
        *,
        step_id: str | None = None,
        message_vi: str | None = None,
    ) -> ExamSession | None:
        with self._lock:
            if not self._active:
                return None
            self._active.state = state
            if step_id is not None:
                self._active.step_id = step_id
            if message_vi is not None:
                self._active.message_vi = message_vi
            self._active.updated_at = _utc_now()
            self._append_journal(self._active, "state", self._active.to_journal_dict())
            return self._active

    def clear_if_terminal(self) -> None:
        with self._lock:
            if self._active and self._active.state in (
                SessionState.COMPLETED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            ):
                self._append_journal(self._active, "end", self._active.to_journal_dict())
                self._active = None

    def _append_journal(self, session: ExamSession, event: str, payload: dict[str, Any]) -> None:
        path = self.journal_dir / f"{session.start.session_id}.jsonl"
        line = {
            "event": event,
            "ts": _utc_now().isoformat(),
            "payload": payload,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
