"""Clinic desk APIs: nurse station, doctor review, patient booking, CCCD QR apply."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

import frappe
import requests
from frappe.utils import getdate, now_datetime, today

# Healthcare Patient Appointment.status (Select) — clinic vision flow:
#   book desk     → Open
#   face / start  → Checked In
#   exam finished → Checked Out
APPT_STATUS_BOOKED = "Open"
APPT_STATUS_CHECKED_IN = "Checked In"
APPT_STATUS_CHECKED_OUT = "Checked Out"
APPT_ACTIVE_STATUSES = ("Scheduled", "Open", "Confirmed", "Checked In")
APPT_PAST_DUE_STATUSES = ("Scheduled", "Open", "Confirmed")


def _require_clinic_user(allowed: tuple[str, ...] = ("Nursing User", "Physician", "Healthcare Administrator", "System Manager")) -> None:
    if frappe.session.user == "Guest":
        frappe.throw("Vui lòng đăng nhập.", frappe.AuthenticationError)
    if not set(frappe.get_roles()).intersection(allowed):
        frappe.throw("Bạn không có quyền thực hiện thao tác này.", frappe.PermissionError)


def require_bookable_face(doc, method=None) -> None:
    """All Patient Appointment entry points need a restorable Face ID source."""
    from smart_hospital.api.face_identity import normalize_aiface_enroll_id

    row = frappe.db.get_value(
        "Patient", doc.patient,
        ["custom_aiface_enroll_id", "custom_face_avatar_url"],
        as_dict=True,
    ) or {}
    if not normalize_aiface_enroll_id(row.get("custom_aiface_enroll_id")) or not str(
        row.get("custom_face_avatar_url") or ""
    ).strip():
        frappe.throw("Bệnh nhân chưa lưu ảnh khuôn mặt Face ID. Quét và xác nhận lưu ảnh trước khi đặt lịch.")


def _conf(key: str, default: str | None = None) -> str | None:
    val = frappe.conf.get(key)
    if val is None or val == "":
        return default
    return str(val)


def _set_appointment_status(appointment: str, status: str) -> bool:
    if not appointment or not frappe.db.exists("Patient Appointment", appointment):
        return False
    try:
        frappe.db.set_value("Patient Appointment", appointment, "status", status)
        return True
    except Exception:  # noqa: BLE001
        frappe.log_error(title="set_appointment_status", message=f"{appointment}→{status}")
        return False


def _notify_clinic_update(doctype: str, name: str | None = None) -> None:
    from smart_hospital.api.clinic_shell import publish_clinic_data_update

    publish_clinic_data_update(doctype, name)


def _today_appointments_for_patient(
    patient: str,
    *,
    statuses: tuple[str, ...] | None = None,
) -> list[str]:
    if not patient:
        return []
    filters: dict[str, Any] = {
        "patient": patient,
        "appointment_date": today(),
    }
    if statuses:
        filters["status"] = ["in", list(statuses)]
    else:
        filters["status"] = ["not in", ["Cancelled", "No Show"]]
    return frappe.get_all(
        "Patient Appointment",
        filters=filters,
        pluck="name",
        order_by="modified desc",
        limit_page_length=20,
    )


def update_today_appointment_status(
    patient: str | None = None,
    status: str | None = None,
    appointment: str | None = None,
) -> dict[str, Any]:
    """Set status on today's vision appointment(s) for a patient."""
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if status is None:
        status = frappe.form_dict.get("status")
    if appointment is None:
        appointment = frappe.form_dict.get("appointment")
    if not status:
        return {"success": False, "error": "status_required"}
    updated: list[str] = []
    if appointment:
        if _set_appointment_status(appointment, status):
            updated.append(appointment)
    elif patient:
        # Check-in only touches not-yet-finished rows; check-out same.
        want = (
            APPT_ACTIVE_STATUSES
            if status in (APPT_STATUS_CHECKED_IN, APPT_STATUS_BOOKED)
            else None
        )
        for name in _today_appointments_for_patient(patient, statuses=want):
            if _set_appointment_status(name, status):
                updated.append(name)
    else:
        return {"success": False, "error": "patient_or_appointment_required"}
    if updated:
        frappe.db.commit()
        _notify_clinic_update("Patient Appointment", appointment or updated[0])
    return {"success": True, "status": status, "appointments": updated, "patient": patient}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def check_in_today_appointment(
    patient: str | None = None,
    appointment: str | None = None,
) -> dict[str, Any]:
    """Face gate / nurse start: mark today's appointment Checked In."""
    return update_today_appointment_status(
        patient=patient,
        appointment=appointment,
        status=APPT_STATUS_CHECKED_IN,
    )


@frappe.whitelist(allow_guest=True, methods=["POST"])
def check_out_today_appointment(
    patient: str | None = None,
    appointment: str | None = None,
) -> dict[str, Any]:
    """Exam finished: mark today's appointment Checked Out."""
    return update_today_appointment_status(
        patient=patient,
        appointment=appointment,
        status=APPT_STATUS_CHECKED_OUT,
    )


