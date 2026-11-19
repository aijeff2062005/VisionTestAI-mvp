"""HTTP client for Mac hospital API (Frappe-compatible routes)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HospitalClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.api_key = api_key
        self.api_secret = api_secret

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            h["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        return h

    def lookup_by_enroll_id(self, enroll_id: int) -> dict[str, Any]:
        urls = [
            f"{self.base_url}/api/face/lookup",
            f"{self.base_url}/api/method/smart_hospital.api.face_identity.lookup_by_enroll_id",
        ]
        last_err: Exception | None = None
        for url in urls:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.get(
                        url,
                        params={"enroll_id": enroll_id},
                        headers=self._headers(),
                    )
                    r.raise_for_status()
                    data = r.json()
                    # Frappe wraps in message
                    if isinstance(data, dict) and "message" in data:
                        data = data["message"]
                    return data if isinstance(data, dict) else {"found": False}
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.debug("lookup failed %s: %s", url, exc)
        logger.warning("Hospital lookup failed: %s", last_err)
        return {"found": False, "error": str(last_err) if last_err else "unreachable"}

    def register_face_patient(
        self,
        *,
        enroll_id: int,
        full_name: str,
        uid: str | None = None,
        mobile: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "enroll_id": enroll_id,
            "full_name": full_name,
            "uid": uid,
            "mobile": mobile,
        }
        urls = [
            f"{self.base_url}/api/face/register",
            f"{self.base_url}/api/method/smart_hospital.api.face_identity.register_face_patient",
        ]
        last_err: Exception | None = None
        for url in urls:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, json=body, headers=self._headers())
                    r.raise_for_status()
                    data = r.json()
                    if isinstance(data, dict) and "message" in data:
                        data = data["message"]
                    return data if isinstance(data, dict) else {"success": False}
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.debug("register failed %s: %s", url, exc)
        raise RuntimeError(f"Hospital register failed: {last_err}")

    def start_measurement(self, patient_id: str, station_id: str) -> dict[str, Any]:
        body = {"patient_id": patient_id, "station_id": station_id}
        urls = [
            f"{self.base_url}/api/vision/start",
            f"{self.base_url}/api/method/smart_hospital.api.vision.start_measurement",
        ]
        for url in urls:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, json=body, headers=self._headers())
                    r.raise_for_status()
                    data = r.json()
                    if isinstance(data, dict) and "message" in data:
                        data = data["message"]
                    return data if isinstance(data, dict) else {}
            except Exception as exc:  # noqa: BLE001
                logger.debug("start_measurement failed %s: %s", url, exc)
        return {}

    def results_callback_url(self) -> str:
        """Prefer Frappe method path; lean hospital_api also aliases this route."""
        return (
            f"{self.base_url}/api/method/smart_hospital.api.vision.receive_results"
        )

    def list_today_face_gallery(
        self, appointment_type: str | None = None, *, light: bool = False
    ) -> dict[str, Any]:
        """Faces for patients with appointments today (desk-enrolled avatars)."""
        params: dict[str, Any] = {}
        if appointment_type:
            params["appointment_type"] = appointment_type
        if light:
            params["light"] = 1
        url = (
            f"{self.base_url}/api/method/"
            "smart_hospital.api.clinic_desk.list_today_face_gallery"
        )
        last_err: Exception | None = None
        try:
            with httpx.Client(timeout=self.timeout if light else max(self.timeout, 30.0)) as client:
                r = client.get(url, params=params or None, headers=self._headers())
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and "message" in data:
                    data = data["message"]
                return data if isinstance(data, dict) else {"success": False, "faces": []}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("list_today_face_gallery failed: %s", exc)
        return {
            "success": False,
            "faces": [],
            "error": str(last_err) if last_err else "unreachable",
        }

    def check_in_today_appointment(
        self, *, patient_id: str | None = None, appointment: str | None = None
    ) -> dict[str, Any]:
        """Mark today's Patient Appointment as Checked In after face identify."""
        body = {"patient": patient_id, "appointment": appointment}
        url = (
            f"{self.base_url}/api/method/"
            "smart_hospital.api.clinic_desk.check_in_today_appointment"
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=body, headers=self._headers())
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and "message" in data:
                    data = data["message"]
                return data if isinstance(data, dict) else {"success": False}
        except Exception as exc:  # noqa: BLE001
            logger.warning("check_in_today_appointment failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def apply_cccd_scan(
        self,
        *,
        enroll_id: int | None = None,
        patient_id: str | None = None,
        media_url: str | None = None,
        object_key: str | None = None,
        raw_payload: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "enroll_id": enroll_id,
            "patient": patient_id,
            "media_url": media_url,
            "object_key": object_key,
            "raw_payload": raw_payload,
        }
        url = (
            f"{self.base_url}/api/method/"
            "smart_hospital.api.clinic_desk.apply_cccd_scan"
        )
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=body, headers=self._headers())
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "message" in data:
                data = data["message"]
            return data if isinstance(data, dict) else {"success": False}
