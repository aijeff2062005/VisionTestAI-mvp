"""Capture Face ID display JPEG → media (cccd_qr) → Frappe apply_cccd_scan."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CccdQrPipeline:
    def __init__(
        self,
        *,
        face_client: Any,
        media_client: Any,
        hospital_base_url: str,
        hospital_headers: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
        enabled: bool = True,
    ) -> None:
        self.face = face_client
        self.media = media_client
        self.hospital_base_url = (hospital_base_url or "").rstrip("/")
        self.hospital_headers = hospital_headers or {"Content-Type": "application/json"}
        self.timeout = timeout_seconds
        self.enabled = enabled

    def capture_jpeg(self, enroll_id: int) -> bytes | None:
        """Pull display JPEG for enroll_id from AiFace panel."""
        eid = int(enroll_id)
        if hasattr(self.face, "export_gallery_face"):
            try:
                exported = self.face.export_gallery_face(eid)
            except Exception:  # noqa: BLE001
                logger.exception("export_gallery_face failed enroll_id=%s", eid)
                exported = None
            if isinstance(exported, dict):
                b64 = exported.get("image_b64")
                if b64:
                    try:
                        raw = base64.b64decode(b64)
                        if raw[:2] == b"\xff\xd8":
                            return raw
                    except Exception:  # noqa: BLE001
                        logger.debug("image_b64 decode failed", exc_info=True)

        # Fallback: getuserlist photourl
        if hasattr(self.face, "_api") and hasattr(self.face, "fetch_photo"):
            try:
                ulist = self.face._api({"cmd": "getuserlist", "stn": True})
                for row in ulist.get("record") or []:
                    if int(row.get("id") or -1) != eid:
                        continue
                    photo = str(row.get("photourl") or "").strip()
                    if photo:
                        jpeg = self.face.fetch_photo(photo)
                        if jpeg and jpeg[:2] == b"\xff\xd8":
                            return jpeg
            except Exception:  # noqa: BLE001
                logger.exception("photourl fallback failed enroll_id=%s", eid)
        return None

    def run(
        self,
        *,
        enroll_id: int,
        patient_id: str | None = None,
        session_id: str = "cccd",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"skipped": True, "reason": "disabled"}
        jpeg = self.capture_jpeg(enroll_id)
        if not jpeg:
            return {"success": False, "error": "no_jpeg", "enroll_id": enroll_id}

        ready: dict[str, Any] = {}
        if self.media and getattr(self.media, "enabled", True):
            try:
                ready = self.media.upload_bytes(
                    jpeg,
                    session_id=session_id or f"enroll-{enroll_id}",
                    kind="cccd_qr",
                    content_type="image/jpeg",
                    filename=f"cccd_{enroll_id}.jpg",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("media upload cccd_qr failed")
                return {"success": False, "error": f"media_upload: {exc}", "enroll_id": enroll_id}
        else:
            return {"success": False, "error": "media_disabled", "enroll_id": enroll_id}

        get_url = ready.get("get_url")
        object_key = ready.get("object_key")
        body = {
            "enroll_id": enroll_id,
            "patient": patient_id,
            "media_url": get_url,
            "object_key": object_key,
        }
        url = (
            f"{self.hospital_base_url}/api/method/"
            "smart_hospital.api.clinic_desk.apply_cccd_scan"
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=body, headers=self.hospital_headers)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and "message" in data:
                    data = data["message"]
                if isinstance(data, dict):
                    data["media"] = ready
                    return data
                return {"success": True, "raw": data, "media": ready}
        except Exception as exc:  # noqa: BLE001
            logger.exception("apply_cccd_scan failed")
            return {
                "success": False,
                "error": str(exc),
                "media": ready,
                "enroll_id": enroll_id,
            }
