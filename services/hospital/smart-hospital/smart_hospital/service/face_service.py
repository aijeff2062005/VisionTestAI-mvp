from __future__ import annotations

import json
import mimetypes
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import frappe
import requests
from frappe.utils import add_to_date, now_datetime


SETTINGS_DOCTYPE = "Connection Settings"
DEFAULT_TIMEOUT_SECONDS = (30, 180)


class FaceServiceError(Exception):
	pass


class FaceServiceHTTPError(FaceServiceError):
	def __init__(self, status_code: int, response_body: Any):
		self.status_code = int(status_code)
		self.response_body = response_body
		super().__init__(f"Face Service HTTP {self.status_code}")


def get_token() -> Any:
	"""Fetch a new access token and save it to Connection Settings."""

	return _refresh_access_token()


def register_without_mask(
	username: str,
	full_name: str,
	video_file: Any,
	project_id: str | None = None,
) -> Any:
	"""Call POST /face_registration/without_mask.

	Required input:
	- username
	- full_name
	- video_file
	- project_id, optional override. Defaults to Connection Settings.project_id.
	"""

	data = {
		"username": username,
		"project_id": _get_project_id(project_id),
		"full_name": full_name,
	}
	with _video_file_tuple(video_file) as file_tuple:
		return _request(
			"POST",
			"/api/v2/face_registration/without_mask",
			data=data,
			files={"video": file_tuple},
			auth=True,
			timeout=(30, 180),
		)


def get_registration_status(registration_id: str) -> Any:
	"""Call GET /face_registration/<registration_id>."""

	if not registration_id:
		raise FaceServiceError("registration_id is required.")

	return _request(
		"GET",
		f"/face_registration/{registration_id}",
		auth=True,
	)


def verify_face(
	username: str,
	video_file: Any,
	project_id: str | None = None,
) -> Any:
	"""Call POST /face_verification/.

	Required input:
	- username
	- video_file
	- project_id, optional override. Defaults to Connection Settings.project_id.
	"""

	data = {
		"username": username,
		"project_id": _get_project_id(project_id),
	}
	with _video_file_tuple(video_file) as file_tuple:
		return _request(
			"POST",
			"/api/v3/face_verification/",
			data=data,
			files={"file": file_tuple},
			auth=True,
			timeout=(60, 600),
		)


def _request(
	method: str,
	path: str,
	data: dict[str, Any] | None = None,
	json_data: dict[str, Any] | None = None,
	files: dict[str, Any] | None = None,
	auth: bool = False,
	retry_on_401: bool = True,
	timeout: int | tuple[int, int] | None = None,
) -> Any:
	url = _build_url(path)
	headers = _headers(auth=auth)

	response = _send_request(
		method=method,
		url=url,
		headers=headers,
		data=data,
		json_data=json_data,
		files=files,
		timeout=timeout,
	)

	if auth and response.status_code == 401 and retry_on_401:
		_refresh_access_token()
		_rewind_files(files)
		response = _send_request(
			method=method,
			url=url,
			headers=_headers(auth=True),
			data=data,
			json_data=json_data,
			files=files,
			timeout=timeout,
		)

	if not _is_success_status(response.status_code):
		response_body = _response_body(response)
		_log_non_success_response(method, url, response, response_body)
		raise FaceServiceHTTPError(response.status_code, response_body)

	return _response_body(response)


def _send_request(
	method: str,
	url: str,
	headers: dict[str, str],
	data: dict[str, Any] | None = None,
	json_data: dict[str, Any] | None = None,
	files: dict[str, Any] | None = None,
	timeout: int | tuple[int, int] | None = None,
) -> requests.Response:
	try:
		return requests.request(
			method=method,
			url=url,
			headers=headers,
			data=data,
			json=json_data,
			files=files,
			timeout=timeout or _timeout_seconds(),
		)
	except requests.RequestException as exc:
		_log_face_service_error(
			"Face Service Request Error",
			{
				"method": method,
				"url": url,
				"error": str(exc),
			},
		)
		raise FaceServiceError(f"Face service request failed: {exc}")

def _refresh_access_token() -> Any:
	client_id = _get_config_value("client_id", "FACE_SERVICE_CLIENT_ID")
	client_secret = _get_client_secret()
	if not client_id or not client_secret:
		raise FaceServiceError("client_id and client_secret are required for Face Service token.")
	url = _build_url("/user/get_token")
	response = _send_request(
		method="POST",
		url=url,
		headers={
			"accept": "application/json",
			"Content-Type": "application/json",
		},
		json_data={
			"client_id": client_id,
			"client_secret": client_secret,
		},
	)

	if not _is_success_status(response.status_code):
		_log_non_success_response("POST", url, response)
		return _response_body(response)

	body = _response_body(response)
	if isinstance(body, dict) and body.get("access_token"):
		_save_access_token(body["access_token"], body.get("expires_in"))
	else:
		_log_face_service_error(
			"Face Service Token Missing",
			{
				"url": url,
				"response": body,
			},
		)

	return body


def _headers(auth: bool = False) -> dict[str, str]:
	headers = {
		"accept": "application/json",
	}
	if auth:
		access_token = _get_access_token()
		if not access_token:
			token_response = _refresh_access_token()
			access_token = token_response.get("access_token") if isinstance(token_response, dict) else None
		if not access_token:
			raise FaceServiceError("Face Service access_token is missing.")
		headers["Authorization"] = f"Bearer {access_token}"
	return headers


