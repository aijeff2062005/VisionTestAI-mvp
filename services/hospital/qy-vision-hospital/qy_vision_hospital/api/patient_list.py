"""Patient list endpoint for the Quân y clinic workspace."""

from __future__ import annotations

import re

import frappe
from frappe import _


CLINIC_ROLES = {
	"Nursing User",
	"Physician",
	"Healthcare Administrator",
	"System Manager",
}
DELETE_ROLES = {"Healthcare Administrator", "System Manager"}


def _require_clinic_user():
	if frappe.session.user == "Guest" or not CLINIC_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Bạn không có quyền xem hồ sơ bệnh nhân."), frappe.PermissionError)


@frappe.whitelist()
def list_patients(search: str = "", status: str = "", start: int = 0, page_length: int = 100):
	_require_clinic_user()

	start = max(int(start or 0), 0)
	page_length = min(max(int(page_length or 100), 1), 300)
	filters = {}
	if status in {"Active", "Disabled"}:
		filters["status"] = status

	term = (search or "").strip()
	or_filters = []
	if term:
		like = f"%{term}%"
		or_filters = [
			["Patient", "name", "like", like],
			["Patient", "patient_name", "like", like],
			["Patient", "uid", "like", like],
			["Patient", "custom_his_patient_id", "like", like],
			["Patient", "custom_cccd_last4", "like", like],
			["Patient", "mobile", "like", like],
			["Patient", "email", "like", like],
		]

	rows = frappe.get_list(
		"Patient",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "patient_name", "uid", "custom_his_patient_id", "custom_cccd_last4", "mobile", "email", "status"],
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	return {
		"rows": rows,
		"start": start,
		"page_length": page_length,
		"has_more": len(rows) == page_length,
	}


@frappe.whitelist()
def get_patient_profile(patient: str):
	"""Return the limited QY profile and measurement history for the custom UI."""
	_require_clinic_user()
	patient = (patient or "").strip()
	if not patient:
		frappe.throw(_("Thiếu mã bệnh nhân."))
	profile = frappe.db.get_value(
		"Patient",
		patient,
		["name", "patient_name", "custom_his_patient_id", "custom_cccd_last4", "mobile", "email", "status", "sex", "creation", "modified"],
		as_dict=True,
	)
	if not profile:
		frappe.throw(_("Không tìm thấy hồ sơ bệnh nhân."))
	measurements = frappe.get_all(
		"Vision Measurement",
		filters={"patient": patient},
		fields=["name", "creation"],
		order_by="creation desc",
		limit_page_length=50,
	)
	measurement_ids = [row.name for row in measurements]
	results = []
	if measurement_ids:
		results = frappe.get_all(
			"Visual Acuity",
			filters={"vision_measurement": ["in", measurement_ids]},
			fields=["name", "vision_measurement", "right_score", "left_score", "both_score", "creation"],
			order_by="creation desc",
			limit_page_length=50,
		)
	return {"patient": profile, "results": results}


@frappe.whitelist(methods=["POST"])
def delete_patient(patient: str):
	"""Delete a patient only for clinic administrators; Frappe protects linked records."""
	roles = set(frappe.get_roles())
	if frappe.session.user == "Guest" or not DELETE_ROLES.intersection(roles):
		frappe.throw(_("Chỉ quản trị viên phòng khám mới được xóa bệnh nhân."), frappe.PermissionError)
	patient = (patient or "").strip()
	if not patient or not frappe.db.exists("Patient", patient):
		frappe.throw(_("Không tìm thấy hồ sơ bệnh nhân."))
	if frappe.db.exists("Vision Measurement", {"patient": patient}):
		frappe.throw(_("Bệnh nhân đã có lượt đo. Không thể xóa hồ sơ để bảo toàn lịch sử đo."))
	# Queue/import rows have not produced measurement history and otherwise
	# block deletion through their required Patient link. Remove those rows with
	# the profile; the import batch receipt remains available for audit.
	for request in frappe.get_all("QY Measurement Request", filters={"patient": patient}, pluck="name"):
		frappe.delete_doc("QY Measurement Request", request, ignore_permissions=True, force=True)
	frappe.delete_doc("Patient", patient, ignore_permissions=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("Patient", patient)
	return {"success": True, "patient": patient}


@frappe.whitelist(methods=["POST"])
def register_patient(full_name: str = "", cccd_last4: str = "", mobile: str = "", email: str = ""):
	"""Register a QY patient with the limited demographic fields QY collects."""
	if frappe.session.user == "Guest" or not CLINIC_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Bạn không có quyền đăng ký bệnh nhân."), frappe.PermissionError)
	full_name = (full_name or "").strip()
	cccd_last4 = (cccd_last4 or "").strip()
	mobile = (mobile or "").strip()
	email = (email or "").strip()
	if not full_name:
		frappe.throw(_("Vui lòng nhập họ tên."))
	if not re.fullmatch(r"\d{4}", cccd_last4):
		frappe.throw(_("CCCD cần đúng 4 số cuối."))
	if mobile and not mobile.isdigit():
		frappe.throw(_("Số điện thoại chỉ được chứa chữ số."))

	from qy_vision_hospital.api.xml_intake import ensure_xml_fields

	ensure_xml_fields()
	patient = frappe.get_doc({
		"doctype": "Patient",
		"first_name": full_name,
		"patient_name": full_name,
		"custom_cccd_last4": cccd_last4,
		"mobile": mobile or None,
		"email": email or None,
		"invite_user": 0,
	})
	patient.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("Patient", patient.name)
	return {"success": True, "patient": patient.name, "patient_name": patient.patient_name}
