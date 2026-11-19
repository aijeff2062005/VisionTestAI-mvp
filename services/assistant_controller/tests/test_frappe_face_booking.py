"""Fast contract checks for the VPS booking path without a Frappe runtime."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _load_clinic_desk(monkeypatch):
    frappe = types.ModuleType("frappe")
    frappe.form_dict = {}
    frappe.db = MagicMock()
    frappe.db.exists.return_value = True
    frappe.enqueue = MagicMock()
    frappe.get_doc = MagicMock()
    frappe.get_all = MagicMock()
    frappe.db.get_value.return_value = {
        "custom_aiface_enroll_id": 77502,
        "custom_face_avatar_url": "https://media.example/face.jpg",
    }
    frappe.whitelist = lambda fn=None, **_kw: fn if fn is not None else lambda wrapped: wrapped
    frappe.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda value: value
    utils.now_datetime = lambda: datetime(2026, 10, 5, 10, 0)
    utils.today = lambda: "2026-10-05"
    monkeypatch.setitem(sys.modules, "frappe", frappe)
    monkeypatch.setitem(sys.modules, "frappe.utils", utils)
    source = (
        Path(__file__).resolve().parents[3]
        / "services/hospital/smart-hospital/smart_hospital/api/clinic_desk.py"
    )
    spec = importlib.util.spec_from_file_location("clinic_desk_under_test", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, frappe


def test_booking_uses_insert_hooks_for_face_sync(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    monkeypatch.setattr(desk, "_ensure_vision_appointment_type", lambda _duration: "Vision")
    monkeypatch.setattr(desk, "_default_company", lambda: "Hospital")
    doc = MagicMock()
    doc.name = "APPT-1"
    frappe.get_doc.return_value = doc

    result = desk.book_vision_appointment(patient="P1", appointment_date="2026-10-05", appointment_time="10:30")

    assert result["success"] is True
    assert result["station_push"]["state"] == "queued"
    assert result["face_state"] == "queued"
    frappe.db.commit.assert_not_called()
    frappe.enqueue.assert_not_called()


def test_future_booking_does_not_queue_face(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    monkeypatch.setattr(desk, "_ensure_vision_appointment_type", lambda _duration: "Vision")
    monkeypatch.setattr(desk, "_default_company", lambda: "Hospital")
    frappe.get_doc.return_value.name = "APPT-2"

    result = desk.book_vision_appointment(patient="P1", appointment_date="2026-10-06", appointment_time="10:30")

    assert result["station_push"] is None
    assert result["face_state"] == "scheduled"
    frappe.enqueue.assert_not_called()


def test_booking_without_durable_avatar_is_rejected(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    identity = types.ModuleType("smart_hospital.api.face_identity")
    identity.normalize_aiface_enroll_id = lambda value: int(value) if value else None
    monkeypatch.setitem(sys.modules, "smart_hospital.api.face_identity", identity)
    frappe.db.get_value.return_value = {
        "custom_aiface_enroll_id": 77502,
        "custom_face_avatar_url": "",
    }

    with pytest.raises(ValueError, match="chưa lưu ảnh"):
        desk.require_bookable_face(SimpleNamespace(patient="P1"))
    frappe.enqueue.assert_not_called()


def test_any_same_day_appointment_enqueues_face_after_commit(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    desk.queue_booked_face(SimpleNamespace(patient="P1", appointment_date="2026-10-05"))

    frappe.enqueue.assert_called_once()
    assert frappe.enqueue.call_args.kwargs["enqueue_after_commit"] is True


def test_today_gallery_reports_bookings_without_restorable_faces(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    identity = types.ModuleType("smart_hospital.api.face_identity")
    identity._ensure_custom_fields = lambda: None
    identity.STRANGER_ENROLL_ID = 99999999
    monkeypatch.setitem(sys.modules, "smart_hospital.api.face_identity", identity)
    frappe.get_all.return_value = [
        {"name": "APPT-1", "patient": "P1"},
        {"name": "APPT-2", "patient": "P2"},
    ]
    frappe.db.get_value.side_effect = [
        {"name": "P1", "custom_aiface_enroll_id": 77502,
         "custom_face_avatar_url": ""},
        {"name": "P2", "custom_aiface_enroll_id": 77503,
         "custom_face_avatar_url": "https://media.example/p2.jpg"},
    ]

    result = desk.list_today_face_gallery(light=1)

    assert result["count"] == 1
    assert result["protected_enroll_ids"] == [77502]
    assert result["diagnostics"] == {
        "appointments": 2, "missing_patient": 0,
        "missing_enroll_id": 0, "missing_face_avatar": 1,
    }


def test_face_gallery_includes_recent_past_active_appointments(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    identity = types.ModuleType("smart_hospital.api.face_identity")
    identity._ensure_custom_fields = lambda: None
    identity.STRANGER_ENROLL_ID = 99999999
    monkeypatch.setitem(sys.modules, "smart_hospital.api.face_identity", identity)
    frappe.get_all.return_value = [{"name": "APPT-YESTERDAY", "patient": "P1"}]
    frappe.db.get_value.return_value = {
        "name": "P1", "patient_name": "Patient One",
        "custom_aiface_enroll_id": 77502,
        "custom_aiface_display_name": "Patient One",
        "custom_face_avatar_url": "https://media.example/face.jpg",
        "custom_face_avatar_object_key": "faces/p1.jpg",
    }

    result = desk.list_today_face_gallery(light=1)

    filters = frappe.get_all.call_args.kwargs["filters"]
    assert filters["appointment_date"] == ["between", ["2026-09-28", "2026-10-05"]]
    assert filters["status"] == ["not in", ["Cancelled", "No Show"]]
    assert result["count"] == 1
    assert result["faces"][0]["enroll_id"] == 77502


def test_face_gallery_history_window_can_be_configured(monkeypatch) -> None:
    desk, frappe = _load_clinic_desk(monkeypatch)
    identity = types.ModuleType("smart_hospital.api.face_identity")
    identity._ensure_custom_fields = lambda: None
    identity.STRANGER_ENROLL_ID = 99999999
    monkeypatch.setitem(sys.modules, "smart_hospital.api.face_identity", identity)
    frappe.get_all.return_value = []

    desk.list_today_face_gallery(light=1, history_days=2)

    filters = frappe.get_all.call_args.kwargs["filters"]
    assert filters["appointment_date"] == ["between", ["2026-10-03", "2026-10-05"]]