@frappe.whitelist(allow_guest=True, methods=["POST"])
def apply_cccd_scan(
    patient: str | None = None,
    enroll_id: int | str | None = None,
    media_url: str | None = None,
    object_key: str | None = None,
    raw_payload: str | None = None,
) -> dict[str, Any]:
    """Decode CCCD QR (via qr_decode or raw) and merge onto Patient."""
    from smart_hospital.api.face_identity import _ensure_custom_fields

    _ensure_custom_fields()

    if patient is None:
        patient = frappe.form_dict.get("patient")
    if enroll_id is None:
        enroll_id = frappe.form_dict.get("enroll_id")
    if media_url is None:
        media_url = frappe.form_dict.get("media_url")
    if object_key is None:
        object_key = frappe.form_dict.get("object_key")
    if raw_payload is None:
        raw_payload = frappe.form_dict.get("raw_payload")

    parsed: dict[str, Any] = {}
    raw = (raw_payload or "").strip()

    if not raw and (media_url or object_key):
        qr_base = (_conf("visiontestai_qr_decode_url") or "http://qr_decode:9020").rstrip("/")
        media_token = _conf("visiontestai_media_token") or "dev-media-token"
        if not media_url and object_key:
            media_base = (_conf("visiontestai_media_base") or "http://media:9010").rstrip("/")
            media_url = f"{media_base}/v1/objects/{object_key}"
        try:
            resp = requests.post(
                f"{qr_base}/v1/decode_url",
                json={"url": media_url, "media_token": media_token},
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            frappe.log_error(title="apply_cccd_scan decode_url", message=str(exc))
            return {"success": False, "error": f"qr_decode_failed: {exc}"}
        if not body.get("success"):
            return {"success": False, "error": body.get("error") or "decode_failed", "qr": body}
        raw = body.get("raw") or ""
        parsed = body.get("parsed") or {}
    elif raw:
        # Local light parse (same pipe format)
        parts = [p.strip() for p in raw.split("|")]
        parsed = {
            "nationalId": parts[0] if parts else "",
            "fullName": parts[2] if len(parts) > 2 else "",
            "birthDate": parts[3] if len(parts) > 3 else "",
            "sex": parts[4] if len(parts) > 4 else "",
            "address": parts[5] if len(parts) > 5 else parts[7] if len(parts) > 7 else "",
        }

    if not patient and enroll_id is not None:
        try:
            eid = int(enroll_id)
        except (TypeError, ValueError):
            eid = None
        if eid is not None:
            try:
                patient = frappe.db.get_value(
                    "Patient", {"custom_aiface_enroll_id": eid}, "name"
                )
            except Exception:  # noqa: BLE001
                patient = None

    if not patient:
        return {"success": False, "error": "patient_required", "parsed": parsed, "raw": raw}

    if not frappe.db.exists("Patient", patient):
        return {"success": False, "error": f"patient_not_found:{patient}"}

    doc = frappe.get_doc("Patient", patient)
    national_id = str(parsed.get("nationalId") or "").strip()
    full_name = str(parsed.get("fullName") or "").strip()
    address = str(parsed.get("address") or "").strip()
    sex = str(parsed.get("sex") or "").strip()
    birth = str(parsed.get("birthDate") or "").strip()

    if national_id and hasattr(doc, "uid"):
        doc.uid = national_id
    if full_name:
        parts = full_name.split()
        if parts:
            doc.first_name = parts[0]
            if len(parts) > 1:
                doc.last_name = parts[-1]
            if len(parts) > 2:
                doc.middle_name = " ".join(parts[1:-1])
        if hasattr(doc, "patient_name"):
            doc.patient_name = full_name
    if sex:
        s = sex.lower()
        if s in ("male", "nam", "m", "1"):
            doc.sex = "Male"
        elif s in ("female", "nữ", "nu", "f", "2"):
            doc.sex = "Female"
        else:
            doc.sex = sex
    if birth:
        # Accept DDMMYYYY or YYYY-MM-DD
        try:
            if len(birth) == 8 and birth.isdigit():
                doc.dob = getdate(f"{birth[4:8]}-{birth[2:4]}-{birth[0:2]}")
            else:
                doc.dob = getdate(birth)
        except Exception:  # noqa: BLE001
            pass
    if address and hasattr(doc, "cccd_address"):
        doc.cccd_address = address

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "success": True,
        "patient": doc.name,
        "parsed": parsed,
        "raw": raw,
        "media_url": media_url,
        "applied_at": str(now_datetime()),
    }


