"""Vision measurement start + AC results callback adapters."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import now_datetime


def _acuity_score(eye: dict[str, Any]) -> str:
    """Return the measured level, marking a failed row as below that level."""
    score = str(eye.get("vn_over_10") or eye.get("logmar") or "").strip()
    if eye.get("row_passed") is False and score and not score.startswith("<"):
        return f"<{score}"
    return score


def _letter_rows_from_trials(raw_trials: list[Any] | None) -> list[dict[str, Any]]:
    """Expand AC raw_trials (row aggregates) into one child row per letter."""
    rows: list[dict[str, Any]] = []
    for trial in raw_trials or []:
        if not isinstance(trial, dict):
            continue
        targets = list(trial.get("target") or [])
        heards = list(trial.get("heard") or [])
        n = max(len(targets), len(heards), 0)
        eye = str(trial.get("eye") or "").strip().lower() or "left"
        if eye not in ("left", "right", "both"):
            eye = "left"
        logmar = trial.get("logmar")
        try:
            logmar_f = float(logmar) if logmar is not None else None
        except (TypeError, ValueError):
            logmar_f = None
        vn = trial.get("vn_over_10") or ""
        outcome = str(trial.get("outcome") or "")
        voice_urls = trial.get("voice_urls") or trial.get("voice_url") or []
        if isinstance(voice_urls, str):
            voice_urls = [voice_urls]
        for i in range(n):
            expected = str(targets[i] if i < len(targets) else "").strip().upper()
            actual = str(heards[i] if i < len(heards) else "").strip().upper()
            matched = bool(
                expected
                and actual
                and actual not in ("?", "[UNK]", "UNC", "[UNC]")
                and expected == actual
            )
            voice = ""
            if i < len(voice_urls) and voice_urls[i]:
                voice = str(voice_urls[i])
            rows.append(
                {
                    "eye": eye,
                    "logmar": logmar_f,
                    "vn_over_10": vn,
                    "letter_index": i + 1,
                    "expected": expected,
                    "actual": actual,
                    "matched": 1 if matched else 0,
                    "row_outcome": outcome,
                    "voice_url": voice,
                }
            )
    return rows


@frappe.whitelist(allow_guest=True, methods=["POST"])
def start_measurement(
    patient_id: str | None = None,
    station_id: str | None = None,
) -> dict[str, Any]:
    if patient_id is None:
        patient_id = frappe.form_dict.get("patient_id")
    if station_id is None:
        station_id = frappe.form_dict.get("station_id") or "station-01"
    if not patient_id:
        frappe.throw("patient_id is required")
    if not frappe.db.exists("Patient", patient_id):
        frappe.throw(f"Patient not found: {patient_id}")

    doc = frappe.get_doc(
        {
            "doctype": "Vision Measurement",
            "patient": patient_id,
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    from smart_hospital.api.clinic_shell import publish_clinic_data_update

    publish_clinic_data_update("Vision Measurement", doc.name)
    return {
        "success": True,
        "vision_measurement": doc.name,
        "patient_id": patient_id,
        "station_id": station_id,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive_results() -> dict[str, Any]:
    """Accept assistant_controller results_callback JSON body."""
    raw = frappe.request.get_json(silent=True) or dict(frappe.form_dict)
    if isinstance(raw, str):
        raw = json.loads(raw)

    patient_id = raw.get("patient_id")
    face_enroll_id = raw.get("face_enroll_id")
    patient_name = raw.get("patient_name")
    session_id = raw.get("session_id")
    acuity = raw.get("acuity") or {}
    right = acuity.get("right") or {}
    left = acuity.get("left") or {}
    both = acuity.get("both") or {}
    right_score = _acuity_score(right)
    left_score = _acuity_score(left)
    both_score = _acuity_score(both)
    raw_trials = raw.get("raw_trials") or []
    letter_rows = _letter_rows_from_trials(raw_trials)

    if not patient_id and face_enroll_id:
        patient_id = frappe.db.get_value(
            "Patient",
            {"custom_aiface_enroll_id": int(face_enroll_id)},
            "name",
        )

    # Resolve a retry by session id before creating any fallback measurement.
    # This covers a lost HTTP response after Frappe already committed.
    va_name = None
    if session_id:
        va_name = frappe.db.get_value(
            "Visual Acuity", {"session_id": session_id}, "name"
        )
    if va_name:
        va = frappe.get_doc("Visual Acuity", va_name)
        vm_name = va.vision_measurement
    else:
        vision_measurement = raw.get("vision_measurement") or session_id
        if vision_measurement and frappe.db.exists(
            "Vision Measurement", vision_measurement
        ):
            vm_name = vision_measurement
        else:
            if not patient_id:
                frappe.throw("patient_id or face_enroll_id required")
            vm = frappe.get_doc(
                {
                    "doctype": "Vision Measurement",
                    "patient": patient_id,
                }
            )
            vm.insert(ignore_permissions=True)
            vm_name = vm.name
        va_name = frappe.db.get_value(
            "Visual Acuity", {"vision_measurement": vm_name}, "name"
        )

    payload_json = json.dumps(raw, ensure_ascii=False, default=str)
    if va_name:
        va = frappe.get_doc("Visual Acuity", va_name)
        va.session_id = session_id
        va.right_score = right_score
        va.left_score = left_score
        va.both_score = both_score
        va.result_payload = payload_json
        if letter_rows:
            va.set("letters", letter_rows)
        if raw_trials:
            va.raw_trials_json = json.dumps(raw_trials, ensure_ascii=False, indent=2)
        va.save(ignore_permissions=True)
    else:
        va = frappe.get_doc(
            {
                "doctype": "Visual Acuity",
                "vision_measurement": vm_name,
                "session_id": session_id,
                "right_score": right_score,
                "left_score": left_score,
                "both_score": both_score,
                "result_payload": payload_json,
                "letters": letter_rows,
                "raw_trials_json": json.dumps(raw_trials, ensure_ascii=False, indent=2),
            }
        )
        va.insert(ignore_permissions=True)

    # Link back on Vision Measurement when field exists
    try:
        frappe.db.set_value(
            "Vision Measurement",
            vm_name,
            "visual_acuity",
            va.name,
        )
    except Exception:  # noqa: BLE001
        pass

    checkout: dict[str, Any] | None = None
    if patient_id:
        try:
            from smart_hospital.api.clinic_desk import check_out_today_appointment

            checkout = check_out_today_appointment(patient=patient_id)
        except Exception as exc:  # noqa: BLE001
            checkout = {"success": False, "error": str(exc)}

    frappe.db.commit()
    from smart_hospital.api.clinic_shell import publish_clinic_data_update

    publish_clinic_data_update("Visual Acuity", va.name)
    return {
        "success": True,
        "visual_acuity": va.name,
        "vision_measurement": vm_name,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "received_at": str(now_datetime()),
        "right_score": right_score,
        "left_score": left_score,
        "both_score": both_score,
        "letter_count": len(letter_rows),
        "appointment_checkout": checkout,
    }
