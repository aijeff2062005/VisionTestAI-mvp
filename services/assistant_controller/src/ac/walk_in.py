"""Idle walk-in: today's appointment faces on AiFace → detect one → auto-start test.

Desk no longer needs to press Start. Gallery still refreshes on the 10s loop.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable

from pydantic import HttpUrl

from ac.config import FaceVectorDbConfig
from ac.display_client import DisplayClient
from ac.face_client import FaceClient, FaceMatchResult
from ac.hospital_client import HospitalClient
from ac.models import ExamType, EyesMode, SessionStart
from ac.session_manager import SessionManager

logger = logging.getLogger(__name__)


class FaceWalkInLoop:
    def __init__(
        self,
        *,
        hospital: HospitalClient,
        face: FaceClient,
        sessions: SessionManager,
        display: DisplayClient,
        cfg: FaceVectorDbConfig,
        on_start: Callable[[SessionStart], None],
        callback_url: str,
    ) -> None:
        self.hospital = hospital
        self.face = face
        self.sessions = sessions
        self.display = display
        self.cfg = cfg
        self.on_start = on_start
        self.callback_url = callback_url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_match: FaceMatchResult | None = None
        self._consumed: set[str] = set()

    def start(self) -> None:
        if not getattr(self.cfg, "auto_start_on_face", True):
            logger.info("Walk-in auto-start disabled")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="face-walk-in",
            daemon=True,
        )
        self._thread.start()
        try:
            self.face.ensure_bs_server()
        except Exception:  # noqa: BLE001
            logger.warning("Walk-in ensure_bs_server failed", exc_info=True)
        try:
            if hasattr(self.face, "sync_device_time"):
                self.face.sync_device_time()
            if hasattr(self.face, "_maybe_relax_reverify"):
                self.face._maybe_relax_reverify()
        except Exception:  # noqa: BLE001
            logger.debug("Walk-in clock sync failed", exc_info=True)
        logger.info("Walk-in loop started — AiFace match starts the exam (no Frappe Start)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def take_prematch(self) -> FaceMatchResult | None:
        match = self.last_match
        self.last_match = None
        return match

    def _run(self) -> None:
        scan_msg = "Nhìn vào máy nhận diện khuôn mặt."
        listening_since = time.time()
        result_shown_at: float | None = None
        result_session_seen: str | None = None

        def show_once(message: str, scene: str) -> None:
            last = getattr(getattr(self.display, "hub", None), "last_command", {})
            if last.get("scene") != scene or last.get("text_vi") != message:
                self.display.show_message(message, scene=scene)

        while not self._stop.is_set():
            loop_started = time.monotonic()
            hub = getattr(self.display, "hub", None)
            active = self.sessions.active
            last_result = getattr(hub, "last_result", None)
            if (
                result_shown_at is None
                and active is not None
                and last_result is not None
                and last_result[0] == active.start.session_id
                and last_result[0] != result_session_seen
            ):
                result_shown_at = last_result[1]
                result_session_seen = last_result[0]
            if self.sessions.is_busy():
                self._stop.wait(1.0)
                continue
            try:
                show_once(scan_msg, "face")
            except Exception:  # noqa: BLE001
                logger.debug("scan show_message failed", exc_info=True)

            class _StopIfBusy:
                def is_set(inner_self) -> bool:
                    return self._stop.is_set() or self.sessions.is_busy()

            identify_started = time.monotonic()
            logger.info(
                "WALKIN_FACE_WAIT start timeout_s=90 accept_recent=true min_event_epoch=%s",
                max(listening_since, result_shown_at or 0.0),
            )
            result = self.face.wait_for_identify(
                timeout_seconds=90.0,
                stop_flag=_StopIfBusy(),
                ignore_stranger=True,
                # A scan may arrive while this loop is preparing the listener.
                accept_existing_recent=True,
                sync_clock=False,
                max_age_seconds=90.0,
                skip_keys=self._consumed,
                min_event_epoch=max(listening_since, result_shown_at or 0.0),
            )
            logger.info(
                "WALKIN_FACE_RESULT matched=%s status=%s enroll_id=%s elapsed_ms=%.0f",
                bool(result and result.matched),
                getattr(result, "status", None),
                getattr(result, "enroll_id", None),
                (time.monotonic() - identify_started) * 1000.0,
            )
            result_shown_at = None
            if self._stop.is_set() or self.sessions.is_busy():
                continue
            if not result or not result.matched:
                continue
            consumed_key = f"{result.enroll_id}|{result.event_time or ''}"
            if consumed_key in self._consumed:
                logger.info("Walk-in skip already-used match %s", consumed_key)
                self._stop.wait(1.5)
                continue
            self._consumed.add(consumed_key)
            session_started = time.monotonic()
            start = self._session_from_match(result)
            logger.info(
                "WALKIN_SESSION_BUILD ok=%s elapsed_ms=%.0f enroll_id=%s patient_id=%s",
                start is not None,
                (time.monotonic() - session_started) * 1000.0,
                result.enroll_id,
                getattr(start, "patient_id", None) if start else None,
            )
            if start is None:
                self.display.show_message(
                    "Không tìm thấy hồ sơ bệnh nhân trên hệ thống. Vui lòng liên hệ quầy tiếp nhận.",
                    scene="nomatch",
                )
                self._stop.wait(5.0)
                continue
            self.last_match = result
            logger.info(
                "WALKIN_MATCH enroll_id=%s name=%s → auto-start test loop_ms=%.0f",
                result.enroll_id,
                result.name,
                (time.monotonic() - loop_started) * 1000.0,
            )
            try:
                start_started = time.monotonic()
                self.on_start(start)
                logger.info(
                    "WALKIN_SESSION_STARTED session_id=%s elapsed_ms=%.0f",
                    start.session_id,
                    (time.monotonic() - start_started) * 1000.0,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Walk-in on_start failed")
                self.last_match = None

    def _session_from_match(self, result: FaceMatchResult) -> SessionStart | None:
        enroll_id = result.enroll_id
        patient_id = None
        name = (result.name or "").strip() or None
        if enroll_id is not None:
            try:
                lookup = self.hospital.lookup_by_enroll_id(int(enroll_id))
            except Exception:  # noqa: BLE001
                lookup = {}
            if lookup.get("found") and isinstance(lookup.get("patient"), dict):
                pat = lookup["patient"]
                patient_id = str(pat.get("name") or "") or None
                name = str(
                    pat.get("patient_name") or pat.get("aiface_display_name") or name or ""
                ).strip() or name
                dob = str(pat.get("dob") or pat.get("date_of_birth") or "").strip() or None
            else:
                dob = None
        else:
            dob = None
        if not patient_id:
            logger.warning("Walk-in match enroll_id=%s has no Frappe patient", enroll_id)
            return None
        try:
            callback = HttpUrl(self.callback_url)
        except Exception:  # noqa: BLE001
            logger.exception("Walk-in bad callback_url=%s", self.callback_url)
            return None
        return SessionStart(
            session_id=str(uuid.uuid4()),
            patient_id=patient_id,
            queue_number=name or "WALKIN",
            exam_type=ExamType.DISTANCE_ACUITY_5M,
            eyes=EyesMode.BOTH,
            callback_url=callback,
            correlation_id=str(uuid.uuid4()),
            locale="vi-VN",
            auto_enter_test=True,
            dob=dob,
        )