@frappe.whitelist()
def list_today_appointments(appointment_type: str | None = None) -> dict[str, Any]:
    """Nurse desk: today's Patient Appointments."""
    _require_clinic_user()
    filters: dict[str, Any] = {"appointment_date": today()}
    if appointment_type:
        filters["appointment_type"] = appointment_type
    rows = frappe.get_all(
        "Patient Appointment",
        filters=filters,
        fields=[
            "name",
            "patient",
            "patient_name",
            "status",
            "appointment_time",
            "appointment_type",
            "practitioner",
            "service_unit",
        ],
        order_by="appointment_time asc",
        limit_page_length=200,
    )
    now = now_datetime()
    now_time = now.time()
    for row in rows:
        row["past_due_unconducted"] = False
        row["past_due_note"] = ""
        appt_time = row.get("appointment_time")
        if row.get("status") not in APPT_PAST_DUE_STATUSES or not appt_time:
            continue
        try:
            if appt_time < now_time:
                row["past_due_unconducted"] = True
                row["past_due_note"] = "Appointment time already passed and not conducted."
        except Exception:  # noqa: BLE001
            continue
    return {"success": True, "appointments": rows, "date": today()}


@frappe.whitelist()
def list_arrivals(limit: int = 50) -> dict[str, Any]:
    """Recent patients with AiFace enroll (arrived / registered via Face ID)."""
    limit = int(limit or 50)
    rows = frappe.get_all(
        "Patient",
        filters={"custom_aiface_enroll_id": ["is", "set"]},
        fields=[
            "name",
            "patient_name",
            "uid",
            "mobile",
            "custom_aiface_enroll_id",
            "custom_aiface_display_name",
            "custom_aiface_enrolled_at",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=limit,
    )
    return {"success": True, "arrivals": rows}


def _latest_open_vision_measurement(patient: str) -> str | None:
    """Most recent Vision Measurement for patient that has no Visual Acuity yet."""
    if not patient:
        return None
    rows = frappe.get_all(
        "Vision Measurement",
        filters={"patient": patient},
        fields=["name", "visual_acuity", "creation"],
        order_by="creation desc",
        limit_page_length=10,
    )
    for row in rows:
        if not row.get("visual_acuity"):
            return str(row["name"])
    return str(rows[0]["name"]) if rows else None


@frappe.whitelist()
def start_appointment_measurement(
    appointment: str | None = None,
    patient: str | None = None,
    station_id: str | None = None,
) -> dict[str, Any]:
    """Create Vision Measurement and MQTT-start the station."""
    _require_clinic_user(("Nursing User", "Healthcare Administrator", "System Manager"))
    if appointment is None:
        appointment = frappe.form_dict.get("appointment")
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if station_id is None:
        station_id = frappe.form_dict.get("station_id") or _conf(
            "visiontestai_station_id", "station-01"
        )

    if not patient and appointment:
        patient = frappe.db.get_value("Patient Appointment", appointment, "patient")
    if not patient:
        frappe.throw("patient or appointment required")

    from smart_hospital.api.vision import start_measurement
    from smart_hospital.api.send_vision_measurement import send_vision_measurement

    started = start_measurement(patient_id=patient, station_id=station_id)
    vm = started.get("vision_measurement")
    if appointment and frappe.db.exists("Patient Appointment", appointment):
        _ensure_appointment_desk_fields()
        frappe.db.set_value(
            "Patient Appointment",
            appointment,
            "custom_active_vision_measurement",
            vm,
        )
        frappe.db.commit()
    mqtt = send_vision_measurement(vision_measurement=vm)
    if appointment and frappe.db.exists("Patient Appointment", appointment):
        try:
            frappe.db.set_value(
                "Patient Appointment", appointment, "status", APPT_STATUS_CHECKED_IN
            )
        except Exception:  # noqa: BLE001
            pass
        frappe.db.commit()
        _notify_clinic_update("Patient Appointment", appointment)
    elif patient:
        update_today_appointment_status(
            patient=patient, status=APPT_STATUS_CHECKED_IN
        )
    _notify_clinic_update("Vision Measurement", vm)
    return {
        "success": True,
        "patient": patient,
        "appointment": appointment,
        "vision_measurement": vm,
        "mqtt": mqtt,
    }


@frappe.whitelist()
def cancel_appointment_measurement(
    appointment: str | None = None,
    patient: str | None = None,
    vision_measurement: str | None = None,
    station_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Abort in-progress station exam (MQTT session/cancel) from Nurse Station."""
    _require_clinic_user(("Nursing User", "Healthcare Administrator", "System Manager"))
    if appointment is None:
        appointment = frappe.form_dict.get("appointment")
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if vision_measurement is None:
        vision_measurement = frappe.form_dict.get("vision_measurement")
    if station_id is None:
        station_id = frappe.form_dict.get("station_id") or _conf(
            "visiontestai_station_id", "station-01"
        )
    if reason is None:
        reason = frappe.form_dict.get("reason")

    if not patient and appointment:
        patient = frappe.db.get_value("Patient Appointment", appointment, "patient")

    vm = vision_measurement
    if not vm and appointment and frappe.db.exists("Patient Appointment", appointment):
        _ensure_appointment_desk_fields()
        vm = frappe.db.get_value(
            "Patient Appointment", appointment, "custom_active_vision_measurement"
        )
    if vm and not frappe.db.exists("Vision Measurement", vm):
        frappe.throw(f"Vision Measurement not found: {vm}")
    if not vm and patient:
        vm = _latest_open_vision_measurement(patient)
    if not vm:
        frappe.throw(
            "No open Vision Measurement to cancel — start a measurement first, "
            "or pass vision_measurement."
        )

    from smart_hospital.api.send_vision_measurement import cancel_vision_measurement

    mqtt = cancel_vision_measurement(
        vision_measurement=vm,
        reason=reason or "Cancelled from Nurse Station",
        station_id=station_id,
    )

    # Leave desk able to start again; patient may still be at clinic.
    if appointment and frappe.db.exists("Patient Appointment", appointment):
        try:
            frappe.db.set_value(
                "Patient Appointment", appointment, "status", APPT_STATUS_BOOKED
            )
            frappe.db.commit()
            _notify_clinic_update("Patient Appointment", appointment)
        except Exception:  # noqa: BLE001
            pass
    elif patient:
        update_today_appointment_status(patient=patient, status=APPT_STATUS_BOOKED)

    return {
        "success": True,
        "patient": patient,
        "appointment": appointment,
        "vision_measurement": vm,
        "mqtt": mqtt,
    }


def _default_company() -> str:
    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not company:
        frappe.throw("No Company found — create one in Desk first")
    return str(company)


def _ensure_appointment_desk_fields() -> None:
    """Small desk-only fields that have no standard Patient Appointment field."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "Patient Appointment": [
                {
                    "fieldname": "custom_station_room",
                    "label": "Trạm / phòng đo",
                    "fieldtype": "Data",
                    "insert_after": "department",
                },
                {
                    "fieldname": "custom_priority",
                    "label": "Ưu tiên",
                    "fieldtype": "Select",
                    "options": "Thông thường\nƯu tiên\nKhẩn",
                    "default": "Thông thường",
                    "insert_after": "custom_station_room",
                },
                {
                    "fieldname": "custom_assigned_staff",
                    "label": "Nhân viên phụ trách",
                    "fieldtype": "Link",
                    "options": "User",
                    "insert_after": "custom_priority",
                },
                {
                    "fieldname": "custom_active_vision_measurement",
                    "label": "Phiên đo hiện tại",
                    "fieldtype": "Data",
                    "hidden": 1,
                    "insert_after": "custom_assigned_staff",
                },
            ]
        },
        update=True,
    )
    frappe.clear_cache(doctype="Patient Appointment")


