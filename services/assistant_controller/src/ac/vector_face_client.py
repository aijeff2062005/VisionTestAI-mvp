"""Face gallery VectorDB API client (placeholder contract).

Expected HTTP shapes (until real OpenAPI arrives):

  GET  {base}{list_path}?limit=N
       → { "faces": [ FaceRecord, ... ], "next_cursor": null }

  GET  {base}{get_path}
       → FaceRecord

  GET  {base}{image_path}
       → image/jpeg bytes

FaceRecord fields used by sync:
  enroll_id (int, required)
  full_name / name (str)
  patient_id (str, optional)
  image_url | image_b64 | media_get_url (optional JPEG)
  device_template_b64 (optional — native AiFace ``record`` for setuserinfo)
  embedding (list[float], optional — server search only; not pushed to panel)
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from ac.config import FaceVectorDbConfig

logger = logging.getLogger(__name__)


@dataclass
class FaceRecord:
    enroll_id: int
    full_name: str
    patient_id: str | None = None
    image_url: str | None = None
    image_b64: str | None = None
    media_get_url: str | None = None
    device_template_b64: str | None = None
    embedding: list[float] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> FaceRecord:
        eid = data.get("enroll_id", data.get("enrollid", data.get("aiface_enroll_id")))
        if eid is None:
            raise ValueError(f"face record missing enroll_id: {data!r}")
        name = (
            data.get("full_name")
            or data.get("name")
            or data.get("patient_name")
            or f"user-{eid}"
        )
        return cls(
            enroll_id=int(eid),
            full_name=str(name).strip(),
            patient_id=(str(data["patient_id"]) if data.get("patient_id") else None),
            image_url=(str(data["image_url"]) if data.get("image_url") else None),
            image_b64=(str(data["image_b64"]) if data.get("image_b64") else None),
            media_get_url=(
                str(data["media_get_url"])
                if data.get("media_get_url")
                else (str(data["get_url"]) if data.get("get_url") else None)
            ),
            device_template_b64=(
                str(data["device_template_b64"])
                if data.get("device_template_b64")
                else (str(data["aiface_record"]) if data.get("aiface_record") else None)
            ),
            embedding=list(data.get("embedding") or []),
            raw=data,
        )


class VectorFaceClient:
    """Abstract gallery source."""

    enabled: bool = False

    def upsert_face(
        self,
        *,
        enroll_id: int,
        full_name: str,
        patient_id: str | None = None,
        device_template_b64: str | None = None,
        image_b64: str | None = None,
        media_get_url: str | None = None,
    ) -> bool:
        return False

    def list_faces(self, *, limit: int = 500) -> list[FaceRecord]:
        return []

    def get_face(self, enroll_id: int) -> FaceRecord | None:
        return None

    def fetch_image_bytes(self, record: FaceRecord) -> bytes | None:
        return None


class MockVectorFaceClient(VectorFaceClient):
    """In-memory gallery for lab without a real VectorDB."""

    enabled = True

    def __init__(self, records: list[FaceRecord] | None = None) -> None:
        # Tiny 1x1 JPEG so sync path exercises image push without a CDN.
        tiny_jpeg = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
            "CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGfAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bf//Z"
        )
        self._records = records or [
            FaceRecord(
                enroll_id=10001,
                full_name="Demo Patient A",
                patient_id="P-10001",
                image_b64=base64.b64encode(tiny_jpeg).decode("ascii"),
            ),
            FaceRecord(
                enroll_id=10002,
                full_name="Demo Patient B",
                patient_id="P-10002",
                image_b64=base64.b64encode(tiny_jpeg).decode("ascii"),
            ),
        ]

    def list_faces(self, *, limit: int = 500) -> list[FaceRecord]:
        return self._records[: max(0, limit)]

    def get_face(self, enroll_id: int) -> FaceRecord | None:
        for r in self._records:
            if r.enroll_id == int(enroll_id):
                return r
        return None

    def fetch_image_bytes(self, record: FaceRecord) -> bytes | None:
        if record.image_b64:
            try:
                return base64.b64decode(record.image_b64)
            except Exception:  # noqa: BLE001
                return None
        return None

    def upsert_face(
        self,
        *,
        enroll_id: int,
        full_name: str,
        patient_id: str | None = None,
        device_template_b64: str | None = None,
        image_b64: str | None = None,
        media_get_url: str | None = None,
    ) -> bool:
        # Replace or append in mock gallery
        self._records = [r for r in self._records if r.enroll_id != int(enroll_id)]
        self._records.append(
            FaceRecord(
                enroll_id=int(enroll_id),
                full_name=full_name,
                patient_id=patient_id,
                device_template_b64=device_template_b64,
                image_b64=image_b64,
                media_get_url=media_get_url,
            )
        )
        return True


class HttpVectorFaceClient(VectorFaceClient):
    enabled = True

    def __init__(self, cfg: FaceVectorDbConfig) -> None:
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self.timeout = cfg.timeout_seconds

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.cfg.api_key:
            h[self.cfg.api_key_header] = self.cfg.api_key
        return h

    def list_faces(self, *, limit: int = 500) -> list[FaceRecord]:
        url = f"{self.base_url}{self.cfg.list_path}"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(url, params={"limit": limit}, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        rows = data.get("faces") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise RuntimeError(f"Unexpected VectorDB list payload: {data!r}")
        out: list[FaceRecord] = []
        for row in rows:
            if isinstance(row, dict):
                try:
                    out.append(FaceRecord.from_api(row))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skip bad face row: %s (%s)", row, exc)
        return out[:limit]

    def get_face(self, enroll_id: int) -> FaceRecord | None:
        path = self.cfg.get_path.format(enroll_id=int(enroll_id))
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(url, headers=self._headers())
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
        if isinstance(data, dict) and "face" in data and isinstance(data["face"], dict):
            data = data["face"]
        if not isinstance(data, dict):
            return None
        return FaceRecord.from_api(data)

    def fetch_image_bytes(self, record: FaceRecord) -> bytes | None:
        if record.image_b64:
            try:
                raw = base64.b64decode(record.image_b64)
                if raw[:2] == b"\xff\xd8":
                    return raw
            except Exception:  # noqa: BLE001
                pass
        # Absolute media URL first
        media_url = record.media_get_url
        if media_url and media_url.startswith("http"):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.get(media_url)
                    r.raise_for_status()
                    if r.content[:2] == b"\xff\xd8":
                        return r.content
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fetch media_get_url failed %s: %s", media_url, exc)
        # Relative or absolute VectorDB image_url
        image_url = record.image_url
        if image_url:
            url = (
                image_url
                if image_url.startswith("http")
                else f"{self.base_url}{image_url}"
            )
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.get(url, headers=self._headers())
                    r.raise_for_status()
                    if r.content[:2] == b"\xff\xd8":
                        return r.content
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fetch image_url failed %s: %s", url, exc)
        path = self.cfg.image_path.format(enroll_id=record.enroll_id)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(f"{self.base_url}{path}", headers=self._headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                if r.content[:2] == b"\xff\xd8":
                    return r.content
        except Exception as exc:  # noqa: BLE001
            logger.debug("VectorDB image endpoint failed enroll=%s: %s", record.enroll_id, exc)
            return None
        return None

    def upsert_face(
        self,
        *,
        enroll_id: int,
        full_name: str,
        patient_id: str | None = None,
        device_template_b64: str | None = None,
        image_b64: str | None = None,
        media_get_url: str | None = None,
    ) -> bool:
        url = f"{self.base_url}/v1/faces"
        body: dict[str, Any] = {
            "enroll_id": int(enroll_id),
            "full_name": str(full_name).strip() or f"user-{enroll_id}",
        }
        if patient_id:
            body["patient_id"] = str(patient_id)
        if device_template_b64:
            body["device_template_b64"] = device_template_b64
        if image_b64:
            body["image_b64"] = image_b64
        if media_get_url:
            body["media_get_url"] = media_get_url
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=body, headers=self._headers())
            r.raise_for_status()
            data = r.json() if r.content else {}
        ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
        logger.info(
            "VectorDB upsert enroll_id=%s name=%s media=%s ok=%s",
            enroll_id,
            full_name,
            bool(media_get_url),
            ok,
        )
        return ok


def build_vector_face_client(cfg: FaceVectorDbConfig) -> VectorFaceClient:
    if not cfg.enabled:
        return VectorFaceClient()
    mode = (cfg.mode or "off").strip().lower()
    if mode in ("off", "none", "disabled"):
        return VectorFaceClient()
    if mode == "mock":
        logger.info("Face VectorDB: using mock gallery")
        return MockVectorFaceClient()
    if mode in ("http", "api", "live"):
        logger.info("Face VectorDB: HTTP %s", cfg.base_url)
        return HttpVectorFaceClient(cfg)
    logger.warning("Unknown face_vectordb.mode=%r — disabled", cfg.mode)
    return VectorFaceClient()
