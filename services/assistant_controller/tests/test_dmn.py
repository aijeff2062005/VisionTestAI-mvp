"""DMN engine unit tests."""

from __future__ import annotations

from pathlib import Path

from ac.dmn_engine import DmnEngine
from ac.models import ActionName

DMN = Path(__file__).resolve().parents[1] / "dmn" / "acuity_flow.dmn"


def test_load_tables() -> None:
    eng = DmnEngine(DMN)
    assert "NextAction" in eng.tables


def test_abort_on_cancel() -> None:
    eng = DmnEngine(DMN)
    d = eng.decide_next_action(
        {
            "session_state": "measuring",
            "readiness_ok": True,
            "all_eyes_done": False,
            "cancelled": True,
            "row_complete": False,
            "pass_complete": False,
            "eye_complete": False,
            "need_listen": False,
            "stt_match": False,
            "confidence_ok": False,
        }
    )
    assert d.action == ActionName.ABORT


def test_show_results_when_all_requested_eyes_done() -> None:
    eng = DmnEngine(DMN)
    d = eng.decide_next_action(
        {
            "session_state": "measuring",
            "readiness_ok": True,
            "all_eyes_done": True,
            "cancelled": False,
            "row_complete": False,
            "pass_complete": False,
            "eye_complete": False,
            "need_listen": False,
            "stt_match": False,
            "confidence_ok": True,
        }
    )
    assert d.action == ActionName.SHOW_RESULTS


def test_show_queue_on_accepted() -> None:
    eng = DmnEngine(DMN)
    d = eng.decide_next_action(
        {
            "session_state": "accepted",
            "readiness_ok": False,
            "all_eyes_done": False,
            "cancelled": False,
            "row_complete": False,
            "pass_complete": False,
            "eye_complete": False,
            "need_listen": False,
            "stt_match": False,
            "confidence_ok": False,
        }
    )
    assert d.action == ActionName.SHOW_QUEUE


def test_listen_when_needed() -> None:
    eng = DmnEngine(DMN)
    d = eng.decide_next_action(
        {
            "session_state": "measuring",
            "readiness_ok": True,
            "all_eyes_done": False,
            "cancelled": False,
            "row_complete": False,
            "pass_complete": False,
            "eye_complete": False,
            "need_listen": True,
            "stt_match": False,
            "confidence_ok": False,
        }
    )
    assert d.action == ActionName.LISTEN


def test_switch_eye() -> None:
    eng = DmnEngine(DMN)
    d = eng.decide_next_action(
        {
            "session_state": "measuring",
            "readiness_ok": True,
            "all_eyes_done": False,
            "cancelled": False,
            "row_complete": False,
            "pass_complete": False,
            "eye_complete": True,
            "need_listen": False,
            "stt_match": False,
            "confidence_ok": True,
        }
    )
    assert d.action == ActionName.SWITCH_EYE