def _ensure_vision_appointment_type(duration_minutes: int = 15) -> str:
    """Ensure Appointment Type + Medical Department exist for vision booking."""
    type_name = "Vision Test"
    dept_name = "Vision Testing"
    if not frappe.db.exists("Medical Department", dept_name):
        frappe.get_doc(
            {"doctype": "Medical Department", "department": dept_name}
        ).insert(ignore_permissions=True)

    if frappe.db.exists("Appointment Type", type_name):
        # Keep duration usable for end>start validation
        cur = frappe.db.get_value("Appointment Type", type_name, "default_duration")
        if not cur or int(cur) <= 0:
            frappe.db.set_value("Appointment Type", type_name, "default_duration", duration_minutes)
        return type_name

    frappe.get_doc(
        {
            "doctype": "Appointment Type",
            "appointment_type": type_name,
            "default_duration": duration_minutes,
            "allow_booking_for": "Department",
            "color": "#2490ef",
        }
    ).insert(ignore_permissions=True)
    return type_name


@frappe.whitelist()
def visioncare_appointment_options() -> dict[str, Any]:
    """Return real Frappe records for the desk booking form."""
    _require_clinic_user()
    _ensure_appointment_desk_fields()
    default_type = _ensure_vision_appointment_type()
    rooms = frappe.get_all(
        "Healthcare Service Unit",
        filters={"is_group": 0, "allow_appointments": 1},
        fields=["name", "healthcare_service_unit_name"],
        order_by="healthcare_service_unit_name asc",
        limit_page_length=200,
    )
    clinic_roles = ["Nursing User", "Physician", "Healthcare Administrator", "System Manager"]
    staff_names = frappe.get_all(
        "Has Role", filters={"role": ["in", clinic_roles]}, pluck="parent", limit_page_length=500
    )
    staff = frappe.get_all(
        "User",
        filters={"name": ["in", staff_names or ["__none__"]], "enabled": 1},
        fields=["name", "full_name"],
        order_by="full_name asc",
        limit_page_length=200,
    )
    appointment_types = frappe.get_all(
        "Appointment Type", fields=["name"], order_by="name asc", limit_page_length=200
    )
    return {
        "rooms": rooms,
        "staff": staff,
        "appointment_types": appointment_types,
        "default_type": default_type,
        "statuses": [
            {"value": "Open", "label": "Đã đặt"},
            {"value": "Scheduled", "label": "Đã lên lịch"},
            {"value": "Confirmed", "label": "Đã xác nhận"},
        ],
        "priorities": ["Thông thường", "Ưu tiên", "Khẩn"],
    }


