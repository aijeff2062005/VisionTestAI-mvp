"""Retire role access to the legacy clinic Desk pages."""
from __future__ import annotations

from typing import Any

import frappe

LEGACY_WORKSPACES = (
    "Quản trị phòng khám",
    "Bác sĩ",
    "Điều dưỡng",
    "Smart Hospital",
)

LEGACY_PAGES = (
    "nurse-station",
    "patient-vision-booking",
    "patient-registration",
    "doctor-review",
    "face-service-test",
)


@frappe.whitelist()
def ensure_clinic_desk_roles() -> dict[str, Any]:
    """Remove saved Desk page permissions after the standalone UI is installed."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Vui lòng đăng nhập.", frappe.AuthenticationError)
    if user != "Administrator" and "System Manager" not in frappe.get_roles(user):
        frappe.throw(
            "Chỉ Quản trị hệ thống mới được cập nhật quyền Desk phòng khám.",
            frappe.PermissionError,
        )

    return _ensure_clinic_desk_roles()


def _ensure_clinic_desk_roles() -> dict[str, Any]:
    """Apply the Desk cleanup from trusted internal migration code."""
    for page in LEGACY_PAGES:
        if frappe.db.exists("Page", page):
            frappe.db.set_value("Page", page, "system_page", 1, update_modified=False)
            frappe.db.delete("Has Role", {"parent": page, "parenttype": "Page"})
    for workspace in LEGACY_WORKSPACES:
        if frappe.db.exists("Workspace", workspace):
            frappe.delete_doc("Workspace", workspace, ignore_permissions=True, force=True)
    frappe.clear_cache()
    return {"success": True, "retired_pages": list(LEGACY_PAGES), "retired_workspaces": list(LEGACY_WORKSPACES)}


def execute() -> None:
    _ensure_clinic_desk_roles()
