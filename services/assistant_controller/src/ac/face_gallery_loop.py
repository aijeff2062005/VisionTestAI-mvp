"""Background pull of today's appointment faces + overnight AiFace wipe.

Frappe often cannot reach the Jetson on the clinic LAN, so the station polls
the hospital API and keeps the panel gallery in sync locally.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from ac.config import FaceVectorDbConfig
from ac.face_client import FaceClient
from ac.face_sync import sync_today_appointments_to_device, wipe_device_gallery
from ac.hospital_client import HospitalClient
from ac.media_client import MediaClient

logger = logging.getLogger(__name__)


class TodayFaceSyncLoop:
    def __init__(
        self,
        *,
        hospital: HospitalClient,
        face: FaceClient,
        media: MediaClient | None,
        cfg: FaceVectorDbConfig,
    ) -> None:
        self.hospital = hospital
        self.face = face
        self.media = media
        self.cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_wipe_date: str | None = None
        self._last_sig: str | None = None
        self._last_audit_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="today-face-sync",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Today-face sync loop started poll=%.1fs overnight_wipe=%s@%02d:%02d",
            float(self.cfg.sync_today_poll_seconds or 10.0),
            bool(self.cfg.overnight_wipe_enabled),
            int(self.cfg.overnight_wipe_hour),
            int(self.cfg.overnight_wipe_minute),
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def sync_now(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            return self._sync_once(force=force)

    def _gallery_signature(self, gallery: dict[str, Any]) -> str:
        faces = gallery.get("faces") or []
        parts: list[str] = []
        for row in faces:
            try:
                eid = int(row.get("enroll_id"))
            except (TypeError, ValueError):
                continue
            fp = (
                str(row.get("avatar_fp") or "")
                or str(row.get("object_key") or "")
                or str(row.get("media_get_url") or "")[:48]
            )
            alen = row.get("avatar_len")
            if alen is None:
                alen = len(str(row.get("media_get_url") or "")) + len(
                    str(row.get("image_b64") or "")
                )
            name = str(row.get("full_name") or row.get("patient_name") or "")
            parts.append(f"{eid}:{alen}:{fp}:{name}")
        return "|".join(sorted(parts))

    def _sync_once(self, *, force: bool = False) -> dict[str, Any]:
        if not self.cfg.sync_today_appointments_only:
            return {"skipped": True, "reason": "sync_today_appointments_only=false"}
        light = self.hospital.list_today_face_gallery(light=True)
        if not light.get("success"):
            err = light.get("error") or "list_today_face_gallery(light) failed"
            logger.warning("Today-face poll: %s", err)
            return {"success": False, "error": err}
        sig = self._gallery_signature(light)
        count = int(light.get("count") or len(light.get("faces") or []))
        if not force and sig == self._last_sig and time.monotonic() - self._last_audit_at < 60.0:
            return {"success": True, "unchanged": True, "count": count}
        res = sync_today_appointments_to_device(
            self.hospital,
            self.face,
            self.media,
            max_faces=self.cfg.max_faces,
            device_face_backupnum=self.cfg.device_face_backupnum,
            prune_not_in_today=self.cfg.prune_not_in_today,
        )
        out = res.as_dict()
        out["success"] = not res.failed and not res.errors
        if out["success"]:
            self._last_sig = sig
            self._last_audit_at = time.monotonic()
        out["unchanged"] = False
        out["count"] = count
        logger.info("Today-face poll sync: %s", out)
        return out

    def _maybe_overnight_wipe(self) -> None:
        if not self.cfg.overnight_wipe_enabled:
            return
        now = datetime.now()
        target_h = int(self.cfg.overnight_wipe_hour)
        target_m = int(self.cfg.overnight_wipe_minute)
        # Fire once in the wipe minute window.
        if now.hour != target_h or now.minute != target_m:
            return
        day = now.strftime("%Y-%m-%d")
        if self._last_wipe_date == day:
            return
        with self._lock:
            if self._last_wipe_date == day:
                return
            # Do not discard the panel's only working copy when today's
            # bookings exist but Frappe cannot provide their face images.
            source = self.hospital.list_today_face_gallery(light=True)
            if not source.get("success"):
                logger.warning("Overnight AiFace wipe deferred: face gallery unavailable")
                return
            diagnostics = source.get("diagnostics")
            if not isinstance(diagnostics, dict) or "appointments" not in diagnostics:
                logger.warning("Overnight AiFace wipe deferred: gallery diagnostics unavailable")
                return
            missing = sum(int(diagnostics.get(key) or 0) for key in (
                "missing_patient", "missing_enroll_id", "missing_face_avatar",
            ))
            if missing:
                logger.warning(
                    "Overnight AiFace wipe deferred: %d of %d today's appointments lack a restorable face",
                    missing, int(diagnostics.get("appointments") or 0),
                )
                return
            logger.info("Overnight AiFace gallery wipe starting (%s %02d:%02d)", day, target_h, target_m)
            wipe = wipe_device_gallery(self.face, preserve_stranger=True)
            if wipe.get("error"):
                logger.warning("Overnight AiFace wipe failed; will retry: %s", wipe["error"])
                return
            self._last_wipe_date = day
            self._last_sig = None
            self._last_audit_at = 0.0
            logger.info("Overnight AiFace gallery wipe done: %s", wipe)

    def _run(self) -> None:
        poll = max(3.0, float(self.cfg.sync_today_poll_seconds or 10.0))
        # Immediate first sync so desk enrolls show up without waiting a full tick.
        try:
            self.sync_now(force=True)
        except Exception:  # noqa: BLE001
            logger.exception("Today-face initial sync failed")
        while not self._stop.wait(poll):
            try:
                self._maybe_overnight_wipe()
                self.sync_now(force=False)
            except Exception:  # noqa: BLE001
                logger.exception("Today-face poll iteration failed")
