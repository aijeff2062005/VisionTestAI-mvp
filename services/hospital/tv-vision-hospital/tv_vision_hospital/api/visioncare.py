"""Authenticated data and administration API for standalone VisionCare UI."""
from __future__ import annotations
import frappe
from frappe.utils import today
STAFF={"Nursing User","Physician","Healthcare Administrator","System Manager"}
ADMIN={"Healthcare Administrator","System Manager"}
def _require(roles=STAFF):
    if frappe.session.user=="Guest": frappe.throw("Vui lòng đăng nhập.",frappe.AuthenticationError)
    if not set(frappe.get_roles()).intersection(roles): frappe.throw("Bạn không có quyền.",frappe.PermissionError)
@frappe.whitelist()
def bootstrap():
    _require(); u=frappe.get_doc("User",frappe.session.user); roles=set(frappe.get_roles())
    return {"user":u.name,"full_name":u.full_name or u.name,"roles":sorted(roles),"is_admin":bool(roles.intersection(ADMIN)),"can_measure":bool(roles.intersection({"Nursing User", *ADMIN})),"can_review":bool(roles.intersection({"Physician", *ADMIN})),"station_url":frappe.db.get_single_value("Connection Settings","aiface_station_url") or ""}
@frappe.whitelist()
def dashboard_summary():
    _require()
    acuities = frappe.get_all("Visual Acuity", fields=["vision_measurement"])
    pending = sum(
        1 for row in acuities
        if row.vision_measurement
        and not frappe.db.exists("Eye Prescription", {"vision_measurement": row.vision_measurement})
    )
    return {"patients":frappe.db.count("Patient"),"appointments_today":frappe.db.count("Patient Appointment",{"appointment_date":today()}),"waiting":frappe.db.count("Patient Appointment",{"appointment_date":today(),"status":"Open"}),"pending_reviews":pending}
@frappe.whitelist()
def list_patients(search="",limit=100):
    _require(); limit=min(max(int(limit or 100),1),300); or_filters=[]
    if search:
        term=f"%{search}%"
        or_filters=[["Patient","patient_name","like",term],["Patient","uid","like",term],["Patient","mobile","like",term],["Patient","email","like",term]]
    return frappe.get_all("Patient",or_filters=or_filters,fields=["name","patient_name","uid","mobile","email","sex","dob","image","custom_aiface_enroll_id","custom_face_avatar_url"],order_by="modified desc",limit_page_length=limit)
@frappe.whitelist()
def list_appointments(start_date=None,end_date=None):
    _require(); start_date=start_date or today(); end_date=end_date or start_date
    rows = frappe.get_all("Patient Appointment",filters={"appointment_date":["between",[start_date,end_date]]},fields=["name","patient","patient_name","appointment_date","appointment_time","appointment_type","status","practitioner"],order_by="appointment_date asc, appointment_time asc",limit_page_length=300)
    for row in rows:
        row["mobile"] = frappe.db.get_value("Patient", row.patient, "mobile") if row.patient else ""
    return rows
@frappe.whitelist()
def list_history(limit=100):
    _require(); rows=frappe.get_all("Visual Acuity",fields=["name","vision_measurement","right_score","left_score","both_score","creation"],order_by="creation desc",limit_page_length=min(int(limit or 100),300))
    for row in rows:
        patient = frappe.db.get_value("Vision Measurement", row.vision_measurement, "patient") if row.vision_measurement else None
        row["patient"] = patient or ""
        row["patient_name"] = frappe.db.get_value("Patient", patient, "patient_name") if patient else ""
    return rows
@frappe.whitelist()
def list_users():
    _require(ADMIN); rows=frappe.get_all("User",filters={"user_type":"System User","enabled":1},fields=["name","full_name","email","enabled"],order_by="full_name asc",limit_page_length=300)
    for row in rows: row["roles"]=[r.role for r in frappe.get_all("Has Role",filters={"parent":row.name,"parenttype":"User"},fields=["role"])]
    return rows
@frappe.whitelist(methods=["POST"])
def create_user(email,first_name,password,role):
    _require(ADMIN)
    if role not in {"Nursing User","Physician","Healthcare Administrator"}: frappe.throw("Vai trò không hợp lệ.")
    if frappe.db.exists("User",email): frappe.throw("Email đã được sử dụng.")
    u=frappe.get_doc({"doctype":"User","email":email,"first_name":first_name,"enabled":1,"user_type":"System User","send_welcome_email":0,"roles":[{"role":role}]}); u.insert(ignore_permissions=True)
    from frappe.utils.password import update_password
    update_password(email,password); return {"success":True,"user":email}
@frappe.whitelist(methods=["POST"])
def update_station_url(url=""):
    _require(ADMIN); d=frappe.get_single("Connection Settings"); d.aiface_station_url=(url or "").strip(); d.save(ignore_permissions=True); frappe.db.commit(); return {"success":True}


