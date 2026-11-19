"""Permanently wipe a Patient and all clinic records tied to them."""

from __future__ import annotations

from typing import Any

import frappe

from smart_hospital.overrides.patient import unlink_patient_contacts

_CLINIC_STAFF_ROLES = {
	"System Manager",
	"Healthcare Administrator",
	"Nursing User",
	"Physician",
}

# Delete these first so Patient is not blocked by clinic links.
_DELETE_FIRST = (
	"Eye Prescription",
	"Visual Acuity",
	"Vision Measurement",
	"Patient Appointment",
	"Patient Encounter",
	"Vital Signs",
	"Lab Test",
	"Clinical Procedure",
	"Inpatient Record",
	"Patient Medical Record",
	"Patient Assessment",
	"Therapy Session",
	"Therapy Plan",
)


def _as_names(value: Any) -> list[str]:
	if value is None:
		value = frappe.form_dict.get("patients") or frappe.form_dict.get("patient")
	if isinstance(value, str):
		raw = value.strip()
		if raw.startswith("["):
			import json

			value = json.loads(raw)
		else:
			value = [raw]
	names: list[str] = []
	for item in value or []:
		name = str(item or "").strip()
		if name and name not in names:
			names.append(name)
	return names


def _assert_can_wipe() -> None:
	if frappe.session.user == "Administrator":
		return
	roles = set(frappe.get_roles())
	if roles & _CLINIC_STAFF_ROLES:
		return
	if frappe.has_permission("Patient", "delete"):
		return
	frappe.throw("Bạn không có quyền xóa bệnh nhân.", frappe.PermissionError)


def _doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _is_table(doctype: str) -> bool:
	return bool(frappe.db.get_value("DocType", doctype, "istable"))


def _force_delete(doctype: str, name: str) -> bool:
	try:
		frappe.delete_doc(
			doctype,
			name,
			force=True,
			ignore_permissions=True,
			ignore_missing=True,
			delete_permanently=True,
		)
		return True
	except TypeError:
		try:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			return True
		except Exception:  # noqa: BLE001
			pass
	except Exception:  # noqa: BLE001
		frappe.log_error(
			title="patient_wipe force_delete",
			message=f"{doctype} {name}\n{frappe.get_traceback()}",
		)
	try:
		frappe.db.delete(doctype, {"name": name})
		return True
	except Exception:  # noqa: BLE001
		return False


def _names(doctype: str, filters: dict[str, Any]) -> list[str]:
	if not _doctype_exists(doctype):
		return []
	try:
		return frappe.get_all(doctype, filters=filters, pluck="name")
	except Exception:  # noqa: BLE001
		return []


def _linked_via_patient_field(patient: str) -> dict[str, list[str]]:
	found: dict[str, list[str]] = {}
	fields = frappe.get_all(
		"DocField",
		filters={"fieldtype": "Link", "options": "Patient"},
		fields=["parent", "fieldname"],
	)
	custom = frappe.get_all(
		"Custom Field",
		filters={"dt": ["!=", ""], "fieldtype": "Link", "options": "Patient"},
		fields=["dt", "fieldname"],
	)
	seen: set[tuple[str, str]] = set()
	rows = list(fields) + [
		frappe._dict({"parent": row.dt, "fieldname": row.fieldname}) for row in custom
	]
	for row in rows:
		doctype = row.parent
		fieldname = row.fieldname
		if not doctype or doctype == "Patient" or (doctype, fieldname) in seen:
			continue
		seen.add((doctype, fieldname))
		if not _doctype_exists(doctype) or _is_table(doctype):
			continue
		names = _names(doctype, {fieldname: patient})
		if names:
			found.setdefault(doctype, [])
			for name in names:
				if name not in found[doctype]:
					found[doctype].append(name)
	return found


def _clinic_docs_for_patient(patient: str) -> dict[str, list[str]]:
	docs = _linked_via_patient_field(patient)
	vms = list(docs.get("Vision Measurement") or [])
	vms += _names("Vision Measurement", {"patient": patient})
	vms = list(dict.fromkeys(vms))
	if vms:
		docs["Vision Measurement"] = vms
		vas = _names("Visual Acuity", {"vision_measurement": ["in", vms]})
		if vas:
			docs["Visual Acuity"] = list(dict.fromkeys((docs.get("Visual Acuity") or []) + vas))
	files = _names("File", {"attached_to_doctype": "Patient", "attached_to_name": patient})
	if files:
		docs["File"] = files
	for parenttype in ("Contact", "Address"):
		parents = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Patient", "link_name": patient, "parenttype": parenttype},
			pluck="parent",
		)
		if parents:
			docs[parenttype] = list(dict.fromkeys(parents))
	return docs