@frappe.whitelist()
def book_vision_appointment(
    patient: str | None = None,
    appointment_date: str | None = None,
    appointment_time: str | None = None,
    practitioner: str | None = None,
    notes: str | None = None,
    duration: int | str | None = None,
    appointment_type: str | None = None,
    department: str | None = None,
    station_room: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assigned_staff: str | None = None,
) -> dict[str, Any]:
    """Patient desk: create a vision Patient Appointment."""
    _require_clinic_user()
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if not patient:
        frappe.throw("patient is required")
    if not frappe.db.exists("Patient", patient):
        frappe.throw(f"Patient not found: {patient}")

    appointment_date = appointment_date or frappe.form_dict.get("appointment_date") or today()
    appointment_time = appointment_time or frappe.form_dict.get("appointment_time")
    if not appointment_time:
        appointment_time = now_datetime().strftime("%H:%M")
    if isinstance(appointment_time, str) and len(appointment_time) == 5:
        appointment_time = f"{appointment_time}:00"
    practitioner = practitioner or frappe.form_dict.get("practitioner")
    notes = notes or frappe.form_dict.get("notes") or "Vision acuity"
    if duration is None:
        duration = frappe.form_dict.get("duration")
    duration_minutes = int(duration or 15)
    if duration_minutes <= 0:
        duration_minutes = 15

    _ensure_appointment_desk_fields()
    if appointment_type is None:
        appointment_type = frappe.form_dict.get("appointment_type")
    appt_type = appointment_type or _ensure_vision_appointment_type(duration_minutes)
    if not frappe.db.exists("Appointment Type", appt_type):
        frappe.throw("Loại khám không tồn tại.")
    company = _default_company()
    department = department or frappe.form_dict.get("department") or "Vision Testing"
    if not frappe.db.exists("Medical Department", department):
        department = "Vision Testing"
    status = status or frappe.form_dict.get("status") or APPT_STATUS_BOOKED
    if status not in {"Open", "Scheduled", "Confirmed"}:
        frappe.throw("Trạng thái lịch không hợp lệ.")
    priority = priority or frappe.form_dict.get("priority") or "Thông thường"
    if priority not in {"Thông thường", "Ưu tiên", "Khẩn"}:
        frappe.throw("Mức ưu tiên không hợp lệ.")
    station_room = station_room or frappe.form_dict.get("station_room") or department
    assigned_staff = assigned_staff or frappe.form_dict.get("assigned_staff")
    if assigned_staff and not frappe.db.exists("User", assigned_staff):
        frappe.throw("Nhân viên phụ trách không tồn tại.")

    payload: dict[str, Any] = {
        "doctype": "Patient Appointment",
        "patient": patient,
        "company": company,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "appointment_type": appt_type,
        "appointment_for": "Department",
        "department": department,
        "duration": duration_minutes,
        "status": status,
        "notes": notes,
        "appointment_based_on_check_in": 1,
        "custom_station_room": station_room,
        "custom_priority": priority,
        "custom_assigned_staff": assigned_staff,
    }
    if practitioner and frappe.db.exists("Healthcare Practitioner", practitioner):
        payload["appointment_for"] = "Practitioner"
        payload["practitioner"] = practitioner
        payload.pop("department", None)

    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _notify_clinic_update("Patient Appointment", doc.name)

    # Keep the original synchronous fast path: wait for the station to confirm
    # its face update before reporting the booking's Face ID state.
    is_today = str(getdate(appointment_date)) == str(getdate(today()))
    station_push: dict[str, Any] | None = None
    face_state = "scheduled"
    if is_today:
        try:
            station_push = push_patient_face_to_station(patient=patient)
        except Exception as exc:  # noqa: BLE001
            station_push = {"success": False, "error": str(exc)}
        face_state = "synced" if station_push.get("success") else "sync_failed"
        if face_state == "sync_failed":
            frappe.log_error(
                title="Face ID gallery push failed",
                message=f"{patient}: {station_push.get('error') or 'station did not confirm push'}",
            )

    return {
        "success": True,
        "appointment": doc.name,
        "patient": patient,
        "appointment_type": appt_type,
        "duration": duration_minutes,
        "station_push": station_push,
        "face_state": face_state,
    }


@frappe.whitelist()
def list_pending_reviews(limit: int = 50) -> dict[str, Any]:
    """Doctor desk: Visual Acuity rows needing review / prescription."""
    _require_clinic_user(("Physician", "Healthcare Administrator", "System Manager"))
    limit = int(limit or 50)
    vas = frappe.get_all(
        "Visual Acuity",
        fields=["name", "vision_measurement", "right_score", "left_score", "both_score", "creation"],
        order_by="creation desc",
        limit_page_length=limit,
    )
    out = []
    for va in vas:
        vm = va.get("vision_measurement")
        patient = None
        patient_name = None
        if vm and frappe.db.exists("Vision Measurement", vm):
            patient = frappe.db.get_value("Vision Measurement", vm, "patient")
            if patient:
                patient_name = frappe.db.get_value("Patient", patient, "patient_name")
        rx = frappe.db.exists("Eye Prescription", {"vision_measurement": vm}) if vm else None
        out.append(
            {
                **va,
                "patient": patient,
                "patient_name": patient_name,
                "eye_prescription": rx,
                "reviewed": bool(rx),
            }
        )
    return {"success": True, "items": out}