@frappe.whitelist()
def patient_detail(patient):
    _require()
    if not patient or not frappe.db.exists("Patient", patient):
        frappe.throw("Không tìm thấy hồ sơ bệnh nhân.")
    doc = frappe.get_doc("Patient", patient)
    fields = ("name", "patient_name", "status", "first_name", "middle_name", "last_name", "uid", "mobile", "phone", "email", "sex", "dob", "blood_group", "image", "custom_aiface_enroll_id", "custom_aiface_display_name", "custom_face_avatar_url", "allergies", "medical_history", "surgical_history", "custom_emergency_contact_name", "custom_emergency_contact_phone", "custom_visit_reason", "custom_uses_glasses")
    result = {field: doc.get(field) for field in fields if doc.meta.has_field(field)}
    result["cccd_address"] = doc.get("custom_địa_chỉ_nhà") if doc.meta.has_field("custom_địa_chỉ_nhà") else ""
    return result


@frappe.whitelist(methods=["POST"])
def update_patient_profile(
    patient,
    patient_name,
    uid,
    sex,
    dob=None,
    mobile=None,
    phone=None,
    email=None,
    cccd_address=None,
    blood_group=None,
    allergies=None,
    medical_history=None,
    surgical_history=None,
    emergency_contact_name=None,
    emergency_contact_phone=None,
    visit_reason=None,
    uses_glasses=None,
):
    _require()
    patient = str(patient or "").strip()
    patient_name = str(patient_name or "").strip()
    uid = str(uid or "").strip()
    sex = str(sex or "").strip()
    if not patient or not frappe.db.exists("Patient", patient):
        frappe.throw("Không tìm thấy hồ sơ bệnh nhân.")
    if not patient_name or not uid or sex not in {"Male", "Female", "Other"}:
        frappe.throw("Họ tên, CCCD và giới tính là bắt buộc.")
    if frappe.db.exists("Patient", {"uid": uid, "name": ["!=", patient]}):
        frappe.throw("CCCD đã được sử dụng bởi hồ sơ bệnh nhân khác.")
    if mobile and not str(mobile).strip().isdigit():
        frappe.throw("Số điện thoại chỉ được chứa chữ số.")
    if phone and not str(phone).strip().isdigit():
        frappe.throw("Số điện thoại chỉ được chứa chữ số.")
    if emergency_contact_phone and not str(emergency_contact_phone).strip().isdigit():
        frappe.throw("Số điện thoại liên hệ khẩn cấp chỉ được chứa chữ số.")

    doc = frappe.get_doc("Patient", patient)
    doc.first_name = patient_name
    doc.patient_name = patient_name
    doc.uid = uid
    doc.sex = sex
    for field, value in {
        "dob": dob,
        "mobile": mobile,
        "phone": phone,
        "email": email,
        "blood_group": blood_group,
        "allergies": allergies,
        "medical_history": medical_history,
        "surgical_history": surgical_history,
        "custom_emergency_contact_name": emergency_contact_name,
        "custom_emergency_contact_phone": emergency_contact_phone,
        "custom_visit_reason": visit_reason,
        "custom_uses_glasses": uses_glasses,
        "custom_địa_chỉ_nhà": cccd_address,
    }.items():
        if doc.meta.has_field(field):
            doc.set(field, str(value).strip() if value not in (None, "") else None)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.publish_realtime(
        "smart_hospital_data_updated",
        {"doctype": "Patient", "name": patient},
        after_commit=True,
    )
    return {"success": True, "patient": patient, "patient_name": patient_name}


@frappe.whitelist()
def visual_acuity_detail(visual_acuity):
    _require()
    if not visual_acuity or not frappe.db.exists("Visual Acuity", visual_acuity):
        frappe.throw("Không tìm thấy kết quả đo.")
    doc = frappe.get_doc("Visual Acuity", visual_acuity)
    result = {field: doc.get(field) for field in ("name", "vision_measurement", "right_score", "left_score", "both_score", "creation", "modified") if doc.meta.has_field(field)}
    vm = result.get("vision_measurement")
    patient = frappe.db.get_value("Vision Measurement", vm, "patient") if vm and frappe.db.exists("Vision Measurement", vm) else None
    result["patient"] = patient
    result["patient_name"] = frappe.db.get_value("Patient", patient, "patient_name") if patient else ""
    result["measurement"] = frappe.db.get_value("Vision Measurement", vm, ["name", "patient", "creation", "modified"], as_dict=True) if vm and frappe.db.exists("Vision Measurement", vm) else {}
    result["prescription"] = frappe.db.get_value("Eye Prescription", {"vision_measurement": vm}, ["name", "conclusion", "creation", "modified"], as_dict=True) if vm and frappe.db.exists("Eye Prescription", {"vision_measurement": vm}) else None
    result["letters"] = [{key: row.get(key) for key in ("eye", "logmar", "vn_over_10", "letter_index", "expected", "actual", "matched", "row_outcome")} for row in (doc.get("letters") or [])]
    return result