_PORTAL_USER_ROLES = {"Patient", "Customer", "All", "Guest", "Desk User"}


def _patient_row(patient: str) -> dict[str, Any] | None:
	if not frappe.db.exists("Patient", patient):
		return None
	fields = ["name", "patient_name", "uid", "email", "mobile"]
	meta = frappe.get_meta("Patient")
	if meta.has_field("custom_aiface_enroll_id"):
		fields.append("custom_aiface_enroll_id")
	if meta.has_field("user_id"):
		fields.append("user_id")
	if meta.has_field("customer"):
		fields.append("customer")
	if meta.has_field("custom_face_avatar_object_key"):
		fields.append("custom_face_avatar_object_key")
	if meta.has_field("custom_face_avatar_url"):
		fields.append("custom_face_avatar_url")
	return frappe.db.get_value("Patient", patient, fields, as_dict=True)


def _is_portal_only_user(user_name: str) -> bool:
	if not user_name or user_name in ("Administrator", "Guest"):
		return False
	if not frappe.db.exists("User", user_name):
		return False
	user_type = frappe.db.get_value("User", user_name, "user_type")
	if user_type == "Website User":
		return True
	roles = set(frappe.get_roles(user_name))
	return not (roles - _PORTAL_USER_ROLES)


def _purge_party_links(link_doctype: str, link_name: str) -> dict[str, int]:
	"""Remove Dynamic Links and delete orphan Contact / Address rows."""
	removed: dict[str, int] = {}
	if not link_doctype or not link_name:
		return removed
	links = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": link_doctype, "link_name": link_name},
		fields=["name", "parent", "parenttype"],
	)
	parents: dict[str, set[str]] = {}
	for link in links:
		frappe.db.delete("Dynamic Link", {"name": link.name})
		if link.parenttype:
			parents.setdefault(str(link.parenttype), set()).add(link.parent)
	for parenttype, names in parents.items():
		if parenttype not in ("Contact", "Address"):
			continue
		ok = 0
		for parent in names:
			remaining = frappe.get_all(
				"Dynamic Link",
				filters={"parent": parent, "parenttype": parenttype},
				limit=1,
			)
			if remaining:
				continue
			if _force_delete(parenttype, parent):
				ok += 1
		if ok:
			removed[parenttype] = removed.get(parenttype, 0) + ok
	return removed


def _delete_timeline(doctype: str, name: str) -> None:
	if not doctype or not name:
		return
	pairs = (
		("Comment", {"reference_doctype": doctype, "reference_name": name}),
		("Communication", {"reference_doctype": doctype, "reference_name": name}),
		("ToDo", {"reference_type": doctype, "reference_name": name}),
		("File", {"attached_to_doctype": doctype, "attached_to_name": name}),
		("Version", {"ref_doctype": doctype, "docname": name}),
		("DocShare", {"share_doctype": doctype, "share_name": name}),
	)
	for child, filters in pairs:
		if not _doctype_exists(child):
			continue
		for docname in _names(child, filters):
			_force_delete(child, docname)


def _contacts_by_email_mobile(email: str, mobile: str) -> list[str]:
	found: list[str] = []
	filters: list[list[Any]] = []
	if email:
		filters.append(["email_id", "=", email])
	if mobile:
		filters.append(["mobile_no", "=", mobile])
	if not filters:
		return found
	try:
		for name in frappe.get_all("Contact", or_filters=filters, pluck="name"):
			if name not in found:
				found.append(name)
	except Exception:  # noqa: BLE001
		pass
	return found


def _delete_portal_user(user_name: str) -> bool:
	if not _is_portal_only_user(user_name):
		return False
	return _force_delete("User", user_name)