@frappe.whitelist()
def save_eye_prescription(
    patient: str | None = None,
    vision_measurement: str | None = None,
    conclusion: str | None = None,
) -> dict[str, Any]:
    _require_clinic_user(("Physician", "Healthcare Administrator", "System Manager"))
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if vision_measurement is None:
        vision_measurement = frappe.form_dict.get("vision_measurement")
    if conclusion is None:
        conclusion = frappe.form_dict.get("conclusion")
    if not patient or not vision_measurement:
        frappe.throw("patient and vision_measurement required")

    existing = frappe.db.exists(
        "Eye Prescription", {"vision_measurement": vision_measurement}
    )
    if existing:
        doc = frappe.get_doc("Eye Prescription", existing)
        doc.conclusion = conclusion
        doc.patient = patient
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Eye Prescription",
                "patient": patient,
                "vision_measurement": vision_measurement,
                "conclusion": conclusion,
            }
        )
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _notify_clinic_update("Eye Prescription", doc.name)
    return {"success": True, "eye_prescription": doc.name}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def list_today_face_gallery(
    appointment_type: str | None = None,
    light: int | str | None = None,
    history_days: int | str | None = None,
) -> dict[str, Any]:
    """Faces for active appointments from the recent past through today.

    The panel is a local verify cache, so a recently-booked patient remains
    matchable after midnight. Cancelled/no-show appointments are excluded.
    light=1 returns enroll ids + avatar fingerprints only (for Jetson poll).
    """
    from smart_hospital.api.face_identity import _ensure_custom_fields, STRANGER_ENROLL_ID

    _ensure_custom_fields()
    if appointment_type is None:
        appointment_type = frappe.form_dict.get("appointment_type")
    if light is None:
        light = frappe.form_dict.get("light")
    if history_days is None:
        history_days = frappe.form_dict.get("history_days")
    light_mode = str(light or "").strip().lower() in ("1", "true", "yes")

    # Include prior-day appointments so a midnight/UTC boundary does not
    # empty the face cache before the clinic can serve the booked patient.
    # Keep the history bounded; callers can override for a supervised rollout.
    try:
        history_days_i = max(0, min(30, int(history_days if history_days is not None else 7)))
    except (TypeError, ValueError):
        history_days_i = 7
    start_date = getdate(today())
    if isinstance(start_date, str):
        from datetime import date

        start_date = date.fromisoformat(start_date)
    start_date = start_date - timedelta(days=history_days_i)
    filters: dict[str, Any] = {
        "appointment_date": ["between", [str(start_date), str(today())]],
        "status": ["not in", ["Cancelled", "No Show"]],
    }
    if appointment_type:
        filters["appointment_type"] = appointment_type
    appts = frappe.get_all(
        "Patient Appointment",
        filters=filters,
        fields=["name", "patient", "patient_name", "appointment_time", "status"],
        order_by="appointment_date desc, appointment_time asc",
        limit_page_length=500,
    )
    faces: list[dict[str, Any]] = []
    protected_enroll_ids: list[int] = []
    diagnostics = {"appointments": len(appts), "missing_patient": 0,
                   "missing_enroll_id": 0, "missing_face_avatar": 0}
    seen: set[str] = set()
    for appt in appts:
        patient = appt.get("patient")
        if not patient or patient in seen:
            if not patient:
                diagnostics["missing_patient"] += 1
            continue
        seen.add(patient)
        row = frappe.db.get_value(
            "Patient",
            patient,
            [
                "name",
                "patient_name",
                "custom_aiface_enroll_id",
                "custom_aiface_display_name",
                "custom_face_avatar_url",
                "custom_face_avatar_object_key",
            ],
            as_dict=True,
        )
        if not row:
            diagnostics["missing_patient"] += 1
            continue
        eid = row.get("custom_aiface_enroll_id")
        try:
            eid_i = int(eid) if eid not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            eid_i = None
        if eid_i is None or eid_i <= 0 or eid_i == STRANGER_ENROLL_ID:
            diagnostics["missing_enroll_id"] += 1
            continue
        avatar = (row.get("custom_face_avatar_url") or "").strip()
        if not avatar:
            diagnostics["missing_face_avatar"] += 1
            protected_enroll_ids.append(eid_i)
            continue
        if avatar.startswith("http://media:") or avatar.startswith("https://media:"):
            from smart_hospital.api.face_identity import _media_conf, _public_media_base, _rewrite_media_url

            avatar = _rewrite_media_url(avatar, _public_media_base(_media_conf()[0])) or avatar
        if light_mode:
            kind = "data" if avatar.startswith("data:") else "url"
            faces.append(
                {
                    "patient": row.get("name"),
                    "enroll_id": eid_i,
                    "full_name": row.get("custom_aiface_display_name")
                    or row.get("patient_name")
                    or row.get("name"),
                    "avatar_kind": kind,
                    "avatar_len": len(avatar),
                    "avatar_fp": hashlib.sha256(avatar.encode("utf-8")).hexdigest(),
                    "object_key": row.get("custom_face_avatar_object_key"),
                    "appointment": appt.get("name"),
                }
            )
            continue
        media_url = None if avatar.startswith("data:") else avatar
        image_b64 = avatar.split(",", 1)[-1] if avatar.startswith("data:") else None
        faces.append(
            {
                "patient": row.get("name"),
                "patient_name": row.get("patient_name") or appt.get("patient_name"),
                "enroll_id": eid_i,
                "full_name": row.get("custom_aiface_display_name")
                or row.get("patient_name")
                or row.get("name"),
                "media_get_url": media_url,
                "image_b64": image_b64,
                "object_key": row.get("custom_face_avatar_object_key"),
                "appointment": appt.get("name"),
                "appointment_time": appt.get("appointment_time"),
                "status": appt.get("status"),
            }
        )
    return {
        "success": True,
        "date": today(),
        "faces": faces,
        "count": len(faces),
        "light": light_mode,
        "diagnostics": diagnostics,
        # Preserve an already enrolled panel face while the desk repairs the
        # missing durable avatar for a patient booked today.
        "protected_enroll_ids": protected_enroll_ids,
    }


