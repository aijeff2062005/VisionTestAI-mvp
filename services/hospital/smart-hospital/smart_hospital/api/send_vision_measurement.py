import json

import frappe
import requests

try:
	import paho.mqtt.publish as mqtt_publish
except ImportError:  # pragma: no cover
	mqtt_publish = None


def _mqtt_settings() -> tuple[str, int, str, str | None, str | None, bool, str | None]:
	"""Broker endpoint, station credentials, and optional TLS settings."""
	host = frappe.conf.get("visiontestai_mqtt_host") or "mqtt"
	port = int(frappe.conf.get("visiontestai_mqtt_port") or 1883)
	station = frappe.conf.get("visiontestai_station_id") or "station-01"
	user = frappe.conf.get("visiontestai_mqtt_user") or frappe.conf.get("visiontestai_mqtt_username")
	password = frappe.conf.get("visiontestai_mqtt_password")
	tls = str(frappe.conf.get("visiontestai_mqtt_tls") or "").strip().lower() in (
		"1", "true", "yes", "on"
	)
	ca_certs = frappe.conf.get("visiontestai_mqtt_tls_ca_certs") or None
	return (
		str(host),
		port,
		str(station),
		(str(user) if user else None),
		(str(password) if password else None),
		tls,
		(str(ca_certs) if ca_certs else None),
	)


def _mqtt_tls_options(enabled: bool, ca_certs: str | None) -> dict | None:
	"""Paho publish.single TLS options; system CA roots are used by default."""
	if not enabled:
		return None
	options = {"ca_certs": ca_certs} if ca_certs else {}
	return options


@frappe.whitelist(allow_guest=True, methods=["POST"])
def send_vision_measurement(vision_measurement=None):
	"""Start exam on station via MQTT (lab path). Optional HTTP only if configured."""
	if vision_measurement is None:
		vision_measurement = frappe.form_dict.get("vision_measurement")

	if not vision_measurement:
		frappe.throw("Chưa xác định lần đo")

	if not frappe.db.exists("Vision Measurement", vision_measurement):
		frappe.throw(f"Không tìm thấy Vision Measurement: {vision_measurement}")

	measurement = frappe.get_doc("Vision Measurement", vision_measurement)
	patient_id = measurement.patient
	patient = frappe.get_doc("Patient", patient_id)
	host, port, station_id, mqtt_user, mqtt_pass, mqtt_tls, mqtt_ca_certs = _mqtt_settings()
	site = frappe.utils.get_url()
	callback_url = f"{site}/api/method/smart_hospital.api.vision.receive_results"

	payload = {
		"schema_version": "0.1.0",
		"session_id": measurement.name,
		"patient_id": patient_id,
		"patient_name": patient.patient_name or patient.first_name or patient_id,
		"dob": str(patient.dob) if patient.dob else None,
		"sex": patient.sex or None,
		"exam_type": "distance_acuity_5m",
		"eyes": "both",
		"callback_url": callback_url,
		"correlation_id": measurement.name,
		# Desk starts the regular station flow, which includes face recognition.
		"auto_enter_test": False,
	}
	topic = f"qlbn/station/{station_id}/session/start"

	if mqtt_publish is None:
		frappe.throw(
			"paho-mqtt is not installed in the Frappe image — rebuild visiontestai/frappe:clinic"
		)

	try:
		auth = None
		if mqtt_user:
			auth = {"username": mqtt_user, "password": mqtt_pass or ""}
		mqtt_publish.single(
			topic,
			payload=json.dumps(payload),
			hostname=host,
			port=port,
			auth=auth,
			qos=1,
			tls=_mqtt_tls_options(mqtt_tls, mqtt_ca_certs),
		)
		return {
			"success": True,
			"transport": "mqtt",
			"topic": topic,
			"mqtt_host": host,
			"mqtt_port": port,
			"vision_measurement": measurement.name,
			"callback_url": callback_url,
		}
	except Exception as exc:  # noqa: BLE001
		frappe.log_error(title="MQTT session/start failed", message=str(exc))
		# Explicit HTTP override only (never default to dead 127.0.0.1:5000)
		ai_url = (frappe.conf.get("visiontestai_station_http") or "").strip()
		if not ai_url:
			frappe.throw(
				f"MQTT publish to {host}:{port} topic {topic} failed: {exc}. "
				"Check mqtt container / credentials, or set visiontestai_station_http."
			)

	response = requests.post(
		ai_url,
		json={"vision_measurement": measurement.name, **payload},
		timeout=10,
	)
	response.raise_for_status()
	return {
		"success": True,
		"transport": "http_fallback",
		"message": "Đã gửi mã số lần đo thị lực",
		"vision_measurement": measurement.name,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def cancel_vision_measurement(vision_measurement=None, reason=None, station_id=None):
	"""Abort an in-progress exam on the station via MQTT session/cancel."""
	if vision_measurement is None:
		vision_measurement = frappe.form_dict.get("vision_measurement")
	if reason is None:
		reason = frappe.form_dict.get("reason")
	if station_id is None:
		station_id = frappe.form_dict.get("station_id")

	if not vision_measurement:
		frappe.throw("Chưa xác định lần đo (vision_measurement)")

	host, port, default_station, mqtt_user, mqtt_pass, mqtt_tls, mqtt_ca_certs = _mqtt_settings()
	station_id = str(station_id or default_station)
	reason_text = (str(reason).strip() if reason else "") or "Cancelled from Nurse Station"

	payload = {
		"schema_version": "0.1.0",
		"session_id": str(vision_measurement),
		"reason": reason_text,
		"correlation_id": str(vision_measurement),
	}
	topic = f"qlbn/station/{station_id}/session/cancel"

	if mqtt_publish is None:
		frappe.throw(
			"paho-mqtt is not installed in the Frappe image — rebuild visiontestai/frappe:clinic"
		)

	try:
		auth = None
		if mqtt_user:
			auth = {"username": mqtt_user, "password": mqtt_pass or ""}
		mqtt_publish.single(
			topic,
			payload=json.dumps(payload),
			hostname=host,
			port=port,
			auth=auth,
			qos=1,
			tls=_mqtt_tls_options(mqtt_tls, mqtt_ca_certs),
		)
		return {
			"success": True,
			"transport": "mqtt",
			"topic": topic,
			"mqtt_host": host,
			"mqtt_port": port,
			"vision_measurement": str(vision_measurement),
			"station_id": station_id,
			"reason": reason_text,
		}
	except Exception as exc:  # noqa: BLE001
		frappe.log_error(title="MQTT session/cancel failed", message=str(exc))
		frappe.throw(
			f"MQTT publish to {host}:{port} topic {topic} failed: {exc}. "
			"Check mqtt container / credentials."
		)
