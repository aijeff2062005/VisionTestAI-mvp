"""Clinic Desk workspaces — ERPNext-style layout, icons, role-scoped sidebar."""

from __future__ import annotations

import json
import uuid
from typing import Any

import frappe
from frappe import _

from qy_vision_hospital.api.clinic_constants import CLINIC_WORKSPACES, WS_ADMIN, WS_DOCTOR, WS_NURSE

# ERPNext / Healthcare modules not used in the vision clinic demo.
WORKSPACES_TO_HIDE: tuple[str, ...] = (
	"Home",
	"Build",
	"Buying",
	"Selling",
	"Stock",
	"Invoicing",
	"CRM",
	"Manufacturing",
	"Assets",
	"Quality",
	"Projects",
	"Support",
	"Website",
	"Users",
	"Financial Reports",
	"Subcontracting",
	"Healthcare",
	"Outpatient",
	"Inpatient",
	"Rehabilitation",
	"Diagnostics",
	"Insurance",
	"Emergency",
	"ERPNext Settings",
	"Integrations",
	"Setup",
	"Smart Hospital",
	"Framework",
	"Accounting",
	"Organization",
	"Data",
	"Email",
	"System",
	"Printing",
	"Automation",
	"Payments",
	"Taxes",
	"Banking",
	"My Workspaces",
)

# Frappe v16 Healthcare app folder on Desk (parent of Outpatient, Healthcare, etc.).
DESKTOP_APP_ICONS_TO_HIDE: tuple[str, ...] = (
	"Marley Health",
)


def _uid() -> str:
	return uuid.uuid4().hex[:10]


def _block(block_type: str, **data: Any) -> dict[str, Any]:
	return {"id": _uid(), "type": block_type, "data": data}


def _header(text: str) -> dict[str, Any]:
	return _block("header", text=text, col=12)


def _spacer() -> dict[str, Any]:
	return _block("spacer", col=12)


def _shortcut(shortcut_name: str, col: int = 3) -> dict[str, Any]:
	return _block("shortcut", shortcut_name=shortcut_name, col=col)


def _card(card_name: str, col: int = 4) -> dict[str, Any]:
	return _block("card", card_name=card_name, col=col)


def _number_card(name: str, col: int = 3) -> dict[str, Any]:
	return _block("number_card", number_card_name=name, col=col)


def _chart(chart_name: str, col: int = 12) -> dict[str, Any]:
	return _block("chart", chart_name=chart_name, col=col)


def _section_shortcuts() -> dict[str, Any]:
	return _header(f'<span class="h4">{_("Your Shortcuts")}</span>')


def _section_reports() -> dict[str, Any]:
	return _header(f'<span class="h4">{_("Reports &amp; Masters")}</span>')


DEFAULT_CLINIC_CHART = "Department wise Patient Appointments"
FALLBACK_CLINIC_CHART = "Patient Appointments"

DEFAULT_CLINIC_NUMBER_CARDS: tuple[str, ...] = (
	"Total Patients",
	"Total Patients Admitted",
	"Open Appointments",
	"Appointments to Bill",
)


def _existing_chart_name(preferred: str | None = None) -> str | None:
	for name in (preferred, DEFAULT_CLINIC_CHART, FALLBACK_CLINIC_CHART):
		if name and frappe.db.exists("Dashboard Chart", name):
			return name
	return None


def _existing_number_cards(names: tuple[str, ...] | list[str] | None = None) -> list[str]:
	source = names or DEFAULT_CLINIC_NUMBER_CARDS
	return [name for name in source if frappe.db.exists("Number Card", name)]


def healthcare_home_content(
	*,
	shortcut_labels: list[str],
	card_names: list[str],
	chart_name: str | None = DEFAULT_CLINIC_CHART,
	number_cards: tuple[str, ...] | list[str] | None = None,
) -> str:
	"""Marley Healthcare workspace layout: chart → KPI row → shortcuts → master cards."""
	blocks: list[dict[str, Any]] = []

	chart = _existing_chart_name(chart_name) if chart_name else None
	if chart:
		blocks.append(_chart(chart))

	for card in _existing_number_cards(number_cards):
		blocks.append(_number_card(card, col=3))

	if shortcut_labels or card_names:
		blocks.append(_spacer())

	if shortcut_labels:
		blocks.append(_section_shortcuts())
		for label in shortcut_labels:
			blocks.append(_shortcut(label, col=4))

	if shortcut_labels and card_names:
		blocks.append(_spacer())

	if card_names:
		blocks.append(_section_reports())
		for name in card_names:
			blocks.append(_card(name, col=4))

	return json.dumps(blocks)


def nurse_workspace_content() -> str:
	return healthcare_home_content(
		shortcut_labels=[
			"Danh sách bệnh nhân",
			"Hàng chờ đo",
			"Kết quả đo",
			"Đăng ký bệnh nhân",
		],
		card_names=["Bệnh nhân"],
	)


