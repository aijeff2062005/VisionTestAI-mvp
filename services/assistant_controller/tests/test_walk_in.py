"""Face scans must reach the walk-in gate even when today's gallery is empty."""

from __future__ import annotations

import time

from ac.config import AppConfig
from ac.display_client import DisplayClient, DisplayHub
from ac.face_client import FaceMatchResult
from ac.walk_in import FaceWalkInLoop


class _Hospital:
    def list_today_face_gallery(self, **kwargs):  # noqa: ANN003
        raise AssertionError("The appointment gallery must not gate face scans")

    def lookup_by_enroll_id(self, enroll_id):  # noqa: ANN001
        assert enroll_id == 77502
        return {"found": True, "patient": {"name": "PAT-1", "patient_name": "Bệnh nhân thử"}}


class _Sessions:
    active = None

    def is_busy(self):
        return False


class _Face:
    def __init__(self):
        self.options = None

    def wait_for_identify(self, **kwargs):  # noqa: ANN003
        self.options = kwargs
        return FaceMatchResult(
            matched=True, patient_id="77502", enroll_id=77502,
            name="Bệnh nhân thử", status="matched", event_time="2026-10-07 16:13:51",
        )


def test_face_scan_starts_without_today_gallery() -> None:
    face = _Face()
    started = []
    hub = DisplayHub()
    loop = FaceWalkInLoop(
        hospital=_Hospital(), face=face, sessions=_Sessions(),
        display=DisplayClient(hub), cfg=AppConfig().face_vectordb,
        on_start=lambda session: (started.append(session), loop._stop.set()),
        callback_url="http://127.0.0.1:8000/callback",
    )

    before = time.time()
    loop._run()

    assert len(started) == 1
    assert started[0].patient_id == "PAT-1"
    assert face.options["accept_existing_recent"] is True
    assert face.options["min_event_epoch"] >= before


def test_unmapped_enroll_id_cannot_be_used_as_frappe_patient() -> None:
    class MissingHospital(_Hospital):
        def lookup_by_enroll_id(self, enroll_id):  # noqa: ANN001
            return {"found": False}

    loop = FaceWalkInLoop(
        hospital=MissingHospital(), face=_Face(), sessions=_Sessions(),
        display=DisplayClient(DisplayHub()), cfg=AppConfig().face_vectordb,
        on_start=lambda session: None,
        callback_url="http://127.0.0.1:8000/callback",
    )

    match = FaceMatchResult(matched=True, patient_id="77502", enroll_id=77502)
    assert loop._session_from_match(match) is None
