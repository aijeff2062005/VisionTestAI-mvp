"""Readiness and STT bridges (mock + SmartEyes / Sloan)."""

from __future__ import annotations

import logging
import random
import sys
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ac.microphone_stream import SharedMicrophoneStream

logger = logging.getLogger(__name__)

LETTER_POOL = ["C", "D", "H", "K", "N", "O", "R", "S", "V", "Z"]
LETTER_RECENT_WINDOW = 3

# Best-effort English → Vietnamese for chart overlay during WAIT_READY.
_COACHING_VI = {
    "step into camera view": "Vui lòng vào khung hình camera.",
    "only one person should be in frame": "Chỉ một người trong khung hình.",
    "stand zone not found — check white floor in view": "Không thấy vùng đứng — kiểm tra sàn trắng trong khung hình.",
    "stand on the white floor (stand zone)": "Vui lòng đứng vào vùng sàn trắng.",
    "stand on the marked floor line": "Vui lòng đứng vào vị trí đánh dấu trên sàn.",
    "hold position in the stand zone...": "Giữ nguyên vị trí trong vùng đứng…",
    "put on over-ear headphones": "Vui lòng đeo tai nghe over-ear.",
    "put on headphones": "Vui lòng đeo tai nghe.",
    "wear headphones": "Vui lòng đeo tai nghe.",
    "place headphones on your head (over both ears)": "Vui lòng đeo tai nghe lên đầu (cả hai tai).",
    "keep headphones on your head...": "Giữ tai nghe trên đầu…",
    "cover your left eye": "Vui lòng che mắt trái.",
    "cover your right eye": "Vui lòng che mắt phải.",
    "face the camera": "Vui lòng nhìn thẳng vào camera.",
    "face the camera so both eyes are visible": "Vui lòng nhìn thẳng camera để thấy cả hai mắt.",
    "ready": "Sẵn sàng.",
}


@dataclass
class ReadinessSnapshot:
    zone_ok: bool = False
    headphones_on: bool = False
    under_test: str = "UNKNOWN"
    ready: bool = False
    coaching_vi: str = ""
    error: str | None = None


@dataclass
class SttResult:
    letter: str
    confidence: float
    reliable: bool
    raw: str | None = None
    acceptance_threshold: float | None = None