def _station_url() -> str:
    from smart_hospital.api.face_identity import get_aiface_station_url

    cfg = get_aiface_station_url()
    url = str(cfg.get("aiface_station_url") or "").rstrip("/")
    if not cfg.get("success") or not url:
        raise RuntimeError(cfg.get("error") or "aiface_station_url_not_configured")
    return url


def _remove_patient_face_from_station(patient: str) -> dict[str, Any]:
    """Remove only this patient's device face after their last gallery booking."""
    row = frappe.db.get_value("Patient", patient, "custom_aiface_enroll_id")
    try:
        enroll_id = int(row or 0)
    except (TypeError, ValueError):
        enroll_id = 0
    if enroll_id <= 0 or enroll_id == 99999999:
        return {"success": True, "skipped": True, "reason": "missing_enroll_id"}

    url = ""
    try:
        url = f"{_station_url()}/api/face/delete_one"
        response = requests.post(url, json={"enroll_id": enroll_id}, timeout=20)
        body = response.json() if response.content else {}
        if not response.ok or not isinstance(body, dict) or not body.get("success"):
            error = body.get("detail") or body.get("error") if isinstance(body, dict) else None
            return {"success": False, "error": error or f"HTTP {response.status_code}", "station": url}
        return {"success": True, "enroll_id": enroll_id, "station": url, "result": body}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc), "station": url}


@frappe.whitelist()
def patient_face_sync_status(patient: str | None = None) -> dict[str, Any]:
    """Report Face ID readiness for the patient's current avatar, not booking success."""
    patient = patient or frappe.form_dict.get("patient")
    if not patient or not frappe.db.exists("Patient", patient):
        return {"success": False, "error": "patient_not_found"}
    row = frappe.db.get_value(
        "Patient", patient, ["custom_aiface_enroll_id", "custom_face_avatar_url"], as_dict=True,
    ) or {}
    try:
        eid = int(row.get("custom_aiface_enroll_id") or 0)
    except (TypeError, ValueError):
        eid = 0
    avatar = str(row.get("custom_face_avatar_url") or "").strip()
    if not eid or not avatar:
        return {"success": True, "ready": False, "error": "missing_face_avatar"}
    if avatar.startswith(("http://media:", "https://media:")):
        from smart_hospital.api.face_identity import _media_conf, _public_media_base, _rewrite_media_url

        avatar = _rewrite_media_url(avatar, _public_media_base(_media_conf()[0])) or avatar
    version = hashlib.sha256((avatar.split(",", 1)[-1] if avatar.startswith("data:") else avatar).encode("utf-8")).hexdigest()
    try:
        resp = requests.get(
            f"{_station_url()}/api/face/gallery_status/{eid}",
            params={"version": version},
            timeout=(2, 5),
        )
        resp.raise_for_status()
        return {"success": True, "ready": bool(resp.json().get("ready")), "enroll_id": eid}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "ready": False, "error": str(exc)}


