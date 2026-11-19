"""Role-scoped clinic Desk: workspaces, pages, permissions."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any
from uuid import uuid4

import frappe

from qy_vision_hospital.api.clinic_constants import WS_ADMIN, WS_DOCTOR, WS_NURSE
from qy_vision_hospital.api.clinic_shell import apply_clinic_shell
from qy_vision_hospital.api.clinic_workspaces import (
	DEFAULT_CLINIC_NUMBER_CARDS,
	clinic_admin_workspace_content,
	clinic_admin_workspace_links,
	doctor_workspace_content,
	doctor_workspace_links,
	hide_noise_workspaces,
	nurse_workspace_content,
	nurse_workspace_links,
	sync_clinic_desktop_navigation,
	upsert_workspace,
)

NURSE_PAGES = (
	"visioncare",
	"nurse-station",
)
# Shared: nurses + doctors can register patients.
SHARED_PAGES = ("patient-registration", "clinic-patients")
DOCTOR_PAGES = ("doctor-review",)
# Hidden from sidebar/search (system_page) but reachable from registration redirect.
FACE_CAPTURE_PAGES = ("face-service-test",)

NURSE_ROLES = ("Nursing User", "Physician", "Healthcare Administrator", "System Manager")
DOCTOR_ROLES = ("Physician", "Healthcare Administrator", "System Manager")
SHARED_PAGE_ROLES = (
	"Nursing User",
	"Physician",
	"Healthcare Administrator",
	"System Manager",
)
ADMIN_ROLES = ("System Manager", "Healthcare Administrator")
FACE_CAPTURE_ROLES = (
	"System Manager",
	"Nursing User",
	"Physician",
	"Healthcare Administrator",
)

_NEW_PATIENT_SHORTCUT = {
	"type": "Page",
	"link_to": "patient-registration",
	"label": "Đăng ký bệnh nhân",
	"color": "Green",
	"doc_view": "",
}

_PATIENT_LIST_SHORTCUT = {
	"type": "DocType",
	"link_to": "Patient",
	"label": "Danh sách bệnh nhân",
	"color": "Orange",
	"doc_view": "",
}


def _set_doc_roles(doctype: str, name: str, roles: tuple[str, ...]) -> None:
	if not frappe.db.exists(doctype, name):
		return
	frappe.db.delete("Has Role", {"parent": name, "parenttype": doctype})
	for role in roles:
		if frappe.db.exists("Role", role):
			frappe.get_doc(
				{
					"doctype": "Has Role",
					"parent": name,
					"parenttype": doctype,
					"parentfield": "roles",
					"role": role,
				}
			).insert(ignore_permissions=True)


def _set_page_meta(page: str, *, title: str | None = None, icon: str | None = None, system_page: int | None = None) -> None:
	if not frappe.db.exists("Page", page):
		return
	values: dict[str, Any] = {}
	if title is not None:
		values["title"] = title
	if icon is not None:
		values["icon"] = icon
	if system_page is not None:
		values["system_page"] = system_page
	if values:
		frappe.db.set_value("Page", page, values, update_modified=False)


def _tighten_doctype_permissions() -> None:
	"""Keep nurses out of result history while preserving queue workflows."""
	if frappe.db.exists("DocType", "Vision Measurement"):
		for perm in frappe.get_all(
			"DocPerm",
			filters={"parent": "Vision Measurement", "role": "Nursing User"},
			fields=["name"],
		):
			frappe.db.set_value(
				"DocPerm",
				perm.name,
				{"create": 0, "write": 0, "delete": 0, "read": 1},
			)
	for doctype in ("Visual Acuity", "Eye Prescription"):
		if not frappe.db.exists("DocType", doctype):
			continue
		for perm in frappe.get_all(
			"DocPerm",
			filters={"parent": doctype, "role": "Nursing User"},
			fields=["name"],
		):
			frappe.db.set_value("DocPerm", perm.name, {"read": 0, "create": 0, "write": 0, "delete": 0})


def _disable_patient_quick_entry() -> None:
	"""new-patient-* opens Đăng ký bệnh nhân (CCCD + face), not Healthcare quick entry."""
	if not frappe.db.exists("DocType", "Patient"):
		return
	if frappe.db.get_value("DocType", "Patient", "quick_entry"):
		frappe.db.set_value("DocType", "Patient", "quick_entry", 0, update_modified=False)


def _hide_patient_phone_field() -> None:
	"""Clinic uses Mobile only — hide redundant Healthcare Phone field."""
	if not frappe.db.exists("DocType", "Patient"):
		return
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for prop, value, ptype in (
		("hidden", "1", "Check"),
		("in_list_view", "0", "Check"),
	):
		make_property_setter(
			"Patient",
			"phone",
			prop,
			value,
			ptype,
			validate_fields_for_doctype=False,
		)
	frappe.clear_cache(doctype="Patient")


@frappe.whitelist()
def ensure_clinic_desk_roles() -> dict[str, Any]:
	"""Apply clinic Desk layout: role pages, ERPNext-style workspaces, hide noise."""
	for page in NURSE_PAGES:
		_set_doc_roles("Page", page, NURSE_ROLES)
	for page in SHARED_PAGES:
		_set_doc_roles("Page", page, SHARED_PAGE_ROLES)
	for page in DOCTOR_PAGES:
		_set_doc_roles("Page", page, DOCTOR_ROLES)
	for page in FACE_CAPTURE_PAGES:
		_set_doc_roles("Page", page, FACE_CAPTURE_ROLES)

	_set_page_meta("visioncare", title="VisionCare Hospital", icon="eye")
	_set_page_meta("nurse-station", title="Hàng chờ đo", icon="users")
	_set_page_meta("patient-registration", title="Đăng ký bệnh nhân", icon="user-plus")
	_set_page_meta("clinic-patients", title="Danh sách bệnh nhân", icon="users")
	_set_page_meta("patient-vision-booking", title="Đặt lịch thị lực", icon="calendar", system_page=1)
	_set_page_meta("doctor-review", title="Duyệt kết quả", icon="file-text")
	_set_page_meta(
		"face-service-test",
		title="Face Capture (Dev)",
		icon="camera",
		system_page=1,
	)

	hidden = hide_noise_workspaces()
	_tighten_doctype_permissions()
	_disable_patient_quick_entry()
	_hide_patient_phone_field()

	upsert_workspace(
		WS_NURSE,
		title="Nurse",
		icon="users",
		roles=NURSE_ROLES,
		sequence_id=1.0,
		indicator_color="blue",
		content=nurse_workspace_content(),
		links=nurse_workspace_links(),
		number_cards=list(DEFAULT_CLINIC_NUMBER_CARDS),
		shortcuts=[
			{
				"type": "DocType",
				"link_to": "Patient",
				"label": "Danh sách bệnh nhân",
				"color": "Orange",
				"doc_view": "",
			},
			{
				"type": "Page",
				"link_to": "nurse-station",
				"label": "Hàng chờ đo",
				"color": "Orange",
				"doc_view": "",
			},
			{
				"type": "DocType",
				"link_to": "Visual Acuity",
				"label": "Kết quả đo",
				"color": "Green",
				"doc_view": "",
			},
			dict(_NEW_PATIENT_SHORTCUT),
		],
	)

	upsert_workspace(
		WS_DOCTOR,
		title="Doctor",
		icon="stethoscope",
		roles=DOCTOR_ROLES,
		sequence_id=2.0,
		indicator_color="orange",
		content=doctor_workspace_content(),
		links=doctor_workspace_links(),
		number_cards=list(DEFAULT_CLINIC_NUMBER_CARDS),
		shortcuts=[
			dict(_PATIENT_LIST_SHORTCUT),
			{
				"type": "Page",
				"link_to": "nurse-station",
				"label": "Hàng chờ đo",
				"color": "Orange",
				"doc_view": "",
			},
			{
				"type": "DocType",
				"link_to": "Visual Acuity",
				"label": "Kết quả đo",
				"color": "Green",
				"doc_view": "",
			},
			{
				"type": "Page",
				"link_to": "doctor-review",
				"label": "Duyệt kết quả",
				"color": "Blue",
				"doc_view": "",
			},
			dict(_NEW_PATIENT_SHORTCUT),
			{
				"type": "DocType",
				"link_to": "Eye Prescription",
				"label": "Đơn kính",
				"color": "Orange",
				"doc_view": "",
			},
		],
	)

	upsert_workspace(
		WS_ADMIN,
		title="Clinic Administration",
		icon="setting",
		roles=ADMIN_ROLES,
		sequence_id=0.5,
		indicator_color="green",
		content=clinic_admin_workspace_content(),
		links=clinic_admin_workspace_links(),
		number_cards=list(DEFAULT_CLINIC_NUMBER_CARDS),
		shortcuts=[
			dict(_PATIENT_LIST_SHORTCUT),
			{
				"type": "Page",
				"link_to": "nurse-station",
				"label": "Hàng chờ đo",
				"color": "Orange",
				"doc_view": "",
			},
			{
				"type": "DocType",
				"link_to": "Visual Acuity",
				"label": "Kết quả đo",
				"color": "Green",
				"doc_view": "",
			},
			{
				"type": "Page",
				"link_to": "doctor-review",
				"label": "Duyệt kết quả",
				"color": "Blue",
				"doc_view": "",
			},
			dict(_NEW_PATIENT_SHORTCUT),
		],
	)

	desktop_navigation = sync_clinic_desktop_navigation()
	clinic_shell = apply_clinic_shell()

	frappe.clear_cache()
	if frappe.db.exists("DocType", "System Settings"):
		frappe.db.set_single_value("System Settings", "language", "vi")
		frappe.db.commit()
	return {
		"success": True,
		"nurse_pages": list(NURSE_PAGES),
		"doctor_pages": list(DOCTOR_PAGES),
		"workspaces": [WS_ADMIN, WS_NURSE, WS_DOCTOR],
		"hidden_workspaces": hidden,
		"desktop_navigation": desktop_navigation,
		"clinic_shell": clinic_shell,
	}


def execute() -> None:
	"""Patch entrypoint."""
	ensure_clinic_desk_roles()


def _require_clinic_admin() -> None:
	if frappe.session.user == "Administrator":
		return
	roles = set(frappe.get_roles(frappe.session.user))
	if not roles.intersection(ADMIN_ROLES):
		frappe.throw("Bạn không có quyền quản trị phòng khám.", frappe.PermissionError)


@frappe.whitelist()
def get_clinic_settings() -> dict[str, Any]:
    """Return QY site branding and the configured measurement station."""
    raw_branding = frappe.defaults.get_global_default("qy_vision_hospital_branding") or "{}"
    try:
        branding = json.loads(raw_branding)
    except (TypeError, ValueError):
        branding = {}
    return {
        "station_id": str(frappe.conf.get("visiontestai_station_id") or "station-01"),
        "branding": {
            "clinic_name": str(branding.get("clinic_name") or "VisionCare Hospital"),
            "logo_url": str(branding.get("logo_url") or ""),
            "primary_color": str(branding.get("primary_color") or "#0B8F87"),
        },
    }


@frappe.whitelist()
def save_clinic_branding(clinic_name: str, logo_url: str = "", primary_color: str = "#0B8F87") -> dict[str, Any]:
    """Persist site-specific hospital name, logo and bright theme color."""
    _require_clinic_admin()
    clinic_name = (clinic_name or "").strip()
    logo_url = (logo_url or "").strip()
    primary_color = (primary_color or "").strip().upper()
    if not clinic_name or len(clinic_name) > 100:
        frappe.throw("Tên bệnh viện cần có từ 1 đến 100 ký tự.")
    if not re.fullmatch(r"#[0-9A-F]{6}", primary_color):
        frappe.throw("Mã màu không hợp lệ.")
    if logo_url and not logo_url.startswith("/files/"):
        frappe.throw("Logo phải được tải lên từ trang cài đặt này.")
    branding = {"clinic_name": clinic_name, "logo_url": logo_url, "primary_color": primary_color}
    frappe.defaults.set_global_default("qy_vision_hospital_branding", json.dumps(branding, ensure_ascii=False))
    frappe.db.commit()
    return {"success": True, "branding": branding}


@frappe.whitelist()
def upload_clinic_logo(file_name: str, content_base64: str) -> dict[str, str]:
    """Store a public raster logo for the current QY site."""
    _require_clinic_admin()
    extension = (file_name or "").rsplit(".", 1)[-1].lower()
    if extension not in {"png", "jpg", "jpeg", "webp"}:
        frappe.throw("Logo chỉ nhận file PNG, JPG hoặc WEBP.")
    try:
        content = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError):
        frappe.throw("Không đọc được file logo.")
    if not content or len(content) > 700 * 1024:
        frappe.throw("Logo phải nhỏ hơn 700 KB.")
    valid_signature = (
        (extension == "png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {"jpg", "jpeg"} and content.startswith(b"\xff\xd8\xff"))
        or (extension == "webp" and len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP")
    )
    if not valid_signature:
        frappe.throw("Nội dung file không khớp định dạng ảnh được hỗ trợ.")
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"qy-clinic-logo-{uuid4().hex[:10]}.{extension}",
        "content": content,
        "is_private": 0,
    })
    file_doc.insert(ignore_permissions=True)
    return {"file_url": file_doc.file_url}


@frappe.whitelist()
def list_clinic_users() -> list[dict[str, Any]]:
	"""List staff accounts without exposing credentials or API secrets."""
	_require_clinic_admin()
	users = frappe.get_all(
		"User",
		filters={"user_type": "System User"},
		fields=["name", "full_name", "enabled", "user_type"],
		order_by="full_name asc",
		limit_page_length=250,
	)
	for user in users:
		user["roles"] = frappe.get_all(
			"Has Role",
			filters={"parent": user["name"], "parenttype": "User"},
			pluck="role",
			order_by="role asc",
		)
	return users


@frappe.whitelist()
def create_clinic_user(first_name: str, email: str, password: str, role: str = "Nursing User") -> dict[str, Any]:
	"""Create a QY staff account from the branded clinic UI."""
	_require_clinic_admin()
	first_name = (first_name or "").strip()
	email = (email or "").strip().lower()
	password = password or ""
	allowed_roles = {"Nursing User", "Physician", "Healthcare Administrator"}
	if not first_name or not email:
		frappe.throw("Vui lòng nhập họ tên và email.")
	if role not in allowed_roles or not frappe.db.exists("Role", role):
		frappe.throw("Vai trò được chọn không hợp lệ.")
	if len(password) < 8:
		frappe.throw("Mật khẩu tạm phải có ít nhất 8 ký tự.")
	if frappe.db.exists("User", email):
		frappe.throw("Email này đã được dùng cho một tài khoản khác.")

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"user_type": "System User",
			"enabled": 1,
			"send_welcome_email": 0,
			"new_password": password,
		}
	)
	user.append("roles", {"role": role})
	user.insert(ignore_permissions=True)
	return {"success": True, "user": user.name}
