"""Upload patient audio/images to Mac media gateway (not Hospital API)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MediaClient:
    """HTTP PUT to media gateway; MQTT grant/ready is optional side-channel."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "dev-media-token",
        timeout_seconds: float = 30.0,
        station_id: str = "station-01",
        enabled: bool = True,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.timeout = timeout_seconds
        self.station_id = station_id
        self.enabled = enabled and bool(self.base_url)

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        h = {"X-Media-Token": self.token}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def request_grant(
        self,
        *,
        session_id: str,
        kind: str,
        content_type: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        body = {
            "station_id": self.station_id,
            "session_id": session_id,
            "kind": kind,
            "content_type": content_type,
            "filename": filename,
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/v1/grants",
                json=body,
                headers=self._headers("application/json"),
            )
            r.raise_for_status()
            return r.json()

    def upload_bytes(
        self,
        data: bytes,
        *,
        session_id: str,
        kind: str,
        content_type: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Grant → PUT → ready dict (object_key, get_url, sha256, …)."""
        if not self.enabled:
            logger.info("Media client disabled — skip upload kind=%s", kind)
            return {"skipped": True, "kind": kind}
        grant = self.request_grant(
            session_id=session_id,
            kind=kind,
            content_type=content_type,
            filename=filename,
        )
        put_url = grant.get("put_url")
        if not put_url:
            raise RuntimeError(f"media grant missing put_url: {grant}")
        with httpx.Client(timeout=self.timeout) as client:
            r = client.put(put_url, content=data, headers=self._headers(content_type))
            r.raise_for_status()
            ready = r.json()
        logger.info(
            "Media uploaded kind=%s key=%s size=%s",
            kind,
            ready.get("object_key"),
            ready.get("size"),
        )
        return ready if isinstance(ready, dict) else {"raw": ready}

    def upload_file(
        self,
        path: str,
        *,
        session_id: str,
        kind: str,
        content_type: str,
    ) -> dict[str, Any]:
        from pathlib import Path

        p = Path(path)
        return self.upload_bytes(
            p.read_bytes(),
            session_id=session_id,
            kind=kind,
            content_type=content_type,
            filename=p.name,
        )

    def download_bytes(self, get_url: str) -> bytes:
        """GET an object (absolute or path) with media token."""
        url = (get_url or "").strip()
        if not url:
            raise ValueError("empty get_url")
        if url.startswith("/"):
            url = f"{self.base_url}{url}"
        else:
            url = self._rewrite_docker_media_host(url)
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(url, headers=self._headers())
            r.raise_for_status()
            return r.content

    def _rewrite_docker_media_host(self, url: str) -> str:
        """Frappe stores http://media:9010/... which only works inside Docker."""
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host not in ("media", "face_vectordb", "qr_decode") or not self.base_url:
            return url
        base = urlparse(self.base_url)
        if not base.netloc:
            return url
        rewritten = urlunparse(
            (
                base.scheme or parsed.scheme,
                base.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
        logger.info("rewrote media URL %s → %s", parsed.netloc, base.netloc)
        return rewritten


def mqtt_request_payload(
    *,
    session_id: str,
    kind: str,
    content_type: str,
    filename: str | None = None,
) -> str:
    """JSON for `qlbn/media/{station}/object/request` (AC → media gateway)."""
    return json.dumps(
        {
            "schema_version": "0.1.0",
            "ts": time.time(),
            "session_id": session_id,
            "kind": kind,
            "content_type": content_type,
            "filename": filename,
        },
        ensure_ascii=False,
    )