def _get_access_token() -> str | None:
	return _get_config_value("access_token", "FACE_SERVICE_ACCESS_TOKEN")


def _get_project_id(project_id: str | None = None) -> str:
	if project_id not in (None, ""):
		return str(project_id)

	settings_project_id = _get_config_value("project_id", "FACE_SERVICE_PROJECT_ID")
	if settings_project_id in (None, ""):
		raise FaceServiceError("project_id is required in Connection Settings.")
	return str(settings_project_id)


def _get_client_secret() -> str | None:
	try:
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		secret = settings.get_password("client_secret")
		if secret:
			return secret
	except Exception:
		pass

	return _get_config_value("client_secret", "FACE_SERVICE_CLIENT_SECRET")


def _save_access_token(access_token: str, expires_in: Any | None = None):
	frappe.db.set_single_value(SETTINGS_DOCTYPE, "access_token", access_token)

	if expires_in not in (None, ""):
		try:
			expires_at = add_to_date(now_datetime(), seconds=int(float(expires_in)))
			frappe.db.set_single_value(SETTINGS_DOCTYPE, "access_time", expires_at)
		except (TypeError, ValueError):
			_log_face_service_error(
				"Face Service Token Expire Parse Error",
				{
					"expires_in": expires_in,
				},
			)


def _build_url(path: str) -> str:
	base_url = _get_config_value("face_service_url", "FACE_SERVICE_URL")
	if not base_url:
		raise FaceServiceError("face_service_url is required in Connection Settings.")

	return f"{str(base_url).rstrip('/')}/{path.lstrip('/')}"


def _timeout_seconds() -> tuple[int, int]:
	value = _get_config_value("face_service_timeout_seconds", "FACE_SERVICE_TIMEOUT_SECONDS")
	if value in (None, ""):
		return DEFAULT_TIMEOUT_SECONDS
	try:
		return (30, int(float(value)))
	except (TypeError, ValueError):
		return DEFAULT_TIMEOUT_SECONDS


def _get_config_value(fieldname: str, env_name: str | None = None) -> Any:
	try:
		meta = frappe.get_meta(SETTINGS_DOCTYPE)
		if meta.has_field(fieldname):
			value = frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
			if value not in (None, ""):
				return value
	except Exception:
		pass

	conf_value = frappe.conf.get(fieldname) if getattr(frappe, "conf", None) else None
	if conf_value not in (None, ""):
		return conf_value

	if env_name:
		env_value = os.environ.get(env_name)
		if env_value not in (None, ""):
			return env_value

	return None


@contextmanager
def _video_file_tuple(video_file: Any):
	if not video_file:
		raise FaceServiceError("video_file is required.")

	if isinstance(video_file, (str, Path)):
		path = Path(video_file).resolve()
		if not path.exists():
			raise FaceServiceError(f"video_file does not exist: {path}")
		content = path.read_bytes()
		if not content:
			raise FaceServiceError(f"video_file is empty: {path}")
		content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
		yield (path.name, content, content_type)
		return

	if isinstance(video_file, (bytes, bytearray)):
		content = bytes(video_file)
		if not content:
			raise FaceServiceError("video_file is empty.")
		yield ("video.mp4", content, "video/mp4")
		return

	stream = getattr(video_file, "stream", None) or video_file
	if not hasattr(stream, "read"):
		raise FaceServiceError("video_file must be a readable file, bytes, or file path.")
	if hasattr(stream, "seek"):
		stream.seek(0)

	content = stream.read()
	if isinstance(content, str):
		content = content.encode("utf-8")
	if not content:
		raise FaceServiceError("video_file is empty.")

	filename = _get_file_name(video_file)
	content_type = _get_content_type(video_file, filename)
	yield (filename, content, content_type)


def _get_file_name(file_obj: Any) -> str:
	filename = getattr(file_obj, "filename", None) or getattr(file_obj, "name", None)
	return str(filename).strip() if filename else "video.mp4"


def _get_content_type(file_obj: Any, filename: str) -> str:
	content_type = getattr(file_obj, "content_type", None) or getattr(file_obj, "mimetype", None)
	if content_type:
		return str(content_type)
	return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _rewind_files(files: dict[str, Any] | None):
	if not files:
		return

	for file_value in files.values():
		stream = file_value[1] if isinstance(file_value, tuple) and len(file_value) > 1 else file_value
		if hasattr(stream, "seek"):
			try:
				stream.seek(0)
			except Exception:
				pass


def _response_body(response: requests.Response) -> Any:
	try:
		return response.json()
	except ValueError:
		return response.text


def _is_success_status(status_code: int) -> bool:
	return 200 <= int(status_code) < 300


def _log_non_success_response(
	method: str,
	url: str,
	response: requests.Response,
	response_body: Any | None = None,
):
	_log_face_service_error(
		f"Face Service HTTP {response.status_code}",
		{
			"method": method,
			"url": url,
			"status_code": response.status_code,
			"response": _response_body(response) if response_body is None else response_body,
		},
	)


def _log_face_service_error(title: str, payload: dict[str, Any]):
	frappe.log_error(
		title=title,
		message=json.dumps(payload, ensure_ascii=False, default=str, indent=2),
	)
