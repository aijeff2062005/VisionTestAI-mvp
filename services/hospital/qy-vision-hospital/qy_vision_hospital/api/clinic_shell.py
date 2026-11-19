"""Clinic Desk shell — Smart Hospital only; Healthcare/Marley/ERPNext hidden from staff."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import frappe

from qy_vision_hospital.api.clinic_constants import CLINIC_WORKSPACES

CLINIC_STAFF_ROLES: tuple[str, ...] = (
	"Nursing User",
	"Physician",
	"Healthcare Administrator",
)

DEV_BYPASS_ROLES: tuple[str, ...] = (
	"System Manager",
	"Administrator",
)

CLINIC_PAGES: tuple[str, ...] = (
	"visioncare",
	"user-settings",
	"nurse-station",
	"patient-registration",
	"clinic-patients",
	"doctor-review",
	"face-service-test",
)

CLINIC_DOCTYPES: tuple[str, ...] = (
	"Patient",
	"Patient Appointment",
	"Visual Acuity",
	"Eye Prescription",
	"Vision Measurement",
	"QY Measurement Request",
	"Connection Settings",
)

ROLE_HOME_PAGE: dict[str, str] = {
	# Desk SPA routes (after HTTP /desk). Priority is applied in clinic_shell.js.
	"Physician": "visioncare",
	"Nursing User": "visioncare",
	"Healthcare Administrator": "visioncare",
	"System Manager": "visioncare",
}
BLOCKED_WORKSPACE_SLUGS: frozenset[str] = frozenset(
	{
		"healthcare",
		"outpatient",
		"inpatient",
		"rehabilitation",
		"diagnostics",
		"insurance",
		"emergency",
		"home",
		"buying",
		"selling",
		"stock",
		"crm",
		"accounting",
		"framework",
		"marley-health",
	}
)

BLOCKED_PAGE_NAMES: tuple[str, ...] = (
	"patient_history",
	"patient-progress",
)

CLINIC_DESKTOP_ICON_LABELS: tuple[str, ...] = ()


def _slug(value: str) -> str:
	return (value or "").lower().replace(" ", "-")


def clinic_shell_enabled_for_user(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Guest":
		return False
	# Keep the local Frappe Administrator inside the clinic shell as well, so
	# local testing opens Smart Hospital instead of exposing the app switcher.
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if roles.intersection(DEV_BYPASS_ROLES):
		return False
	return bool(roles.intersection(CLINIC_STAFF_ROLES))


def get_clinic_shell_boot() -> dict[str, Any]:
	return {
		"enabled": clinic_shell_enabled_for_user(),
		"allowed_pages": list(CLINIC_PAGES),
		"allowed_doctype_slugs": [_slug(d) for d in CLINIC_DOCTYPES],
		# Staff use the shared VisionCare page as the clinic UI. Keep the legacy
		# workspaces provisioned for compatibility, but never route users into them.
		"allowed_workspaces": [],
		"allowed_workspace_slugs": [],
		"blocked_workspace_slugs": sorted(BLOCKED_WORKSPACE_SLUGS),
		"blocked_pages": list(BLOCKED_PAGE_NAMES),
		"role_home_page": ROLE_HOME_PAGE,
	}


def boot_session(bootinfo: dict[str, Any]) -> None:
	bootinfo["clinic_shell"] = get_clinic_shell_boot()


def publish_clinic_data_update(doctype: str, name: str | None = None) -> None:
	"""Notify every open Desk tab after a clinic API commits a data change.

	Clinic API callers commit explicitly before calling this helper. Registering
	this publish with ``after_commit=True`` here would therefore leave the
	notification queued with no subsequent commit to flush it.
	"""
	try:
		frappe.publish_realtime(
			"smart_hospital_data_updated",
			{"doctype": doctype, "name": name},
		)
	except Exception:  # noqa: BLE001
		frappe.log_error(title="smart_hospital_data_updated", message=f"{doctype}:{name}")


@frappe.whitelist()
def get_app_version() -> dict[str, str]:
	"""Return a content version so Desk clients can reload after a deploy."""
	try:
		app_version = version("qy_vision_hospital")
	except PackageNotFoundError:
		app_version = "0.1.0"

	app_root = Path(__file__).resolve().parents[1]
	digest = hashlib.sha256()
	for relative_path in (
		"api/clinic_roles.py",
		"api/patient_list.py",
		"public/js/clinic_shell.js",
		"qy_vision_hospital/page/visioncare/visioncare.js",
		"qy_vision_hospital/page/visioncare/visioncare.css",
		"qy_vision_hospital/page/clinic_patients/clinic_patients.js",
		"qy_vision_hospital/page/patient_registration/patient_registration.js",
		"qy_vision_hospital/page/patient_vision_booking/patient_vision_booking.js",
		"translations/vi.csv",
		"translations/en.csv",
	):
		path = app_root / relative_path
		if path.is_file():
			digest.update(path.read_bytes())
	return {"version": f"{app_version}-{digest.hexdigest()[:12]}"}


def enforce_clinic_only_desktop() -> list[str]:
	"""Hide every desktop icon except the three Smart Hospital workspaces."""
	allowed = set(CLINIC_DESKTOP_ICON_LABELS)
	changed: list[str] = []
	for row in frappe.get_all("Desktop Icon", fields=["name", "label", "hidden"]):
		should_show = row.label in allowed
		if bool(row.hidden) == (not should_show):
			continue
		frappe.db.set_value("Desktop Icon", row.name, "hidden", 0 if should_show else 1)
		changed.append(f"{'show' if should_show else 'hide'}:{row.label}")
	return changed


def _lock_healthcare_only_pages() -> list[str]:
	"""Remove Healthcare-only pages from clinic roles."""
	locked: list[str] = []
	for page in BLOCKED_PAGE_NAMES:
		if not frappe.db.exists("Page", page):
			continue
		frappe.db.set_value("Page", page, "system_page", 1, update_modified=False)
		frappe.db.delete("Has Role", {"parent": page, "parenttype": "Page"})
		locked.append(page)
	return locked


def apply_clinic_shell() -> dict[str, Any]:
	return {
		"desktop": enforce_clinic_only_desktop(),
		"locked_pages": _lock_healthcare_only_pages(),
		"boot": get_clinic_shell_boot(),
	}
