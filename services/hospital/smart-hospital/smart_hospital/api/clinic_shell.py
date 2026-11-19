"""Shared clinic update notifications and redirect from retired Desk routes."""
from __future__ import annotations

import frappe

CLINIC_STAFF_ROLES = ("Nursing User", "Physician", "Healthcare Administrator", "System Manager")


def redirect_legacy_desk() -> None:
    """Redirect clinic users from the retired Desk interface."""
    request = getattr(frappe.local, "request", None)
    path = (getattr(request, "path", "") if request else "").rstrip("/") or "/"
    if path in {"/desk/visioncare", "/desk/setup-wizard"}:
        if user == "Guest":
            frappe.local.flags.redirect_location = "/login?redirect-to=/desk/visioncare"
            raise frappe.Redirect
        if user == "Administrator" or roles.intersection(CLINIC_STAFF_ROLES):
            if path != "/desk/visioncare":
                frappe.local.flags.redirect_location = "/desk/visioncare"
                raise frappe.Redirect
            return
    if not (path in {"/app", "/desk", "/visioncare"} or (path.startswith("/app/") and path != "/app/visioncare")):
        return
    user = frappe.session.user
    roles = set(frappe.get_roles(user)) if user != "Guest" else set()
    if user == "Administrator" or roles.intersection(CLINIC_STAFF_ROLES):
        frappe.local.flags.redirect_location = "/app/visioncare"
        raise frappe.Redirect


def publish_clinic_data_update(doctype: str, name: str | None = None) -> None:
    """Notify open clinic UI sessions after a committed data change."""
    try:
        frappe.publish_realtime("smart_hospital_data_updated", {"doctype": doctype, "name": name})
    except Exception:  # noqa: BLE001
        frappe.log_error(title="smart_hospital_data_updated", message=f"{doctype}:{name}")