def doctor_workspace_content() -> str:
	return healthcare_home_content(
		chart_name=FALLBACK_CLINIC_CHART,
		number_cards=("Total Patients", "Open Appointments", "Appointments to Bill"),
		shortcut_labels=[
			"Danh sách bệnh nhân",
			"Hàng chờ đo",
			"Kết quả đo",
			"Duyệt kết quả",
			"Đăng ký bệnh nhân",
			"Đơn kính",
		],
		card_names=["Kết quả khám", "Hồ sơ bệnh nhân"],
	)


def clinic_admin_workspace_content() -> str:
	return healthcare_home_content(
		# The clinic sites do not install the ERPNext appointment dashboard chart.
		# Keep the workspace generator from reintroducing a stale chart block on
		# every migrate/sync; a missing chart can leave the Desk home looking empty.
		chart_name=None,
		shortcut_labels=[
			"Danh sách bệnh nhân",
			"Hàng chờ đo",
			"Kết quả đo",
			"Duyệt kết quả",
			"Đăng ký bệnh nhân",
		],
		card_names=["Kết quả khám", "Hồ sơ bệnh nhân", "Hệ thống"],
	)


def nurse_workspace_links() -> list[dict[str, Any]]:
	return [
		{"type": "Card Break", "label": "Bệnh nhân", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Danh sách bệnh nhân",
			"link_to": "Patient",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{"type": "Card Break", "label": "Hàng chờ", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Hàng chờ đo",
			"link_to": "nurse-station",
			"link_type": "Page",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
	]


def doctor_workspace_links() -> list[dict[str, Any]]:
	return [
		{"type": "Card Break", "label": "Kết quả khám", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Kết quả đo",
			"link_to": "Visual Acuity",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{
			"type": "Link",
			"label": "Đơn kính",
			"link_to": "Eye Prescription",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{"type": "Card Break", "label": "Hồ sơ bệnh nhân", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Bệnh nhân",
			"link_to": "Patient",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
	]


def clinic_admin_workspace_links() -> list[dict[str, Any]]:
	return [
		{"type": "Card Break", "label": "Kết quả khám", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Kết quả đo",
			"link_to": "Visual Acuity",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{
			"type": "Link",
			"label": "Đơn kính",
			"link_to": "Eye Prescription",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{"type": "Card Break", "label": "Hồ sơ bệnh nhân", "link_count": 0, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{
			"type": "Link",
			"label": "Bệnh nhân",
			"link_to": "Patient",
			"link_type": "DocType",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
		{
			"type": "Link",
			"label": "Hàng chờ đo",
			"link_to": "nurse-station",
			"link_type": "Page",
			"hidden": 0,
			"is_query_report": 0,
			"onboard": 0,
			"dependencies": "",
		},
	]


def hide_noise_workspaces() -> list[str]:
	hidden: list[str] = []
	for name in WORKSPACES_TO_HIDE:
		if not frappe.db.exists("Workspace", name):
			continue
		frappe.db.set_value("Workspace", name, "is_hidden", 1)
		hidden.append(name)
	return hidden


# Workspace autoname = field:label — name and label must match.
WORKSPACE_ALIASES: dict[str, tuple[str, ...]] = {
	WS_NURSE: (WS_NURSE, "Điều dưỡng"),
	WS_DOCTOR: (WS_DOCTOR, "Bác sĩ"),
	WS_ADMIN: (WS_ADMIN, "Quản trị phòng khám", "Smart Hospital"),
}


def upsert_workspace(
	label: str,
	*,
	title: str,
	icon: str,
	roles: tuple[str, ...],
	shortcuts: list[dict[str, Any]],
	links: list[dict[str, Any]],
	content: str,
	sequence_id: float,
	indicator_color: str = "blue",
	number_cards: list[str] | None = None,
) -> None:
	for alias in WORKSPACE_ALIASES.get(label, (label,)):
		if frappe.db.exists("Workspace", alias):
			frappe.delete_doc("Workspace", alias, force=True, ignore_permissions=True)

	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": label,
			"label": label,
			"title": title,
			"module": "QY Vision Hospital",
			"icon": icon,
			"public": 1,
			"is_hidden": 0,
			"content": content,
			"sequence_id": sequence_id,
			"indicator_color": indicator_color,
			"shortcuts": shortcuts,
			"links": links,
			"roles": [{"role": role} for role in roles if frappe.db.exists("Role", role)],
		}
	)
	if number_cards:
		for card_name in number_cards:
			if frappe.db.exists("Number Card", card_name):
				doc.append("number_cards", {"label": card_name, "number_card_name": card_name})
	doc.insert(ignore_permissions=True)


# Stale English names from early smart_hospital workspaces (break desktop icon routing).
STALE_SIDEBAR_AND_ICON_NAMES: tuple[str, ...] = (
	"Nurse",
	"Doctor",
	"Smart Hospital",
	"Clinic Admin",
)

SHORTCUT_SIDEBAR_ICONS: dict[str, str] = {
	"nurse-station": "users",
	"patient-registration": "user-plus",
	"patient-vision-booking": "calendar",
	"doctor-review": "file-text",
	"Patient": "users-round",
	"clinic-patients": "users-round",
	"Patient Appointment": "calendar-fold",
	"Visual Acuity": "eye",
	"Eye Prescription": "glasses",
	"Vision Measurement": "ruler",
	"Connection Settings": "plug",
	"Healthcare Settings": "settings",
}

# Keep each clinic sidebar focused on the three requested destinations.
CLINIC_SIDEBAR_VISIBLE_LINKS: frozenset[str] = frozenset(
	{"Patient", "nurse-station", "Visual Acuity"}
)


def _sidebar_items_for_workspace(workspace_name: str) -> list[dict[str, Any]]:
	workspace = frappe.get_doc("Workspace", workspace_name)
	items: list[dict[str, Any]] = [
		{
			"label": "Home",
			"link_to": workspace_name,
			"link_type": "Workspace",
			"type": "Link",
			"icon": "home",
			"idx": 1,
		}
	]
	for idx, shortcut in enumerate(workspace.shortcuts, start=2):
		if shortcut.label == "Trạm điều dưỡng":
			continue
		if shortcut.link_to not in CLINIC_SIDEBAR_VISIBLE_LINKS:
			continue
		items.append(
			{
				"label": shortcut.label,
				"link_to": shortcut.link_to,
				"link_type": shortcut.type,
				"type": "Link",
				"icon": SHORTCUT_SIDEBAR_ICONS.get(shortcut.link_to, "link"),
				"idx": idx,
			}
		)
	return items


def remove_stale_clinic_sidebars_and_icons() -> list[str]:
	removed: list[str] = []
	for name in STALE_SIDEBAR_AND_ICON_NAMES:
		if frappe.db.exists("Workspace Sidebar", name):
			frappe.delete_doc("Workspace Sidebar", name, force=True, ignore_permissions=True)
			removed.append(f"sidebar:{name}")
		if frappe.db.exists("Desktop Icon", name):
			frappe.delete_doc("Desktop Icon", name, force=True, ignore_permissions=True)
			removed.append(f"icon:{name}")
	return removed


def upsert_workspace_sidebar(workspace_name: str) -> None:
	if not frappe.db.exists("Workspace", workspace_name):
		return
	header_icon = frappe.db.get_value("Workspace", workspace_name, "icon")
	items = _sidebar_items_for_workspace(workspace_name)
	if frappe.db.exists("Workspace Sidebar", workspace_name):
		frappe.delete_doc("Workspace Sidebar", workspace_name, force=True, ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Workspace Sidebar",
			"title": workspace_name,
			"header_icon": header_icon,
			"standard": 0,
			"module": "QY Vision Hospital",
			"items": items,
		}
	)
	doc.insert(ignore_permissions=True)


def upsert_desktop_icon_for_sidebar(sidebar_title: str) -> None:
	if not frappe.db.exists("Workspace Sidebar", sidebar_title):
		return
	icon = frappe.db.get_value("Workspace", sidebar_title, "icon")
	fields = {
		"label": sidebar_title,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": sidebar_title,
		"icon": icon,
		"hidden": 0,
	}
	if frappe.db.exists("Desktop Icon", sidebar_title):
		frappe.db.set_value("Desktop Icon", sidebar_title, fields, update_modified=False)
		return
	max_idx = frappe.db.sql("SELECT COALESCE(MAX(idx), 0) FROM `tabDesktop Icon`")[0][0]
	doc = frappe.get_doc(
		{
			"doctype": "Desktop Icon",
			**fields,
			"idx": max_idx + 1,
			"standard": 0,
		}
	)
	doc.insert(ignore_permissions=True)


def hide_noise_desktop_icons() -> list[str]:
	hidden: list[str] = []
	targets = set(WORKSPACES_TO_HIDE) | set(DESKTOP_APP_ICONS_TO_HIDE)

	for name in targets:
		if frappe.db.exists("Desktop Icon", name):
			frappe.db.set_value("Desktop Icon", name, "hidden", 1)
			hidden.append(name)

	for parent in DESKTOP_APP_ICONS_TO_HIDE:
		for row in frappe.get_all(
			"Desktop Icon",
			filters={"parent_icon": parent},
			pluck="name",
		):
			if frappe.db.get_value("Desktop Icon", row, "hidden"):
				continue
			frappe.db.set_value("Desktop Icon", row, "hidden", 1)
			hidden.append(row)

	for row in frappe.get_all(
		"Desktop Icon",
		filters={"app": "healthcare", "hidden": 0},
		pluck="name",
	):
		frappe.db.set_value("Desktop Icon", row, "hidden", 1)
		hidden.append(row)

	return hidden


def sync_clinic_desktop_navigation() -> dict[str, Any]:
	"""Rebuild Workspace Sidebars + Desktop Icons so Frappe desktop routing resolves."""
	removed = remove_stale_clinic_sidebars_and_icons()
	sidebars: list[str] = []
	for ws in (WS_ADMIN, WS_NURSE, WS_DOCTOR):
		upsert_workspace_sidebar(ws)
		upsert_desktop_icon_for_sidebar(ws)
		sidebars.append(ws)
	hide_noise_desktop_icons()
	from qy_vision_hospital.api.clinic_shell import enforce_clinic_only_desktop

	return {
		"removed": removed,
		"sidebars": sidebars,
		"clinic_desktop_icons": enforce_clinic_only_desktop(),
	}