class ReadinessBridge:
    def snapshot(self) -> ReadinessSnapshot:
        raise NotImplementedError

    def latest_jpeg(self) -> bytes | None:
        return None

    def latest_jpeg_seq(self) -> tuple[bytes | None, int]:
        return self.latest_jpeg(), 0

    def start(self, *, exam: bool = False) -> None:
        return None

    def stop(self, *, force: bool = False) -> None:
        return None

    def set_preview_enabled(self, enabled: bool) -> dict[str, Any]:
        """Operator /preview toggle — optional; default no-op."""
        return {"preview_enabled": bool(enabled), "running": False, "exam_hold": False}

    def preview_status(self) -> dict[str, Any]:
        return {"preview_enabled": False, "running": False, "exam_hold": False}

    def set_source(self, source: str | int) -> None:
        return None

    def get_stand_zone(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "stand zone not supported",
            "mode": "floor",
            "detect_in_zone": False,
            "polygon": [],
            "track_box": [],
            "tool": None,
            "legacy": True,
        }

    def set_stand_zone(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("stand zone not supported")


class MockReadinessBridge(ReadinessBridge):
    """Becomes ready after a short delay; under_test follows requested eye."""

    def __init__(self, delay_seconds: float = 0.5) -> None:
        self.delay = delay_seconds
        self._t0 = time.monotonic()
        self.force_under_test: str = "RIGHT"

    def snapshot(self) -> ReadinessSnapshot:
        ready = (time.monotonic() - self._t0) >= self.delay
        return ReadinessSnapshot(
            zone_ok=ready,
            headphones_on=ready,
            under_test=self.force_under_test if ready else "UNKNOWN",
            ready=ready,
            coaching_vi="" if ready else "Đang chờ bệnh nhân vào vị trí (mock)…",
        )

    def reset_timer(self) -> None:
        self._t0 = time.monotonic()


def _coach_vi(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    key = raw.lower()
    if key in _COACHING_VI:
        return _COACHING_VI[key]
    for eng, vi in _COACHING_VI.items():
        if eng and eng in key:
            return vi
    # Unmapped English must not reach the patient chart.
    if any("a" <= c.lower() <= "z" for c in raw) and not any(ord(c) > 127 for c in raw):
        return ""
    return raw


def map_smarteyes_state(state: Any) -> ReadinessSnapshot:
    """Map SmartEyes ReadinessState → AC ReadinessSnapshot (pure, testable)."""
    coaching = str(getattr(state, "coaching", "") or "")
    coaching_vi = _coach_vi(coaching)
    under = str(getattr(state, "under_test", "UNKNOWN") or "UNKNOWN").upper()
    return ReadinessSnapshot(
        zone_ok=bool(getattr(state, "line_pass", False)),
        headphones_on=bool(getattr(state, "headphones_pass", False)),
        under_test=under,
        ready=bool(getattr(state, "ready", False)),
        coaching_vi=coaching_vi,
    )


class RealtimeFrameGrabber:
    """Threaded camera reader that drains the OS buffer queue continuously.

    Guarantees that read_latest() returns the most recent frame captured
    by the hardware with minimum latency, eliminating multi-second V4L2 queue delays.
    """

    def __init__(self, cap: Any) -> None:
        self.cap = cap
        self._frame = None
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._frame_seq = 0
        self._read_seq = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._reader,
            name="v4l2-drain-reader",
            daemon=True,
        )
        self._thread.start()

    def _reader(self) -> None:
        while not self._stop.is_set():
            try:
                ok, frame = self.cap.read()
            except Exception:  # noqa: BLE001
                time.sleep(0.01)
                continue
            if not ok or frame is None or getattr(frame, "size", 0) == 0:
                time.sleep(0.01)
                continue
            with self._new_frame:
                self._frame = frame
                self._frame_seq += 1
                self._new_frame.notify_all()

    def read_latest(self, timeout: float = 0.5) -> tuple[bool, Any]:
        with self._new_frame:
            if not self._new_frame.wait_for(
                lambda: self._frame_seq > self._read_seq or self._stop.is_set(),
                timeout=timeout,
            ) or self._stop.is_set():
                return False, None
            self._read_seq = self._frame_seq
            frame = self._frame
        return frame is not None, frame

    def release(self) -> None:
        self._stop.set()
        with self._new_frame:
            self._new_frame.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self.cap.release()
        except Exception:  # noqa: BLE001
            pass


class SmartEyesReadinessBridge(ReadinessBridge):
    """Live webcam readiness via SmartEyesPipeline (conda env smarteyes)."""

    def __init__(
        self,
        smarteyes_root: Path,
        *,
        config_path: Path | None = None,
        source: str | int = "macbook",
        show_window: bool = True,
        strict: bool = True,
        preview_enabled: bool = False,
    ) -> None:
        self.root = smarteyes_root
        self.config_path = config_path or (smarteyes_root / "configs" / "default.yaml")
        self.source = source
        self.show_window = show_window
        self.strict = strict
        self._lock = threading.RLock()
        self._snap = ReadinessSnapshot(coaching_vi="Đang khởi động camera SmartEyes…")
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stt_inference_active = threading.Event()
        self._started = False
        self._pipeline = None
        self._import_error: str | None = None
        self._jpeg: bytes | None = None
        self._jpeg_seq = 0
        # Preview MJPEG/render is opt-in (Jetson CPU). Exam WAIT_READY still starts CV.
        self._preview_enabled = bool(preview_enabled)
        self._exam_hold = False

        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        try:
            import cv2  # noqa: F401
            from src.config_loader import load_config  # type: ignore
            from src.pipeline import SmartEyesPipeline  # type: ignore

            self._load_config = load_config
            self._Pipeline = SmartEyesPipeline
            self._cv2 = __import__("cv2")
        except Exception as exc:  # noqa: BLE001
            self._import_error = (
                f"SmartEyes unavailable ({exc}). "
                "Activate conda env `smarteyes` and reinstall AC deps there "
                "(conda activate smarteyes && pip install -e VisionTestAI/assistant_controller)."
            )
            logger.error(self._import_error)
            self._snap = ReadinessSnapshot(
                ready=False,
                coaching_vi=self._import_error,
                error=self._import_error,
            )

    def set_stt_inference_active(self, active: bool) -> None:
        """Briefly yield CV compute while Sloan runs; camera and state stay alive."""
        if active:
            self._stt_inference_active.set()
        else:
            self._stt_inference_active.clear()

    def start(self, *, exam: bool = False) -> None:
        if self._import_error:
            with self._lock:
                self._snap = ReadinessSnapshot(
                    ready=False,
                    coaching_vi=self._import_error,
                    error=self._import_error,
                )
            if self.strict:
                raise RuntimeError(self._import_error)
            return
        with self._lock:
            if exam:
                self._exam_hold = True
            if self._started:
                return
            self._started = True
            self._stop.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="smarteyes-ready",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "SmartEyes readiness started source=%s window=%s exam=%s preview=%s",
            self.source,
            self.show_window,
            exam,
            self._preview_enabled,
        )

    def stop(self, *, force: bool = False) -> None:
        with self._lock:
            if not force:
                # Soft stop = exam released. Keep CV if operator left preview ON.
                self._exam_hold = False
                if self._preview_enabled:
                    return
            else:
                self._exam_hold = False
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._started = False
            pipe = self._pipeline
            self._pipeline = None
            self._jpeg = None
            self._snap = ReadinessSnapshot(
                coaching_vi="Preview tắt — SmartEyes idle.",
            )
        if pipe is not None:
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                logger.exception("SmartEyes pipeline close failed")
        if self.show_window and self._import_error is None:
            try:
                self._cv2.destroyAllWindows()
            except Exception:  # noqa: BLE001
                pass

    def set_preview_enabled(self, enabled: bool) -> dict[str, Any]:
        enabled = bool(enabled)
        with self._lock:
            self._preview_enabled = enabled
            if not enabled:
                self._jpeg = None
            exam_hold = bool(self._exam_hold)
        if enabled:
            self.start(exam=False)
        elif not exam_hold:
            # Only tear down CV when no exam gate needs it.
            self.stop(force=True)
        return self.preview_status()

    def preview_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "preview_enabled": bool(self._preview_enabled),
                "running": bool(self._started),
                "exam_hold": bool(self._exam_hold),
            }

    def set_source(self, source: str | int) -> None:
        with self._lock:
            if str(self.source) == str(source):
                return
            self.source = source
            running = bool(self._started)
            exam_hold = bool(self._exam_hold)
        if running and not exam_hold:
            logger.info("SmartEyes camera source switched to %s; restarting capture loop", source)
            self.stop(force=True)
            self.start(exam=False)

    def _stand_zone_path(self) -> Path:
        return Path(self.config_path).resolve().parent / "stand_zone.json"

    def get_stand_zone(self) -> dict[str, Any]:
        if self._import_error:
            return {
                "ok": False,
                "error": self._import_error,
                "mode": "floor",
                "detect_in_zone": False,
                "polygon": [],
                "track_box": [],
                "tool": None,
                "legacy": True,
            }
        try:
            from src.stand_zone import (  # type: ignore
                ensure_track_box,
                load_stand_zone_file,
                seed_stand_zone_from_cfg,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "mode": "floor",
                "detect_in_zone": False,
                "polygon": [],
                "track_box": [],
                "tool": None,
                "legacy": True,
            }

        zone = load_stand_zone_file(self._stand_zone_path())
        with self._lock:
            pipe = self._pipeline
        track_box: list[float] = []
        if pipe is not None and hasattr(pipe, "get_stand_zone"):
            live = pipe.get_stand_zone()
            mode = str(live.get("mode") or "fixed")
            detect = bool(live.get("detect_in_zone"))
            polygon = list(live.get("polygon") or [])
            track_box = list(live.get("track_box") or [])
            tool = (zone or {}).get("tool")
        elif zone:
            mode = str(zone.get("mode") or "fixed")
            detect = bool(zone.get("detect_in_zone"))
            polygon = list(zone.get("polygon") or [])
            track_box = ensure_track_box(zone)
            tool = zone.get("tool")
        else:
            try:
                cfg = self._load_config(self.config_path)
                seeded = seed_stand_zone_from_cfg(cfg)
                mode = str(seeded.get("mode") or "fixed")
                detect = bool(seeded.get("detect_in_zone"))
                polygon = list(seeded.get("polygon") or [])
                track_box = list(seeded.get("track_box") or ensure_track_box(seeded))
                tool = seeded.get("tool")
            except Exception:  # noqa: BLE001
                mode, detect, polygon, tool = "floor", False, [], None
                track_box = []
        if not track_box and zone:
            track_box = ensure_track_box(zone)
        legacy = mode == "floor" and not detect
        return {
            "ok": True,
            "mode": mode,
            "detect_in_zone": detect,
            "polygon": polygon,
            "track_box": track_box,
            "tool": tool,
            "legacy": legacy,
            "path": str(self._stand_zone_path()),
        }

    def set_stand_zone(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._import_error:
            raise RuntimeError(self._import_error)
        from src.stand_zone import (  # type: ignore
            ensure_track_box,
            legacy_stand_zone_payload,
            load_stand_zone_file,
            normalize_polygon,
            normalize_track_box,
            save_stand_zone_file,
        )

        body = dict(payload or {})
        existing = load_stand_zone_file(self._stand_zone_path()) or {}
        legacy = bool(body.get("legacy")) or str(body.get("tool") or "").lower() == "legacy"

        def _resolve_track_box(src: dict[str, Any]) -> list[float]:
            raw = src.get("track_box")
            if raw is None:
                raw = src.get("detect_box")
            if raw is not None:
                try:
                    return normalize_track_box(list(raw))
                except (TypeError, ValueError):
                    pass
            return ensure_track_box(existing)

        if legacy:
            zone = legacy_stand_zone_payload(existing)
            raw = body.get("points") if body.get("points") is not None else body.get("polygon")
            if raw:
                try:
                    zone["polygon"] = normalize_polygon(list(raw))
                except ValueError:
                    pass
            if body.get("track_box") is not None or body.get("detect_box") is not None:
                zone["track_box"] = _resolve_track_box(body)
        else:
            tool = str(body.get("tool") or existing.get("tool") or "box").lower()
            if tool == "legacy":
                tool = "box"
            # Track-box-only save: keep stand polygon; stand save: keep track_box unless sent.
            raw_pts = body.get("points") if body.get("points") is not None else body.get("polygon")
            if tool == "track":
                polygon = list(existing.get("polygon") or [])
                if len(polygon) >= 3:
                    try:
                        polygon = normalize_polygon(polygon)
                    except ValueError:
                        pass
                track_box = _resolve_track_box(body)
            else:
                if raw_pts is None:
                    raw_pts = existing.get("polygon") or []
                if not raw_pts or len(raw_pts) < 3:
                    try:
                        cfg = self._load_config(self.config_path)
                        seeded = seed_stand_zone_from_cfg(cfg)
                        raw_pts = seeded.get("polygon") or []
                    except Exception:
                        pass
                if not raw_pts or len(raw_pts) < 3:
                    raw_pts = [[0.3, 0.7], [0.7, 0.7], [0.7, 0.95], [0.3, 0.95]]
                polygon = normalize_polygon(list(raw_pts))
                if body.get("track_box") is not None or body.get("detect_box") is not None:
                    track_box = _resolve_track_box(body)
                else:
                    track_box = ensure_track_box({**existing, "polygon": polygon})
            mode = str(body.get("mode") or existing.get("mode") or "fixed").lower()
            if mode == "floor":
                mode = "fixed"
            if "detect_in_zone" in body:
                detect = bool(body.get("detect_in_zone"))
            else:
                detect = True if tool != "legacy" else bool(existing.get("detect_in_zone", True))
            zone = {
                "mode": mode,
                "detect_in_zone": detect,
                "tool": tool,
                "polygon": polygon,
                "track_box": track_box,
            }

        save_stand_zone_file(self._stand_zone_path(), zone)

        applied: dict[str, Any] | None = None
        with self._lock:
            pipe = self._pipeline
        if pipe is not None and hasattr(pipe, "set_stand_zone"):
            applied = pipe.set_stand_zone(
                mode=str(zone.get("mode")),
                polygon=list(zone.get("polygon") or []),
                detect_in_zone=bool(zone.get("detect_in_zone")),
                track_box=list(zone.get("track_box") or []),
            )

        out = self.get_stand_zone()
        out["saved"] = True
        out["applied_live"] = applied is not None
        return out

    def snapshot(self) -> ReadinessSnapshot:
        with self._lock:
            return ReadinessSnapshot(
                zone_ok=self._snap.zone_ok,
                headphones_on=self._snap.headphones_on,
                under_test=self._snap.under_test,
                ready=self._snap.ready,
                coaching_vi=self._snap.coaching_vi,
                error=self._snap.error,
            )

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def latest_jpeg_seq(self) -> tuple[bytes | None, int]:
        with self._lock:
            return self._jpeg, self._jpeg_seq

    def _publish_jpeg(self, vis: Any) -> None:
        """Keep native camera geometry for stand-zone setup and inspection."""
        try:
            ok, buf = self._cv2.imencode(
                ".jpg",
                vis,
                [int(self._cv2.IMWRITE_JPEG_QUALITY), 85],
            )
            if not ok:
                return
            jpeg = buf.tobytes()
        except Exception:  # noqa: BLE001
            return
        with self._lock:
            self._jpeg = jpeg
            self._jpeg_seq += 1

    def _capture_loop(self) -> None:
        try:
            from src.camera_utils import open_video_capture  # type: ignore

            cfg = self._load_config(self.config_path)
            cfg = dict(cfg)
            # Honor clinic.yaml checks (stand / headphones / eyes).
            checks = dict(cfg.get("checks") or {})
            checks.setdefault("stand", True)
            checks.setdefault("headphones", True)
            checks.setdefault("eyes", True)
            cfg["checks"] = checks
            spell = dict(cfg.get("spell") or {})
            spell["enabled"] = False
            cfg["spell"] = spell
            # Prefer lighter capture for Jetson CPU path
            video = dict(cfg.get("video") or {})
            video.setdefault("width", 640)
            video.setdefault("height", 480)
            cfg["video"] = video

            pipeline = self._Pipeline(cfg=cfg)
            with self._lock:
                self._pipeline = pipeline

            w = int(video.get("width") or 640)
            h = int(video.get("height") or 480)
            fps = int(video.get("fps") or 30)
            raw_cap = open_video_capture(self.source, width=w, height=h, fps=fps)
            cap = RealtimeFrameGrabber(raw_cap)

            window = "SmartEyes · AC readiness"
            # OpenCV HighGUI must run on the main thread on macOS; AC capture
            # runs in a daemon thread → fall back to headless if GUI fails.
            gui_ok = False
            if self.show_window:
                try:
                    self._cv2.namedWindow(window, self._cv2.WINDOW_NORMAL)
                    gui_ok = True
                except Exception as gui_exc:  # noqa: BLE001
                    logger.warning(
                        "SmartEyes preview window unavailable (%s); "
                        "continuing headless — coaching is on the chart UI (:8088)",
                        gui_exc,
                    )
                    gui_ok = False

            while not self._stop.is_set():
                if self._stt_inference_active.is_set():
                    time.sleep(0.01)
                    continue
                ok, frame = cap.read_latest(timeout=0.3)
                if not ok or frame is None:
                    with self._lock:
                        self._snap = ReadinessSnapshot(
                            ready=False,
                            coaching_vi="Mất tín hiệu camera SmartEyes",
                            error="camera_read_failed",
                        )
                    time.sleep(0.05)
                    continue
                if bool(cfg.get("video", {}).get("mirror", True)):
                    frame = self._cv2.flip(frame, 1)
                result = pipeline.process_frame(frame)
                snap = map_smarteyes_state(result.state)
                with self._lock:
                    want_preview = bool(self._preview_enabled)
                if want_preview:
                    try:
                        vis = pipeline.render(result)
                        self._publish_jpeg(vis)
                        if gui_ok and vis is not None:
                            try:
                                self._cv2.imshow(window, vis)
                                key = self._cv2.waitKey(1) & 0xFF
                                if key in (ord("q"), ord("Q"), 27):
                                    logger.info(
                                        "SmartEyes window quit key — keep polling until AC stops"
                                    )
                            except Exception as gui_exc:  # noqa: BLE001
                                logger.warning(
                                    "SmartEyes preview failed; headless now: %s", gui_exc
                                )
                                gui_ok = False
                    except Exception:  # noqa: BLE001
                        logger.debug("SmartEyes JPEG preview encode failed", exc_info=True)
                with self._lock:
                    self._snap = snap
            cap.release()
        except Exception as exc:  # noqa: BLE001
            logger.exception("SmartEyes capture loop failed")
            msg = f"SmartEyes lỗi: {exc}"
            with self._lock:
                self._snap = ReadinessSnapshot(ready=False, coaching_vi=msg, error=str(exc))
            if self.strict:
                # Leave error on snapshot; WAIT_READY will timeout / fail.
                pass
        finally:
            try:
                self._cv2.destroyAllWindows()
            except Exception:  # noqa: BLE001
                pass


class SttBridge:
    def listen_one(
        self,
        *,
        timeout: float = 45.0,
        min_confidence: float = 0.55,
        head: str | None = None,
    ) -> SttResult:
        raise NotImplementedError

    def listen_chunk(
        self,
        *,
        timeout: float,
        min_confidence: float = 0.55,
        head: str | None = None,
        stop_flag: Any | None = None,
        ignore_initial_seconds: float = 0.0,
    ) -> SttResult:
        del ignore_initial_seconds
        if stop_flag is not None and stop_flag.is_set():
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="cancelled")
        return self.listen_one(
            timeout=timeout, min_confidence=min_confidence, head=head
        )

    def close(self) -> None:
        return None