def _customers_for_patient(row: dict[str, Any]) -> list[str]:
	found: list[str] = []
	customer = (row.get("customer") or "").strip()
	if customer:
		found.append(customer)
	patient_name = (row.get("name") or "").strip()
	display = (row.get("patient_name") or "").strip()
	for candidate in (patient_name, display, f"{patient_name} - 1", f"{display} - 1"):
		if candidate and frappe.db.exists("Customer", candidate) and candidate not in found:
			other = frappe.db.exists(
				"Patient",
				{"customer": candidate, "name": ["!=", patient_name]},
			)
			if not other:
				found.append(candidate)
	return found


def _portal_users_for_patient(row: dict[str, Any]) -> list[str]:
	found: list[str] = []
	user_id = (row.get("user_id") or "").strip()
	if user_id:
		found.append(user_id)
	email = (row.get("email") or "").strip()
	mobile = (row.get("mobile") or "").strip()
	filters: list[list[Any]] = []
	if email:
		filters.append(["email", "=", email])
	if mobile:
		filters.append(["mobile_no", "=", mobile])
	if filters:
		for name in frappe.get_all("User", or_filters=filters, pluck="name"):
			if name not in found:
				found.append(name)
	return found


def _delete_vectordb(enroll_id: int) -> dict[str, Any]:
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
	url = f"{str(base).rstrip('/')}/v1/faces/{int(enroll_id)}"
	try:
		resp = requests.delete(
			url,
			headers={"X-Api-Key": str(api_key)},
			timeout=15,
		)
		return {"ok": resp.ok, "status": resp.status_code}
	except Exception as exc:  # noqa: BLE001
		return {"ok": False, "error": str(exc)}


def _delete_aiface(enroll_id: int) -> dict[str, Any]:
	import requests
	from smart_hospital.api.face_identity import get_aiface_station_url

	cfg = get_aiface_station_url() or {}
	station = str(cfg.get("aiface_station_url") or "").rstrip("/")
	if not station:
		return {"ok": False, "error": cfg.get("error") or "aiface_station_url_not_configured"}
	url = f"{station}/api/face/delete_one"
	try:
		resp = requests.post(url, json={"enroll_id": int(enroll_id)}, timeout=20)
		return {"ok": resp.ok, "status": resp.status_code}
	except Exception as exc:  # noqa: BLE001
		return {"ok": False, "error": str(exc)}


def _object_key_from_media_url(url: str | None) -> str | None:
	from urllib.parse import unquote

	raw = (url or "").strip()
	if not raw:
		return None
	marker = "/v1/objects/"
	if marker not in raw:
		return None
	key = unquote(raw.split(marker, 1)[1].split("?", 1)[0]).strip("/")
	return key or None


def _media_keys_for_patient(row: dict[str, Any], docs: dict[str, list[str]]) -> tuple[list[str], list[str]]:
	keys: list[str] = []
	sessions: list[str] = []

	def _add_key(value: str | None) -> None:
		key = (value or "").strip()
		if key and key not in keys:
			keys.append(key)

	def _add_session(value: str | None) -> None:
		sid = (value or "").strip()
		if sid and sid not in sessions and "/" not in sid:
			sessions.append(sid)

	_add_key(row.get("custom_face_avatar_object_key"))
	_add_key(_object_key_from_media_url(row.get("custom_face_avatar_url")))
	for file_name in docs.get("File") or []:
		file_url = frappe.db.get_value("File", file_name, "file_url") or ""
		_add_key(_object_key_from_media_url(file_url))

	name = (row.get("name") or "").strip()
	uid = (row.get("uid") or "").strip()
	# Patient display names are not identifiers: media safe_key normalizes
	# different accented names to the same path. Purge only stable IDs.
	for raw in (name, uid):
		if raw:
			_add_session(f"patient-{raw}")
	eid = _enroll_id(row)
	if eid is not None:
		_add_session(f"face-{eid}")
		_add_session(f"enroll-{eid}")
		_add_session(f"backfill-{eid}")
	for doctype in ("Vision Measurement", "Patient Appointment", "Patient Encounter"):
		for docname in docs.get(doctype) or []:
			_add_session(str(docname))
	return keys, sessions


