"""QY-only XML intake and measurement queue APIs."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Any

import frappe
from frappe.utils import getdate, now_datetime


ALLOWED_ROLES = {"Nursing User", "Physician", "Healthcare Administrator", "System Manager"}
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_BATCH_PATIENTS = 500


def ensure_xml_fields() -> None:
	"""Create QY-specific HIS identifiers without treating partial CCCD as a full UID."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Patient": [
				{
					"fieldname": "custom_his_patient_id",
					"label": "Mã bệnh nhân HIS",
					"fieldtype": "Data",
					"insert_after": "uid",
					"unique": 1,
					"in_list_view": 0,
					"hidden": 1,
				},
				{
					"fieldname": "custom_cccd_last4",
					"label": "4 số cuối CCCD",
					"fieldtype": "Data",
					"insert_after": "custom_his_patient_id",
					"in_list_view": 0,
					"hidden": 1,
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Patient")
	if frappe.db.exists("DocType", "QY Measurement Request"):
		frappe.db.sql("""
			UPDATE `tabQY Measurement Request`
			SET measurement_date = DATE(received_at)
			WHERE measurement_date IS NULL AND received_at IS NOT NULL
		""")


def _require_clinic_user() -> None:
	if frappe.session.user == "Guest" or not ALLOWED_ROLES.intersection(frappe.get_roles()):
		frappe.throw("Bạn không có quyền thao tác hàng chờ đo.", frappe.PermissionError)


def _parse_xml(xml_content: str) -> list[dict[str, str]]:
	if not xml_content or len(xml_content.encode("utf-8")) > MAX_XML_BYTES:
		frappe.throw("File XML rỗng hoặc vượt quá 2 MB.")
	if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml_content, re.IGNORECASE):
		frappe.throw("XML không được khai báo DOCTYPE hoặc ENTITY.")
	try:
		root = ET.fromstring(xml_content)
	except ET.ParseError as exc:
		frappe.throw(f"XML sai định dạng: {exc}")
	if root.tag != "patients":
		frappe.throw("Thẻ gốc XML phải là <patients>.")
	patient_nodes = root.findall("patient")
	if not patient_nodes or len(patient_nodes) > MAX_BATCH_PATIENTS:
		frappe.throw(f"Lô XML cần có từ 1 đến {MAX_BATCH_PATIENTS} bệnh nhân.")
	patients = []
	seen_ids = set()
	for node in patient_nodes:
		values = {child.tag: (child.text or "").strip() for child in node}
		his_id = values.get("his_patient_id", "")
		full_name = values.get("full_name", "")
		last4 = values.get("cccd_last4", "")
		if not his_id or not full_name or not re.fullmatch(r"\d{4}", last4):
			frappe.throw("Mỗi bệnh nhân cần mã HIS, họ tên và đúng 4 số cuối CCCD.")
		if len(his_id) > 140 or len(full_name) > 140:
			frappe.throw("Mã bệnh nhân hoặc họ tên vượt quá độ dài cho phép.")
		if his_id in seen_ids:
			frappe.throw(f"Mã HIS {his_id} bị lặp trong cùng lô XML.")
		seen_ids.add(his_id)
		patients.append({"his_patient_id": his_id, "full_name": full_name, "cccd_last4": last4})
	return patients


def _patient_for_xml(values: dict[str, str]) -> tuple[str, bool]:
	patient_name = frappe.db.get_value(
		"Patient", {"custom_his_patient_id": values["his_patient_id"]}, "name"
	)
	created = not bool(patient_name)
	if created:
		patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": values["full_name"],
				"patient_name": values["full_name"],
				"custom_his_patient_id": values["his_patient_id"],
				"custom_cccd_last4": values["cccd_last4"],
				"invite_user": 0,
			}
		)
		patient.insert(ignore_permissions=True, ignore_mandatory=True)
		patient_name = patient.name
	else:
		# Update only the fields owned by this XML contract. Saving the whole
		# Patient document revalidates unrelated mandatory fields (for example
		# sex), which may be empty on an existing patient imported from HIS.
		updates = {
			"patient_name": values["full_name"],
			"custom_cccd_last4": values["cccd_last4"],
		}
		if frappe.get_meta("Patient").has_field("first_name"):
			updates["first_name"] = values["full_name"]
		frappe.db.set_value("Patient", patient_name, updates, update_modified=True)
	return str(patient_name), created