class MockSttBridge(SttBridge):
    """Returns the expected letter with high confidence (tests / demo without mic)."""

    def __init__(self) -> None:
        self.expect_letter: str | None = None
        self.force_confidence: float = 0.95
        self.force_fail: bool = False
        # For head=three_labels demos: TRUE | SKIP | FALSE
        self.expect_confirm: str | None = "TRUE"

    def listen_one(
        self,
        *,
        timeout: float = 45.0,
        min_confidence: float = 0.55,
        head: str | None = None,
    ) -> SttResult:
        time.sleep(min(0.05, timeout))
        if self.force_fail:
            return SttResult(letter="[UNK]", confidence=0.2, reliable=False, raw="?")
        if (head or "sloan").strip().lower() == "three_labels":
            label = (self.expect_confirm or "TRUE").strip().upper()
            conf = self.force_confidence
            reliable = conf >= min_confidence
            return SttResult(
                letter=label if reliable else "[UNK]",
                confidence=conf,
                reliable=reliable,
                raw=label,
            )
        letter = self.expect_letter or random.choice(LETTER_POOL)
        conf = self.force_confidence
        reliable = conf >= min_confidence
        return SttResult(
            letter=letter if reliable else "[UNK]",
            confidence=conf,
            reliable=reliable,
            raw=letter,
        )


