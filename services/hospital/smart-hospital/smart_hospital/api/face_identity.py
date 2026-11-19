"""AiFace enroll_id ↔ Patient identity APIs for smart_hospital."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime


STRANGER_ENROLL_ID = 99999999


def next_aiface_enroll_id() -> int:
    """Next free Face ID number (skips 0 and stranger id)."""
    _ensure_custom_fields()
    row = frappe.db.sql(
        """
        SELECT MAX(custom_aiface_enroll_id)
        FROM `tabPatient`
        WHERE custom_aiface_enroll_id IS NOT NULL
          AND custom_aiface_enroll_id > 0
          AND custom_aiface_enroll_id <> %s
        """,
        (STRANGER_ENROLL_ID,),
    )
    current = int(row[0][0] or 0) if row else 0
    nxt = current + 1
    if nxt == STRANGER_ENROLL_ID:
        nxt += 1
    # Guard against rare race / holes filled with 0
    while frappe.db.exists("Patient", {"custom_aiface_enroll_id": nxt}):
        nxt += 1
        if nxt == STRANGER_ENROLL_ID:
            nxt += 1
    return nxt


def normalize_aiface_enroll_id(value) -> int | None:
    """Treat blank / 0 as unset (Int fields often default to 0 and break UNIQUE)."""
    if value in (None, "", "0", 0):
        return None
    try:
        eid = int(value)
    except (TypeError, ValueError):
        return None
    if eid <= 0 or eid == STRANGER_ENROLL_ID:
        return None
    return eid


def ensure_patient_genders() -> None:
    """Seed the standard linked Gender options required by Healthcare Patient."""
    for gender in ("Male", "Female", "Other"):
        if not frappe.db.exists("Gender", gender):
            frappe.get_doc({"doctype": "Gender", "gender": gender}).insert(ignore_permissions=True)


def _ensure_custom_fields() -> None:
    """Idempotent Patient custom fields for AiFace / desk webcam avatar."""
    fields = [
        {
            "fieldname": "custom_aiface_enroll_id",
            "label": "AiFace Enroll ID / Face ID Number",
            "fieldtype": "Int",
            "insert_after": "uid",
            "unique": 1,
            "in_list_view": 0,
            "description": "Auto-assigned on desk webcam face capture. Used for same-day AiFace verify.",
        },
        {
            "fieldname": "custom_aiface_display_name",
            "label": "AiFace Display Name",
            "fieldtype": "Data",
            "insert_after": "custom_aiface_enroll_id",
        },
        {
            "fieldname": "custom_aiface_enrolled_at",
            "label": "AiFace Enrolled At",
            "fieldtype": "Datetime",
            "insert_after": "custom_aiface_display_name",
            "read_only": 1,
        },
        {
            "fieldname": "custom_face_avatar_url",
            "label": "Face Avatar URL",
            # Long Text: media URLs or (fallback) data:image/jpeg;base64,... exceed Data/Small Text limits.
            "fieldtype": "Long Text",
            "insert_after": "custom_aiface_enrolled_at",
            "description": "Media gateway JPEG used as Patient avatar and same-day AiFace import.",
        },
        {
            "fieldname": "custom_emergency_contact_name",
            "label": "Người liên hệ khẩn cấp – Họ và tên",
            "fieldtype": "Data",
            "insert_after": "custom_face_avatar_object_key",
        },
        {
            "fieldname": "custom_emergency_contact_phone",
            "label": "Người liên hệ khẩn cấp – Số điện thoại",
            "fieldtype": "Data",
            "insert_after": "custom_emergency_contact_name",
        },
        {
            "fieldname": "custom_visit_reason",
            "label": "Lý do khám / triệu chứng",
            "fieldtype": "Select",
            "options": "Kiểm tra định kỳ\nNhìn xa mờ\nNhìn gần mờ\nMỏi mắt\nTái khám\nKhác",
            "insert_after": "custom_emergency_contact_phone",
        },
        {
            "fieldname": "custom_uses_glasses",
            "label": "Đang sử dụng kính?",
            "fieldtype": "Select",
            "options": "Chưa rõ\nCó\nKhông",
            "insert_after": "custom_visit_reason",
        },
        {
            "fieldname": "custom_face_avatar_object_key",
            "label": "Face Avatar Object Key",
            "fieldtype": "Data",
            "insert_after": "custom_face_avatar_url",
            "read_only": 1,
        },
    ]
    for df in fields:
        existing = frappe.db.exists(
            "Custom Field",
            {"dt": "Patient", "fieldname": df["fieldname"]},
        )
        if existing:
            # Upgrade type/meta when we change the schema (e.g. Data → Long Text).
            doc = frappe.get_doc("Custom Field", existing)
            changed = False
            for key in ("fieldtype", "label", "description", "read_only", "unique", "in_list_view", "options"):
                if key in df and doc.get(key) != df[key]:
                    doc.set(key, df[key])
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Custom Field",
                **{"dt": "Patient"},
                **df,
            }
        )
        doc.insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Patient")
    ensure_chart_voice_settings()


def ensure_chart_voice_settings() -> None:
    """Healthcare Settings: Auto | Male | Female. AC reads this via lookup."""
    if not frappe.db.exists("DocType", "Healthcare Settings"):
        return
    fieldname = "custom_chart_voice_gender"
    existing = frappe.db.exists(
        "Custom Field",
        {"dt": "Healthcare Settings", "fieldname": fieldname},
    )
    payload = {
        "fieldname": fieldname,
        "label": "Chart Voice Gender",
        "fieldtype": "Select",
        "options": "Auto\nMale\nFemale",
        "default": "Auto",
        "description": (
            "Voice on the vision-test chart. Auto: male patient hears the female "
            "pack; female patient hears the current default voice. Unknown sex "
            "keeps the current default voice. Male/Female forces that pack."
        ),
    }
    if existing:
        doc = frappe.get_doc("Custom Field", existing)
        changed = False
        for key in ("label", "fieldtype", "options", "default", "description"):
            if key in payload and doc.get(key) != payload[key]:
                doc.set(key, payload[key])
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
        return
    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": "Healthcare Settings",
            **payload,
        }
    ).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Healthcare Settings")


def clinic_voice_gender() -> str:
    """Clinic-wide override: Auto | Male | Female (site conf wins if set)."""
    conf = frappe.conf.get("visiontestai_voice_gender")
    if conf:
        return str(conf)
    try:
        if frappe.db.exists("DocType", "Healthcare Settings"):
            val = frappe.db.get_single_value(
                "Healthcare Settings", "custom_chart_voice_gender"
            )
            if val:
                return str(val)
    except Exception:
        pass
    return "Auto"


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def lookup_by_enroll_id(enroll_id: int | str | None = None) -> dict[str, Any]:
    _ensure_custom_fields()
    if enroll_id is None:
        enroll_id = frappe.form_dict.get("enroll_id")
    try:
        eid = int(enroll_id)
    except (TypeError, ValueError):
        frappe.throw("enroll_id is required")

    name = frappe.db.get_value(
        "Patient",
        {"custom_aiface_enroll_id": eid},
        "name",
    )
    if not name:
        return {
            "found": False,
            "enroll_id": eid,
            "voice_gender": clinic_voice_gender(),
        }

    patient = frappe.get_doc("Patient", name)
    dob = getattr(patient, "dob", None)
    dob = getattr(patient, "dob", None) or getattr(patient, "date_of_birth", None)
    if dob is not None:
        try:
            dob = str(dob)
        except Exception:
            dob = None
    return {
        "found": True,
        "voice_gender": clinic_voice_gender(),
        "patient": {
            "name": patient.name,
            "patient_name": patient.patient_name or patient.first_name,
            "uid": getattr(patient, "uid", None),
            "mobile": getattr(patient, "mobile", None),
            "dob": dob,
            "sex": getattr(patient, "sex", None),
            "aiface_enroll_id": getattr(patient, "custom_aiface_enroll_id", None),
            "aiface_display_name": getattr(
                patient, "custom_aiface_display_name", None
            ),
        },
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_face_patient(
    enroll_id: int | str | None = None,
    full_name: str | None = None,
    uid: str | None = None,
    mobile: str | None = None,
) -> dict[str, Any]:
    _ensure_custom_fields()
    if enroll_id is None:
        enroll_id = frappe.form_dict.get("enroll_id")
    if full_name is None:
        full_name = frappe.form_dict.get("full_name")
    if uid is None:
        uid = frappe.form_dict.get("uid")
    if mobile is None:
        mobile = frappe.form_dict.get("mobile")

    try:
        eid = int(enroll_id)
    except (TypeError, ValueError):
        frappe.throw("enroll_id is required")
    if eid == STRANGER_ENROLL_ID:
        frappe.throw("Cannot register stranger enroll id")
    if not full_name or not str(full_name).strip():
        frappe.throw("full_name is required")

    full_name = str(full_name).strip()
    existing = frappe.db.get_value(
        "Patient",
        {"custom_aiface_enroll_id": eid},
        "name",
    )
    by_uid = None
    if uid:
        by_uid = frappe.db.get_value("Patient", {"uid": uid}, "name")

    if existing:
        doc = frappe.get_doc("Patient", existing)
        doc.first_name = full_name
        doc.custom_aiface_display_name = full_name
        if uid:
            doc.uid = uid
        if mobile:
            doc.mobile = mobile
        if not doc.custom_aiface_enrolled_at:
            doc.custom_aiface_enrolled_at = now_datetime()
        doc.save(ignore_permissions=True)
    elif by_uid:
        doc = frappe.get_doc("Patient", by_uid)
        doc.custom_aiface_enroll_id = eid
        doc.custom_aiface_display_name = full_name
        doc.custom_aiface_enrolled_at = now_datetime()
        if mobile:
            doc.mobile = mobile
        doc.save(ignore_permissions=True)
    else:
        parts = full_name.split(None, 1)
        doc = frappe.get_doc(
            {
                "doctype": "Patient",
                "first_name": parts[0],
                "last_name": parts[1] if len(parts) > 1 else None,
                "sex": "Other",
                "uid": uid,
                "mobile": mobile,
                "custom_aiface_enroll_id": eid,
                "custom_aiface_display_name": full_name,
                "custom_aiface_enrolled_at": now_datetime(),
            }
        )
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {
        "success": True,
        "patient": {
            "name": doc.name,
            "patient_name": doc.patient_name or full_name,
            "aiface_enroll_id": eid,
        },
    }


@frappe.whitelist()
def link_patient_enroll(
    patient: str | None = None,
    enroll_id: int | str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Attach AiFace enroll_id to an existing Patient (Desk Register Face)."""
    _ensure_custom_fields()
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if enroll_id is None:
        enroll_id = frappe.form_dict.get("enroll_id")
    if display_name is None:
        display_name = frappe.form_dict.get("display_name")

    if not patient:
        frappe.throw("patient is required")
    if not frappe.db.exists("Patient", patient):
        frappe.throw(f"Patient not found: {patient}")

    try:
        eid = int(enroll_id)
    except (TypeError, ValueError):
        frappe.throw("enroll_id is required")
    if eid == STRANGER_ENROLL_ID:
        frappe.throw("Cannot link stranger enroll id")

    # Clear enroll_id from any other patient that still holds it
    other = frappe.db.get_value(
        "Patient",
        {"custom_aiface_enroll_id": eid, "name": ["!=", patient]},
        "name",
    )
    if other:
        frappe.db.set_value(
            "Patient",
            other,
            {
                "custom_aiface_enroll_id": None,
                "custom_aiface_display_name": None,
            },
        )

    doc = frappe.get_doc("Patient", patient)
    name = (display_name or doc.patient_name or doc.first_name or "").strip()
    doc.custom_aiface_enroll_id = eid
    doc.custom_aiface_display_name = name or f"user-{eid}"
    doc.custom_aiface_enrolled_at = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "success": True,
        "patient": {
            "name": doc.name,
            "patient_name": doc.patient_name or name,
            "aiface_enroll_id": eid,
            "aiface_display_name": doc.custom_aiface_display_name,
        },
    }