@frappe.whitelist(methods=["POST"])
def import_patient_xml(xml_content: str | None = None, source_file: str | None = None, source_key: str | None = None) -> dict[str, Any]:
	"""Import a patient-list XML; content fingerprint makes retries idempotent."""
	_require_clinic_user()
	xml_content = xml_content or frappe.form_dict.get("xml_content")
	source_file = (source_file or frappe.form_dict.get("source_file") or "").strip()[:140]
	source_key = (source_key or frappe.form_dict.get("source_key") or "").strip()[:140]
	patients = _parse_xml(str(xml_content or ""))
	ensure_xml_fields()
	# Ignore XML order/formatting, while treating changed patient demographics
	# as a new import version. This lets repeat HIS exports update the Patient
	# record without creating a second measurement request for the same HIS ID.
	canonical_patients = sorted(
		(p["his_patient_id"], p["full_name"], p["cccd_last4"])
		for p in patients
	)
	payload_hash = hashlib.sha256(
		json.dumps(canonical_patients, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
	).hexdigest()
	# This is an internal receipt key, not a field HIS must send.
	import_date = getdate()
	batch_id = f"{import_date}-{payload_hash}"
	existing_batch = frappe.db.get_value(
		"QY XML Import Batch", {"batch_id": batch_id}, ["name", "payload_hash"], as_dict=True
	)
	if not existing_batch:
		batch = frappe.get_doc({
			"doctype": "QY XML Import Batch",
			"batch_id": batch_id,
			"payload_hash": payload_hash,
			"source_file": source_file,
			"received_at": now_datetime(),
			"patient_count": len(patients),
		})
		batch.insert(ignore_permissions=True)
	requests = []
	created_count = 0
	duplicate_count = 0
	patient_names_to_publish = set()
	for values in patients:
		# A stable per-batch/per-patient key makes an API retry safe.
		item_key = hashlib.sha256(f"{batch_id}\0{values['his_patient_id']}".encode("utf-8")).hexdigest()
		# Always sync demographics first. An existing measurement request prevents
		# a new queue row, but must not prevent the Patient record from updating.
		patient, created = _patient_for_xml(values)
		created_count += int(created)
		patient_names_to_publish.add(patient)
		prior_request = frappe.db.get_value("QY Measurement Request", {
			"his_patient_id": values["his_patient_id"], "measurement_date": import_date,
		}, ["name", "patient"], as_dict=True)
		if prior_request:
			requests.append({"request": prior_request.name, "patient": prior_request.patient, "duplicate": True})
			duplicate_count += 1
			continue
		existing = frappe.db.get_value("QY Measurement Request", {"source_key": item_key}, ["name", "patient"], as_dict=True)
		if existing:
			requests.append({"request": existing.name, "patient": existing.patient, "duplicate": True})
			duplicate_count += 1
			continue
		request = frappe.get_doc(
			{
				"doctype": "QY Measurement Request",
				"patient": patient,
				"his_patient_id": values["his_patient_id"],
				"cccd_last4": values["cccd_last4"],
				"measurement_date": import_date,
				"received_at": now_datetime(),
				"source_file": source_file,
				"source_key": item_key,
				"status": "Chờ đo",
			}
		)
		request.insert(ignore_permissions=True)
		requests.append({"request": request.name, "patient": patient, "duplicate": False})
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	for patient_name in patient_names_to_publish:
		publish_clinic_data_update("Patient", patient_name)
	for item in requests:
		if item["duplicate"]:
			continue
		publish_clinic_data_update("QY Measurement Request", item["request"])
	return {
		"success": True,
		"batch_id": batch_id,
		"received": len(patients),
		"queued": len(patients) - duplicate_count,
		"duplicates": duplicate_count,
		"patients_created": created_count,
		"patients_synced": len(patient_names_to_publish),
		"requests": requests,
	}


@frappe.whitelist()
def list_measurement_queue(limit: int = 200) -> dict[str, Any]:
	_require_clinic_user()
	limit = min(max(int(limit or 200), 1), 500)
	rows = frappe.get_all(
		"QY Measurement Request",
		filters={"status": ["in", ["Chờ đo", "Đang đo", "Hoàn tất"]], "measurement_date": getdate()},
		fields=["name", "patient", "his_patient_id", "cccd_last4", "measurement_date", "received_at", "status", "vision_measurement"],
		order_by="received_at asc, creation asc",
		limit_page_length=500,
	)
	active = bool(frappe.db.exists("QY Measurement Request", {"status": "Đang đo"}))
	# Preserve an in-progress measurement across midnight while keeping all
	# other rows scoped to today's measurement date.
	active_row = frappe.get_all("QY Measurement Request", filters={"status": "Đang đo"}, fields=["name", "patient", "his_patient_id", "cccd_last4", "measurement_date", "received_at", "status", "vision_measurement"], limit_page_length=1)
	if active_row and all(row.name != active_row[0].name for row in rows):
		rows = active_row + rows
	rows = rows[:limit]
	next_waiting = next((row.name for row in rows if row.status == "Chờ đo"), None)
	for row in rows:
		row["patient_name"] = frappe.db.get_value("Patient", row.patient, "patient_name") or row.patient
		row["can_start"] = not active and row.status == "Chờ đo" and row.name == next_waiting
		row["visual_acuity_result"] = frappe.db.get_value(
			"Visual Acuity", {"vision_measurement": row.vision_measurement}, "name"
		) if row.vision_measurement else None
	return {"success": True, "requests": rows}


@frappe.whitelist(methods=["POST"])
def add_patient_to_measurement_queue(patient: str | None = None) -> dict[str, Any]:
	"""Add an existing patient to today's queue without creating a duplicate Patient."""
	_require_clinic_user()
	patient = (patient or frappe.form_dict.get("patient") or "").strip()
	if not patient or not frappe.db.exists("Patient", patient):
		frappe.throw("Không tìm thấy hồ sơ bệnh nhân.")
	if frappe.db.exists("QY Measurement Request", {"status": "Đang đo"}):
		frappe.throw("Đang có lượt đo hoạt động. Hãy hoàn tất hoặc dừng lượt đó trước khi thêm bệnh nhân.")
	today = getdate()
	todays_requests = frappe.get_all(
		"QY Measurement Request",
		filters={"patient": patient, "measurement_date": today, "status": ["in", ["Chờ đo", "Đang đo", "Hoàn tất"]]},
		fields=["name", "measurement_date", "received_at"],
		limit_page_length=500,
	)
	if todays_requests:
		frappe.throw("Bệnh nhân này đã có lượt đo trong hàng chờ hôm nay.")
	patient_doc = frappe.get_doc("Patient", patient)
	his_id = patient_doc.get("custom_his_patient_id") or patient_doc.name
	request = frappe.get_doc({
		"doctype": "QY Measurement Request",
		"patient": patient,
		"his_patient_id": his_id,
		"cccd_last4": patient_doc.get("custom_cccd_last4") or "",
		"received_at": now_datetime(),
		"measurement_date": today,
		"source_file": "Thêm thủ công tại phòng khám",
		"source_key": f"manual-{uuid.uuid4().hex}",
		"status": "Chờ đo",
	})
	request.insert(ignore_permissions=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("QY Measurement Request", request.name)
	return {"success": True, "request": request.name, "patient": patient}


@frappe.whitelist(methods=["POST"])
def cancel_queue_request(request: str | None = None) -> dict[str, Any]:
	"""Cancel a waiting queue item while retaining its import/audit record."""
	_require_clinic_user()
	request = request or frappe.form_dict.get("request")
	if not request or not frappe.db.exists("QY Measurement Request", request):
		frappe.throw("Không tìm thấy yêu cầu đo.")
	queue_item = frappe.get_doc("QY Measurement Request", request)
	if queue_item.status != "Chờ đo":
		frappe.throw("Chỉ có thể bỏ khỏi hàng chờ khi lượt đang ở trạng thái Chờ đo.")
	if getdate(queue_item.measurement_date or queue_item.received_at) != getdate():
		frappe.throw("Chỉ có thể bỏ lượt thuộc hàng chờ hôm nay.")
	queue_item.status = "Đã hủy"
	queue_item.save(ignore_permissions=True, ignore_version=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("QY Measurement Request", queue_item.name)
	return {"success": True, "request": queue_item.name}


@frappe.whitelist(methods=["POST"])
def start_queue_measurement(request: str | None = None, station_id: str | None = None) -> dict[str, Any]:
	_require_clinic_user()
	request = request or frappe.form_dict.get("request")
	station_id = station_id or frappe.form_dict.get("station_id") or frappe.conf.get("visiontestai_station_id") or "station-01"
	if not request or not frappe.db.exists("QY Measurement Request", request):
		frappe.throw("Không tìm thấy yêu cầu đo.")
	queue_item = frappe.get_doc("QY Measurement Request", request)
	if queue_item.status != "Chờ đo":
		frappe.throw("Yêu cầu này không còn ở trạng thái Chờ đo.")
	if getdate(queue_item.measurement_date or queue_item.received_at) != getdate():
		frappe.throw("Chỉ có thể bắt đầu lượt thuộc hàng chờ hôm nay.")
	if frappe.db.exists("QY Measurement Request", {"status": "Đang đo"}):
		frappe.throw("Đang có một phiên đo khác. Hãy hoàn tất hoặc dừng phiên đó trước.")
	today = getdate()
	waiting_today = frappe.get_all(
		"QY Measurement Request",
		filters={"status": "Chờ đo", "measurement_date": today},
		fields=["name", "received_at", "measurement_date"],
		order_by="received_at asc, creation asc",
		limit_page_length=500,
	)
	first_waiting = waiting_today[0] if waiting_today else None
	if not first_waiting or first_waiting.name != queue_item.name:
		frappe.throw("Hãy bắt đầu theo thứ tự bệnh nhân trong hàng chờ.")
	from smart_hospital.api.vision import start_measurement
	from smart_hospital.api.send_vision_measurement import send_vision_measurement

	started = start_measurement(patient_id=queue_item.patient, station_id=station_id)
	measurement = started["vision_measurement"]
	result = send_vision_measurement(vision_measurement=measurement)
	queue_item.status = "Đang đo"
	queue_item.vision_measurement = measurement
	queue_item.save(ignore_permissions=True, ignore_version=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("QY Measurement Request", queue_item.name)
	return {"success": True, "request": queue_item.name, "patient": queue_item.patient, "vision_measurement": measurement, "mqtt": result}


@frappe.whitelist(methods=["POST"])
def stop_queue_measurement(request: str | None = None, reason: str | None = None) -> dict[str, Any]:
	_require_clinic_user()
	request = request or frappe.form_dict.get("request")
	if not request or not frappe.db.exists("QY Measurement Request", request):
		frappe.throw("Không tìm thấy yêu cầu đo.")
	queue_item = frappe.get_doc("QY Measurement Request", request)
	if queue_item.status != "Đang đo" or not queue_item.vision_measurement:
		frappe.throw("Yêu cầu này không có phiên đo đang chạy.")
	from smart_hospital.api.send_vision_measurement import cancel_vision_measurement

	mqtt = cancel_vision_measurement(
		vision_measurement=queue_item.vision_measurement,
		reason=reason or "Stopped from QY measurement queue",
	)
	queue_item.status = "Chờ đo"
	queue_item.save(ignore_permissions=True, ignore_version=True)
	frappe.db.commit()
	from qy_vision_hospital.api.clinic_shell import publish_clinic_data_update

	publish_clinic_data_update("QY Measurement Request", queue_item.name)
	return {"success": True, "request": queue_item.name, "vision_measurement": queue_item.vision_measurement, "mqtt": mqtt}


def mark_queue_completed(doc, method=None) -> None:
	"""Mark the QY queue item complete after its Visual Acuity result arrives."""
	measurement = getattr(doc, "vision_measurement", None)
	if not measurement or not frappe.db.exists("QY Measurement Request", {"vision_measurement": measurement, "status": "Đang đo"}):
		return
	name = frappe.db.get_value("QY Measurement Request", {"vision_measurement": measurement, "status": "Đang đo"}, "name")
	frappe.db.set_value("QY Measurement Request", name, "status", "Hoàn tất", update_modified=True)


def source_key_for_file(file_name: str, modified_ns: int, contents: bytes) -> str:
	"""Stable idempotency key for retries of one immutable incoming XML file."""
	digest = hashlib.sha256(contents).hexdigest()
	return hashlib.sha256(f"{file_name}\0{modified_ns}\0{digest}".encode("utf-8")).hexdigest()


@frappe.whitelist(methods=["GET"])
def daily_vision_report(report_date: str | None = None) -> dict[str, Any]:
	"""Return completed QY measurements for VisionAgent's daily PDFs."""
	_require_clinic_user()
	day = getdate(report_date) if report_date else getdate()
	items = frappe.get_all(
		"QY Measurement Request",
		filters={"measurement_date": day, "status": "Hoàn tất"},
		fields=["name", "patient", "his_patient_id", "vision_measurement"],
		order_by="received_at asc, name asc",
		limit_page_length=10000,
	)
	rows = []
	for item in items:
		measurement = item.vision_measurement
		if not measurement:
			continue
		vm = frappe.get_doc("Vision Measurement", measurement)
		acuity = frappe.get_all("Visual Acuity", filters={"vision_measurement": measurement},
			fields=["right_score", "left_score", "both_score", "session_id", "raw_trials_json"], limit_page_length=1)
		patient = frappe.db.get_value("Patient", item.patient, ["patient_name", "sex", "dob"], as_dict=True) or {}
		result = acuity[0] if acuity else {}
		rows.append({
			"request": item.name, "patient_id": item.his_patient_id or item.patient,
			"patient_name": patient.get("patient_name") or item.patient,
			"sex": patient.get("sex") or "", "dob": str(patient.get("dob") or ""),
			"measured_at": str(vm.creation), "right_score": result.get("right_score") or "",
			"left_score": result.get("left_score") or "", "both_score": result.get("both_score") or "",
			"session_id": result.get("session_id") or "", "letters": result.get("raw_trials_json") or "",
			"right_refraction": {key: getattr(vm, f"right_{key}", None) or "" for key in ("sph", "cyl", "axis", "add", "pd", "iop")},
			"left_refraction": {key: getattr(vm, f"left_{key}", None) or "" for key in ("sph", "cyl", "axis", "add", "pd", "iop")},
		})
	return {"success": True, "report_date": str(day), "rows": rows}
