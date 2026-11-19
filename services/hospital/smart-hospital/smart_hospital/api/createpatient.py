import frappe

from smart_hospital.api.face_identity import _ensure_custom_fields, ensure_patient_genders, next_aiface_enroll_id


def _text(value) -> str:
    return str(value or "").strip()


def _apply_fields(patient, values: dict) -> None:
    for key, value in values.items():
        if value is None:
            continue
        if key == "cccd_address":
            if "custom_địa_chỉ_nhà" in patient.meta.get_valid_columns():
                patient.set("custom_địa_chỉ_nhà", value)
            continue
        if patient.meta.has_field(key):
            patient.set(key, value)
    if patient.meta.has_field("invite_user"):
        patient.invite_user = 0


def _patient_payload(patient) -> dict:
    return {
        "success": True,
        "patient": patient.name,
        "patient_name": patient.patient_name,
        "uid": patient.uid,
        "aiface_enroll_id": getattr(patient, "custom_aiface_enroll_id", None),
    }


@frappe.whitelist()
def create_patient(
    first_name=None,
    patient_name=None,
    middle_name=None,
    last_name=None,
    sex=None,
    dob=None,
    uid=None,
    national_id=None,
    mobile=None,
    phone=None,
    email=None,
    cccd_address=None,
    blood_group=None,
    allergies=None,
    surgical_history=None,
    medical_history=None,
    emergency_contact_name=None,
    emergency_contact_phone=None,
    visit_reason=None,
    uses_glasses=None,
    require_gender=0,
):
    if frappe.session.user == "Guest" or not set(frappe.get_roles()).intersection(
        {"Nursing User", "Physician", "Healthcare Administrator", "System Manager"}
    ):
        frappe.throw("Bạn không có quyền đăng ký bệnh nhân.", frappe.PermissionError)
    sex = _text(sex or frappe.form_dict.get("sex"))
    if str(require_gender).strip().lower() in {"1", "true", "yes"}:
        if not sex:
            frappe.throw("Vui lòng chọn giới tính trước khi tạo hồ sơ.")
        if sex not in {"Male", "Female", "Other"}:
            frappe.throw("Giới tính không hợp lệ.")

    _ensure_custom_fields()
    ensure_patient_genders()

    uid = _text(national_id or uid or frappe.form_dict.get("national_id") or frappe.form_dict.get("uid"))
    full_name = _text(patient_name or frappe.form_dict.get("patient_name"))
    if not full_name:
        full_name = " ".join(part for part in (last_name, middle_name, first_name) if _text(part))
    if not uid:
        frappe.throw("Số CCCD là bắt buộc.")
    if not uid.isdigit() or len(uid) not in (9, 12):
        frappe.throw("CCCD chỉ gồm 9 hoặc 12 chữ số.")
    if not full_name:
        frappe.throw("Họ và tên là bắt buộc.")

    # Frappe's Patient doctype stores a required first_name. Keep the complete
    # Vietnamese display name there so a single full-name field is preserved.
    if patient_name:
        first_name = full_name
        middle_name = None
        last_name = None
    else:
        first_name = _text(first_name)
        if not first_name:
            frappe.throw("Họ và tên là bắt buộc.")

    mobile = _text(mobile)
    email = _text(email)
    phone = _text(phone)
    emergency_contact_phone = _text(emergency_contact_phone)
    if mobile and not mobile.isdigit():
        frappe.throw("Số điện thoại chỉ được chứa chữ số.")
    if emergency_contact_phone and not emergency_contact_phone.isdigit():
        frappe.throw("Số điện thoại liên hệ chỉ được chứa chữ số.")
    middle_name = _text(middle_name) or None
    last_name = _text(last_name) or None
    cccd_address = _text(cccd_address) or None

    # Registration must never turn a shared phone/email (or a repeated CCCD)
    # into an implicit edit of an existing patient's medical record.
    if uid and frappe.db.exists("Patient", {"uid": uid}):
        frappe.throw("CCCD đã có hồ sơ bệnh nhân. Hãy mở hồ sơ đó để chỉnh sửa.")

    face_id = next_aiface_enroll_id()
    patient = frappe.get_doc(
        {
            "doctype": "Patient",
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "sex": sex,
            "dob": dob,
            "uid": uid,
            "mobile": mobile or None,
            "phone": phone or None,
            "email": email or None,
            "blood_group": blood_group,
            "allergies": allergies,
            "surgical_history": surgical_history,
            "medical_history": medical_history,
            "custom_emergency_contact_name": _text(emergency_contact_name) or None,
            "custom_emergency_contact_phone": emergency_contact_phone or None,
            "custom_visit_reason": _text(visit_reason) or None,
            "custom_uses_glasses": _text(uses_glasses) or None,
            "custom_aiface_enroll_id": face_id,
            "invite_user": 0,
        }
    )
    if patient.meta.has_field("patient_name"):
        patient.patient_name = full_name
    _apply_fields(patient, {"cccd_address": cccd_address})
    # Other demographic and medical fields may be updated after registration.
    patient.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    frappe.publish_realtime(
        "smart_hospital_data_updated",
        {"doctype": "Patient", "name": patient.name},
        after_commit=True,
    )
    return _patient_payload(patient)