@frappe.whitelist()
def push_patient_face_to_station(
    patient: str | None = None,
    request_timeout: int | float | None = None,
) -> dict[str, Any]:
    """Push one patient's avatar JPEG to Jetson AiFace (same-day verify cache)."""
    from smart_hospital.api.face_identity import _ensure_custom_fields, STRANGER_ENROLL_ID

    _ensure_custom_fields()
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if not patient:
        return {"success": False, "error": "patient_required"}
    if not frappe.db.exists("Patient", patient):
        return {"success": False, "error": f"patient_not_found:{patient}"}

    row = frappe.db.get_value(
        "Patient",
        patient,
        [
            "name",
            "patient_name",
            "custom_aiface_enroll_id",
            "custom_aiface_display_name",
            "custom_face_avatar_url",
        ],
        as_dict=True,
    )
    eid = row.get("custom_aiface_enroll_id") if row else None
    try:
        eid_i = int(eid) if eid not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        eid_i = None
    avatar = (row.get("custom_face_avatar_url") or "").strip() if row else ""
    if avatar.startswith("http://media:") or avatar.startswith("https://media:"):
        from smart_hospital.api.face_identity import _media_conf, _public_media_base, _rewrite_media_url

        avatar = _rewrite_media_url(avatar, _public_media_base(_media_conf()[0])) or avatar
    if eid_i is None or eid_i == STRANGER_ENROLL_ID:
        return {"success": False, "error": "missing_enroll_id", "patient": patient}
    if not avatar:
        return {"success": False, "error": "missing_avatar", "patient": patient}

    # Only push when patient has an appointment today (capacity + overnight wipe model).
    has_today = frappe.db.exists(
        "Patient Appointment",
        {
            "patient": patient,
            "appointment_date": today(),
            "status": ["not in", ["Cancelled", "No Show"]],
        },
    )
    if not has_today:
        return {
            "success": True,
            "skipped": True,
            "reason": "no_appointment_today",
            "patient": patient,
            "enroll_id": eid_i,
        }

    payload = {
        "enroll_id": eid_i,
        "full_name": row.get("custom_aiface_display_name")
        or row.get("patient_name")
        or patient,
        "media_get_url": avatar if not avatar.startswith("data:") else None,
        "image_b64": avatar.split(",", 1)[-1] if avatar.startswith("data:") else None,
        "patient_id": patient,
    }
    url = ""
    try:
        url = f"{_station_url()}/api/face/push_one"
        timeout = 8 if request_timeout is None else float(request_timeout)
        if timeout <= 0:
            timeout = 8
        resp = requests.post(url, json=payload, timeout=(3, timeout))
        body = resp.json() if resp.content else {}
        if not resp.ok or not body.get("success"):
            return {
                "success": False,
                "error": body.get("error") or f"Face ID chưa xác nhận ảnh (HTTP {resp.status_code})",
                "station": url,
            }
        return {"success": True, "station": url, "result": body}
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(title="push_patient_face_to_station", message=str(exc))
        return {"success": False, "error": str(exc), "station": url}


@frappe.whitelist()
def sync_today_faces_to_station() -> dict[str, Any]:
    """Ask Jetson AC to reload AiFace gallery from today's appointments."""
    url = ""
    try:
        url = f"{_station_url()}/api/face/sync_today"
        resp = requests.post(url, json={}, timeout=120)
        body = resp.json() if resp.content else {}
        if not resp.ok or not isinstance(body, dict) or not body.get("success"):
            error = body.get("error") if isinstance(body, dict) else None
            return {
                "success": False,
                "error": error or f"HTTP {resp.status_code}",
                "station": url,
            }
        return {"success": True, "station": url, "result": body}
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(title="sync_today_faces_to_station", message=str(exc))
        return {"success": False, "error": str(exc), "station": url}


@frappe.whitelist()
def wipe_aiface_gallery_nightly() -> dict[str, Any]:
    """Compatibility target for a stale Frappe cron; Jetson guards its own cleanup."""
    return {"success": True, "skipped": True}


@frappe.whitelist()
def remove_appointment(appointment: str | None = None) -> dict[str, Any]:
    """Drop a booked appointment from today's nurse list (does not delete Patient)."""
    if appointment is None:
        appointment = frappe.form_dict.get("appointment")
    _require_clinic_user(("Nursing User", "Healthcare Administrator", "System Manager"))
    if not appointment:
        frappe.throw("appointment is required")
    if not frappe.db.exists("Patient Appointment", appointment):
        frappe.throw(f"Appointment not found: {appointment}")

    doc = frappe.get_doc("Patient Appointment", appointment)
    if doc.status == APPT_STATUS_CHECKED_IN:
        frappe.throw("Dừng phiên đo trước khi xóa lịch hẹn.")
    patient = doc.patient
    action = "removed"
    try:
        doc = frappe.get_doc("Patient Appointment", appointment)
        if int(doc.docstatus or 0) == 1:
            doc.cancel()
            action = "cancelled"
        else:
            frappe.delete_doc(
                "Patient Appointment",
                appointment,
                ignore_permissions=True,
                force=True,
            )
            action = "deleted"
    except Exception as exc:  # noqa: BLE001
        if not _set_appointment_status(appointment, "Cancelled"):
            frappe.throw(f"Could not remove appointment: {exc}")
        frappe.db.commit()
        action = "cancelled"
    else:
        frappe.db.commit()
    _notify_clinic_update("Patient Appointment", appointment)

    # Removing an appointment releases the device slot immediately. The next
    # patient can then be enrolled on panels with a limited user capacity.
    face_sync = None
    face_sync = _remove_patient_face_from_station(patient)
    if not face_sync.get("success"):
        frappe.log_error(
            title="Face ID deletion after appointment removal failed",
            message=f"{appointment} / {patient}: {face_sync.get('error') or face_sync}",
        )

    return {
        "success": True,
        "appointment": appointment,
        "patient": patient,
        "action": action,
        "face_sync": face_sync,
    }