class UiSttBridge(SttBridge):
    """Clinic: wait for a tablet letter answer (no auto-fill)."""

    def __init__(self) -> None:
        self._hub: Any = None
        self._stop: Any = None

    def bind(self, hub: Any, *, stop_flag: Any = None) -> None:
        self._hub = hub
        self._stop = stop_flag

    def listen_one(
        self,
        *,
        timeout: float = 45.0,
        min_confidence: float = 0.55,
        head: str | None = None,
    ) -> SttResult:
        if self._hub is None:
            logger.error("UiSttBridge has no display hub; treat as timeout")
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="no_hub")
        wait = getattr(self._hub, "wait_ui_event", None)
        if wait is None:
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="no_wait")
        # Confirm-protocol voice head maps to chart Đúng / Sai / Bỏ qua buttons.
        if (head or "sloan").strip().lower() == "three_labels":
            ev = wait(
                {"confirm_yes", "confirm_no", "skip_letter"},
                timeout=timeout,
                stop_flag=self._stop,
            )
            if not ev:
                return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="timeout")
            action = str(ev.get("action") or "")
            if action == "confirm_yes":
                return SttResult(letter="TRUE", confidence=1.0, reliable=True, raw="confirm_yes")
            if action == "confirm_no":
                return SttResult(letter="FALSE", confidence=1.0, reliable=True, raw="confirm_no")
            if action == "skip_letter":
                return SttResult(letter="SKIP", confidence=1.0, reliable=True, raw="skip")
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw=action or "unknown")
        ev = wait(
            {"speak_letter", "skip_letter"},
            timeout=timeout,
            stop_flag=self._stop,
        )
        if not ev:
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="timeout")
        action = str(ev.get("action") or "")
        if action == "skip_letter":
            # Orchestrator replaces letter with current target when raw=skip
            return SttResult(letter="*", confidence=1.0, reliable=True, raw="skip")
        payload = ev.get("payload") if isinstance(ev, dict) else None
        letter = ""
        if isinstance(payload, dict):
            letter = str(payload.get("letter") or "").strip().upper()
        if not letter:
            letter = str(ev.get("letter") or "").strip().upper()
        if len(letter) != 1 or not ("A" <= letter <= "Z"):
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw=letter or "?")
        conf = max(float(min_confidence), 0.95)
        return SttResult(letter=letter, confidence=conf, reliable=True, raw=letter)


class ExclusiveInputSttBridge(SttBridge):
    """Use the one answer source chosen for this examination."""

    def __init__(self, speech: SttBridge, tablet: UiSttBridge) -> None:
        self.speech = speech
        self.tablet = tablet
        self._hub: Any = None
        self.shared_microphone = getattr(speech, "shared_microphone", None)

    def bind(self, hub: Any, *, stop_flag: Any = None) -> None:
        self._hub = hub
        self.tablet.bind(hub, stop_flag=stop_flag)

    def update_config(self, **kwargs: Any) -> None:
        if hasattr(self.speech, "update_config"):
            self.speech.update_config(**kwargs)
            self.shared_microphone = getattr(self.speech, "shared_microphone", None)

    def listen_one(self, *, timeout: float = 45.0, min_confidence: float = 0.55,
                   head: str | None = None) -> SttResult:
        return self.listen_chunk(timeout=timeout, min_confidence=min_confidence, head=head)

    def listen_chunk(self, *, timeout: float, min_confidence: float = 0.55,
                     head: str | None = None, stop_flag: Any | None = None,
                     ignore_initial_seconds: float = 0.0) -> SttResult:
        if self._hub is not None and self._hub.input_mode == "tablet":
            return self.tablet.listen_chunk(
                timeout=timeout, min_confidence=min_confidence,
                head=head, stop_flag=stop_flag,
            )
        return self.speech.listen_chunk(
            timeout=timeout, min_confidence=min_confidence, head=head,
            stop_flag=stop_flag, ignore_initial_seconds=ignore_initial_seconds,
        )

    def close(self) -> None:
        self.speech.close()