@frappe.whitelist()
def get_aiface_station_url() -> dict[str, Any]:
    """Desk JS / station push: Jetson AC URL (Tailscale, not clinic LAN)."""
    url = frappe.conf.get("visiontestai_aiface_station_url") or ""
    try:
        if frappe.db.exists("DocType", "Connection Settings"):
            cs = frappe.db.get_single_value("Connection Settings", "aiface_station_url")
            if cs and "192.168.1.125" not in str(cs):
                url = cs
    except Exception:  # noqa: BLE001
        pass
    if not str(url).strip():
        return {
            "success": False,
            "error": "aiface_station_url_not_configured",
            "aiface_station_url": None,
        }
    return {"success": True, "aiface_station_url": str(url).rstrip("/")}


def _media_conf() -> tuple[str, str]:
    media_base = (
        frappe.conf.get("visiontestai_media_base")
        or frappe.conf.get("visiontestai_media_base_url")
        or "http://192.168.1.78:9010"
    )
    media_token = frappe.conf.get("visiontestai_media_token") or "dev-media-token"
    return str(media_base).rstrip("/"), str(media_token)


def _public_media_base(media_base: str) -> str:
    """Host Jetson/desk can reach — not the Docker DNS name `media`."""
    pub = (
        frappe.conf.get("visiontestai_media_public_base")
        or frappe.conf.get("MEDIA_PUBLIC_BASE")
    )
    if pub:
        return str(pub).rstrip("/")
    host = frappe.conf.get("visiontestai_vps_tailnet_host")
    if host:
        return f"http://{str(host).split('/')[0]}:9010"
    if "://media" in str(media_base):
        funnel = frappe.conf.get("visiontestai_vps_funnel_host")
        if funnel and str(funnel).startswith("http"):
            return str(media_base)
    return str(media_base).rstrip("/")