def _purge_patient_media(row: dict[str, Any], docs: dict[str, list[str]]) -> dict[str, Any]:
	"""Delete this patient's JPEGs from the media gateway (avatar / face / enroll)."""
	import requests

	from smart_hospital.api.face_identity import _media_conf

	object_keys, session_ids = _media_keys_for_patient(row, docs)
	if not object_keys and not session_ids:
		return {"ok": True, "skipped": True, "count": 0}
	media_base, media_token = _media_conf()
	try:
		resp = requests.post(
			f"{media_base}/v1/purge",
			json={"object_keys": object_keys, "session_ids": session_ids},
			headers={"X-Media-Token": str(media_token), "Content-Type": "application/json"},
			timeout=20,
		)
		if not resp.ok:
			return {
				"ok": False,
				"status": resp.status_code,
				"error": (resp.text or "")[:300],
				"object_keys": object_keys,
				"session_ids": session_ids,
			}
		body = resp.json() if resp.content else {}
		if not isinstance(body, dict):
			body = {"raw": body}
		body.setdefault("ok", True)
		body["object_keys"] = object_keys
		body["session_ids"] = session_ids
		return body
	except Exception as exc:  # noqa: BLE001
		return {
			"ok": False,
			"error": str(exc),
			"object_keys": object_keys,
			"session_ids": session_ids,
		}


def _enroll_id(row: dict[str, Any] | None) -> int | None:
	if not row:
		return None
	raw = row.get("custom_aiface_enroll_id")
	try:
		eid = int(raw)
	except (TypeError, ValueError):
		return None
	if eid <= 0 or eid == 99999999:
		return None
	return eid


def purge_customer_if_orphan(customer_name: str, keep_patient: str | None = None) -> bool:
	"""Delete a Customer (and its Contact/Address) if no other Patient points at it.

	Never delete a Customer whose name is still a live Patient — Healthcare can
	cascade Customer delete onto that Patient.
	"""
	customer_name = (customer_name or "").strip()
	if not customer_name or not frappe.db.exists("Customer", customer_name):
		return False
	if frappe.db.exists("Patient", customer_name) and customer_name != keep_patient:
		return False
	filters: dict[str, Any] = {"customer": customer_name}
	if keep_patient:
		filters["name"] = ["!=", keep_patient]
	if frappe.db.exists("Patient", filters):
		return False
	_purge_party_links("Customer", customer_name)
	_delete_timeline("Customer", customer_name)
	return _force_delete("Customer", customer_name)


@frappe.whitelist()
def purge_orphan_clinic_parties() -> dict[str, Any]:
	"""Remove Customers/Contacts left behind after a Patient was deleted."""
	_assert_can_wipe()
	linked = {
		str(name)
		for name in frappe.get_all("Patient", filters={"customer": ["!=", ""]}, pluck="customer")
		if name
	}
	removed_customers: list[str] = []
	for customer in frappe.get_all("Customer", pluck="name"):
		if customer in linked:
			continue
		if purge_customer_if_orphan(customer):
			removed_customers.append(customer)

	removed_contacts: list[str] = []
	for contact in frappe.get_all("Contact", pluck="name"):
		if contact in ("Nurse Tran", "Doctor Nguyen"):
			continue
		links = frappe.get_all(
			"Dynamic Link",
			filters={"parent": contact, "parenttype": "Contact"},
			fields=["link_doctype", "link_name"],
		)
		if any(row.link_doctype == "Patient" and frappe.db.exists("Patient", row.link_name) for row in links):
			continue
		if any(row.link_doctype == "Customer" and frappe.db.exists("Customer", row.link_name) for row in links):
			continue
		# Staff contacts for clinic Users — keep.
		email = frappe.db.get_value("Contact", contact, "email_id") or ""
		if email in ("nurse@imes.local", "doctor@imes.local", "admin@example.com"):
			continue
		if _force_delete("Contact", contact):
			removed_contacts.append(contact)

	frappe.db.commit()
	return {
		"success": True,
		"customers": removed_customers,
		"contacts": removed_contacts,
	}


