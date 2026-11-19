"""SmartEyes readiness mapping + results JSON/display."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import HttpUrl

from ac.audio_player import AudioPlayer
from ac.config import AppConfig, ProtocolConfig
from ac.display_client import DisplayClient, DisplayHub
from ac.dmn_engine import DmnEngine
from ac.http_callback import HttpCallbackClient
from ac.models import EyesMode, ExamType, SessionStart, SessionState
from ac.orchestrator import Orchestrator
from ac.readiness_bridge import MockReadinessBridge, MockSttBridge, map_smarteyes_state
from ac.session_manager import SessionManager

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FakeState:
    line_pass: bool = True
    headphones_pass: bool = True
    under_test: str = "RIGHT"
    ready: bool = True
    coaching: str = "Stand on the marked floor line"


def test_map_smarteyes_state_ready() -> None:
    snap = map_smarteyes_state(FakeState())
    assert snap.ready is True
    assert snap.zone_ok is True
    assert snap.headphones_on is True
    assert snap.under_test == "RIGHT"
    assert "đứng" in snap.coaching_vi.lower() or "Vui lòng" in snap.coaching_vi


def test_map_smarteyes_state_not_ready() -> None:
    snap = map_smarteyes_state(
        FakeState(line_pass=False, headphones_pass=False, ready=False, coaching="Put on headphones")
    )
    assert snap.ready is False
    assert snap.zone_ok is False
    assert "tai nghe" in snap.coaching_vi.lower()


class CapturingHttp(HttpCallbackClient):
    def __init__(self) -> None:
        super().__init__(timeout_seconds=1.0)
        self.posted = []
        self.fail = False

    def post_results(self, callback_url, results, *, correlation_id=None):  # noqa: ANN001
        if self.fail:
            raise RuntimeError("sink down")
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
            confidence_threshold=0.8,
            staircase=True,
            demo_mode=True,
        ),
    )
    cfg.paths.journals = str(tmp_path / "journals")
    cfg.paths.dmn = str(ROOT / "dmn" / "acuity_flow.dmn")
    cfg.paths.scenarios = str(ROOT / "scenarios" / "vi" / "manifest.yaml")
    cfg.bridges.readiness = "mock"
    cfg.bridges.face.mode = "off"
    return cfg


def test_submit_writes_json_and_display_results(fast_cfg: AppConfig, tmp_path: Path) -> None:
    sessions = SessionManager(fast_cfg.station_id, tmp_path / "journals")
    dmn = DmnEngine(ROOT / "dmn" / "acuity_flow.dmn")
    hub = DisplayHub()
    display = DisplayClient(hub)
    audio = AudioPlayer(ROOT / "scenarios" / "vi" / "manifest.yaml")
    readiness = MockReadinessBridge(delay_seconds=0.0)
    stt = MockSttBridge()
    http = CapturingHttp()
    http.fail = True  # HTTP best-effort — session still completes
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
        session_id="sess-results",
        patient_id="1",
        queue_number="A1",
        exam_type=ExamType.DISTANCE_ACUITY_5M,
        eyes=EyesMode.BOTH,
        callback_url=HttpUrl("http://127.0.0.1:9/results"),
        correlation_id="c1",
    )
    session, err = sessions.start(start)
    assert err is None and session is not None
    session.face_name = "Vu Pham"
    session.face_enroll_id = 1
    orch.start_session_async(session)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if SessionState.COMPLETED in statuses:
            break
        time.sleep(0.05)

    assert SessionState.COMPLETED in statuses
    out = tmp_path / "journals" / "sess-results_results.json"
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["patient_name"] == "Vu Pham"
    assert data["face_enroll_id"] == 1
    assert hub.last_command.get("type") == "results"
    assert "Vu Pham" in (hub.last_command.get("patient_name") or "")