def _rewrite_media_url(url: str | None, media_base: str) -> str | None:
    """Force grant put/get URLs onto the backend-reachable media host.

    Media advertises MEDIA_PUBLIC_BASE (Tailscale/LAN). From a Docker backend
    that address often hairpins and times out; `visiontestai_media_base`
    (e.g. http://media:9010) is the host that already answered /v1/grants.
    """
    if not url:
        return url
    raw = str(url)
    if raw.startswith("/"):
        return f"{media_base.rstrip('/')}{raw}"
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(raw)
    base = urlparse(media_base)
    if not parsed.scheme or not parsed.netloc or not base.netloc:
        return raw
    return urlunparse(
        (
            base.scheme or parsed.scheme,
            base.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _upload_avatar_jpeg(patient: str, jpeg: bytes) -> dict[str, Any]:
    """Grant → PUT JPEG to media gateway as kind=avatar."""
    import requests

    media_base, media_token = _media_conf()
    headers = {"X-Media-Token": media_token, "Content-Type": "application/json"}
    grant_body = {
        "station_id": frappe.conf.get("visiontestai_station_id") or "station-01",
        "session_id": f"patient-{patient}",
        "kind": "avatar",
        "content_type": "image/jpeg",
        "filename": f"{patient}_avatar.jpg",
    }
    grant_resp = requests.post(
        f"{media_base}/v1/grants",
        json=grant_body,
        headers=headers,
        timeout=8,
    )
    grant_resp.raise_for_status()
    grant = grant_resp.json()
    put_url = _rewrite_media_url(grant.get("put_url"), media_base)
    if not put_url:
        raise RuntimeError(f"media grant missing put_url: {grant}")
    put_headers = {"X-Media-Token": media_token, "Content-Type": "image/jpeg"}
    put_resp = requests.put(put_url, data=jpeg, headers=put_headers, timeout=8)
    put_resp.raise_for_status()
    ready = put_resp.json() if put_resp.content else {}
    if not isinstance(ready, dict):
        ready = {}
    get_url = _rewrite_media_url(
        ready.get("get_url") or grant.get("get_url"),
        _public_media_base(media_base),
    )
    object_key = ready.get("object_key") or grant.get("object_key")
    return {
        "get_url": get_url,
        "object_key": object_key,
        "size": ready.get("size") or len(jpeg),
        "sha256": ready.get("sha256"),
    }


def _attach_patient_image(doc, jpeg: bytes) -> str | None:
    """Store the face JPEG as Patient.image so Desk list/form show the avatar."""
    import hashlib
    import os

    from frappe.utils import get_files_path

    if not jpeg or not getattr(doc, "name", None):
        return None

    digest = hashlib.sha256(bytes(jpeg)).hexdigest()[:12]
    fname = f"{digest}_face.jpg"
    files_path = get_files_path(is_private=0)
    if isinstance(files_path, (bytes, bytearray)):
        files_path = files_path.decode("utf-8")
    files_path = str(files_path)
    os.makedirs(files_path, exist_ok=True)
    dest = os.path.join(files_path, fname)
    with open(dest, "wb") as handle:
        handle.write(bytes(jpeg))

    file_url = f"/files/{fname}"
    doc.image = file_url
    if getattr(doc, "user_id", None) and frappe.db.exists("User", doc.user_id):
        try:
            frappe.db.set_value("User", doc.user_id, "user_image", file_url, update_modified=False)
        except Exception:  # noqa: BLE001
            pass
    return file_url


def _upsert_face_vectordb(
    *,
    enroll_id: int,
    full_name: str,
    patient_id: str,
    media_get_url: str | None,
    image_b64: str | None,
) -> dict[str, Any]:
    """Best-effort gallery upsert so AC can sync today's appointments."""
    import requests

    base = (
        frappe.conf.get("visiontestai_face_vectordb_url")
        or frappe.conf.get("FACE_VECTORDB_BASE_URL")
        or "http://face_vectordb:8100"
    )
    api_key = (
        frappe.conf.get("visiontestai_face_vectordb_key")
        or frappe.conf.get("FACE_VECTORDB_API_KEY")
        or "dev-face-vdb-key"
    )
    headers = {"Content-Type": "application/json", "X-Api-Key": str(api_key)}
    body = {
        "enroll_id": int(enroll_id),
        "full_name": full_name,
        "patient_id": patient_id,
        "media_get_url": media_get_url,
        "image_b64": image_b64,
    }
    try:
        resp = requests.post(
            f"{str(base).rstrip('/')}/v1/faces",
            json=body,
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        return {"ok": True, "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(title="face_vectordb upsert", message=str(exc))
        return {"ok": False, "error": str(exc)}


@frappe.whitelist(methods=["POST"])
def register_patient_face_avatar(
    patient: str | None = None,
    image_b64: str | None = None,
    enroll_id: int | str | None = None,
    display_name: str | None = None,
    push_today: int | str | None = 1,
) -> dict[str, Any]:
    """Desk webcam enroll: store avatar JPEG + enroll_id (no live AiFace capture).

    Optionally asks the Jetson station to push this avatar onto AiFace when the
    patient already has an appointment today.
    """
    import base64

    if frappe.session.user == "Guest" or not set(frappe.get_roles()).intersection(
        {"Nursing User", "Physician", "Healthcare Administrator", "System Manager"}
    ):
        frappe.throw("Bạn không có quyền đăng ký khuôn mặt.", frappe.PermissionError)

    _ensure_custom_fields()
    if patient is None:
        patient = frappe.form_dict.get("patient")
    if image_b64 is None:
        image_b64 = frappe.form_dict.get("image_b64")
    if enroll_id is None:
        enroll_id = frappe.form_dict.get("enroll_id")
    if display_name is None:
        display_name = frappe.form_dict.get("display_name")
    if push_today is None:
        push_today = frappe.form_dict.get("push_today", 1)

    if not patient:
        frappe.throw("patient is required")
    if not frappe.db.exists("Patient", patient):
        frappe.throw(f"Patient not found: {patient}")
    if not image_b64:
        frappe.throw("image_b64 is required")

    raw = str(image_b64).strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        jpeg = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        frappe.throw(f"bad image_b64: {exc}")
    if len(jpeg) < 100 or jpeg[:2] != b"\xff\xd8":
        frappe.throw("image must be a JPEG face frame")
    # AiFace Select-File path rejects >500KB
    if len(jpeg) > 500 * 1024:
        frappe.throw("face JPEG too large (max 500KB)")

    doc = frappe.get_doc("Patient", patient)
    name = (
        (display_name or getattr(doc, "custom_aiface_display_name", None) or doc.patient_name or doc.first_name or "")
        .strip()
        or patient
    )

    eid = normalize_aiface_enroll_id(enroll_id)
    if eid is None:
        eid = normalize_aiface_enroll_id(getattr(doc, "custom_aiface_enroll_id", None))
    if eid is None:
        eid = next_aiface_enroll_id()

    # Clear enroll_id from any other patient that still holds it
    other = frappe.db.get_value(
        "Patient",
        {"custom_aiface_enroll_id": eid, "name": ["!=", patient]},
        "name",
    )
    if other:
        frappe.db.set_value(
            "Patient",
            other,
            {
                "custom_aiface_enroll_id": None,
                "custom_aiface_display_name": None,
            },
        )

    media_meta: dict[str, Any] = {}
    try:
        media_meta = _upload_avatar_jpeg(patient, jpeg)
        if not media_meta.get("get_url"):
            raise RuntimeError("media upload did not return a face image URL")
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(title="register_patient_face_avatar media", message=str(exc))
        # Fall back to data URL stored on Patient so desk enroll still succeeds.
        media_meta = {
            "get_url": f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode('ascii')}",
            "object_key": None,
            "error": str(exc),
        }

    doc.custom_aiface_enroll_id = eid
    doc.custom_aiface_display_name = name
    doc.custom_aiface_enrolled_at = now_datetime()
    doc.custom_face_avatar_url = media_meta.get("get_url")
    doc.custom_face_avatar_object_key = media_meta.get("object_key")
    try:
        _attach_patient_image(doc, jpeg)
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(title="register_patient_face_avatar image", message=frappe.get_traceback())
        if not doc.image or str(doc.image).startswith("http://media"):
            doc.image = f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode('ascii')}"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    image_b64_clean = base64.b64encode(jpeg).decode("ascii")
    vdb = _upsert_face_vectordb(
        enroll_id=eid,
        full_name=name,
        patient_id=patient,
        media_get_url=media_meta.get("get_url")
        if not str(media_meta.get("get_url") or "").startswith("data:")
        else None,
        image_b64=image_b64_clean,
    )

    push_result: dict[str, Any] | None = None
    want_push = str(push_today).strip().lower() not in ("0", "false", "no", "")
    if want_push:
        try:
            from smart_hospital.api.clinic_desk import queue_patient_face_to_station

            push_result = queue_patient_face_to_station(patient)
        except Exception as exc:  # noqa: BLE001
            push_result = {"success": False, "error": str(exc)}

    return {
        "success": True,
        "patient": {
            "name": doc.name,
            "patient_name": doc.patient_name or name,
            "aiface_enroll_id": eid,
            "aiface_display_name": doc.custom_aiface_display_name,
            "face_avatar_url": doc.custom_face_avatar_url,
            "face_avatar_object_key": doc.custom_face_avatar_object_key,
            "image": doc.image,
        },
        "media": media_meta,
        "vectordb": vdb,
        "station_push": push_result,
    }
