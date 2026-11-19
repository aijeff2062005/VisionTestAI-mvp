"""Orchestrator happy-path with mock adapters."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from pydantic import HttpUrl

from ac.audio_player import AudioPlayer
from ac.config import AppConfig, ProtocolConfig
from ac.display_client import DisplayClient, DisplayHub
from ac.dmn_engine import DmnEngine
from ac.http_callback import HttpCallbackClient
from ac.models import ActionName, EyesMode, ExamType, SessionStart, SessionState
from ac.orchestrator import Orchestrator
from ac.readiness_bridge import MockReadinessBridge, MockSttBridge, SttBridge, SttResult
from ac.session_manager import SessionManager

ROOT = Path(__file__).resolve().parents[1]


class CapturingHttp(HttpCallbackClient):
    def __init__(self) -> None:
        super().__init__(timeout_seconds=1.0)
        self.posted = []

    def post_results(self, callback_url, results, *, correlation_id=None):  # noqa: ANN001
        self.posted.append(results)
        return {"ok": True}


@pytest.fixture
def fast_cfg(tmp_path: Path) -> AppConfig:
    cfg = AppConfig(
        station_id="test-station",
        protocol=ProtocolConfig(
            letters_per_row=2,
            max_misses=1,
            start_logmar=0.5,
            row_logmars=[0.5, 0.3, 0.1],
            same_size_retries=1,
            max_rows_per_eye=6,
            letter_timeout_seconds=2.0,
            readiness_timeout_seconds=5.0,
            letter_uncertain_threshold=0.45,
            letter_accept_threshold=0.75,
            staircase=True,
            demo_mode=True,
        ),
    )
    cfg.paths.journals = str(tmp_path / "journals")
    cfg.paths.dmn = str(ROOT / "dmn" / "acuity_flow.dmn")
    cfg.paths.scenarios = str(ROOT / "scenarios" / "vi" / "manifest.yaml")
    return cfg


def test_happy_path_both_eyes(fast_cfg: AppConfig, tmp_path: Path) -> None:
    sessions = SessionManager(fast_cfg.station_id, tmp_path / "journals")
    dmn = DmnEngine(ROOT / "dmn" / "acuity_flow.dmn")
    hub = DisplayHub()
    display = DisplayClient(hub)
    audio = AudioPlayer(ROOT / "scenarios" / "vi" / "manifest.yaml")
    readiness = MockReadinessBridge(delay_seconds=0.0)
    stt = MockSttBridge()
    http = CapturingHttp()
    statuses: list[SessionState] = []

    def publish(status):  # noqa: ANN001
        statuses.append(status.state)

    orch = Orchestrator(
        cfg=fast_cfg,
        sessions=sessions,
        dmn=dmn,
        display=display,
        audio=audio,
        readiness=readiness,
        stt=stt,
        http=http,
        publish_status=publish,
    )

    start = SessionStart(
        session_id="sess-happy",
        patient_id="P1",
        queue_number="A1",
        exam_type=ExamType.DISTANCE_ACUITY_5M,
        eyes=EyesMode.BOTH,
        callback_url=HttpUrl("http://127.0.0.1:9/results"),
        correlation_id="c1",
    )
    session, err = sessions.start(start)
    assert err is None and session is not None
    orch.start_session_async(session)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if http.posted and SessionState.COMPLETED in statuses:
            break
        active = sessions.active
        if active is None and SessionState.COMPLETED in statuses:
            break
        time.sleep(0.05)

    assert http.posted, f"no results posted; statuses={statuses}"
    result = http.posted[0]
    assert result.session_id == "sess-happy"
    assert "right" in result.acuity or "left" in result.acuity
    eye = result.acuity.get("right") or result.acuity.get("left")
    assert eye is not None
    assert eye.vn_over_10 and eye.vn_over_10.endswith("/10")
    assert SessionState.COMPLETED in statuses
    assert result.protocol.letter_protocol == "model_a_threshold_band"
    assert set(result.acuity) <= {"right", "left"}


def test_adaptive_row_decision_and_verify_smaller(fast_cfg: AppConfig, tmp_path: Path) -> None:
    fast_cfg.protocol.adaptive_row_testing = True
    fast_cfg.protocol.adaptive_initial_letters = 2
    fast_cfg.protocol.adaptive_tiebreak_letters = 1
    fast_cfg.protocol.adaptive_verify_letters = 2
    sessions = SessionManager(fast_cfg.station_id, tmp_path / "journals_adaptive")
    orch = Orchestrator(
        cfg=fast_cfg,
        sessions=sessions,
        dmn=DmnEngine(ROOT / "dmn" / "acuity_flow.dmn"),
        display=DisplayClient(DisplayHub()),
        audio=AudioPlayer(ROOT / "scenarios" / "vi" / "manifest.yaml"),
        readiness=MockReadinessBridge(delay_seconds=0.0),
        stt=MockSttBridge(),
        http=CapturingHttp(),
        publish_status=lambda _status: None,
    )
    start = SessionStart(
        session_id="sess-adaptive",
        patient_id="P3",
        eyes=EyesMode.BOTH,
        callback_url=HttpUrl("http://127.0.0.1:9/results"),
    )
    session, err = sessions.start(start)
    assert err is None and session is not None
    assert session.eyes_order() == ["right", "left"]

    session.current_logmar = 0.5
    session.current_letters = ["C", "D", "H"]
    orch._row_shown = True
    session.heard_letters = ["?"]
    assert orch._row_complete(session) is False
    session.heard_letters = ["?", "?"]
    assert orch._row_complete(session) is False
    session.heard_letters = ["?", "D"]
    assert orch._row_complete(session) is True

    session.heard_letters = ["?", "?", "?"]
    assert orch._row_complete(session) is True
    orch._execute(session, ActionName.RECORD, "b9_record")
    assert session.verifying_smaller_row is True
    assert session.current_logmar == 0.3
    assert session.eye_complete is False
    assert session.trials[-1].outcome == "fail_three_verify_smaller"

    session.current_letters = ["K", "O"]
    session.heard_letters = ["?", "?"]
    orch._row_shown = True
    assert orch._row_complete(session) is True
    orch._execute(session, ActionName.RECORD, "b9_record")
    assert session.eye_complete is True
    assert session.verifying_smaller_row is False
    assert session.trials[-1].outcome == "verify_smaller_stop"


def test_wait_ready_speaker_advances_on_ready_or_zone_ok(fast_cfg: AppConfig, tmp_path: Path) -> None:
    fast_cfg.ui.patient_flow = "speaker_v1"
    sessions = SessionManager(fast_cfg.station_id, tmp_path / "journals_speaker")
    hub = DisplayHub()
    display = DisplayClient(hub)
    audio = AudioPlayer(ROOT / "scenarios" / "vi" / "manifest.yaml")
    readiness = MockReadinessBridge(delay_seconds=0.0)
    stt = MockSttBridge()
    http = CapturingHttp()

    orch = Orchestrator(
        cfg=fast_cfg,
        sessions=sessions,
        dmn=DmnEngine(ROOT / "dmn" / "acuity_flow.dmn"),
        display=display,
        audio=audio,
        readiness=readiness,
        stt=stt,
        http=http,
        publish_status=lambda _status: None,
    )
    start = SessionStart(
        session_id="sess-speaker-ready",
        patient_id="P_SPK",
        eyes=EyesMode.BOTH,
        callback_url=HttpUrl("http://127.0.0.1:9/results"),
    )
    session, err = sessions.start(start)
    assert err is None and session is not None
    session.speaker_flow = True

    failed = orch._wait_ready_speaker(session, fast_cfg.protocol, "b3_stand")
    assert failed is False
    assert session.readiness_ok is True
    assert session.zone_done is True

