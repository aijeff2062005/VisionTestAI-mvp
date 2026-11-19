"""A delayed VPS cancellation must not stop a newer walk-in exam."""

from pydantic import HttpUrl

from ac.models import SessionStart
from ac.session_manager import SessionManager


def test_cancel_for_old_id_keeps_current_session_running(tmp_path) -> None:
    sessions = SessionManager("station", tmp_path / "journals")
    active, error = sessions.start(SessionStart(
        session_id="new-walk-in", patient_id="P1",
        callback_url=HttpUrl("http://127.0.0.1:9/results"),
    ))
    assert error is None and active is not None
    assert sessions.cancel("old-frappe-session", "Stopped from Nurse Station") is None
    assert sessions.is_busy()
    assert not active.cancelled