class SloanSttBridge(SttBridge):
    def __init__(
        self,
        sloan_root: Path,
        min_confidence: float = 0.55,
        *,
        audio_url: str = "",
        audio_sample_rate: int = 48000,
        energy_threshold: float = 0.025,
        silence_duration: float = 0.35,
        min_margin: float = 0.05,
        min_voiced_seconds: float = 0.22,
        vad_padding_seconds: float = 0.12,
        class_confidence_thresholds: dict[str, float] | None = None,
        confirm_dung_priority_threshold: float = 0.40,
        chart_audio_url: str = "",
        mic_hub: Any | None = None,
        input_device: str = "",
    ) -> None:
        self.sloan_root = sloan_root
        self.min_confidence = min_confidence
        self.audio_url = str(audio_url or "").strip()
        self.chart_audio_url = str(chart_audio_url or "").strip()
        self.mic_hub = mic_hub
        self.input_device = str(input_device or "").strip()
        self.audio_sample_rate = int(audio_sample_rate)
        self.energy_threshold = float(energy_threshold)
        self.silence_duration = float(silence_duration)
        self.min_margin = float(min_margin)
        self.min_voiced_seconds = float(min_voiced_seconds)
        self.vad_padding_seconds = max(0.0, float(vad_padding_seconds))
        self.class_confidence_thresholds = {
            str(label).strip().upper(): max(0.0, min(1.0, float(threshold)))
            for label, threshold in (class_confidence_thresholds or {}).items()
            if str(label).strip().upper() in set("CDHKNORSVZ")
        }
        self.confirm_dung_priority_threshold = max(
            0.0, min(1.0, float(confirm_dung_priority_threshold))
        )
        self._vad_noise_floor: dict[int, float] = {}
        self.shared_microphone: SharedMicrophoneStream | None = None
        if getattr(self.mic_hub, "audio_input", "device") == "device":
            self.shared_microphone = SharedMicrophoneStream(
                self.input_device,
                samplerate=16000,
            )
        self._recognizer = None
        self.inference_activity_callback: Callable[[bool], None] | None = None
        self._fallback = MockSttBridge()
        try:
            if str(sloan_root) not in sys.path:
                sys.path.insert(0, str(sloan_root))
            from runtime import Recognizer  # type: ignore

            self._recognizer = Recognizer(enabled_heads=("sloan",))
            logger.info("Sloan STT recognizer loaded from %s", sloan_root)
            self._warm_up_recognizer()
        except Exception:  # noqa: BLE001
            logger.exception("Sloan STT unavailable; mock STT will be used for listen_one")

        # Open once at service startup so the first spoken letter cannot be
        # clipped by PortAudio/Pulse setup. Failure is retried lazily on listen.
        if self.shared_microphone is not None:
            self.shared_microphone.start()

    def update_config(
        self,
        *,
        min_confidence: float | None = None,
        energy_threshold: float | None = None,
        input_device: str | None = None,
    ) -> None:
        if min_confidence is not None:
            self.min_confidence = float(min_confidence)
        if energy_threshold is not None:
            self.energy_threshold = float(energy_threshold)
        if input_device is not None and str(input_device).strip() != self.input_device:
            self.input_device = str(input_device).strip()
            if self.shared_microphone is not None:
                try:
                    self.shared_microphone.stop()
                except Exception:
                    pass
                self.shared_microphone = SharedMicrophoneStream(
                    self.input_device,
                    samplerate=16000,
                )
                try:
                    self.shared_microphone.start()
                except Exception:
                    logger.warning("Failed to restart shared microphone for %s", self.input_device)

    def _warm_up_recognizer(self) -> None:
        """Pay CUDA/kernel startup cost at service boot, before the first patient."""
        if self._recognizer is None:
            return
        import numpy as np

        started = time.monotonic()
        t = np.arange(8000, dtype=np.float32) / 16000.0
        probe = (0.01 * np.sin(2.0 * np.pi * 500.0 * t)).astype(np.float32)
        self._recognizer.predict(
            probe,
            16000,
            min_confidence=self.min_confidence,
            min_margin=self.min_margin,
            head="sloan",
            class_confidence_thresholds={},
            confirm_dung_priority_threshold=self.confirm_dung_priority_threshold,
        )
        logger.info("Sloan STT warm-up complete in %.3fs", time.monotonic() - started)

    def _listen_url(self) -> str:
        prefer_chart = (
            getattr(self.mic_hub, "audio_input", "") == "browser"
            or getattr(self.mic_hub, "mic_live", False)
        )
        if self.chart_audio_url and prefer_chart:
            return self.chart_audio_url
        return self.audio_url

    def _listen_device(
        self,
        *,
        timeout: float,
        min_confidence: float,
        head: str,
    ) -> SttResult:
        try:
            import numpy as np
        except ImportError:
            logger.warning("numpy missing; mock STT")
            return self._fallback.listen_one(
                timeout=timeout, min_confidence=min_confidence, head=head
            )
        from ac.audio_device import resolve_sounddevice

        device = resolve_sounddevice(self.input_device, kind="input")
        sr = 16000
        logger.info(
            "Listening on local mic device=%s head=%s vad_th=%.4f min_conf=%.3f",
            device if device is not None else self.input_device or "default",
            head,
            self.energy_threshold,
            min_confidence,
        )
        mono, used_sr = self._record_device(timeout, samplerate=sr, device=device)
        if getattr(mono, "size", 0) == 0:
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="silence")
        pred = self._recognizer.predict(
            np.asarray(mono).reshape(-1),
            used_sr,
            min_confidence=min_confidence,
            min_margin=self.min_margin,
            head=head,
            class_confidence_thresholds=self.class_confidence_thresholds,
            confirm_dung_priority_threshold=self.confirm_dung_priority_threshold,
        )
        return self._stt_result_from_pred(pred)

    def _record_device(
        self,
        timeout: float,
        *,
        samplerate: int,
        device: int | str | None,
    ) -> tuple[Any, int]:
        """Read one utterance from the persistent Yealink/Pulse stream."""
        del device
        if self.shared_microphone is None:
            self.shared_microphone = SharedMicrophoneStream(
                self.input_device,
                samplerate=samplerate,
            )
        cursor = self.shared_microphone.cursor()

        def read_chunks(wait_seconds: float) -> list[Any]:
            nonlocal cursor
            chunks, cursor = self.shared_microphone.read_after(cursor, wait_seconds)
            return chunks

        return self._record_vad(timeout, samplerate=samplerate, read_chunks=read_chunks)

    def _record_device_chunk(
        self,
        timeout: float,
        *,
        samplerate: int = 16000,
        stop_flag: Any | None = None,
    ) -> tuple[list[Any], int]:
        """Capture one fixed window without reopening or stopping the microphone."""
        if self.shared_microphone is None:
            self.shared_microphone = SharedMicrophoneStream(
                self.input_device, samplerate=samplerate
            )
        cursor = self.shared_microphone.cursor()
        chunks: list[Any] = []
        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline and not (
            stop_flag is not None and stop_flag.is_set()
        ):
            incoming, cursor = self.shared_microphone.read_after(
                cursor, min(0.15, max(0.0, deadline - time.monotonic()))
            )
            chunks.extend(incoming)
        return chunks, samplerate

    def _split_vad_segments(
        self, chunks: list[Any], *, samplerate: int
    ) -> list[Any]:
        """Filter a fixed window and return padded speech segments."""
        import math
        import numpy as np
        from scipy.signal import butter, sosfilt

        if not chunks:
            return []
        highpass = butter(2, 80.0, btype="highpass", fs=samplerate, output="sos")
        lowpass = butter(
            2, min(3400.0, samplerate * 0.45), btype="lowpass",
            fs=samplerate, output="sos"
        )
        sos = np.concatenate([highpass, lowpass], axis=0)
        filtered = sosfilt(sos, np.concatenate(chunks)) * 1.2
        sizes = [len(chunk) for chunk in chunks]
        frames: list[Any] = []
        offset = 0
        for size in sizes:
            frames.append(filtered[offset:offset + size].astype(np.float32))
            offset += size

        noise = self._vad_noise_floor.get(samplerate, 0.0025)
        voiced: list[bool] = []
        for frame in frames:
            rms = float(np.sqrt(np.mean(frame * frame) + 1e-10))
            gate = max(self.energy_threshold, noise * 2.2)
            is_voice = rms >= gate
            voiced.append(is_voice)
            if not is_voice:
                noise = noise * 0.95 + rms * 0.05
        self._vad_noise_floor[samplerate] = noise

        frame_seconds = float(np.median(sizes)) / samplerate
        end_gap = max(1, int(math.ceil(self.silence_duration / frame_seconds)))
        pad = max(0, int(math.ceil(self.vad_padding_seconds / frame_seconds)))
        groups: list[tuple[int, int]] = []
        start: int | None = None
        last_voice = -1
        for i, is_voice in enumerate(voiced):
            if is_voice:
                if start is None and i > 0 and voiced[i - 1]:
                    start = i - 1
                if start is not None:
                    last_voice = i
            elif start is not None and i - last_voice >= end_gap:
                groups.append((start, last_voice))
                start = None
        if start is not None:
            groups.append((start, last_voice))

        segments: list[Any] = []
        for start, end in groups:
            voice_count = sum(voiced[start:end + 1])
            voice_seconds = sum(sizes[i] for i in range(start, end + 1) if voiced[i]) / samplerate
            if voice_count < 3 or voice_seconds < self.min_voiced_seconds:
                continue
            lo, hi = max(0, start - pad), min(len(frames), end + pad + 1)
            segments.append(np.concatenate(frames[lo:hi]).astype(np.float32, copy=False))
        return segments

    def listen_chunk(
        self,
        *,
        timeout: float,
        min_confidence: float = 0.55,
        head: str | None = None,
        stop_flag: Any | None = None,
        ignore_initial_seconds: float = 0.0,
    ) -> SttResult:
        """Predict every VAD segment; highest confidence wins, later wins ties."""
        stt_head = (head or "sloan").strip().lower() or "sloan"
        if self._recognizer is None or getattr(self.mic_hub, "audio_input", "") != "device":
            return self.listen_one(
                timeout=timeout, min_confidence=min_confidence, head=stt_head
            )
        try:
            chunks, sr = self._record_device_chunk(timeout, stop_flag=stop_flag)
            if stop_flag is not None and stop_flag.is_set():
                return SttResult(
                    letter="[UNK]", confidence=0.0, reliable=False, raw="cancelled"
                )
            skip_samples = max(0, int(round(float(ignore_initial_seconds) * sr)))
            if skip_samples:
                trimmed: list[Any] = []
                for chunk in chunks:
                    if skip_samples >= len(chunk):
                        skip_samples -= len(chunk)
                        continue
                    trimmed.append(chunk[skip_samples:])
                    skip_samples = 0
                chunks = trimmed
            segments = self._split_vad_segments(chunks, samplerate=sr)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sloan chunk capture failed: %s", exc)
            return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="capture_error")

        best: SttResult | None = None
        best_candidate: SttResult | None = None
        dung_priority_threshold = float(
            getattr(self, "confirm_dung_priority_threshold", 0.40)
        )
        activity = getattr(self, "inference_activity_callback", None)
        if activity is not None:
            activity(True)
        try:
            for index, segment in enumerate(segments):
                if stop_flag is not None and stop_flag.is_set():
                    return SttResult(
                        letter="[UNK]", confidence=0.0, reliable=False, raw="cancelled"
                    )
                pred = self._recognizer.predict(
                    segment,
                    sr,
                    min_confidence=min_confidence,
                    min_margin=self.min_margin,
                    head=stt_head,
                    class_confidence_thresholds={},
                    confirm_dung_priority_threshold=dung_priority_threshold,
                )
                result = self._stt_result_from_pred(pred)
                if (
                    best_candidate is None
                    or result.confidence >= best_candidate.confidence
                ):
                    best_candidate = result
                result_is_priority_dung = (
                    stt_head == "three_labels"
                    and result.letter == "TRUE"
                    and str(result.raw or "").upper() == "DUNG"
                    and result.confidence >= dung_priority_threshold
                )
                eligible = result.reliable and (
                    result_is_priority_dung
                    or result.confidence >= float(min_confidence)
                )
                logger.info(
                    "Sloan chunk segment=%s/%s head=%s label=%s raw=%s conf=%.3f eligible=%s",
                    index + 1, len(segments), stt_head, result.letter,
                    result.raw, result.confidence, eligible,
                )
                if eligible:
                    best_is_priority_dung = bool(
                        best
                        and stt_head == "three_labels"
                        and best.letter == "TRUE"
                        and str(best.raw or "").upper() == "DUNG"
                        and best.confidence >= dung_priority_threshold
                    )
                    if (
                        best is None
                        or (result_is_priority_dung and not best_is_priority_dung)
                        or (result_is_priority_dung == best_is_priority_dung
                            and result.confidence >= best.confidence)
                    ):
                        best = result
        finally:
            if activity is not None:
                activity(False)
        if best is not None:
            return best
        # Preserve a real VAD segment's confidence even when margin/threshold
        # rejects its label. The controller needs that value to distinguish a
        # low-confidence miss from the configurable replacement band.
        if best_candidate is not None:
            return best_candidate
        return SttResult(letter="[UNK]", confidence=0.0, reliable=False, raw="chunk_unrecognized")

    def _record_vad(
        self,
        timeout: float,
        *,
        samplerate: int,
        read_chunks: Callable[[float], list[Any]],
    ) -> tuple[Any, int]:
        """Adaptive, filtered VAD shared by local and network capture paths.

        This intentionally mirrors ``infer_sloan_realtime.py``: 80–3400 Hz
        band-pass, adaptive noise floor, two-chunk onset, short end silence,
        voiced-ratio validation and 1.2x input gain.
        """
        import numpy as np
        from scipy.signal import butter, sosfilt

        highpass = butter(2, 80.0, btype="highpass", fs=samplerate, output="sos")
        lowpass = butter(
            2,
            min(3400.0, samplerate * 0.45),
            btype="lowpass",
            fs=samplerate,
            output="sos",
        )
        sos = np.concatenate([highpass, lowpass], axis=0)
        filter_state = np.zeros((sos.shape[0], 2), dtype=np.float64)
        noise_floors = getattr(self, "_vad_noise_floor", {})
        self._vad_noise_floor = noise_floors
        noise_floor = noise_floors.get(samplerate, 0.0025)
        noise_multiplier = 2.2
        input_gain = 1.2
        min_voiced_chunks = 3
        min_voiced_ratio = 0.35
        max_active_seconds = 2.8
        pre: deque[Any] = deque(maxlen=3)
        buffers: list[Any] = []
        onset_chunks = 0
        voiced_chunks = 0
        total_chunks = 0
        active_samples = 0
        silence_samples = 0
        active = False
        last_rms = 0.0
        last_gate = self.energy_threshold
        deadline = time.monotonic() + max(1.0, timeout)

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            incoming = read_chunks(min(0.15, max(0.0, remaining)))
            if not incoming:
                continue
            for raw_chunk in incoming:
                filtered, filter_state = sosfilt(sos, raw_chunk, zi=filter_state)
                chunk = (filtered * input_gain).astype(np.float32)
                rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-10))
                gate = max(self.energy_threshold, noise_floor * noise_multiplier)
                last_rms = rms
                last_gate = gate

                if not active:
                    if rms < gate:
                        noise_floor = noise_floor * 0.95 + rms * 0.05
                    pre.append(chunk)
                    onset_chunks = onset_chunks + 1 if rms >= gate else 0
                    if onset_chunks >= 2:
                        active = True
                        buffers = list(pre)
                        silence_samples = 0
                        active_samples = sum(item.size for item in buffers)
                        voiced_chunks = onset_chunks
                        total_chunks = len(pre)
                else:
                    buffers.append(chunk)
                    active_samples += chunk.size
                    total_chunks += 1
                    if rms >= gate:
                        voiced_chunks += 1
                        silence_samples = 0
                    else:
                        silence_samples += chunk.size

                    should_finish = (
                        silence_samples >= samplerate * self.silence_duration
                        or active_samples >= samplerate * max_active_seconds
                    )
                    if should_finish:
                        duration = active_samples / float(samplerate)
                        voiced_ratio = voiced_chunks / max(1, total_chunks)
                        accepted = (
                            duration >= self.min_voiced_seconds
                            and voiced_chunks >= min_voiced_chunks
                            and voiced_ratio >= min_voiced_ratio
                        )
                        if accepted:
                            audio = np.concatenate(buffers).astype(np.float32, copy=False)
                            self._vad_noise_floor[samplerate] = noise_floor
                            logger.info(
                                "Sloan VAD accepted duration=%.3fs voiced=%s/%s "
                                "noise=%.4f gate=%.4f",
                                duration,
                                voiced_chunks,
                                total_chunks,
                                noise_floor,
                                gate,
                            )
                            return audio, samplerate
                        logger.debug(
                            "Sloan VAD rejected duration=%.3fs voiced=%s/%s "
                            "noise=%.4f gate=%.4f",
                            duration,
                            voiced_chunks,
                            total_chunks,
                            noise_floor,
                            gate,
                        )
                        active = False
                        buffers = []
                        pre.clear()
                        onset_chunks = 0
                        voiced_chunks = 0
                        total_chunks = 0
                        active_samples = 0
                        silence_samples = 0

        if active and buffers:
            duration = active_samples / float(samplerate)
            voiced_ratio = voiced_chunks / max(1, total_chunks)
            if (
                duration >= self.min_voiced_seconds
                and voiced_chunks >= min_voiced_chunks
                and voiced_ratio >= min_voiced_ratio
            ):
                self._vad_noise_floor[samplerate] = noise_floor
                return np.concatenate(buffers).astype(np.float32, copy=False), samplerate
        self._vad_noise_floor[samplerate] = noise_floor
        logger.info(
            "Sloan VAD silence timeout=%.2fs rms=%.4f gate=%.4f noise=%.4f",
            timeout,
            last_rms,
            last_gate,
            noise_floor,
        )
        return np.empty(0, dtype=np.float32), samplerate

    def _record_network(
        self,
        timeout: float,
        *,
        audio_url: str | None = None,
    ) -> tuple[Any, int]:
        """Capture one VAD-delimited utterance from float32le HTTP audio.

        Short noise spikes below ``min_voiced_seconds`` are discarded so the
        MacBook mic floor does not trigger false “please repeat” flashes.
        """
        sr = self.audio_sample_rate
        block_samples = max(256, int(sr * 0.03))
        block_bytes = block_samples * 4
        req = urllib.request.Request(
            audio_url or self.audio_url,
            headers={"User-Agent": "AC-Sloan-STT/1.0"},
        )
        with urllib.request.urlopen(req, timeout=max(5.0, timeout + 2.0)) as response:

            def read_chunks(_wait_seconds: float) -> list[Any]:
                import numpy as np

                raw = response.read(block_bytes)
                if not raw:
                    return []
                usable = len(raw) - (len(raw) % 4)
                if usable <= 0:
                    return []
                return [np.frombuffer(raw[:usable], dtype="<f4").copy()]

            return self._record_vad(timeout, samplerate=sr, read_chunks=read_chunks)

    def close(self) -> None:
        if self.shared_microphone is not None:
            self.shared_microphone.close()

    def listen_one(
        self,
        *,
        timeout: float = 45.0,
        min_confidence: float | None = None,
        head: str | None = None,
    ) -> SttResult:
        conf_th = min_confidence if min_confidence is not None else self.min_confidence
        stt_head = (head or "sloan").strip().lower() or "sloan"
        if self._recognizer is None:
            return self._fallback.listen_one(
                timeout=timeout, min_confidence=conf_th, head=stt_head
            )
        url = self._listen_url()
        if getattr(self.mic_hub, "audio_input", "") == "device" and self.input_device:
            url = ""
        if url:
            try:
                logger.info(
                    "Listening to network mic %s (head=%s th=%.4f)",
                    url,
                    stt_head,
                    self.energy_threshold,
                )
                mono, sr = self._record_network(timeout, audio_url=url)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Network Sloan mic failed: %s", exc)
                if url != self.audio_url and self.audio_url:
                    try:
                        logger.warning("Retrying device mic %s", self.audio_url)
                        mono, sr = self._record_network(
                            timeout, audio_url=self.audio_url
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("Device Sloan mic also failed")
                        return self._listen_device(
                            timeout=timeout, min_confidence=conf_th, head=stt_head
                        )
                else:
                    return self._listen_device(
                        timeout=timeout, min_confidence=conf_th, head=stt_head
                    )
            if getattr(mono, "size", 0) == 0:
                return SttResult(
                    letter="[UNK]", confidence=0.0, reliable=False, raw="silence"
                )
        else:
            return self._listen_device(
                timeout=timeout, min_confidence=conf_th, head=stt_head
            )
        pred = self._recognizer.predict(
            mono,
            sr,
            min_confidence=conf_th,
            min_margin=self.min_margin,
            head=stt_head,
            class_confidence_thresholds=self.class_confidence_thresholds,
            confirm_dung_priority_threshold=self.confirm_dung_priority_threshold,
        )
        return self._stt_result_from_pred(pred)

    @staticmethod
    def _stt_result_from_pred(pred: Any) -> SttResult:
        """Map closed-set skip bucket (X / bỏ qua) to skip, never a confirmable letter."""
        skip_tokens = {"X", "SKIP", "*", "BO_QUA"}
        rows: list[dict[str, Any]] = []
        if (
            isinstance(pred, dict)
            and "prediction" not in pred
            and ("sloan" in pred or "three_labels" in pred)
        ):
            rows = [v for v in pred.values() if isinstance(v, dict)]
        elif isinstance(pred, dict):
            rows = [pred]
        for row in rows:
            letter = str(row.get("prediction") or "").strip().upper()
            raw = str(row.get("detail") or row.get("raw") or "").strip().upper()
            if letter in skip_tokens or raw in skip_tokens:
                return SttResult(letter="*", confidence=1.0, reliable=True, raw="skip")
        row = rows[0] if rows else {}
        return SttResult(
            letter=str(row.get("prediction") or "[UNK]"),
            confidence=float(row.get("confidence") or 0.0),
            reliable=bool(row.get("reliable")),
            raw=str(row.get("detail") or row.get("raw") or row.get("prediction") or ""),
            acceptance_threshold=(
                float(row["acceptance_threshold"])
                if row.get("acceptance_threshold") is not None
                else None
            ),
        )


def build_readiness_bridge(
    kind: str,
    smarteyes_root: Path,
    *,
    config_path: Path | None = None,
    source: str | int = "macbook",
    show_window: bool = True,
    strict: bool = True,
    preview_enabled: bool = False,
) -> ReadinessBridge:
    if kind == "smarteyes":
        return SmartEyesReadinessBridge(
            smarteyes_root,
            config_path=config_path,
            source=source,
            show_window=show_window,
            strict=strict,
            preview_enabled=preview_enabled,
        )
    return MockReadinessBridge()


def build_stt_bridge(
    kind: str,
    sloan_root: Path,
    min_confidence: float,
    *,
    audio_url: str = "",
    audio_sample_rate: int = 48000,
    energy_threshold: float = 0.025,
    silence_duration: float = 0.35,
    min_margin: float = 0.05,
    min_voiced_seconds: float = 0.22,
    vad_padding_seconds: float = 0.12,
    class_confidence_thresholds: dict[str, float] | None = None,
    confirm_dung_priority_threshold: float = 0.40,
    chart_audio_url: str = "",
    mic_hub: Any | None = None,
    input_device: str = "",
) -> SttBridge:
    key = (kind or "mock").strip().lower()
    if key == "sloan":
        return SloanSttBridge(
            sloan_root,
            min_confidence=min_confidence,
            audio_url=audio_url,
            audio_sample_rate=audio_sample_rate,
            energy_threshold=energy_threshold,
            silence_duration=silence_duration,
            min_margin=min_margin,
            min_voiced_seconds=min_voiced_seconds,
            vad_padding_seconds=vad_padding_seconds,
            class_confidence_thresholds=class_confidence_thresholds,
            confirm_dung_priority_threshold=confirm_dung_priority_threshold,
            chart_audio_url=chart_audio_url,
            mic_hub=mic_hub,
            input_device=input_device,
        )
    if key == "ui":
        return UiSttBridge()
    return MockSttBridge()


def _sloan_upper(letter: str) -> str:
    return str(letter or "").strip().upper()


def next_sloan_letter(
    recent: list[str] | None = None,
    *,
    pool: list[str] | None = None,
) -> str:
    """Pick one Sloan letter that is not among the last 3 shown.

    If that would empty the pool, avoid only the last 1, then any letter.
    """
    letters = list(pool) if pool is not None else list(LETTER_POOL)
    if not letters:
        raise ValueError("Sloan letter pool is empty")
    window = [_sloan_upper(x) for x in (recent or []) if _sloan_upper(x)]
    window = window[-LETTER_RECENT_WINDOW:]
    exclude_layers: list[set[str]] = [set(window)]
    if window:
        exclude_layers.append({window[-1]})
    exclude_layers.append(set())
    for exclude in exclude_layers:
        choices = [L for L in letters if L not in exclude]
        if choices:
            return random.choice(choices)
    return random.choice(letters)


def random_letters(
    n: int = 5,
    *,
    recent: list[str] | None = None,
    pool: list[str] | None = None,
) -> list[str]:
    """Pick n Sloan letters, each avoiding the closest 3 already shown.

    ``recent`` is prior shown letters (last 3 are used). Picks in this call
    also update that window, so a row change still avoids the previous row.
    """
    history = [_sloan_upper(x) for x in (recent or []) if _sloan_upper(x)]
    out: list[str] = []
    for _ in range(max(0, int(n))):
        letter = next_sloan_letter(history, pool=pool)
        out.append(letter)
        history.append(letter)
    return out
