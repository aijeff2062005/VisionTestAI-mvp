"""Patient delete + Face ID auto-number helpers."""

from __future__ import annotations

from typing import Any

import frappe


def unlink_patient_contacts(patient_name: str) -> list[str]:
	"""Remove Dynamic Links from Contact → Patient; delete orphan Contacts.

	Healthcare creates a Contact when inserting Patient; Desk delete then fails with
	"Cannot delete or cancel because Patient … is linked with Contact …".
	"""
	if not patient_name:
		return []

	links = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Patient", "link_name": patient_name},
		fields=["name", "parent", "parenttype"],
	)
	contact_names: set[str] = set()
	for link in links:
		frappe.db.delete("Dynamic Link", {"name": link.name})
		if link.parenttype == "Contact":
			contact_names.add(link.parent)

	deleted: list[str] = []
	for contact in contact_names:
		remaining = frappe.get_all(
			"Dynamic Link",
			filters={"parent": contact, "parenttype": "Contact"},
			limit=1,
		)
		if remaining:
			continue
		try:
			frappe.delete_doc(
				"Contact",
				contact,
				force=True,
				ignore_permissions=True,
				ignore_missing=True,
			)
			deleted.append(contact)
		except Exception:  # noqa: BLE001
			frappe.log_error(
				title="unlink_patient_contacts Contact delete",
				message=frappe.get_traceback(),
			)
	return deleted


def on_patient_trash(doc, method=None):
	"""Best-effort cleanup if delete got past link checks (force / ignore_links)."""
	unlink_patient_contacts(doc.name)
	customer = (getattr(doc, "customer", None) or "").strip()
	display = (getattr(doc, "patient_name", None) or doc.name or "").strip()
	from smart_hospital.api.patient_wipe import purge_customer_if_orphan

	for candidate in (customer, doc.name, display):
		if candidate:
			purge_customer_if_orphan(candidate, keep_patient=doc.name)



def try_import_healthcare_patient():
	try:
		from healthcare.healthcare.doctype.patient.patient import Patient as HealthcarePatient

		return HealthcarePatient
	except Exception:  # noqa: BLE001
		return None


_HealthcarePatient = try_import_healthcare_patient()
_Base = _HealthcarePatient or frappe.model.document.Document


def _orphan_customer_for_name(patient_name: str) -> str | None:
	wanted = (patient_name or "").strip()
	if not wanted:
		return None
	candidates = [wanted]
	by_label = frappe.db.get_value("Customer", {"customer_name": wanted}, "name")
	if by_label:
		candidates.append(by_label)
	for candidate in candidates:
		if not candidate or not frappe.db.exists("Customer", candidate):
			continue
		if frappe.db.exists("Patient", {"customer": candidate}):
			continue
		return candidate
	return None


class SmartPatient(_Base):
	"""Extend Healthcare Patient: Face ID auto-count + Desk Delete."""

	ignore_linked_doctypes = [
		"Contact",
		"Customer",
		"Address",
	]

	def validate(self):
		# Clinic patients are not portal logins. Healthcare defaults invite_user=1
		# and then throws if a leftover User already has that email/mobile.
		if self.meta.has_field("invite_user"):
			self.invite_user = 0
		super().validate()
		self._ensure_unique_aiface_enroll_id()

	def before_insert(self):
		if self.meta.has_field("invite_user"):
			self.invite_user = 0
		if hasattr(self, "set_full_name"):
			self.set_full_name()
		if not self.customer:
			reuse = _orphan_customer_for_name(self.patient_name or "")
			if reuse:
				self.customer = reuse
		super().before_insert()
		self._ensure_unique_aiface_enroll_id(assign_if_missing=True)

	def after_insert(self):
		super().after_insert()
		# Healthcare after_insert() reloads from DB (DEFAULT invite_user=1).
		if self.meta.has_field("invite_user"):
			self.invite_user = 0
			self.db_set("invite_user", 0, update_modified=False)

	def on_update(self):
		if self.meta.has_field("invite_user"):
			self.invite_user = 0
		super().on_update()

	def create_website_user(self):
		"""Do not create a Desk/portal User when registering a clinic patient."""
		return

	def _ensure_unique_aiface_enroll_id(self, assign_if_missing: bool = False):
		"""Int defaults to 0 → UNIQUE clash; always keep a positive unique Face ID."""
		from smart_hospital.api.face_identity import (
			next_aiface_enroll_id,
			normalize_aiface_enroll_id,
		)

		if not self.meta.has_field("custom_aiface_enroll_id"):
			return
		eid = normalize_aiface_enroll_id(getattr(self, "custom_aiface_enroll_id", None))
		if eid is None:
			# Column is NOT NULL (defaults to 0) — must assign a real id
			if assign_if_missing or self.is_new() or not self.get("custom_aiface_enroll_id"):
				self.custom_aiface_enroll_id = next_aiface_enroll_id()
			return
		clash = frappe.db.get_value(
			"Patient",
			{"custom_aiface_enroll_id": eid, "name": ["!=", self.name or ""]},
			"name",
		)
		if clash:
			self.custom_aiface_enroll_id = next_aiface_enroll_id()
		else:
			self.custom_aiface_enroll_id = eid

	def delete(self, ignore_permissions=False, force=False, **kwargs):
		unlink_patient_contacts(self.name)
		try:
			return frappe.delete_doc(
				self.doctype,
				self.name,
				ignore_permissions=True,
				force=True,
				ignore_links=True,
				delete_permanently=kwargs.get("delete_permanently", False),
			)
		except TypeError:
			return frappe.delete_doc(
				self.doctype,
				self.name,
				ignore_permissions=True,
				force=True,
			)


@frappe.whitelist()
def force_delete_patient(patient: str | None = None) -> dict[str, Any]:
	"""Desk/API helper: full wipe of Patient and related clinic records."""
	from smart_hospital.api.patient_wipe import wipe_patient

	return wipe_patient(patient)


@frappe.whitelist()
def safe_client_delete(doctype: str, name: str):
	"""Replace frappe.client.delete for Patient so clinic records are wiped too."""
	if doctype == "Patient":
		from smart_hospital.api.patient_wipe import wipe_patient

		wipe_patient(name)
		return "ok"
	frappe.delete_doc(doctype, name)
	return "ok"
