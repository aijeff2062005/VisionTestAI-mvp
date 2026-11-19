"""AiFace closed-device client — identify patient from on-device face DB."""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

# Device marks unknown faces with this enroll id.
STRANGER_ENROLL_ID = 99999999


def _ipv4_to_u32(ip: str) -> int:
    parts = [int(x) for x in ip.split(".")]
    if len(parts) != 4:
        raise ValueError(ip)
    return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) & 0xFFFFFFFF


def _u32_to_ipv4(n: int) -> str:
    n = int(n) & 0xFFFFFFFF
    return f"{(n >> 24) & 255}.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def _guess_lan_ip(peer_host: str) -> str | None:
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((peer_host, 80))
        ip = sock.getsockname()[0]
        sock.close()
        return str(ip)
    except Exception:  # noqa: BLE001
        return None


@dataclass
class FaceMatchResult:
    matched: bool
    patient_id: str | None = None
    name: str | None = None
    score: float | None = None
    enroll_id: int | None = None
    status: Literal["matched", "stranger", "timeout", "error", "deferred"] = "deferred"
    message: str = "face deferred"
    event_time: str | None = None
    photo_url: str | None = None
    image_b64: str | None = None


class FaceClient:
    """No-op stub (tests / face disabled)."""

    enabled: bool = False

    def wait_for_identify(
        self,
        *,
        timeout_seconds: float = 120.0,
        stop_flag: Any = None,
        on_stranger: Any = None,
        on_tick: Any = None,
        expect_enroll_id: int | None = None,
        ignore_stranger: bool = False,
        accept_existing_recent: bool = False,
        sync_clock: bool = True,
        max_age_seconds: float | None = None,
        skip_keys: Any = None,
        min_event_epoch: float | None = None,
    ) -> FaceMatchResult:
        return FaceMatchResult(
            matched=False,
            status="deferred",
            message="Face gate deferred; connect closed-device API later",
        )

    def match(self, face_image_ref: str | None = None) -> FaceMatchResult:
        return self.wait_for_identify(timeout_seconds=0.1)

    def push_enroll(self, patient_id: str, image_ref: str) -> bool:
        return False

    def upsert_gallery_user(
        self,
        *,
        enroll_id: int,
        full_name: str,
        device_template_b64: str | None = None,
        photo_bytes: bytes | None = None,
        backupnum: int = 50,
        replace_existing: bool = True,
    ) -> bool:
        return False

    def export_gallery_face(self, enroll_id: int) -> dict[str, Any] | None:
        """Export on-device face template/photo for VectorDB upload."""
        return None

    def enroll_user(
        self,
        full_name: str,
        *,
        photo_url: str | None = None,
        photo_bytes: bytes | None = None,
        image_b64: str | None = None,
        enroll_id: int | None = None,
        verify_timeout_seconds: float = 0.0,
        stop_flag: Any = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        return {"success": False, "error": "face gate disabled"}

    def ensure_bs_server(self, host: str | None = None, port: int = 7788) -> None:
        return None


class AiFaceClient(FaceClient):
    """HTTP client for AiFace / AI Biometric panel (POST /api JSON cmds)."""

    enabled = True

    def __init__(
        self,
        host: str = "192.168.1.18",
        password: str = "12345678",
        *,
        port: int = 80,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 8.0,
        accept_recent_seconds: float = 15.0,
        relax_reverify: bool = True,
        live_events_url: str = "http://127.0.0.1:7790/events",
        callback_host: str = "",
        callback_port: int = 7788,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.base_url = f"http://{host}:{port}".rstrip("/")
        self.password = password
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        # Max age for a new log row after baseline (does not replay old scans).
        self.accept_recent_seconds = accept_recent_seconds
        self.relax_reverify = relax_reverify
        self.live_events_url = (live_events_url or "").rstrip("/")
        self.callback_host = (callback_host or "").strip()
        self.callback_port = int(callback_port)
        self._endpoint_lock = threading.RLock()
        self.gallery_lock = threading.RLock()
        self._gallery_versions_path = Path(__file__).resolve().parents[2] / "data" / "face_gallery_versions.json"
        try:
            self._gallery_versions = json.loads(self._gallery_versions_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._gallery_versions = {}
        if not isinstance(self._gallery_versions, dict):
            self._gallery_versions = {}
        self._last_live_image_b64: str | None = None
        # Persistent client for BS :7790 polls (avoid TCP+TLS setup every tick)
        self._live_http: httpx.Client | None = None
        self._api_http: httpx.Client | None = None
        self._live_healthy = False

    def update_endpoint(self, host: str, port: int) -> None:
        """Switch subsequent panel API calls without rebuilding the pipeline."""
        with self._endpoint_lock:
            self.host = str(host).strip()
            self.port = int(port)
            self.base_url = f"http://{self.host}:{self.port}".rstrip("/")

    def _gallery_key(self, enroll_id: int) -> str:
        return f"{self.base_url}|{int(enroll_id)}"

    def gallery_version(self, enroll_id: int) -> str | None:
        return self._gallery_versions.get(self._gallery_key(enroll_id))

    def gallery_ready(self, enroll_id: int, version: str) -> bool:
        if self.gallery_version(enroll_id) != version:
            return False
        if not self.gallery_lock.acquire(blocking=False):
            return False
        try:
            rows = self._api({"cmd": "getuserlist", "stn": True}, timeout=2.5).get("record") or []
            for row in rows:
                try:
                    if int(row.get("id") or 0) == int(enroll_id) and int(row.get("face") or 0) > 0:
                        return True
                except (TypeError, ValueError, AttributeError):
                    continue
            return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("gallery_ready enrollid=%s unavailable: %s", enroll_id, exc)
            return False
        finally:
            self.gallery_lock.release()

    def set_gallery_version(self, enroll_id: int, version: str | None) -> None:
        key = self._gallery_key(enroll_id)
        if version is None:
            self._gallery_versions.pop(key, None)
        else:
            self._gallery_versions[key] = version
        try:
            path = self._gallery_versions_path
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._gallery_versions), encoding="utf-8")
            os.replace(temp, path)
        except OSError as exc:
            logger.warning("Gallery version cache could not be saved: %s", exc)

    def test_connection(self, *, timeout: float = 3.0) -> dict[str, Any]:
        data = self._api({"cmd": "getdevinfo"}, timeout=timeout)
        if not data.get("result"):
            raise RuntimeError(data.get("msg") or f"getdevinfo failed: {data}")
        return data

    def ensure_bs_server(self, host: str | None = None, port: int | None = None) -> bool:
        """Point the panel's cloud/BS server at this station (:7788)."""
        want_host = (host or "").strip() or self.callback_host or _guess_lan_ip(self.host)
        want_port = int(port if port is not None else self.callback_port)
        if not want_host:
            logger.warning("Cannot guess station LAN IP for AiFace serverip")
            return False
        try:
            want = _ipv4_to_u32(want_host)
            info = self._api({"cmd": "getdevinfo"})
            cur_ip = int(info.get("serverip") or 0)
            cur_port = int(info.get("serverport") or 0)
            use_bs = int(info.get("use_bs") or 0)
            if cur_ip == want and cur_port == want_port and use_bs == 1:
                self.callback_host = want_host
                self.callback_port = want_port
                logger.info("AiFace BS server already %s:%s", want_host, want_port)
                return True
            out = self._api(
                {
                    "cmd": "setdevinfo",
                    "serverip": want,
                    "serverport": want_port,
                    "use_bs": 1,
                    "use_domain_name": 0,
                    "server_dns_name": want_host,
                }
            )
            logger.info(
                "AiFace BS server %s:%s → %s:%s result=%s",
                _u32_to_ipv4(cur_ip) if cur_ip else "0",
                cur_port,
                want_host,
                want_port,
                out.get("result"),
            )
            ok = bool(out.get("result"))
            if ok:
                self.callback_host = want_host
                self.callback_port = want_port
            return ok
        except Exception as exc:  # noqa: BLE001
            logger.warning("AiFace ensure_bs_server failed: %s", exc)
            return False

    def _live_client(self) -> httpx.Client:
        with self._endpoint_lock:
            if self._live_http is None or self._live_http.is_closed:
                self._live_http = httpx.Client(timeout=httpx.Timeout(0.6, connect=0.25))
            return self._live_http

    def _api_client(self) -> httpx.Client:
        with self._endpoint_lock:
            if self._api_http is None or self._api_http.is_closed:
                self._api_http = httpx.Client(
                    timeout=self.timeout_seconds,
                    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                )
            return self._api_http

    def close(self) -> None:
        with self._endpoint_lock:
            for client in (self._api_http, self._live_http):
                if client is not None:
                    client.close()

    def _api(self, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        with self._endpoint_lock:
            base_url = self.base_url
            password = self.password
        body = {"password": password, **payload}
        resp = self._api_client().post(
            f"{base_url}/api",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout or self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected AiFace response: {data!r}")
        return data

    def get_logs(self, *, stn: int = 1) -> list[dict[str, Any]]:
        data = self._api({"cmd": "getlog", "stn": stn})
        if not data.get("result"):
            raise RuntimeError(data.get("msg") or f"getlog failed: {data}")
        records = data.get("record") or []
        return list(records) if isinstance(records, list) else []

    def get_rtlogs(self, *, index: int = 0) -> list[dict[str, Any]]:
        try:
            data = self._api({"cmd": "getrtlog", "index": index})
        except Exception as exc:  # noqa: BLE001
            logger.debug("getrtlog unavailable: %s", exc)
            return []
        if not data.get("result"):
            return []
        records = data.get("record") or []
        return list(records) if isinstance(records, list) else []

    def get_user_name(self, enroll_id: int) -> str | None:
        data = self._api({"cmd": "getuserinfo", "enrollid": enroll_id})
        if data.get("result"):
            name = data.get("name")
            return str(name) if name else None
        return None

    def fetch_photo(self, photo_url: str) -> bytes:
        """Download a stranger/log photo from the device."""
        url = photo_url.strip()
        if url.startswith("/"):
            url = urljoin(self.base_url + "/", url.lstrip("/"))
        elif not url.startswith("http"):
            url = urljoin(self.base_url + "/", url)
        resp = self._api_client().get(url)
        resp.raise_for_status()
        return resp.content

    def latest_stranger_photo_url(self) -> str | None:
        """Newest stranger log photo, if any."""
        try:
            records = self._merge_records()
        except Exception:  # noqa: BLE001
            return None
        for rec in records:
            try:
                eid = int(rec.get("enrollid"))
            except (TypeError, ValueError):
                continue
            if eid != STRANGER_ENROLL_ID:
                continue
            photo = str(rec.get("photourl") or "").strip()
            if photo:
                return photo
        return None

    def sync_device_time(self) -> bool:
        """Push host clock to device (wrong device time breaks freshness filters)."""
        cloudtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            out = self._api({"cmd": "settime", "cloudtime": cloudtime})
            ok = bool(out.get("result"))
            logger.info("AiFace settime %s → %s", cloudtime, ok)
            return ok
        except Exception as exc:  # noqa: BLE001
            logger.warning("AiFace settime failed: %s", exc)
            return False

    def delete_user(self, enroll_id: int) -> bool:
        """Remove a user and confirm it disappeared from the device list."""
        eid = int(enroll_id)
        try:
            for attempt in range(2):
                self._api({"cmd": "deleteuser", "enrollid": eid, "backupnum": 13})
                listing = self._api({"cmd": "getuserlist", "stn": True})
                rows = listing.get("record")
                if not isinstance(rows, list):
                    raise RuntimeError(f"AiFace returned no user list while verifying deletion: {listing}")
                still_present = any(
                    int(row.get("id") or 0) == eid
                    for row in rows
                    if isinstance(row, dict)
                )
                if not still_present:
                    self.set_gallery_version(eid, None)
                    return True
                logger.warning(
                    "deleteuser enrollid=%s still present after attempt %d",
                    eid,
                    attempt + 1,
                )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("deleteuser enrollid=%s failed: %s", eid, exc)
            return False

    def _user_has_face_photo(self, enroll_id: int, *, min_len: int = 1000) -> bool:
        """True when device stores a display/match photo (backupnum 50)."""
        try:
            info = self._api({"cmd": "getuserinfo", "enrollid": int(enroll_id), "backupnum": 50})
        except Exception:  # noqa: BLE001
            return False
        if not info.get("result"):
            return False
        record = info.get("record")
        return isinstance(record, str) and len(record) >= min_len

    def _create_user_shell(self, enroll_id: int, name: str) -> dict[str, Any]:
        return self._api(
            {
                "cmd": "setuserinfo",
                "enrollid": int(enroll_id),
                "name": name,
                "backupnum": 0,
                "admin": 0,
                "enable": 1,
                "card": "0",
                "pwd": 0,
                "record": "0",
            }
        )

    def _start_live_enroll(self, enroll_id: int, name: str) -> dict[str, Any]:
        """One-shot on-device face capture request (adduser).

        ``reason=3 / device is working`` means the panel is busy (usually still
        identifying). That is NOT proof enrollment started — caller must retry
        until ``result=true`` or a real face template / match appears.
        """
        payload = {
            "cmd": "adduser",
            "enrollid": int(enroll_id),
            "name": name,
            # Face capture on this AiFace firmware: backupnum 50 (display/face).
            # backupnum 0 returns "device is working" while identify is active and
            # never stores a Face template (Capacity Face stays 0).
            "backupnum": 50,
            "admin": 0,
            "flag": 0,
        }
        try:
            return self._api(payload, timeout=max(15.0, self.timeout_seconds))
        except Exception as exc:  # noqa: BLE001
            logger.warning("adduser failed enrollid=%s: %s", enroll_id, exc)
            return {"result": False, "msg": str(exc)}

    def _face_field_b64(self, photo_bytes: bytes) -> str | None:
        """Encode JPEG for AiFace BS ``setuserinfo.face`` (same as Select File UI).

        Device UI limits: ≤500KB, ≤1024×1024, jpeg/png/bmp. We only push JPEG.
        """
        if not photo_bytes or len(photo_bytes) < 100 or photo_bytes[:2] != b"\xff\xd8":
            return None
        if len(photo_bytes) > 500 * 1024:
            logger.warning("face JPEG too large (%d bytes) — AiFace max 500KB", len(photo_bytes))
            return None
        return base64.b64encode(photo_bytes).decode("ascii")

    def _push_display_photo(self, enroll_id: int, name: str, photo_bytes: bytes) -> bool:
        """Push face JPEG via official ``setuserinfo.face`` (Select File path).

        Unlike ``backupnum=50`` + ``record``, this builds matchable Face + photourl.
        """
        b64 = self._face_field_b64(photo_bytes)
        if not b64:
            return False
        try:
            out = self._api(
                {
                    "cmd": "setuserinfo",
                    "enrollid": int(enroll_id),
                    "name": name,
                    "department": "",
                    "shiftid": 1,
                    "admin": 0,
                    "pwd": 0,
                    "card": 0,
                    "zoneid": 0,
                    "groupid": 0,
                    "access_times": 0,
                    "verifymode": 0,
                    "birthday": "",
                    "starttime": "",
                    "endtime": "",
                    "userprofile": "",
                    "face": b64,
                },
                timeout=max(60.0, self.timeout_seconds),
            )
            ok = bool(out.get("result"))
            if ok:
                self.set_gallery_version(enroll_id, None)
                logger.info(
                    "face JPEG → device enrollid=%s (%d bytes) ok",
                    enroll_id,
                    len(photo_bytes),
                )
            else:
                logger.warning(
                    "face JPEG push failed enrollid=%s: %s",
                    enroll_id,
                    out.get("msg"),
                )
            return ok
        except Exception as exc:  # noqa: BLE001
            logger.debug("display photo push failed enrollid=%s: %s", enroll_id, exc)
            return False

    def upsert_gallery_user(
        self,
        *,
        enroll_id: int,
        full_name: str,
        device_template_b64: str | None = None,
        photo_bytes: bytes | None = None,
        backupnum: int = 50,
        replace_existing: bool = True,
    ) -> bool:
        """Load one gallery face onto the panel for **on-device** verify at scan time.

        JPEG photos use the device UI path: ``setuserinfo`` with ``face`` (base64).
        That creates matchable Face + ``photourl``. Native non-JPEG templates still
        go through ``backupnum`` + ``record``.
        """
        name = str(full_name or "").strip() or f"user-{enroll_id}"
        eid = int(enroll_id)

        tmpl = (device_template_b64 or "").strip() or None
        tmpl_is_jpeg = False
        if tmpl:
            try:
                tmpl_is_jpeg = base64.b64decode(tmpl)[:2] == b"\xff\xd8"
            except Exception:  # noqa: BLE001
                tmpl_is_jpeg = False

        # Prefer real photo bytes; fall back to JPEG-looking template.
        jpeg = photo_bytes if photo_bytes and photo_bytes[:2] == b"\xff\xd8" else None
        if jpeg is None and tmpl_is_jpeg and tmpl:
            try:
                jpeg = base64.b64decode(tmpl)
            except Exception:  # noqa: BLE001
                jpeg = None

        # setuserinfo.face replaces the user's photo in place. Avoid the
        # list → delete → set → list round trip on the immediate booking path.
        if jpeg is not None:
            ok = self._push_display_photo(eid, name, jpeg)
            if ok:
                logger.info(
                    "Gallery upsert enrollid=%s name=%s source=face_jpeg ok=%s",
                    eid,
                    name,
                    ok,
                )
                return True
            logger.warning("Gallery upsert enrollid=%s: face JPEG push failed", eid)
            return False

        # Native non-JPEG template via backupnum/record.
        if not tmpl or tmpl_is_jpeg:
            logger.warning("upsert enrollid=%s: no template or photo", eid)
            return False

        # Native templates cannot replace the existing slot through the JPEG
        # upload command, so keep the original delete-before-create behavior.
        if replace_existing:
            self.delete_user(eid)

        shell = self._create_user_shell(eid, name)
        if not shell.get("result"):
            logger.warning("upsert shell failed enrollid=%s: %s", eid, shell)
            return False

        try:
            out = self._api(
                {
                    "cmd": "setuserinfo",
                    "enrollid": eid,
                    "name": name,
                    "backupnum": int(backupnum),
                    "admin": 0,
                    "enable": 1,
                    "card": "0",
                    "pwd": 0,
                    "record": tmpl,
                },
                timeout=max(20.0, self.timeout_seconds),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("upsert setuserinfo failed enrollid=%s: %s", eid, exc)
            return False

        ok = bool(out.get("result"))
        logger.info(
            "Gallery upsert enrollid=%s name=%s source=device_template backupnum=%s ok=%s",
            eid,
            name,
            backupnum,
            ok,
        )
        return ok

    def export_gallery_face(self, enroll_id: int) -> dict[str, Any] | None:
        """Pull native face record (+ optional JPEG) from the panel for VectorDB.

        Returns dict with enroll_id, full_name, device_template_b64, image_b64?
        or None if the enroll has no Face template on device.
        """
        eid = int(enroll_id)
        try:
            info = self._api({"cmd": "getuserinfo", "enrollid": eid, "backupnum": 50})
        except Exception as exc:  # noqa: BLE001
            logger.warning("export getuserinfo failed enrollid=%s: %s", eid, exc)
            return None
        if not info.get("result"):
            return None
        record = info.get("record")
        if not isinstance(record, str) or len(record) < 1000:
            logger.warning("export enrollid=%s: no face template on device", eid)
            return None
        name = str(info.get("name") or "").strip() or f"user-{eid}"
        out: dict[str, Any] = {
            "enroll_id": eid,
            "full_name": name,
            "device_template_b64": record,
        }
        # Prefer device photo URL when present (display JPEG).
        try:
            ulist = self._api({"cmd": "getuserlist", "stn": True})
            for row in ulist.get("record") or []:
                if int(row.get("id") or -1) != eid:
                    continue
                photo = str(row.get("photourl") or "").strip()
                if photo:
                    try:
                        jpeg = self.fetch_photo(photo)
                        if jpeg and len(jpeg) >= 100:
                            out["image_b64"] = base64.b64encode(jpeg).decode("ascii")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("export photo fetch failed: %s", exc)
                break
        except Exception as exc:  # noqa: BLE001
            logger.debug("export getuserlist failed: %s", exc)
        # If record itself is a JPEG, also store as image_b64.
        if "image_b64" not in out:
            try:
                raw = base64.b64decode(record)
                if raw[:2] == b"\xff\xd8":
                    out["image_b64"] = record
            except Exception:  # noqa: BLE001
                pass
        return out

    def fetch_live_events(self, *, since: float, include_image: bool = False) -> list[dict[str, Any]]:
        if not self.live_events_url:
            return []
        params = {"since": str(since), "image": "1" if include_image else "0"}
        try:
            resp = self._live_client().get(self.live_events_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            self._live_healthy = False
            logger.debug("live events poll failed: %s", exc)
            return []
        self._live_healthy = True
        events = data.get("events") if isinstance(data, dict) else None
        return list(events) if isinstance(events, list) else []

    def enroll_user(
        self,
        full_name: str,
        *,
        photo_url: str | None = None,
        photo_bytes: bytes | None = None,
        image_b64: str | None = None,
        enroll_id: int | None = None,
        verify_timeout_seconds: float = 25.0,
        stop_flag: Any = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        """Register on Face ID via live capture (adduser), then verify device match.

        Remote ``setuserinfo`` photo-only enroll creates ghost users that never match.
        Option 2: chart supplies name → device captures face from camera → rescan confirms.

        While the panel is identifying a stranger, ``adduser`` returns
        ``device is working``. We pause briefly, then run a short active loop
        (default 25s) with UI progress — never a silent long wait.
        """
        name = str(full_name).strip()
        if not name:
            return {"success": False, "error": "full_name is required"}

        if photo_bytes is None and image_b64:
            try:
                photo_bytes = base64.b64decode(image_b64)
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": f"bad_image_b64: {exc}"}

        if photo_bytes is None and self._last_live_image_b64:
            try:
                photo_bytes = base64.b64decode(self._last_live_image_b64)
            except Exception:  # noqa: BLE001
                photo_bytes = None

        if photo_bytes is None:
            url = (photo_url or "").strip() or (self.latest_stranger_photo_url() or "")
            if url:
                try:
                    photo_bytes = self.fetch_photo(url)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to fetch stranger photo %s: %s", url, exc)

        eid = int(enroll_id) if enroll_id is not None else (int(time.time()) % 90000 + random.randint(1000, 9999))
        timeout = max(8.0, float(verify_timeout_seconds or 25.0))

        def _progress(msg: str) -> None:
            if callable(on_progress):
                try:
                    on_progress(msg)
                except Exception:  # noqa: BLE001
                    logger.exception("enroll on_progress failed")

        try:
            self.delete_user(eid)
            shell = self._create_user_shell(eid, name)
            if not shell.get("result"):
                return {"success": False, "raw": shell, "enroll_id": eid, "error": "shell_failed"}

            if timeout <= 0:
                add_out = self._start_live_enroll(eid, name)
                return {
                    "success": True,
                    "pending": True,
                    "enroll_id": eid,
                    "name": name,
                    "raw": add_out,
                }

            _progress("Đang chuẩn bị chụp khuôn mặt… vui lòng nhìn thẳng máy Face ID.")
            time.sleep(2.0)

            self.sync_device_time()
            self._maybe_relax_reverify()
            try:
                baseline = self._merge_records()
            except Exception as exc:  # noqa: BLE001
                return {
                    "success": False,
                    "error": f"baseline_failed: {exc}",
                    "enroll_id": eid,
                }
            seen: set[str] = {self._event_key(rec) for rec in baseline}
            live_since = time.time()
            seen_live: set[str] = set()
            deadline = time.monotonic() + timeout
            last_add: dict[str, Any] = {"result": False}
            add_ok = False
            last_progress = 0.0
            last_add_at = 0.0
            last_face_check = 0.0
            attempt = 0

            logger.info(
                "AiFace enroll loop enrollid=%s timeout=%.0fs baseline=%d",
                eid,
                timeout,
                len(seen),
            )

            while time.monotonic() < deadline:
                if stop_flag is not None and getattr(stop_flag, "is_set", lambda: False)():
                    return {
                        "success": False,
                        "error": "cancelled",
                        "enroll_id": eid,
                        "name": name,
                    }

                now = time.monotonic()
                if now - last_progress >= 2.0:
                    left = max(0, int(deadline - now))
                    _progress(f"Nhìn thẳng máy Face ID để đăng ký khuôn mặt… ({left}s)")
                    last_progress = now

                # Retry adduser every ~2.5s until device accepts capture.
                if (not add_ok) and (now - last_add_at >= 2.5):
                    attempt += 1
                    last_add = self._start_live_enroll(eid, name)
                    last_add_at = now
                    if last_add.get("result"):
                        add_ok = True
                        logger.info("adduser accepted enrollid=%s attempt=%s", eid, attempt)
                    else:
                        logger.info(
                            "adduser busy enrollid=%s attempt=%s reason=%s msg=%s",
                            eid,
                            attempt,
                            last_add.get("reason"),
                            last_add.get("msg"),
                        )

                # Live BS match for this enroll id
                for ev in reversed(self.fetch_live_events(since=live_since, include_image=True)):
                    key = f"live|{ev.get('enroll_id')}|{ev.get('event_time')}|{ev.get('received_at')}"
                    if key in seen_live:
                        continue
                    seen_live.add(key)
                    try:
                        enroll_id_ev = int(ev.get("enroll_id"))
                    except (TypeError, ValueError):
                        continue
                    if enroll_id_ev == eid:
                        match_name = (
                            str(ev.get("name") or "").strip()
                            or self.get_user_name(eid)
                            or name
                        )
                        match = FaceMatchResult(
                            matched=True,
                            patient_id=str(eid),
                            name=match_name,
                            enroll_id=eid,
                            status="matched",
                            message=f"Nhận diện: {match_name}",
                            event_time=str(ev.get("event_time") or "") or None,
                            image_b64=ev.get("image_b64") if isinstance(ev.get("image_b64"), str) else None,
                        )
                        if photo_bytes and len(photo_bytes) >= 100:
                            self._push_display_photo(eid, name, photo_bytes)
                        logger.info("AiFace enroll LIVE match enrollid=%s", eid)
                        return {
                            "success": True,
                            "enroll_id": eid,
                            "name": match_name,
                            "match": match,
                            "raw": last_add,
                        }

                # getlog match for this enroll id
                try:
                    records = self._merge_records()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("enroll getlog poll failed: %s", exc)
                    time.sleep(0.5)
                    continue
                device_now = None
                if records:
                    device_now = self._parse_event_time(str(records[0].get("time") or ""))
                for rec in reversed([r for r in records if self._event_key(r) not in seen]):
                    seen.add(self._event_key(rec))
                    age = self._age_seconds(rec, now=device_now)
                    if age is not None and age > self.accept_recent_seconds:
                        continue
                    result = self._result_from_rec(rec)
                    if result and result.matched and result.enroll_id == eid:
                        if photo_bytes and len(photo_bytes) >= 100:
                            self._push_display_photo(eid, name, photo_bytes)
                        logger.info("AiFace enroll getlog match enrollid=%s", eid)
                        return {
                            "success": True,
                            "enroll_id": eid,
                            "name": str(result.name or name),
                            "match": result,
                            "raw": last_add,
                        }

                # Periodic face-photo presence check (template landed)
                if now - last_face_check >= 3.0:
                    last_face_check = now
                    if self._user_has_face_photo(eid):
                        logger.info("AiFace face photo present enrollid=%s", eid)
                        # Keep looping briefly for a real match event.
                        add_ok = True

                time.sleep(0.6)

            return {
                "success": False,
                "error": "enroll_verify_timeout",
                "enroll_id": eid,
                "name": name,
                "raw": last_add,
                "message": (
                    "Máy Face ID chưa chụp được khuôn mặt (đang bận nhận diện). "
                    "Bước ra 2 giây, nhìn lại máy, rồi bấm Đăng ký lại."
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("AiFace enroll_user failed: %s", exc)
            return {"success": False, "error": str(exc), "enroll_id": eid}

    def _maybe_relax_reverify(self) -> None:
        """Shorten device re-verify cooldown so demo rescans create new logs."""
        if not self.relax_reverify:
            return
        try:
            info = self._api({"cmd": "getdevinfo"})
            current = int(info.get("reverifytime") or 0)
            if current <= 5:
                return
            # Keep other settings; only shrink reverify window for demo.
            payload = {"cmd": "setdevinfo", "reverifytime": 5}
            out = self._api(payload)
            logger.info(
                "AiFace reverifytime %s → 5 (demo): %s",
                current,
                out.get("result"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not relax AiFace reverifytime: %s", exc)

    def _event_key(self, rec: dict[str, Any]) -> str:
        return f"{rec.get('time')}|{rec.get('enrollid')}|{rec.get('mode')}|{rec.get('photourl') or ''}"

    def _parse_event_time(self, raw: str) -> datetime | None:
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    def _age_seconds(self, rec: dict[str, Any], *, now: datetime | None = None) -> float | None:
        ts = self._parse_event_time(str(rec.get("time") or ""))
        if ts is None:
            return None
        # Device clock may differ from host; compare against newest log time as "now"
        # when provided via now= newest_ts.
        ref = now or datetime.now()
        return max(0.0, (ref - ts).total_seconds())

    def _merge_records(self) -> list[dict[str, Any]]:
        """Device getlog is newest-first; keep that order (do not sort by naive clock).

        AiFace may store UTC while the station is ICT — string-sorting times then
        treats leftover afternoon logs as newer than the live scan.
        """
        logs = self.get_logs()
        seen = {self._event_key(rec) for rec in logs}
        extra: list[dict[str, Any]] = []
        for rec in self.get_rtlogs():
            key = self._event_key(rec)
            if key in seen:
                continue
            seen.add(key)
            extra.append(rec)
        return extra + logs

    def _result_from_rec(self, rec: dict[str, Any]) -> FaceMatchResult | None:
        enroll_raw = rec.get("enrollid")
        try:
            enroll_id = int(enroll_raw)
        except (TypeError, ValueError):
            return None
        event_time = str(rec.get("time") or "")
        name = (rec.get("name") or "").strip() or None
        photo_url = str(rec.get("photourl") or "").strip() or None
        if enroll_id == STRANGER_ENROLL_ID:
            return FaceMatchResult(
                matched=False,
                enroll_id=enroll_id,
                status="stranger",
                message=(
                    "Chưa có trong hệ thống — vui lòng nhập họ tên trên màn hình, "
                    "bấm Đăng ký và nhìn vào máy để được đo"
                ),
                event_time=event_time or None,
                photo_url=photo_url,
            )
        if not name:
            fresh = self.get_user_name(enroll_id)
            if fresh:
                name = fresh
            else:
                name = f"ID {enroll_id}"
        return FaceMatchResult(
            matched=True,
            patient_id=str(enroll_id),
            name=name,
            enroll_id=enroll_id,
            status="matched",
            message=f"Nhận diện: {name}",
            event_time=event_time or None,
            photo_url=photo_url,
        )

    def wait_for_identify(
        self,
        *,
        timeout_seconds: float = 120.0,
        stop_flag: Any = None,
        on_stranger: Any = None,
        on_tick: Any = None,
        expect_enroll_id: int | None = None,
        ignore_stranger: bool = False,
        accept_existing_recent: bool = False,
        sync_clock: bool = True,
        max_age_seconds: float | None = None,
        skip_keys: Any = None,
        min_event_epoch: float | None = None,
    ) -> FaceMatchResult:
        """Poll device logs + clinic AiFace BS live events until a verify.

        By default does not replay old getlog rows. Walk-in sets
        ``accept_existing_recent`` so a scan that already happened (panel
        beeped, chart still idle) still starts the session.

        ``skip_keys`` are ``enroll_id|event_time`` pairs already used to start
        a session — do not replay them.
        """
        if sync_clock:
            self.sync_device_time()
            self._maybe_relax_reverify()
        deadline = time.monotonic() + max(0.5, timeout_seconds)
        stranger_notified = False
        max_age = float(
            self.accept_recent_seconds if max_age_seconds is None else max_age_seconds
        )
        live_lookback = max(max_age, 0.0) if accept_existing_recent else 0.0
        live_since = max(time.time() - live_lookback, float(min_event_epoch or 0.0))
        seen_live: set[str] = set()
        expect_id = int(expect_enroll_id) if expect_enroll_id is not None else None
        skip = {str(k) for k in (skip_keys or [])}
        # Live BS events are near-real-time; getlog is slower — poll them on different cadences.
        live_interval = min(0.2, max(0.1, float(self.poll_interval_seconds) * 0.25))
        # Respect an explicitly faster polling interval when the live event
        # bridge is unavailable (notably the post-enrolment verification path).
        # Production keeps its configured 1 s cadence; short diagnostic waits
        # must still get more than the initial baseline request.
        log_interval = max(0.05, float(self.poll_interval_seconds))
        last_log_poll = 0.0
        last_tick = 0.0

        try:
            baseline = self._merge_records()
        except Exception as exc:  # noqa: BLE001
            logger.exception("AiFace baseline log fetch failed")
            return FaceMatchResult(
                matched=False,
                status="error",
                message=f"Không kết nối được máy Face ID: {exc}",
            )

        if accept_existing_recent:
            # Newest device log wins (no host-clock age). Skip already-used keys
            # and do not fall back to an older patient.
            for rec in baseline:
                try:
                    eid = int(rec.get("enrollid"))
                except (TypeError, ValueError):
                    continue
                et = str(rec.get("time") or "")
                event_dt = self._parse_event_time(et)
                if min_event_epoch is not None and (
                    event_dt is None or event_dt.timestamp() < min_event_epoch
                ):
                    continue
                consume = f"{eid}|{et}"
                if eid == STRANGER_ENROLL_ID:
                    break
                if consume in skip:
                    break
                if expect_id is not None and eid != expect_id:
                    continue
                result = self._result_from_rec(rec)
                if result is None or not result.matched:
                    break
                logger.info(
                    "AiFace reuse newest getlog match enrollid=%s name=%s at %s",
                    result.enroll_id,
                    result.name,
                    result.event_time,
                )
                return result

        # Ignore every event already on the device when the wait starts.
        seen: set[str] = {self._event_key(rec) for rec in baseline}
        logger.info(
            "AiFace waiting for fresh scan (ignoring %d existing log entries, live=%s, expect=%s, live_interval=%.2fs, reuse_recent=%s)",
            len(seen),
            self.live_events_url or "off",
            expect_id,
            live_interval,
            accept_existing_recent,
        )

        while time.monotonic() < deadline:
            if stop_flag is not None and getattr(stop_flag, "is_set", lambda: False)():
                return FaceMatchResult(
                    matched=False,
                    status="timeout",
                    message="Đã hủy nhận diện khuôn mặt",
                )
            now_m = time.monotonic()
            if callable(on_tick) and (now_m - last_tick) >= 0.5:
                last_tick = now_m
                try:
                    on_tick()
                except Exception:  # noqa: BLE001
                    logger.exception("on_tick failed")

            # 1) Live BS sendlog feed (preferred — real-time). Skip bulky JPEGs unless stranger.
            live_events = self.fetch_live_events(since=live_since, include_image=False)
            for ev in reversed(live_events):
                key = f"live|{ev.get('enroll_id')}|{ev.get('event_time')}|{ev.get('received_at')}"
                if key in seen_live:
                    continue
                seen_live.add(key)
                try:
                    enroll_id = int(ev.get("enroll_id"))
                except (TypeError, ValueError):
                    continue
                if min_event_epoch is not None and float(ev.get("received_at") or 0) < min_event_epoch:
                    continue
                image_b64 = ev.get("image_b64") if isinstance(ev.get("image_b64"), str) else None
                if enroll_id == STRANGER_ENROLL_ID:
                    if ignore_stranger or expect_id is not None:
                        logger.debug("AiFace LIVE stranger ignored (expect=%s)", expect_id)
                        continue
                    # One image fetch only when registering a stranger
                    if not image_b64:
                        for rich in self.fetch_live_events(since=live_since, include_image=True):
                            if (
                                str(rich.get("enroll_id")) == str(enroll_id)
                                and rich.get("event_time") == ev.get("event_time")
                                and isinstance(rich.get("image_b64"), str)
                            ):
                                image_b64 = rich["image_b64"]
                                break
                    if image_b64:
                        self._last_live_image_b64 = image_b64
                    result = FaceMatchResult(
                        matched=False,
                        enroll_id=enroll_id,
                        status="stranger",
                        message=(
                            "Chưa có trong hệ thống — vui lòng nhập họ tên trên màn hình, "
                            "bấm Đăng ký và nhìn vào máy để được đo"
                        ),
                        event_time=str(ev.get("event_time") or "") or None,
                        image_b64=image_b64,
                    )
                    logger.info("AiFace LIVE stranger at %s", result.event_time)
                    if callable(on_stranger):
                        try:
                            on_stranger(result)
                        except Exception:  # noqa: BLE001
                            logger.exception("on_stranger callback failed")
                    stranger_notified = True
                    continue
                if expect_id is not None and enroll_id != expect_id:
                    logger.debug("AiFace LIVE skip enrollid=%s (expect %s)", enroll_id, expect_id)
                    continue
                consume = f"{enroll_id}|{ev.get('event_time') or ''}"
                if consume in skip:
                    continue
                # Prefer event name — avoid blocking get_user_name round-trip before UI updates
                name = (str(ev.get("name") or "").strip() or None) or f"ID {enroll_id}"
                logger.info("AiFace LIVE match enrollid=%s name=%s", enroll_id, name)
                return FaceMatchResult(
                    matched=True,
                    patient_id=str(enroll_id),
                    name=name,
                    enroll_id=enroll_id,
                    status="matched",
                    message=f"Nhận diện: {name}",
                    event_time=str(ev.get("event_time") or "") or None,
                    image_b64=image_b64,
                )

            # The bridge's `since` filter is exclusive. Keep a 1 ms overlap
            # (deduplicated by seen_live) so a same-tick event is not lost.
            if live_events:
                newest = max(float(ev.get("received_at") or 0) for ev in live_events)
                live_since = max(live_since, newest - 0.001)

            # 2) Fallback: HTTP getlog (slower path)
            # Live push remains fast; the panel logs are a safety net. Avoid
            # two extra panel requests every 0.2 s while the push bridge is up.
            fallback_interval = max(1.0, log_interval) if self._live_healthy else log_interval
            if (now_m - last_log_poll) >= fallback_interval:
                last_log_poll = now_m
                try:
                    records = self._merge_records()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AiFace log poll failed: %s", exc)
                    time.sleep(live_interval)
                    continue

                device_now = None
                if records:
                    device_now = self._parse_event_time(str(records[0].get("time") or ""))

                new_recs = [r for r in records if self._event_key(r) not in seen]
                new_recs.reverse()  # oldest → newest among unseen
                for rec in new_recs:
                    key = self._event_key(rec)
                    seen.add(key)
                    age = self._age_seconds(rec, now=device_now)
                    event_dt = self._parse_event_time(str(rec.get("time") or ""))
                    if min_event_epoch is not None and (
                        event_dt is None or event_dt.timestamp() < min_event_epoch
                    ):
                        continue
                    if age is not None and age > self.accept_recent_seconds:
                        logger.debug(
                            "AiFace skip stale new key age=%.0fs enrollid=%s",
                            age,
                            rec.get("enrollid"),
                        )
                        continue
                    result = self._result_from_rec(rec)
                    if result is None:
                        continue
                    if result.status == "stranger":
                        if ignore_stranger or expect_id is not None:
                            continue
                        logger.info(
                            "AiFace stranger event at %s photo=%s",
                            result.event_time,
                            result.photo_url,
                        )
                        if callable(on_stranger):
                            try:
                                on_stranger(result)
                            except Exception:  # noqa: BLE001
                                logger.exception("on_stranger callback failed")
                        stranger_notified = True
                        continue
                    if expect_id is not None and result.enroll_id != expect_id:
                        continue
                    consume = f"{result.enroll_id}|{result.event_time or ''}"
                    if consume in skip:
                        continue
                    logger.info(
                        "AiFace fresh match enrollid=%s name=%s at %s",
                        result.enroll_id,
                        result.name,
                        result.event_time,
                    )
                    return result

            time.sleep(live_interval)

        if expect_id is not None:
            return FaceMatchResult(
                matched=False,
                status="timeout",
                message=(
                    "Hết thời gian chờ xác nhận đăng ký — vui lòng nhìn lại máy Face ID"
                ),
            )
        if stranger_notified:
            return FaceMatchResult(
                matched=False,
                status="stranger",
                message="Chưa đăng ký (hết thời gian chờ). Vui lòng thử lại.",
            )
        return FaceMatchResult(
            matched=False,
            status="timeout",
            message="Hết thời gian chờ nhận diện khuôn mặt — vui lòng nhìn vào máy Face ID",
        )


def build_face_client(
    mode: str,
    *,
    host: str = "192.168.1.18",
    password: str = "12345678",
    port: int = 80,
    poll_interval_seconds: float = 1.0,
    accept_recent_seconds: float = 15.0,
    live_events_url: str = "http://127.0.0.1:7790/events",
    callback_host: str = "",
    callback_port: int = 7788,
) -> FaceClient:
    mode_l = (mode or "off").strip().lower()
    if mode_l in ("off", "none", "mock", "stub", "deferred"):
        return FaceClient()
    if mode_l in ("aiface", "device", "live"):
        return AiFaceClient(
            host=host,
            password=password,
            port=port,
            poll_interval_seconds=poll_interval_seconds,
            accept_recent_seconds=accept_recent_seconds,
            live_events_url=live_events_url,
            callback_host=callback_host,
            callback_port=callback_port,
        )
    logger.warning("Unknown face bridge %r — using stub", mode)
    return FaceClient()