@frappe.whitelist()
def preview_patient_wipe(patients: Any = None) -> dict[str, Any]:
	"""Counts for the warning dialog. Does not delete."""
	_assert_can_wipe()
	names = _as_names(patients)
	if not names:
		frappe.throw("Chọn ít nhất một bệnh nhân.")
	items: list[dict[str, Any]] = []
	totals: dict[str, int] = {}
	for name in names:
		row = _patient_row(name)
		if not row:
			items.append({"name": name, "missing": True})
			continue
		docs = _clinic_docs_for_patient(name)
		counts = {dt: len(vals) for dt, vals in docs.items() if vals}
		customers = _customers_for_patient(row)
		users = _portal_users_for_patient(row)
		if customers:
			counts["Customer"] = len(customers)
		if users:
			counts["User"] = len(users)
		media_keys, media_sessions = _media_keys_for_patient(row, docs)
		if media_keys or media_sessions:
			counts["Media"] = max(len(media_keys), 1)
		for dt, n in counts.items():
			totals[dt] = totals.get(dt, 0) + n
		items.append(
			{
				"name": name,
				"patient_name": row.get("patient_name") or name,
				"uid": row.get("uid") or "",
				"enroll_id": _enroll_id(row),
				"counts": counts,
			}
		)
	return {"success": True, "patients": items, "totals": totals}


@frappe.whitelist()
def wipe_patient(patients: Any = None) -> dict[str, Any]:
	"""Delete the patient and every clinic record / face identity tied to them."""
	_assert_can_wipe()
	names = _as_names(patients)
	if not names:
		frappe.throw("Chọn ít nhất một bệnh nhân.")

	wiped: list[dict[str, Any]] = []
	errors: list[dict[str, Any]] = []

	for name in names:
		row = _patient_row(name)
		if not row:
			errors.append({"patient": name, "error": "not_found"})
			continue
		docs = _clinic_docs_for_patient(name)
		deleted: dict[str, int] = {}
		external: dict[str, Any] = {}
		external["media"] = _purge_patient_media(row, docs)

		ordered = [dt for dt in _DELETE_FIRST if dt in docs] + [
			dt for dt in docs if dt not in _DELETE_FIRST
		]
		for doctype in ordered:
			ok = 0
			for docname in docs.get(doctype) or []:
				if _force_delete(doctype, docname):
					ok += 1
			if ok:
				deleted[doctype] = ok

		eid = _enroll_id(row)
		if eid is not None:
			external["vectordb"] = _delete_vectordb(eid)
			external["aiface"] = _delete_aiface(eid)

		customers = _customers_for_patient(row)
		portal_users = _portal_users_for_patient(row)

		link_stats = _purge_party_links("Patient", name)
		for customer_name in customers:
			extra = _purge_party_links("Customer", customer_name)
			for key, n in extra.items():
				link_stats[key] = link_stats.get(key, 0) + n
			_delete_timeline("Customer", customer_name)
		_delete_timeline("Patient", name)

		for contact in _contacts_by_email_mobile(row.get("email") or "", row.get("mobile") or ""):
			if _force_delete("Contact", contact):
				link_stats["Contact"] = link_stats.get("Contact", 0) + 1

		contacts = unlink_patient_contacts(name)
		try:
			frappe.delete_doc(
				"Patient",
				name,
				force=True,
				ignore_permissions=True,
				ignore_links=True,
				delete_permanently=True,
			)
		except TypeError:
			frappe.delete_doc("Patient", name, force=True, ignore_permissions=True)

		users_deleted: list[str] = []
		for user_name in portal_users:
			_delete_timeline("User", user_name)
			if _delete_portal_user(user_name):
				users_deleted.append(user_name)
				deleted["User"] = deleted.get("User", 0) + 1

		customers_deleted: list[str] = []
		for customer_name in customers:
			if _force_delete("Customer", customer_name):
				customers_deleted.append(customer_name)
				deleted["Customer"] = deleted.get("Customer", 0) + 1

		for key, n in link_stats.items():
			if n:
				deleted[key] = deleted.get(key, 0) + n

		wiped.append(
			{
				"patient": name,
				"patient_name": row.get("patient_name") or name,
				"deleted": deleted,
				"contacts_removed": contacts,
				"users_deleted": users_deleted,
				"customers_deleted": customers_deleted,
				"external": external,
			}
		)

	frappe.db.commit()
	orphans = purge_orphan_clinic_parties()
	return {
		"success": not errors,
		"wiped": wiped,
		"errors": errors,
		"count": len(wiped),
		"orphans": orphans,
	}
