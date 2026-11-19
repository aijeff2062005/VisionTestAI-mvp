"""Display WebSocket hub + FastAPI server for the character chart."""

from __future__ import annotations

import asyncio
import hashlib
import httpx
import ipaddress
import json
import logging
import math
import os
import re
import signal
import shutil
import socket
import threading
import time
import uuid
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

DISPLAY_DIR = Path(__file__).resolve().parents[2] / "display"
CONTROL_DIR = Path(__file__).resolve().parents[2] / "control"
SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"
_SAFE_WAV = re.compile(r"^[A-Za-z0-9._-]+\.wav$")
_INSTRUCTION_DEFAULTS = {
    "stand": "/static/art/vitringoi.jpg",
    "face": "/static/art/huongdanquetkhuonmat.jpg",
    "cover_right": "/static/art/domattrai.jpg",
    "cover_left": "/static/art/domatphai.jpg",
}
_INSTRUCTION_IMAGE_LIMIT = 10 * 1024 * 1024

_DEFAULT_CORS = (
    "http://192.168.1.78:8000,"
    "http://127.0.0.1:8000,"
    "http://localhost:8000"
)


class DisplayHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._broadcast_lock = asyncio.Lock()
        self.last_command: dict[str, Any] = {
            "type": "show_message",
            "mode": "idle",
            "scene": "face",
            "text_vi": "Nhìn vào máy nhận diện khuôn mặt.",
            "exam_mode": True,
        }
        self.last_command_at: float = time.time()
        self.display_revision = 0
        self.display_boot_id = uuid.uuid4().hex
        self.last_kiosk_applied: dict[str, Any] = {}
        self.last_result: tuple[str, float] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ui_events: list[dict[str, Any]] = []
        self._ui_event = threading.Event()
        self.audio_input: str = "device"
        self.audio_output: str = "sounddevice"
        self.audio_device_label: str = ""
        self.input_mode: str = "speak"
        self._mode_choice_open = False
        self.active_letter_window_id: str | None = None
        self._stimulus_ready_window_id: str | None = None
        self._stimulus_ready_event = threading.Event()
        self._mode_lock = threading.Lock()
        self.mic_sample_rate: int = 48000
        self._mic_lock = threading.Lock()
        self._mic_buf = bytearray()
        self._mic_event = threading.Event()
        self._mic_clients = 0
        self.display_metrics: dict[str, Any] = {}

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def mic_live(self) -> bool:
        return self._mic_clients > 0

    def mic_connect(self) -> None:
        with self._mic_lock:
            self._mic_clients += 1

    def mic_disconnect(self) -> None:
        with self._mic_lock:
            self._mic_clients = max(0, self._mic_clients - 1)
            if self._mic_clients == 0:
                self._mic_buf.clear()

    def push_mic_pcm(self, data: bytes) -> None:
        if not data:
            return
        with self._mic_lock:
            self._mic_buf.extend(data)
            max_bytes = int(self.mic_sample_rate) * 4 * 2
            if len(self._mic_buf) > max_bytes:
                del self._mic_buf[:-max_bytes]
            self._mic_event.set()

    def read_mic_pcm(self, nbytes: int, timeout: float) -> bytes:
        deadline = time.time() + max(0.01, timeout)
        while True:
            with self._mic_lock:
                if len(self._mic_buf) >= nbytes:
                    chunk = bytes(self._mic_buf[:nbytes])
                    del self._mic_buf[:nbytes]
                    return chunk
            remaining = deadline - time.time()
            if remaining <= 0:
                return b"\x00" * nbytes
            self._mic_event.wait(timeout=min(0.05, remaining))
            self._mic_event.clear()

    def push_ui_event(self, event: dict[str, Any]) -> None:
        self._ui_events.append(event)
        self._ui_event.set()

    def reset_input_mode(self, default_mode: str) -> None:
        with self._mode_lock:
            self.input_mode = default_mode
            self._mode_choice_open = False
        self.drain_ui_actions({"select_input_mode"})

    def begin_input_mode_choice(self, default_mode: str) -> None:
        self.reset_input_mode(default_mode)
        with self._mode_lock:
            self._mode_choice_open = True

    def choose_input_mode(self, mode: str) -> bool:
        if mode not in {"speak", "tablet"}:
            return False
        with self._mode_lock:
            if not self._mode_choice_open:
                return False
            self.input_mode = mode
            self._mode_choice_open = False
        return True

    def finish_input_mode_choice(self) -> str:
        with self._mode_lock:
            self._mode_choice_open = False
            return self.input_mode

    def consume_ui_action(self, actions: set[str]) -> str | None:
        """Non-blocking: remove and return first matching action, if any."""
        wanted = {str(a) for a in actions}
        kept: list[dict[str, Any]] = []
        matched: str | None = None
        for ev in self._ui_events:
            act = str(ev.get("action") or "")
            if matched is None and act in wanted:
                matched = act
            else:
                kept.append(ev)
        self._ui_events = kept
        return matched

    def drain_ui_actions(self, actions: set[str] | None = None) -> None:
        """Drop pending UI events (optionally only matching ``actions``)."""
        if actions is None:
            self._ui_events.clear()
            self._ui_event.clear()
            return
        wanted = {str(a) for a in actions}
        self._ui_events = [
            ev for ev in self._ui_events if str(ev.get("action") or "") not in wanted
        ]

    def wait_ui_action(
        self,
        actions: set[str],
        *,
        timeout: float = 120.0,
        stop_flag: Any = None,
    ) -> str | None:
        """Block until display sends one of ``actions`` (button click)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_flag is not None and getattr(stop_flag, "is_set", lambda: False)():
                return None
            # Drain matching events
            kept: list[dict[str, Any]] = []
            matched: str | None = None
            for ev in self._ui_events:
                act = str(ev.get("action") or "")
                if matched is None and act in actions:
                    matched = act
                else:
                    kept.append(ev)
            self._ui_events = kept
            if matched:
                self._ui_event.clear()
                return matched
            remaining = max(0.05, deadline - time.time())
            self._ui_event.wait(timeout=min(0.5, remaining))
            self._ui_event.clear()
        return None

    def wait_ui_event(
        self,
        actions: set[str],
        *,
        timeout: float = 120.0,
        stop_flag: Any = None,
    ) -> dict[str, Any] | None:
        """Block until display sends one of ``actions`` (button click + payload)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_flag is not None and getattr(stop_flag, "is_set", lambda: False)():
                return None

            # Drain matching events
            kept: list[dict[str, Any]] = []
            matched: dict[str, Any] | None = None
            for ev in self._ui_events:
                act = str(ev.get("action") or "")
                if matched is None and act in actions:
                    matched = ev
                else:
                    kept.append(ev)
            self._ui_events = kept

            if matched:
                self._ui_event.clear()
                return matched

            remaining = max(0.05, deadline - time.time())
            self._ui_event.wait(timeout=min(0.5, remaining))
            self._ui_event.clear()
        return None

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._broadcast_lock:
            await asyncio.wait_for(ws.send_json({"type": "input_mode", "input_mode": self.input_mode}), timeout=0.75)
            await asyncio.wait_for(ws.send_json(self.last_command), timeout=0.75)
            async with self._lock:
                self._clients.add(ws)

    def arm_stimulus_window(self, window_id: str) -> None:
        self.active_letter_window_id = window_id
        self._stimulus_ready_window_id = None
        self._stimulus_ready_event.clear()

    def acknowledge_stimulus_ready(
        self, window_id: str, *, from_kiosk: bool, font_ready: bool
    ) -> bool:
        if (
            not from_kiosk
            or not font_ready
            or not window_id
            or window_id != self.active_letter_window_id
        ):
            return False
        self._stimulus_ready_window_id = window_id
        self._stimulus_ready_event.set()
        return True

    def wait_stimulus_ready(
        self, window_id: str, timeout: float, *, stop_flag: Any = None
    ) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while self._stimulus_ready_window_id != window_id:
            if stop_flag is not None and stop_flag.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._stimulus_ready_event.wait(min(0.1, remaining))
        matched = self._stimulus_ready_window_id == window_id
        if not matched and self.active_letter_window_id == window_id:
            self.active_letter_window_id = None
        self._stimulus_ready_window_id = None
        self._stimulus_ready_event.clear()
        return matched

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    _TRANSIENT_TYPES = frozenset(
        {
            "play_audio", "stop_audio", "letter_pad", "display_config",
            "display_calibration", "input_mode", "listen_window_start",
            "instruction_images",
        }
    )

    def _record_display_command(self, command: dict[str, Any]) -> dict[str, Any]:
        self.display_revision += 1
        command = {
            **command,
            "_display_revision": self.display_revision,
            "_display_boot_id": self.display_boot_id,
            "_display_sent_at_ms": int(time.time() * 1000),
        }
        self.last_command = command
        self.last_command_at = time.time()
        if command.get("type") == "results":
            self.last_result = (str(command.get("session_id") or ""), self.last_command_at)
        return command

    async def broadcast(self, command: dict[str, Any]) -> None:
        # Broadcast in command order, but never let one slow/stale browser hold
        # every other screen or eat a tablet answer window.
        async with self._broadcast_lock:
            if command.get("type") not in self._TRANSIENT_TYPES:
                command = self._record_display_command(command)
            async with self._lock:
                clients = list(self._clients)
            outcomes = await asyncio.gather(
                *(asyncio.wait_for(ws.send_json(command), timeout=0.75) for ws in clients),
                return_exceptions=True,
            )
            for ws, outcome in zip(clients, outcomes, strict=False):
                if isinstance(outcome, BaseException):
                    logger.warning("Display WebSocket send failed; dropping client %s: %r", ws.client, outcome)
                    await self.unregister(ws)
                    # A removed socket may remain TCP ESTABLISHED forever. Close it so
                    # the browser reconnects and receives the latest display state.
                    try:
                        await asyncio.wait_for(ws.close(code=1011), timeout=0.75)
                    except Exception:  # noqa: BLE001
                        logger.debug("Display WebSocket close failed", exc_info=True)

    def send(self, command: dict[str, Any]) -> None:
        """Thread-safe send from orchestrator thread."""
        loop = self._loop
        if loop is None or not loop.is_running():
            if command.get("type") not in self._TRANSIENT_TYPES:
                self._record_display_command(command)
            logger.debug("Display command buffered (no loop): %s", command.get("type"))
            return
        fut = asyncio.run_coroutine_threadsafe(self.broadcast(command), loop)
        try:
            fut.result(timeout=2.0)
        except Exception:  # noqa: BLE001
            logger.exception("Display broadcast failed")


class FaceEnrollBody(BaseModel):
    full_name: str = Field(min_length=1)
    enroll_id: int | None = None
    timeout_seconds: float = 25.0


class FacePushOneBody(BaseModel):
    enroll_id: int
    full_name: str = Field(min_length=1)
    media_get_url: str | None = None
    image_b64: str | None = None
    patient_id: str | None = None


class FaceWipeGalleryBody(BaseModel):
    preserve_stranger: bool = True


class CameraPreviewBody(BaseModel):
    enabled: bool = True


class StandZoneBody(BaseModel):
    """Draw stand box/hull or track box on /preview, or flip legacy auto-floor."""

    points: list[list[float]] | None = None
    polygon: list[list[float]] | None = None
    track_box: list[float] | None = None
    detect_box: list[float] | None = None  # alias for track_box
    tool: str | None = None  # box | hull | track | legacy
    mode: str | None = None
    detect_in_zone: bool | None = None
    legacy: bool = False


class FaceDeleteOneBody(BaseModel):
    enroll_id: int


class PipelineSettingsBody(BaseModel):
    input_mode: str | None = None
    camera_source: str | None = None
    input_device: str | None = None
    output_device: str | None = None
    voice_gender: str | None = None
    distance_m: float | None = None
    letter_chunk_seconds: float | None = Field(default=None, ge=1.0, le=30.0)
    tablet_chunk_seconds: float | None = Field(default=None, ge=1.0, le=30.0)
    letter_uncertain_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    letter_accept_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    max_letter_replacements: int | None = Field(default=None, ge=0, le=1)
    left_eye_start_easier_steps: int | None = Field(default=None, ge=0, le=3)
    vps_ip: str | None = None
    vps_mqtt_port: int | None = Field(default=None, ge=1, le=65535)
    frappe_url: str | None = None
    jetson_face_ip: str | None = None
    jetson_face_port: int | None = Field(default=None, ge=1, le=65535)
    face_device_ip: str | None = None
    face_device_port: int | None = Field(default=None, ge=1, le=65535)
    display_calibration_mode: str | None = None
    display_diagonal_inches: float | None = Field(default=None, ge=5.0, le=150.0)
    display_px_per_mm: float | None = Field(default=None, ge=0.2, le=40.0)
    display_calibration_target_mm: float | None = Field(default=None, ge=20.0, le=500.0)


class FaceConnectionTestBody(BaseModel):
    jetson_face_ip: str
    jetson_face_port: int = Field(ge=1, le=65535)
    face_device_ip: str
    face_device_port: int = Field(ge=1, le=65535)


class VpsConnectionTestBody(BaseModel):
    vps_ip: str
    vps_mqtt_port: int = Field(default=1883, ge=1, le=65535)
    frappe_url: str


class DisplayCalibrationBody(BaseModel):
    visible: bool = True
    px_per_mm: float | None = Field(default=None, ge=0.2, le=40.0)
    target_mm: float | None = Field(default=None, ge=20.0, le=500.0)


def _update_yaml_text_field(content: str, section: str, key: str, new_value: Any) -> str:
    if new_value is None:
        return content
    lines = content.splitlines()
    in_section = False
    section_indent = -1
    found_key = False
    new_lines: list[str] = []

    if isinstance(new_value, str):
        val_str = f'"{new_value}"' if (any(c in new_value for c in ': #') or new_value == 'C270') else new_value
    elif isinstance(new_value, float):
        val_str = f"{new_value:.2f}" if round(new_value, 2) != round(new_value, 1) else f"{new_value:.1f}"
    else:
        val_str = str(new_value)

    section_pat = re.compile(r"^(\s*)" + re.escape(section) + r"\s*:\s*(#.*)?$")
    key_pat = re.compile(r"^(\s*)" + re.escape(key) + r"\s*:\s*([^#]*?)(\s*#.*)?$")
    next_sec_pat = re.compile(r"^(\s*)([a-zA-Z0-9_\-]+)\s*:\s*")

    for line in lines:
        m_sec = section_pat.match(line)
        if m_sec:
            in_section = True
            section_indent = len(m_sec.group(1))
            new_lines.append(line)
            continue

        if in_section:
            m_next = next_sec_pat.match(line)
            if m_next and len(m_next.group(1)) <= section_indent:
                if not found_key:
                    indent_str = " " * (section_indent + 2)
                    new_lines.append(f"{indent_str}{key}: {val_str}")
                    found_key = True
                in_section = False

            m_key = key_pat.match(line)
            if in_section and m_key:
                indent = m_key.group(1)
                comment = m_key.group(3) or ""
                new_lines.append(f"{indent}{key}: {val_str}{comment}")
                found_key = True
                continue

        new_lines.append(line)

    if in_section and not found_key:
        indent_str = " " * (section_indent + 2)
        new_lines.append(f"{indent_str}{key}: {val_str}")

    return "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")


def _update_yaml_nested_field(
    content: str, section: str, subsection: str, key: str, new_value: Any
) -> str:
    """Update a key below ``section.subsection`` while preserving YAML comments."""
    lines = content.splitlines()
    section_re = re.compile(r"^(\s*)" + re.escape(section) + r"\s*:\s*(#.*)?$")
    subsection_re = re.compile(r"^(\s*)" + re.escape(subsection) + r"\s*:\s*(#.*)?$")
    key_re = re.compile(r"^(\s*)" + re.escape(key) + r"\s*:\s*([^#]*?)(\s*#.*)?$")
    section_indent = subsection_indent = -1
    in_section = in_subsection = found = False
    val = str(new_value)
    out: list[str] = []

    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        if not in_section:
            match = section_re.match(line)
            if match:
                in_section = True
                section_indent = len(match.group(1))
            out.append(line)
            continue

        if in_subsection and line.strip() and indent <= subsection_indent:
            if not found:
                out.append(" " * (subsection_indent + 2) + f"{key}: {val}")
                found = True
            in_subsection = False

        if line.strip() and indent <= section_indent and not in_subsection:
            in_section = False
            out.append(line)
            continue

        if not in_subsection:
            match = subsection_re.match(line)
            if match and len(match.group(1)) > section_indent:
                in_subsection = True
                subsection_indent = len(match.group(1))
                out.append(line)
                continue

        if in_subsection:
            match = key_re.match(line)
            if match and len(match.group(1)) > subsection_indent:
                out.append(f"{match.group(1)}{key}: {val}{match.group(3) or ''}")
                found = True
                continue
        out.append(line)

    if in_subsection and not found:
        out.append(" " * (subsection_indent + 2) + f"{key}: {val}")
    return "\n".join(out) + ("\n" if content.endswith("\n") else "")


def _update_env_field(content: str, key: str, value: Any) -> str:
    line = f"{key}={value}"
    pattern = re.compile(r"^" + re.escape(key) + r"=.*$", re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(line, content, count=1)
    return content.rstrip() + "\n" + line + "\n"


def _ipv4(value: str, label: str) -> str:
    try:
        parsed = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{label} không phải địa chỉ IPv4 hợp lệ") from exc
    if parsed.version != 4 or parsed.is_unspecified or parsed.is_multicast:
        raise ValueError(f"{label} không phải địa chỉ IPv4 sử dụng được")
    return str(parsed)


def _network_host(value: str, label: str) -> str:
    """Accept an IPv4 address or DNS hostname used by MQTT."""
    host = str(value or "").strip().rstrip(".")
    if not host or "://" in host or "/" in host or any(char.isspace() for char in host):
        raise ValueError(f"{label} phải là hostname hoặc địa chỉ IPv4 hợp lệ")
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in host.split(".")
        ):
            raise ValueError(f"{label} phải là hostname hoặc địa chỉ IPv4 hợp lệ")
        return host
    if parsed.version != 4 or parsed.is_unspecified or parsed.is_multicast:
        raise ValueError(f"{label} không phải hostname hoặc địa chỉ IPv4 sử dụng được")
    return str(parsed)


def _http_base_url(value: str, label: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"{label} phải là URL http hoặc https hợp lệ")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} không được chứa query hoặc fragment")
    return raw


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _http_reachable(url: str, timeout: float = 4.0) -> tuple[bool, str | None]:
    """Check a configured HTTP service without requiring a particular public route."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(url)
        if response.status_code < 500:
            return True, None
        return False, f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _route_source_ip(peer_host: str, peer_port: int = 80) -> str:
    """Return the local IPv4 the kernel would use to reach the Face ID."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((peer_host, int(peer_port)))
            return str(sock.getsockname()[0])
    except OSError:
        return ""


def _auto_px_per_mm(diagonal_inches: float, metrics: dict[str, Any]) -> float | None:
    """Estimate physical CSS px/mm from browser screen size and diagonal."""
    try:
        width = float(metrics.get("screen_width") or 0)
        height = float(metrics.get("screen_height") or 0)
        diagonal_mm = float(diagonal_inches) * 25.4
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or diagonal_mm <= 0:
        return None
    width_mm = diagonal_mm * width / math.hypot(width, height)
    estimate = width / width_mm if width_mm > 0 else 0
    return estimate if 0.2 <= estimate <= 40 else None


def _display_config_payload(cfg: Any, metrics: dict[str, Any]) -> dict[str, Any]:
    display_cfg = getattr(cfg, "display", None)
    proto = getattr(cfg, "protocol", None)
    mode = str(getattr(display_cfg, "calibration_mode", "auto") or "auto").lower()
    diagonal = float(getattr(display_cfg, "diagonal_inches", 32.0))
    saved_ppm = float(getattr(display_cfg, "px_per_mm", 5.42))
    automatic = _auto_px_per_mm(diagonal, metrics) if mode == "auto" else None
    effective = float(automatic if automatic is not None else saved_ppm)
    return {
        "calibration_mode": mode,
        "diagonal_inches": diagonal,
        "px_per_mm": saved_ppm,
        "effective_px_per_mm": effective,
        "auto_px_per_mm": automatic,
        "calibration_target_mm": float(
            getattr(display_cfg, "calibration_target_mm", 100.0)
        ),
        "calibrated_at": str(getattr(display_cfg, "calibrated_at", "") or ""),
        "distance_m": float(getattr(proto, "distance_m", 5.0)),
        "metrics": dict(metrics or {}),
    }


def _scan_hardware() -> dict[str, Any]:
    cameras: list[dict[str, Any]] = []
    v4l_dir = Path("/sys/class/video4linux")
    if v4l_dir.is_dir():
        for dev_path in sorted(v4l_dir.glob("video*")):
            name_file = dev_path / "name"
            node_name = dev_path.name
            dev_node = f"/dev/{node_name}"
            cam_title = name_file.read_text(encoding="utf-8", errors="ignore").strip() if name_file.is_file() else node_name
            cameras.append({
                "id": cam_title if "C270" in cam_title else dev_node,
                "path": dev_node,
                "label": f"{cam_title} ({dev_node})",
            })
    if not cameras:
        import glob
        for dev in sorted(glob.glob("/dev/video*")):
            cameras.append({"id": dev, "path": dev, "label": dev})
    if not cameras:
        cameras.append({"id": "C270", "path": "/dev/video0", "label": "C270 HD WEBCAM (/dev/video0)"})

    audio_mics: list[dict[str, Any]] = [
        {"id": "Yealink", "label": "Yealink USB Dongle (Khuyên dùng)"},
        {"id": "pulse", "label": "PulseAudio Plugin (Mặc định Linux)"},
        {"id": "default", "label": "Hệ thống Mặc định (PortAudio default)"},
    ]
    audio_spks: list[dict[str, Any]] = [
        {"id": "Yealink", "label": "Yealink USB Headset (Khuyên dùng)"},
        {"id": "pulse", "label": "PulseAudio Plugin (Mặc định Linux)"},
        {"id": "default", "label": "Hệ thống Mặc định (PortAudio default)"},
    ]

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for idx, d in enumerate(devices):
            name = str(d.get("name") or "").strip()
            in_ch = int(d.get("max_input_channels") or 0)
            out_ch = int(d.get("max_output_channels") or 0)
            if in_ch > 0 and "monitor" not in name.lower() and not any(m["id"] == name for m in audio_mics):
                audio_mics.append({
                    "id": name,
                    "index": idx,
                    "label": f"{name} ({in_ch} in)",
                })
            if out_ch > 0 and not any(s["id"] == name for s in audio_spks):
                audio_spks.append({
                    "id": name,
                    "index": idx,
                    "label": f"{name} ({out_ch} out)",
                })
    except Exception as exc:
        logger.warning("sounddevice query failed: %s", exc)

    return {
        "cameras": cameras,
        "microphones": audio_mics,
        "speakers": audio_spks,
    }


def _cors_origins() -> list[str]:
    raw = (os.getenv("AC_CORS_ORIGINS") or _DEFAULT_CORS).strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_display_app(
    hub: DisplayHub,
    face: Any | None = None,
    *,
    face_vector: Any | None = None,
    media: Any | None = None,
    hospital: Any | None = None,
    face_vectordb_cfg: Any | None = None,
    readiness: Any | None = None,
    audio_input: str = "device",
    cfg: Any | None = None,
    config_path: Path | str | None = None,
    orchestrator: Any | None = None,
    audio_player: Any | None = None,
    stt_bridge: Any | None = None,
) -> FastAPI:
    resolved_cfg_path = Path(config_path) if config_path else (Path(__file__).resolve().parents[2] / "configs" / "clinic.yaml")
    if not resolved_cfg_path.is_file():
        resolved_cfg_path = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"

    if cfg is not None:
        hub.input_mode = str(getattr(getattr(cfg, "ui", None), "input_mode", "speak"))

    app = FastAPI(title="VisionTestAI Chart Display", version="0.1.0")
    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    enroll_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="face-enroll")
    face_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="face-ops")
    hub.audio_input = (audio_input or "device").strip().lower() or "device"
    instruction_dir = Path(
        os.getenv("AC_INSTRUCTION_IMAGE_DIR")
        or (Path.home() / ".local/share/visiontestai/instruction-images")
    )

    def instruction_images() -> dict[str, dict[str, Any]]:
        images = {}
        for scene, default_url in _INSTRUCTION_DEFAULTS.items():
            path = instruction_dir / f"{scene}.webp"
            if path.is_file():
                version = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                images[scene] = {"url": f"/api/instruction-images/{scene}/file?v={version}", "custom": True}
            else:
                images[scene] = {"url": default_url, "custom": False}
        return images

    @app.get("/api/instruction-images")
    async def get_instruction_images() -> JSONResponse:
        return JSONResponse({"images": instruction_images()}, headers={"Cache-Control": "no-store"})

    @app.get("/api/instruction-images/{scene}/file")
    async def get_instruction_image_file(scene: str) -> FileResponse:
        if scene not in _INSTRUCTION_DEFAULTS:
            raise HTTPException(404, "Unknown instruction scene")
        path = instruction_dir / f"{scene}.webp"
        if not path.is_file():
            raise HTTPException(404, "Instruction image not found")
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-cache"})

    @app.put("/api/instruction-images/{scene}")
    async def put_instruction_image(scene: str, request: Request) -> JSONResponse:
        if scene not in _INSTRUCTION_DEFAULTS:
            raise HTTPException(404, "Unknown instruction scene")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > _INSTRUCTION_IMAGE_LIMIT:
                raise HTTPException(413, "Ảnh phải nhỏ hơn 10 MB")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or image.width > 6000 or image.height > 6000:
                    raise ValueError("Ảnh phải là JPEG, PNG hoặc WebP, tối đa 6000 × 6000 px")
                image.load()
                encoded = BytesIO()
                oriented = ImageOps.exif_transpose(image).convert("RGBA")
                background = Image.new("RGBA", oriented.size, "white")
                background.alpha_composite(oriented)
                background.convert("RGB").save(encoded, format="WEBP", quality=90)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise HTTPException(400, f"Ảnh không hợp lệ: {exc}") from exc
        instruction_dir.mkdir(parents=True, exist_ok=True)
        target = instruction_dir / f"{scene}.webp"
        temporary = instruction_dir / f".{scene}-{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(encoded.getvalue())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        images = instruction_images()
        await hub.broadcast({"type": "instruction_images", "images": images})
        return JSONResponse({"ok": True, "images": images})

    @app.delete("/api/instruction-images/{scene}")
    async def reset_instruction_image(scene: str) -> JSONResponse:
        if scene not in _INSTRUCTION_DEFAULTS:
            raise HTTPException(404, "Unknown instruction scene")
        (instruction_dir / f"{scene}.webp").unlink(missing_ok=True)
        images = instruction_images()
        await hub.broadcast({"type": "instruction_images", "images": images})
        return JSONResponse({"ok": True, "images": images})

    @app.on_event("startup")
    async def _startup() -> None:
        hub.attach_loop(asyncio.get_running_loop())

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            DISPLAY_DIR / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/preview")
    async def camera_preview_page() -> FileResponse:
        path = DISPLAY_DIR / "preview.html"
        if not path.is_file():
            raise HTTPException(404, "preview.html missing")
        return FileResponse(
            path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/control")
    async def control_page() -> Response:
        # /control is now the single entry point for the rebuilt tablet UI.
        return await control_real_page()

    @app.get("/control-real")
    async def control_real_page() -> FileResponse:
        path = CONTROL_DIR / "real.html"
        if not path.is_file():
            raise HTTPException(404, "control/real.html missing")
        return FileResponse(
            path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/control-static/real-integration.js")
    async def control_script() -> FileResponse:
        path = CONTROL_DIR / "real-integration.js"
        if not path.is_file():
            raise HTTPException(404, "real-integration.js missing")
        return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/api/camera/status")
    async def camera_status() -> JSONResponse:
        snap = None
        if readiness is not None and hasattr(readiness, "snapshot"):
            try:
                snap = readiness.snapshot()
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"ok": False, "error": str(exc)})
        jpeg = None
        if readiness is not None and hasattr(readiness, "latest_jpeg"):
            try:
                jpeg = readiness.latest_jpeg()
            except Exception:  # noqa: BLE001
                jpeg = None
        preview_meta: dict[str, Any] = {}
        if readiness is not None and hasattr(readiness, "preview_status"):
            try:
                preview_meta = dict(readiness.preview_status() or {})
            except Exception:  # noqa: BLE001
                preview_meta = {}
        return JSONResponse(
            {
                "ok": True,
                "has_frame": bool(jpeg),
                "ready": bool(getattr(snap, "ready", False)),
                "zone_ok": bool(getattr(snap, "zone_ok", False)),
                "headphones_on": bool(getattr(snap, "headphones_on", False)),
                "under_test": str(getattr(snap, "under_test", "UNKNOWN") or "UNKNOWN"),
                "coaching_vi": str(getattr(snap, "coaching_vi", "") or ""),
                "error": getattr(snap, "error", None),
                "preview_enabled": bool(preview_meta.get("preview_enabled", False)),
                "camera_running": bool(preview_meta.get("running", False)),
                "exam_hold": bool(preview_meta.get("exam_hold", False)),
            }
        )

    @app.post("/api/camera/preview")
    async def camera_preview_toggle(body: CameraPreviewBody) -> JSONResponse:
        """Enable/disable /preview MJPEG + SmartEyes when exam is not holding CV."""
        if readiness is None or not hasattr(readiness, "set_preview_enabled"):
            return JSONResponse(
                {"ok": False, "error": "readiness bridge has no preview control"},
                status_code=503,
            )
        try:
            meta = readiness.set_preview_enabled(bool(body.enabled))
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        return JSONResponse({"ok": True, **dict(meta or {})})

    @app.get("/api/stand-zone")
    async def stand_zone_get() -> JSONResponse:
        if readiness is None or not hasattr(readiness, "get_stand_zone"):
            return JSONResponse(
                {"ok": False, "error": "readiness bridge has no stand-zone control"},
                status_code=503,
            )
        try:
            meta = readiness.get_stand_zone()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        return JSONResponse(dict(meta or {"ok": False}))

    @app.put("/api/stand-zone")
    async def stand_zone_put(body: StandZoneBody) -> JSONResponse:
        if readiness is None or not hasattr(readiness, "set_stand_zone"):
            return JSONResponse(
                {"ok": False, "error": "readiness bridge has no stand-zone control"},
                status_code=503,
            )
        try:
            meta = readiness.set_stand_zone(body.model_dump())
        except NotImplementedError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        return JSONResponse({"ok": True, **dict(meta or {})})

    @app.get("/api/camera/snapshot.jpg")
    async def camera_snapshot() -> Response:
        jpeg = readiness.latest_jpeg() if readiness is not None else None
        if not jpeg:
            raise HTTPException(503, "camera preview not ready yet")
        return Response(content=jpeg, media_type="image/jpeg")

    @app.get("/api/camera/stream.mjpg")
    async def camera_mjpeg() -> StreamingResponse:
        boundary = "frame"

        async def _frames():
            last_seq = -1
            while True:
                if readiness is not None and hasattr(readiness, "latest_jpeg_seq"):
                    jpeg, seq = readiness.latest_jpeg_seq()
                else:
                    jpeg = readiness.latest_jpeg() if readiness is not None else None
                    seq = -1
                if jpeg and (seq != last_seq or seq == -1):
                    last_seq = seq
                    yield (
                        b"--" + boundary.encode("ascii") + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(0.04)

        return StreamingResponse(
            _frames(),
            media_type=f"multipart/x-mixed-replace; boundary={boundary}",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/api/control/mode")
    async def get_control_mode() -> JSONResponse:
        current_cfg = cfg
        if current_cfg is None:
            from ac.config import load_config
            current_cfg = load_config(resolved_cfg_path)
        return JSONResponse({"input_mode": current_cfg.ui.input_mode})

    @app.get("/api/settings")
    async def get_pipeline_settings() -> JSONResponse:
        current_cfg = cfg
        if current_cfg is None:
            try:
                from ac.config import load_config
                current_cfg = load_config(resolved_cfg_path)
            except Exception as exc:
                logger.warning("Could not load config for settings: %s", exc)

        proto = getattr(current_cfg, "protocol", None)
        bridges_cfg = getattr(current_cfg, "bridges", None)
        audio_cfg = getattr(current_cfg, "audio", None)
        voice_cfg = getattr(current_cfg, "voice", None)
        face_cfg = getattr(bridges_cfg, "face", None)
        mqtt_cfg = getattr(current_cfg, "mqtt", None)
        hospital_cfg = getattr(current_cfg, "hospital", None)
        media_cfg = getattr(current_cfg, "media", None)
        vector_cfg = getattr(current_cfg, "face_vectordb", None)
        display_cfg = getattr(current_cfg, "display", None)
        ui_cfg = getattr(current_cfg, "ui", None)
        display_data = _display_config_payload(current_cfg, hub.display_metrics)

        detected_lan_ip = _route_source_ip(
            getattr(face_cfg, "host", "") or "127.0.0.1",
            int(getattr(face_cfg, "port", 80)),
        )
        jetson_lan_ip = getattr(face_cfg, "callback_host", "") or detected_lan_ip
        chart_port = int(getattr(display_cfg, "port", 8088))

        settings_data = {
            "input_mode": getattr(ui_cfg, "input_mode", "speak"),
            "camera_source": getattr(bridges_cfg, "smarteyes_source", "C270"),
            "input_device": getattr(audio_cfg, "input_device", "") or "",
            "output_device": getattr(audio_cfg, "output_device", "") or "",
            "voice_gender": getattr(voice_cfg, "gender", "auto") or "auto",
            "distance_m": float(getattr(proto, "distance_m", 5.0)),
            "letter_chunk_seconds": float(getattr(proto, "letter_chunk_seconds", 3.0)),
            "tablet_chunk_seconds": float(getattr(proto, "tablet_chunk_seconds", 10.0)),
            "letter_uncertain_threshold": float(getattr(proto, "letter_uncertain_threshold", 0.45)),
            "letter_accept_threshold": float(getattr(proto, "letter_accept_threshold", 0.75)),
            "max_letter_replacements": int(getattr(proto, "max_letter_replacements", 1)),
            "left_eye_start_easier_steps": int(getattr(proto, "left_eye_start_easier_steps", 1)),
            "vps_ip": getattr(mqtt_cfg, "host", "") or "",
            "vps_mqtt_port": int(getattr(mqtt_cfg, "port", 1883)),
            "frappe_url": getattr(hospital_cfg, "base_url", "") or "",
            "vps_media_url": getattr(media_cfg, "base_url", "") or "",
            "vps_vectordb_url": getattr(vector_cfg, "base_url", "") or "",
            "jetson_face_ip": getattr(face_cfg, "callback_host", "") or "",
            "jetson_face_port": int(getattr(face_cfg, "callback_port", 7788)),
            "face_device_ip": getattr(face_cfg, "host", "") or "",
            "face_device_port": int(getattr(face_cfg, "port", 80)),
            "face_device_url": f"http://{getattr(face_cfg, 'host', '')}:{int(getattr(face_cfg, 'port', 80))}",
            "jetson_detected_ip": detected_lan_ip,
            "jetson_lan_url": f"http://{jetson_lan_ip}:{chart_port}" if jetson_lan_ip else "",
            "jetson_tailnet_ip": os.getenv("JETSON_TAILNET_HOST", "").strip(),
            "jetson_public_url": os.getenv("JETSON_PUBLIC_URL", "").strip().rstrip("/"),
            "display_calibration_mode": display_data["calibration_mode"],
            "display_diagonal_inches": display_data["diagonal_inches"],
            "display_px_per_mm": display_data["px_per_mm"],
            "display_effective_px_per_mm": display_data["effective_px_per_mm"],
            "display_auto_px_per_mm": display_data["auto_px_per_mm"],
            "display_calibration_target_mm": display_data["calibration_target_mm"],
            "display_calibrated_at": display_data["calibrated_at"],
            "display_metrics": display_data["metrics"],
        }

        hw = _scan_hardware()
        return JSONResponse({
            "ok": True,
            "settings": settings_data,
            "hardware": hw,
            "config_file": str(resolved_cfg_path),
        })

    @app.get("/api/display/config")
    async def get_display_config() -> JSONResponse:
        current_cfg = cfg
        if current_cfg is None:
            from ac.config import load_config
            current_cfg = load_config(resolved_cfg_path)
        return JSONResponse({"ok": True, **_display_config_payload(current_cfg, hub.display_metrics)})

    @app.post("/api/display/calibration")
    async def show_display_calibration(body: DisplayCalibrationBody) -> JSONResponse:
        current_cfg = cfg
        if current_cfg is None:
            from ac.config import load_config
            current_cfg = load_config(resolved_cfg_path)
        payload = _display_config_payload(current_cfg, hub.display_metrics)
        if body.px_per_mm is not None:
            payload["px_per_mm"] = float(body.px_per_mm)
            payload["effective_px_per_mm"] = float(body.px_per_mm)
        if body.target_mm is not None:
            payload["calibration_target_mm"] = float(body.target_mm)
        await hub.broadcast({"type": "display_calibration", "visible": body.visible, **payload})
        return JSONResponse({"ok": True, "visible": body.visible, **payload})

    @app.post("/api/settings/face/test")
    async def test_face_connection(body: FaceConnectionTestBody) -> JSONResponse:
        """Test both local BS listener and AiFace HTTP API without changing config."""
        try:
            jetson_ip = _ipv4(body.jetson_face_ip, "IP Jetson")
            device_ip = _ipv4(body.face_device_ip, "IP Face ID")
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        password = str(getattr(face, "password", "12345678") or "12345678")

        def _probe() -> tuple[bool, dict[str, Any] | None, str | None, bool]:
            callback_ok = _tcp_reachable(jetson_ip, body.jetson_face_port)
            try:
                from ac.face_client import AiFaceClient
                probe = AiFaceClient(
                    host=device_ip,
                    port=body.face_device_port,
                    password=password,
                    timeout_seconds=3.0,
                )
                info = probe.test_connection(timeout=3.0)
                return True, info, None, callback_ok
            except Exception as exc:  # noqa: BLE001
                return False, None, str(exc), callback_ok

        device_ok, info, error, callback_ok = await asyncio.get_running_loop().run_in_executor(
            face_pool, _probe
        )
        ok = bool(device_ok and callback_ok)
        return JSONResponse(
            {
                "ok": ok,
                "face_device": {
                    "ok": device_ok,
                    "endpoint": f"http://{device_ip}:{body.face_device_port}",
                    "model": (info or {}).get("devname") or (info or {}).get("model"),
                    "serial": (info or {}).get("sn"),
                    "firmware": (info or {}).get("firmware") or (info or {}).get("ver"),
                    "error": error,
                },
                "jetson_receiver": {
                    "ok": callback_ok,
                    "endpoint": f"{jetson_ip}:{body.jetson_face_port}",
                    "error": None if callback_ok else "Không thấy dịch vụ BS đang lắng nghe tại IP/cổng này",
                },
                "error": None if ok else "Một hoặc nhiều đầu kết nối chưa sẵn sàng",
            },
            status_code=200 if ok else 503,
        )

    @app.post("/api/settings/vps/test")
    async def test_vps_connection(body: VpsConnectionTestBody) -> JSONResponse:
        """Check configured Frappe, MQTT, Media and VectorDB services without saving."""
        try:
            vps_ip = _network_host(body.vps_ip, "Máy chủ MQTT/VPS")
            frappe_url = _http_base_url(body.frappe_url, "URL Frappe")
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        def _probe() -> dict[str, Any]:
            frappe_ok = False
            frappe_error = None
            try:
                with httpx.Client(timeout=4.0, follow_redirects=False) as client:
                    response = client.get(f"{frappe_url}/api/method/frappe.ping")
                    response.raise_for_status()
                    data = response.json()
                    frappe_ok = data.get("message") == "pong"
                    if not frappe_ok:
                        frappe_error = "Frappe không trả về pong"
            except Exception as exc:  # noqa: BLE001
                frappe_error = str(exc)
            media_url = _http_base_url(
                getattr(getattr(cfg, "media", None), "base_url", ""), "URL Media"
            )
            vectordb_url = _http_base_url(
                getattr(getattr(cfg, "face_vectordb", None), "base_url", ""), "URL Face VectorDB"
            )
            media_ok, media_error = _http_reachable(media_url)
            vectordb_ok, vectordb_error = _http_reachable(vectordb_url)
            ports = {
                "mqtt": _tcp_reachable(vps_ip, body.vps_mqtt_port),
                "media": media_ok,
                "vectordb": vectordb_ok,
            }
            return {
                "frappe": {"ok": frappe_ok, "url": frappe_url, "error": frappe_error},
                "media": {"ok": media_ok, "url": media_url, "error": media_error},
                "vectordb": {"ok": vectordb_ok, "url": vectordb_url, "error": vectordb_error},
                "ports": ports,
            }

        result = await asyncio.get_running_loop().run_in_executor(face_pool, _probe)
        ok = bool(result["frappe"]["ok"] and all(result["ports"].values()))
        return JSONResponse(
            {"ok": ok, "vps_ip": vps_ip, **result},
            status_code=200 if ok else 503,
        )

    @app.put("/api/settings")
    async def update_pipeline_settings(body: PipelineSettingsBody) -> JSONResponse:
        nonlocal cfg
        if body.input_mode is not None and body.input_mode not in ("speak", "tablet"):
            return JSONResponse({"ok": False, "error": "Chế độ nhập phải là speak hoặc tablet"}, status_code=400)
        mode_changed = body.input_mode is not None and body.input_mode != getattr(getattr(cfg, "ui", None), "input_mode", "speak")
        if mode_changed and orchestrator is not None and orchestrator.sessions.is_busy():
            return JSONResponse({"ok": False, "error": "Hãy đợi phiên đo hiện tại kết thúc trước khi đổi chế độ nhập."}, status_code=409)
        root_dir = Path(__file__).resolve().parents[2]
        target_file = resolved_cfg_path
        if not target_file.is_file():
            alt = root_dir / "configs" / "clinic.yaml"
            if alt.is_file():
                target_file = alt

        existing_data: dict[str, Any] = {}
        if target_file.is_file():
            try:
                existing_data = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logger.warning("Failed to load existing yaml %s: %s", target_file, exc)

        for sec in (
            "protocol",
            "bridges",
            "audio",
            "voice",
            "display",
            "mqtt",
            "hospital",
            "media",
            "face_vectordb",
            "ui",
        ):
            if sec not in existing_data or not isinstance(existing_data[sec], dict):
                existing_data[sec] = {}

        face_dict = existing_data["bridges"].setdefault("face", {})
        if not isinstance(face_dict, dict):
            face_dict = {}
            existing_data["bridges"]["face"] = face_dict

        vps_fields_supplied = any(
            value is not None
            for value in (body.vps_ip, body.vps_mqtt_port, body.frappe_url)
        )
        current_mqtt_cfg = getattr(cfg, "mqtt", None)
        current_hospital_cfg = getattr(cfg, "hospital", None)
        current_vps_ip = str(getattr(current_mqtt_cfg, "host", "") or "")
        current_mqtt_port = int(getattr(current_mqtt_cfg, "port", 1883) or 1883)
        current_frappe_url = str(
            getattr(current_hospital_cfg, "base_url", "") or ""
        ).rstrip("/")
        vps_ip = str(
            body.vps_ip if body.vps_ip is not None else current_vps_ip
        ).strip()
        vps_mqtt_port = int(
            body.vps_mqtt_port
            if body.vps_mqtt_port is not None
            else current_mqtt_port
        )
        frappe_url = str(
            body.frappe_url
            if body.frappe_url is not None
            else current_frappe_url
        ).strip()
        if vps_fields_supplied:
            try:
                vps_ip = _network_host(vps_ip, "Máy chủ MQTT/VPS")
                frappe_url = _http_base_url(frappe_url, "URL Frappe")
            except ValueError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        vps_changed = vps_fields_supplied and (
            vps_ip != current_vps_ip
            or vps_mqtt_port != current_mqtt_port
            or frappe_url != current_frappe_url
        )
        # Media and VectorDB may use independent public HTTPS domains; preserve
        # their configured URLs when only the MQTT host changes.
        media_url = str(getattr(getattr(cfg, "media", None), "base_url", "") or "").rstrip("/")
        vectordb_url = str(getattr(getattr(cfg, "face_vectordb", None), "base_url", "") or "").rstrip("/")
        if vps_changed:
            existing_data["mqtt"].update(
                {"host": vps_ip, "port": vps_mqtt_port}
            )
            existing_data["hospital"]["base_url"] = frappe_url
            existing_data["media"]["base_url"] = media_url
            existing_data["face_vectordb"]["base_url"] = vectordb_url
            if current_mqtt_cfg is not None:
                current_mqtt_cfg.host = vps_ip
                current_mqtt_cfg.port = vps_mqtt_port
            if current_hospital_cfg is not None:
                current_hospital_cfg.base_url = frappe_url
            if cfg is not None and hasattr(cfg, "media"):
                cfg.media.base_url = media_url
            if cfg is not None and hasattr(cfg, "face_vectordb"):
                cfg.face_vectordb.base_url = vectordb_url

        face_fields_supplied = any(
            value is not None
            for value in (
                body.jetson_face_ip,
                body.jetson_face_port,
                body.face_device_ip,
                body.face_device_port,
            )
        )
        current_face_cfg = getattr(getattr(cfg, "bridges", None), "face", None)
        jetson_face_ip = str(
            body.jetson_face_ip
            if body.jetson_face_ip is not None
            else getattr(current_face_cfg, "callback_host", "")
        ).strip()
        jetson_face_port = int(
            body.jetson_face_port
            if body.jetson_face_port is not None
            else getattr(current_face_cfg, "callback_port", 7788)
        )
        face_device_ip = str(
            body.face_device_ip
            if body.face_device_ip is not None
            else getattr(current_face_cfg, "host", "")
        ).strip()
        face_device_port = int(
            body.face_device_port
            if body.face_device_port is not None
            else getattr(current_face_cfg, "port", 80)
        )
        face_changed = face_fields_supplied and (
            jetson_face_ip != str(getattr(current_face_cfg, "callback_host", "") or "")
            or jetson_face_port != int(getattr(current_face_cfg, "callback_port", 7788))
            or face_device_ip != str(getattr(current_face_cfg, "host", "") or "")
            or face_device_port != int(getattr(current_face_cfg, "port", 80))
        )

        if face_changed:
            try:
                jetson_face_ip = _ipv4(jetson_face_ip, "IP Jetson")
                face_device_ip = _ipv4(face_device_ip, "IP Face ID")
            except ValueError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
            if not _tcp_reachable(jetson_face_ip, jetson_face_port):
                return JSONResponse(
                    {"ok": False, "error": "Dịch vụ nhận Face ID của Jetson chưa mở tại IP/cổng đã nhập."},
                    status_code=400,
                )

            old_host = str(getattr(face, "host", "") or "")
            old_port = int(getattr(face, "port", 80) or 80)

            def _apply_face_runtime() -> tuple[bool, str | None]:
                try:
                    if face is None or not getattr(face, "enabled", False):
                        return False, "Face ID bridge đang tắt"
                    if hasattr(face, "update_endpoint"):
                        face.update_endpoint(face_device_ip, face_device_port)
                    if hasattr(face, "test_connection"):
                        face.test_connection(timeout=3.0)
                    ok = bool(face.ensure_bs_server(jetson_face_ip, jetson_face_port))
                    return ok, None if ok else "Face ID từ chối cấu hình địa chỉ nhận sự kiện"
                except Exception as exc:  # noqa: BLE001
                    if hasattr(face, "update_endpoint") and old_host:
                        face.update_endpoint(old_host, old_port)
                    return False, str(exc)

            face_ok, face_error = await asyncio.get_running_loop().run_in_executor(
                face_pool, _apply_face_runtime
            )
            if not face_ok:
                return JSONResponse(
                    {"ok": False, "error": f"Không áp dụng được cấu hình Face ID: {face_error}"},
                    status_code=502,
                )

            face_dict.update(
                {
                    "host": face_device_ip,
                    "port": face_device_port,
                    "callback_host": jetson_face_ip,
                    "callback_port": jetson_face_port,
                }
            )
            if current_face_cfg is not None:
                current_face_cfg.host = face_device_ip
                current_face_cfg.port = face_device_port
                current_face_cfg.callback_host = jetson_face_ip
                current_face_cfg.callback_port = jetson_face_port

        # 1. Update the Model A-only acuity protocol.
        if body.input_mode is not None:
            existing_data["ui"]["input_mode"] = body.input_mode
        proto_dict = existing_data["protocol"]
        if body.distance_m is not None:
            proto_dict["distance_m"] = float(body.distance_m)
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.distance_m = float(body.distance_m)
        if body.letter_chunk_seconds is not None:
            proto_dict["letter_chunk_seconds"] = float(body.letter_chunk_seconds)
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.letter_chunk_seconds = float(body.letter_chunk_seconds)
        if body.tablet_chunk_seconds is not None:
            proto_dict["tablet_chunk_seconds"] = float(body.tablet_chunk_seconds)
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.tablet_chunk_seconds = float(body.tablet_chunk_seconds)
        current_low = float(getattr(getattr(cfg, "protocol", None), "letter_uncertain_threshold", 0.45))
        current_high = float(getattr(getattr(cfg, "protocol", None), "letter_accept_threshold", 0.75))
        new_low = float(body.letter_uncertain_threshold) if body.letter_uncertain_threshold is not None else current_low
        new_high = float(body.letter_accept_threshold) if body.letter_accept_threshold is not None else current_high
        if new_low >= new_high:
            return JSONResponse(
                {"ok": False, "error": "Ngưỡng bù phải nhỏ hơn ngưỡng ghi nhận đúng"},
                status_code=400,
            )
        if body.letter_uncertain_threshold is not None:
            proto_dict["letter_uncertain_threshold"] = new_low
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.letter_uncertain_threshold = new_low
        if body.letter_accept_threshold is not None:
            proto_dict["letter_accept_threshold"] = new_high
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.letter_accept_threshold = new_high
        if body.max_letter_replacements is not None:
            proto_dict["max_letter_replacements"] = int(body.max_letter_replacements)
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.max_letter_replacements = int(body.max_letter_replacements)
        if body.left_eye_start_easier_steps is not None:
            proto_dict["left_eye_start_easier_steps"] = int(body.left_eye_start_easier_steps)
            if cfg and hasattr(cfg, "protocol"):
                cfg.protocol.left_eye_start_easier_steps = int(body.left_eye_start_easier_steps)

        # 2. Update bridge hardware settings.
        bridges_dict = existing_data["bridges"]
        if body.camera_source is not None:
            src_val = str(body.camera_source).strip()
            bridges_dict["smarteyes_source"] = src_val
            if cfg and hasattr(cfg, "bridges"):
                cfg.bridges.smarteyes_source = src_val

        # 3. Update audio: input_device, output_device
        audio_dict = existing_data["audio"]
        if body.input_device is not None:
            mic_dev = str(body.input_device).strip()
            audio_dict["input_device"] = mic_dev
            if cfg and hasattr(cfg, "audio"):
                cfg.audio.input_device = mic_dev
            hub.audio_device_label = mic_dev or getattr(hub, "audio_device_label", "")
        if body.output_device is not None:
            spk_dev = str(body.output_device).strip()
            audio_dict["output_device"] = spk_dev
            if cfg and hasattr(cfg, "audio"):
                cfg.audio.output_device = spk_dev
            if not getattr(hub, "audio_device_label", ""):
                hub.audio_device_label = spk_dev

        # 4. Update voice: gender
        if body.voice_gender is not None:
            vg = str(body.voice_gender).strip().lower()
            existing_data["voice"]["gender"] = vg
            if cfg and hasattr(cfg, "voice"):
                cfg.voice.gender = vg
            if audio_player is not None and hasattr(audio_player, "set_gender"):
                try:
                    from ac.audio_player import resolve_voice_gender
                    resolved = resolve_voice_gender(clinic_setting=vg)
                    audio_player.set_gender(resolved)
                except Exception as exc:
                    logger.warning("Hot-reload audio_player voice_gender failed: %s", exc)

        # 5. Physical chart calibration, shared by every chart browser.
        display_changed = any(
            value is not None
            for value in (
                body.display_calibration_mode,
                body.display_diagonal_inches,
                body.display_px_per_mm,
                body.display_calibration_target_mm,
            )
        )
        display_dict = existing_data["display"]
        if body.display_calibration_mode is not None:
            mode = str(body.display_calibration_mode).strip().lower()
            if mode not in ("auto", "manual"):
                return JSONResponse(
                    {"ok": False, "error": "Chế độ hiệu chuẩn phải là auto hoặc manual"},
                    status_code=400,
                )
            display_dict["calibration_mode"] = mode
            if cfg and hasattr(cfg, "display"):
                cfg.display.calibration_mode = mode
        if body.display_diagonal_inches is not None:
            display_dict["diagonal_inches"] = float(body.display_diagonal_inches)
            if cfg and hasattr(cfg, "display"):
                cfg.display.diagonal_inches = float(body.display_diagonal_inches)
        if body.display_px_per_mm is not None:
            display_dict["px_per_mm"] = float(body.display_px_per_mm)
            if cfg and hasattr(cfg, "display"):
                cfg.display.px_per_mm = float(body.display_px_per_mm)
        if body.display_calibration_target_mm is not None:
            display_dict["calibration_target_mm"] = float(body.display_calibration_target_mm)
            if cfg and hasattr(cfg, "display"):
                cfg.display.calibration_target_mm = float(body.display_calibration_target_mm)
        if display_changed:
            calibrated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            display_dict["calibrated_at"] = calibrated_at
            if cfg and hasattr(cfg, "display"):
                cfg.display.calibrated_at = calibrated_at

        # Hot-reload in-memory runtime components
        if audio_player is not None and body.output_device is not None:
            try:
                audio_player.output_device = str(body.output_device).strip()
            except Exception as exc:
                logger.warning("Hot-reload audio_player failed: %s", exc)

        if stt_bridge is not None:
            try:
                if hasattr(stt_bridge, "update_config"):
                    stt_bridge.update_config(
                        min_confidence=body.letter_uncertain_threshold,
                        input_device=body.input_device,
                    )
                else:
                    if body.letter_uncertain_threshold is not None and hasattr(stt_bridge, "min_confidence"):
                        stt_bridge.min_confidence = float(body.letter_uncertain_threshold)
                    if body.input_device is not None and hasattr(stt_bridge, "input_device"):
                        stt_bridge.input_device = str(body.input_device).strip()
            except Exception as exc:
                logger.warning("Hot-reload stt_bridge failed: %s", exc)

        if readiness is not None and body.camera_source is not None:
            try:
                if hasattr(readiness, "set_source"):
                    readiness.set_source(str(body.camera_source).strip())
                elif hasattr(readiness, "source"):
                    readiness.source = str(body.camera_source).strip()
            except Exception as exc:
                logger.warning("Hot-reload readiness camera source failed: %s", exc)

        # Atomic file persistence with 100% comment preservation
        try:
            raw_text = target_file.read_text(encoding="utf-8") if target_file.is_file() else ""
            if raw_text:
                if vps_changed:
                    raw_text = _update_yaml_text_field(raw_text, "mqtt", "host", vps_ip)
                    raw_text = _update_yaml_text_field(raw_text, "mqtt", "port", vps_mqtt_port)
                    raw_text = _update_yaml_text_field(raw_text, "hospital", "base_url", frappe_url)
                    raw_text = _update_yaml_text_field(raw_text, "media", "base_url", media_url)
                    raw_text = _update_yaml_text_field(
                        raw_text, "face_vectordb", "base_url", vectordb_url
                    )
                if body.distance_m is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "distance_m", body.distance_m)
                if body.letter_chunk_seconds is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "letter_chunk_seconds", body.letter_chunk_seconds)
                if body.tablet_chunk_seconds is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "tablet_chunk_seconds", body.tablet_chunk_seconds)
                if body.letter_uncertain_threshold is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "letter_uncertain_threshold", new_low)
                if body.letter_accept_threshold is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "letter_accept_threshold", new_high)
                if body.max_letter_replacements is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "max_letter_replacements", body.max_letter_replacements)
                if body.left_eye_start_easier_steps is not None:
                    raw_text = _update_yaml_text_field(raw_text, "protocol", "left_eye_start_easier_steps", body.left_eye_start_easier_steps)
                if body.camera_source is not None:
                    raw_text = _update_yaml_text_field(raw_text, "bridges", "smarteyes_source", body.camera_source)
                if body.input_device is not None:
                    raw_text = _update_yaml_text_field(raw_text, "audio", "input_device", body.input_device)
                if body.output_device is not None:
                    raw_text = _update_yaml_text_field(raw_text, "audio", "output_device", body.output_device)
                if body.voice_gender is not None:
                    raw_text = _update_yaml_text_field(raw_text, "voice", "gender", body.voice_gender)
                if body.input_mode is not None:
                    raw_text = _update_yaml_text_field(raw_text, "ui", "input_mode", body.input_mode)
                if body.display_calibration_mode is not None:
                    raw_text = _update_yaml_text_field(raw_text, "display", "calibration_mode", body.display_calibration_mode)
                if body.display_diagonal_inches is not None:
                    raw_text = _update_yaml_text_field(raw_text, "display", "diagonal_inches", body.display_diagonal_inches)
                if body.display_px_per_mm is not None:
                    raw_text = _update_yaml_text_field(
                        raw_text, "display", "px_per_mm", f"{float(body.display_px_per_mm):.4f}"
                    )
                if body.display_calibration_target_mm is not None:
                    raw_text = _update_yaml_text_field(raw_text, "display", "calibration_target_mm", body.display_calibration_target_mm)
                if display_changed:
                    raw_text = _update_yaml_text_field(raw_text, "display", "calibrated_at", calibrated_at)
                if face_changed:
                    raw_text = _update_yaml_nested_field(raw_text, "bridges", "face", "host", face_device_ip)
                    raw_text = _update_yaml_nested_field(raw_text, "bridges", "face", "port", face_device_port)
                    raw_text = _update_yaml_nested_field(raw_text, "bridges", "face", "callback_host", jetson_face_ip)
                    raw_text = _update_yaml_nested_field(raw_text, "bridges", "face", "callback_port", jetson_face_port)

                tmp_file = target_file.with_suffix(".yaml.tmp")
                tmp_file.write_text(raw_text, encoding="utf-8")
                tmp_file.replace(target_file)
            else:
                tmp_file = target_file.with_suffix(".yaml.tmp")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    yaml.dump(existing_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                tmp_file.replace(target_file)

            if face_changed or vps_changed:
                env_file = Path(
                    os.getenv("AC_LAB_ENV_FILE")
                    or (root_dir.parents[1] / "deploy" / "env" / "lab.env")
                )
                if env_file.is_file():
                    env_text = env_file.read_text(encoding="utf-8")
                    if vps_changed:
                        env_text = _update_env_field(env_text, "VPS_TAILNET_HOST", vps_ip)
                        env_text = _update_env_field(env_text, "VPS_HOST", vps_ip)
                        env_text = _update_env_field(env_text, "MQTT_HOST", vps_ip)
                        env_text = _update_env_field(env_text, "MQTT_PORT", vps_mqtt_port)
                        env_text = _update_env_field(env_text, "VPS_FUNNEL_HOST", frappe_url)
                        env_text = _update_env_field(env_text, "HOSPITAL_BASE_URL", frappe_url)
                        env_text = _update_env_field(env_text, "MEDIA_BASE_URL", media_url)
                        env_text = _update_env_field(env_text, "MEDIA_PUBLIC_BASE", media_url)
                        env_text = _update_env_field(
                            env_text, "FACE_VECTORDB_BASE_URL", vectordb_url
                        )
                    if face_changed:
                        env_text = _update_env_field(env_text, "JETSON_LAN_IP", jetson_face_ip)
                        env_text = _update_env_field(env_text, "AIFACE_PANEL_IP", face_device_ip)
                        env_text = _update_env_field(env_text, "AIFACE_PANEL_PORT", face_device_port)
                        env_text = _update_env_field(env_text, "AIFACE_CALLBACK_PORT", jetson_face_port)
                    env_tmp = env_file.with_suffix(".env.tmp")
                    env_tmp.write_text(env_text, encoding="utf-8")
                    env_tmp.replace(env_file)
            logger.info("Settings saved and hot-reloaded to %s", target_file)
        except Exception as exc:
            logger.exception("Failed to persist updated YAML config to %s", target_file)
            return JSONResponse({"ok": False, "error": f"Lưu file thất bại: {exc}"}, status_code=500)

        display_payload = _display_config_payload(cfg, hub.display_metrics) if cfg is not None else {}
        if display_changed or body.distance_m is not None:
            await hub.broadcast({"type": "display_config", **display_payload})

        response = JSONResponse({
            "ok": True,
            "message": (
                "Đã lưu cấu hình; dịch vụ sẽ tự khởi động lại để áp dụng chế độ nhập và kết nối."
                if vps_changed or mode_changed
                else "Đã lưu và áp dụng cấu hình thành công."
            ),
            "restart_required": vps_changed or mode_changed,
            "vps": {
                "ip": vps_ip,
                "mqtt": f"{vps_ip}:{vps_mqtt_port}",
                "frappe": frappe_url,
                "media": media_url,
                "vectordb": vectordb_url,
            } if vps_fields_supplied else None,
            "face_connection": {
                "jetson_receiver": f"{jetson_face_ip}:{jetson_face_port}",
                "face_device": f"{face_device_ip}:{face_device_port}",
            } if face_fields_supplied else None,
            "display": display_payload or None,
        })
        if (vps_changed or mode_changed) and os.getenv("REPLACE_AC") == "1":
            def _restart_station_process() -> None:
                time.sleep(1.5)
                logger.warning("Restarting clinic station to apply VPS endpoints")
                os.kill(os.getpid(), signal.SIGTERM)

            threading.Thread(
                target=_restart_station_process,
                name="settings-restart",
                daemon=True,
            ).start()
        return response

    @app.get("/favicon.svg")
    async def favicon_svg() -> FileResponse:
        path = DISPLAY_DIR / "favicon.svg"
        if not path.is_file():
            raise HTTPException(404, "Put your icon at display/favicon.svg")
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/favicon.ico")
    async def favicon_ico() -> FileResponse:
        """Browsers request /favicon.ico; prefer .ico, else serve the SVG."""
        ico = DISPLAY_DIR / "favicon.ico"
        if ico.is_file():
            return FileResponse(ico, media_type="image/x-icon")
        svg = DISPLAY_DIR / "favicon.svg"
        if svg.is_file():
            return FileResponse(svg, media_type="image/svg+xml")
        raise HTTPException(404, "Put favicon.svg or favicon.ico in display/")

    @app.websocket("/ws/display")
    async def ws_display(ws: WebSocket) -> None:
        await hub.register(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(msg, dict) and msg.get("type") == "ui_event":
                    if msg.get("action") == "select_input_mode":
                        payload = msg.get("payload") or {}
                        mode = payload.get("mode") if isinstance(payload, dict) else None
                        if hub.choose_input_mode(str(mode or "")):
                            hub.push_ui_event(msg)
                            await hub.broadcast({"type": "input_mode", "input_mode": hub.input_mode})
                    elif msg.get("action") == "speak_letter":
                        payload = msg.get("payload") or {}
                        window_id = payload.get("window_id") if isinstance(payload, dict) else None
                        if window_id and window_id == hub.active_letter_window_id:
                            hub.push_ui_event(msg)
                    else:
                        hub.push_ui_event(msg)
                elif isinstance(msg, dict) and msg.get("type") == "stimulus_ready":
                    peer_host = (ws.client.host if ws.client else "").lower()
                    window_id = str(msg.get("window_id") or "")
                    hub.acknowledge_stimulus_ready(
                        window_id,
                        from_kiosk=peer_host in {"127.0.0.1", "::1"},
                        font_ready=bool(msg.get("font_ready")),
                    )
                elif isinstance(msg, dict) and msg.get("type") == "display_applied":
                    peer_host = (ws.client.host if ws.client else "").lower()
                    if peer_host not in {"127.0.0.1", "::1"}:
                        continue
                    revision = int(msg.get("revision") or 0)
                    if msg.get("boot_id") != hub.display_boot_id or revision != hub.display_revision:
                        continue
                    delay_ms = max(0, int(time.time() * 1000) - int(hub.last_command.get("_display_sent_at_ms") or 0))
                    hub.last_kiosk_applied = {
                        "revision": revision,
                        "scene": str(msg.get("scene") or ""),
                        "delay_ms": delay_ms,
                        "image_ready": bool(msg.get("image_ready", True)),
                        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                    if delay_ms > 1000 or not hub.last_kiosk_applied["image_ready"]:
                        logger.warning("Kiosk display applied slowly: %s", hub.last_kiosk_applied)
                elif isinstance(msg, dict) and msg.get("type") == "display_metrics":
                    # Only the kiosk chart opened directly on this Jetson can
                    # describe the physical patient display. Remote /preview
                    # browsers must never replace its pixel geometry.
                    host = (ws.headers.get("host") or "").rsplit(":", 1)[0].lower()
                    if host not in {"127.0.0.1", "localhost", "[::1]"}:
                        continue
                    hub.display_metrics = {
                        "screen_width": int(msg.get("screen_width") or 0),
                        "screen_height": int(msg.get("screen_height") or 0),
                        "viewport_width": int(msg.get("viewport_width") or 0),
                        "viewport_height": int(msg.get("viewport_height") or 0),
                        "device_pixel_ratio": float(msg.get("device_pixel_ratio") or 1.0),
                        "fullscreen": bool(msg.get("fullscreen")),
                        "source": "jetson_chart",
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                    current_cfg = cfg
                    if current_cfg is None:
                        from ac.config import load_config
                        current_cfg = load_config(resolved_cfg_path)
                    await ws.send_json(
                        {"type": "display_config", **_display_config_payload(current_cfg, hub.display_metrics)}
                    )
        except WebSocketDisconnect:
            await hub.unregister(ws)

    @app.get("/prompts/vi/{filename}")
    async def prompt_wav(filename: str) -> FileResponse:
        if not _SAFE_WAV.match(filename):
            raise HTTPException(404, "not found")
        path = DISPLAY_DIR / "prompts" / "vi" / filename
        if not path.is_file():
            raise HTTPException(404, "prompt wav missing")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/scenarios/vi/{gender}/{filename}")
    async def scenario_wav(gender: str, filename: str) -> FileResponse:
        if gender not in ("male", "female") or not _SAFE_WAV.match(filename):
            raise HTTPException(404, "not found")
        path = SCENARIOS_DIR / "vi" / gender / filename
        if not path.is_file():
            raise HTTPException(404, "scenario wav missing")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/api/audio/input")
    async def audio_input_status() -> JSONResponse:
        return JSONResponse(
            {
                "input": hub.audio_input,
                "output": getattr(hub, "audio_output", "sounddevice"),
                "device": getattr(hub, "audio_device_label", "") or "",
                "mic_live": hub.mic_live,
                "sample_rate": hub.mic_sample_rate,
            }
        )

    @app.websocket("/ws/mic")
    async def ws_mic(ws: WebSocket) -> None:
        await ws.accept()
        hub.mic_connect()
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data:
                    hub.push_mic_pcm(data)
                    continue
                text = msg.get("text")
                if not text:
                    continue
                try:
                    meta = json.loads(text)
                except Exception:  # noqa: BLE001
                    continue
                rate = meta.get("sampleRate") or meta.get("sample_rate")
                if rate:
                    try:
                        hub.mic_sample_rate = int(rate)
                    except (TypeError, ValueError):
                        pass
        except WebSocketDisconnect:
            pass
        finally:
            hub.mic_disconnect()

    @app.get("/audio.raw")
    async def audio_raw() -> StreamingResponse:
        block = max(256, int(hub.mic_sample_rate * 0.03) * 4)

        async def _pcm():
            while True:
                yield await asyncio.to_thread(hub.read_mic_pcm, block, 0.2)

        return StreamingResponse(
            _pcm(),
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.post("/api/display/command")
    async def post_command(command: dict[str, Any]) -> JSONResponse:
        await hub.broadcast(command)
        return JSONResponse({"ok": True})

    @app.get("/api/display/last")
    async def last_command() -> JSONResponse:
        return JSONResponse(hub.last_command, headers={"Cache-Control": "no-store"})

    @app.get("/api/display/health")
    async def display_health() -> JSONResponse:
        return JSONResponse({
            "revision": hub.display_revision,
            "scene": hub.last_command.get("scene") or hub.last_command.get("type"),
            "last_kiosk_applied": hub.last_kiosk_applied,
        }, headers={"Cache-Control": "no-store"})

    @app.get("/api/face/health")
    async def face_health() -> JSONResponse:
        enabled = bool(face is not None and getattr(face, "enabled", False))
        host = getattr(face, "host", None) if face is not None else None
        today_only = bool(
            face_vectordb_cfg is not None
            and getattr(face_vectordb_cfg, "sync_today_appointments_only", False)
        )
        return JSONResponse(
            {
                "ok": True,
                "enabled": enabled,
                "host": host,
                "service": "aiface_sync_wipe_identify",
                "sync_today_appointments_only": today_only,
                "enrollment": "desk_only",
                "note": (
                    "Patient enrollment is done at the reception desk; "
                    "POST /api/face/enroll remains for lab/debug only."
                ),
            }
        )

    @app.post("/api/face/enroll")
    async def face_enroll(body: FaceEnrollBody) -> JSONResponse:
        if face is None or not getattr(face, "enabled", False):
            raise HTTPException(503, "Face client disabled — start station with FACE_MODE=aiface")
        name = str(body.full_name).strip()
        if not name:
            raise HTTPException(400, "full_name is required")
        timeout = max(8.0, float(body.timeout_seconds or 25.0))
        loop = asyncio.get_running_loop()

        def _do_enroll() -> dict[str, Any]:
            return face.enroll_user(
                name,
                enroll_id=body.enroll_id,
                verify_timeout_seconds=timeout,
            )

        try:
            result = await loop.run_in_executor(enroll_pool, _do_enroll)
        except Exception as exc:  # noqa: BLE001
            logger.exception("face enroll failed")
            raise HTTPException(500, f"enroll_failed: {exc}") from exc
        if not isinstance(result, dict):
            return JSONResponse({"success": False, "error": "bad_enroll_result"})
        return JSONResponse(result)

    @app.post("/api/face/push_one")
    async def face_push_one(body: FacePushOneBody) -> JSONResponse:
        if face is None or not getattr(face, "enabled", False):
            raise HTTPException(503, "Face client disabled — start station with FACE_MODE=aiface")
        from ac.face_sync import push_one_face_to_device

        vdb = face_vectordb_cfg
        backupnum = int(getattr(vdb, "device_face_backupnum", 50) if vdb else 50)
        loop = asyncio.get_running_loop()

        def _do_push() -> bool:
            return push_one_face_to_device(
                face,
                media,
                enroll_id=body.enroll_id,
                full_name=body.full_name,
                media_get_url=body.media_get_url,
                image_b64=body.image_b64,
                backupnum=backupnum,
            )

        try:
            ok = await loop.run_in_executor(face_pool, _do_push)
        except Exception as exc:  # noqa: BLE001
            logger.exception("face push_one failed")
            raise HTTPException(500, f"push_one_failed: {exc}") from exc
        return JSONResponse({"success": bool(ok), "enroll_id": body.enroll_id})

    @app.get("/api/face/gallery_status/{enroll_id}")
    async def face_gallery_status(enroll_id: int, version: str) -> JSONResponse:
        ready = False
        if face is not None and getattr(face, "enabled", False):
            ready = bool(await asyncio.get_running_loop().run_in_executor(
                face_pool, lambda: face.gallery_ready(enroll_id, version),
            ))
        return JSONResponse({"ready": ready, "enroll_id": enroll_id})

    @app.post("/api/face/sync_today")
    async def face_sync_today() -> JSONResponse:
        if face is None or not getattr(face, "enabled", False):
            raise HTTPException(503, "Face client disabled — start station with FACE_MODE=aiface")
        if hospital is None:
            raise HTTPException(503, "Hospital client not configured")
        from ac.face_sync import sync_today_appointments_to_device

        vdb = face_vectordb_cfg
        loop = asyncio.get_running_loop()

        def _do_sync() -> dict[str, Any]:
            res = sync_today_appointments_to_device(
                hospital,
                face,
                media,
                max_faces=int(getattr(vdb, "max_faces", 500) if vdb else 500),
                device_face_backupnum=int(
                    getattr(vdb, "device_face_backupnum", 50) if vdb else 50
                ),
                prune_not_in_today=bool(
                    getattr(vdb, "prune_not_in_today", True) if vdb else True
                ),
            )
            return res.as_dict()

        try:
            result = await loop.run_in_executor(face_pool, _do_sync)
        except Exception as exc:  # noqa: BLE001
            logger.exception("face sync_today failed")
            raise HTTPException(500, f"sync_today_failed: {exc}") from exc
        return JSONResponse({"success": True, **result})

    @app.post("/api/face/wipe_gallery")
    async def face_wipe_gallery(body: FaceWipeGalleryBody) -> JSONResponse:
        if face is None or not getattr(face, "enabled", False):
            raise HTTPException(503, "Face client disabled — start station with FACE_MODE=aiface")
        from ac.face_sync import wipe_device_gallery

        loop = asyncio.get_running_loop()

        def _do_wipe() -> dict[str, Any]:
            return wipe_device_gallery(face, preserve_stranger=body.preserve_stranger)

        try:
            result = await loop.run_in_executor(face_pool, _do_wipe)
        except Exception as exc:  # noqa: BLE001
            logger.exception("face wipe_gallery failed")
            raise HTTPException(500, f"wipe_gallery_failed: {exc}") from exc
        return JSONResponse({"success": True, **result})

    @app.post("/api/face/delete_one")
    async def face_delete_one(body: FaceDeleteOneBody) -> JSONResponse:
        if face is None or not getattr(face, "enabled", False):
            raise HTTPException(503, "Face client disabled — start station with FACE_MODE=aiface")
        loop = asyncio.get_running_loop()

        def _do_delete() -> dict[str, Any]:
            # Serialize deletion with gallery pushes/syncs so a concurrent
            # upsert cannot recreate the same enroll ID while it is removed.
            with face.gallery_lock:
                if not face.delete_user(int(body.enroll_id)):
                    raise HTTPException(
                        502,
                        f"AiFace device still has enroll_id={body.enroll_id} after delete",
                    )
                return {"enroll_id": int(body.enroll_id)}

        try:
            result = await loop.run_in_executor(face_pool, _do_delete)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("face delete_one failed")
            raise HTTPException(500, f"delete_one_failed: {exc}") from exc
        return JSONResponse({"success": True, **result})

    if DISPLAY_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(DISPLAY_DIR)), name="static")
    if CONTROL_DIR.is_dir():
        app.mount("/control-static", StaticFiles(directory=str(CONTROL_DIR)), name="control-static")
    return app


class DisplayClient:
    """Orchestrator-facing display API."""

    def __init__(self, hub: DisplayHub) -> None:
        self.hub = hub

    def show_queue(self, queue_number: str | None, message: str) -> None:
        self.hub.send(
            {
                "type": "show_message",
                "mode": "queue_stub",
                "queue_number": queue_number or "",
                "text_vi": message,
                "exam_mode": True,
            }
        )

    def show_row(
        self,
        logmar: float,
        letters: list[str],
        *,
        letter_pad: bool = False,
        prompt_vi: str | None = None,
        allow_skip: bool = False,
        skip_label: str = "Bỏ qua (đúng)",
    ) -> None:
        cmd: dict[str, Any] = {
            "type": "show_row",
            "mode": "row",
            "logmar": logmar,
            "letters": letters,
            "exam_mode": True,
            "letter_pad": bool(letter_pad),
            "allow_skip": bool(allow_skip),
            "skip_label": skip_label,
            "skip_action": "skip_letter",
        }
        if prompt_vi:
            cmd["prompt_vi"] = prompt_vi
        self.hub.send(cmd)

    def show_single_letter(
        self,
        logmar: float,
        letter: str,
        *,
        eye_side: str | None = None,
        letter_pad: bool = False,
        prompt_vi: str | None = None,
        allow_skip: bool = False,
        skip_label: str = "Bỏ qua (đúng)",
        progress_vi: str | None = None,
        countdown_seconds: float | None = None,
        window_id: str | None = None,
    ) -> None:
        """Boss/confirm protocol: one optotype on the chart."""
        cmd: dict[str, Any] = {
            "type": "show_single",
            "mode": "single",
            "logmar": logmar,
            "letter": str(letter).upper(),
            "exam_mode": True,
            "letter_pad": bool(letter_pad),
            "allow_skip": bool(allow_skip),
            "skip_label": skip_label,
            "skip_action": "skip_letter",
        }
        if eye_side:
            cmd["eye_side"] = str(eye_side).upper()
        if prompt_vi:
            cmd["prompt_vi"] = prompt_vi
        if progress_vi:
            cmd["progress_vi"] = progress_vi
        if countdown_seconds is not None:
            cmd["countdown_seconds"] = max(0.0, float(countdown_seconds))
        if window_id is not None:
            cmd["window_id"] = window_id
            self.hub.arm_stimulus_window(window_id)
        self.hub.send(cmd)

    def start_listen_window(self, window_id: str, seconds: float) -> None:
        self.hub.send(
            {
                "type": "listen_window_start",
                "window_id": window_id,
                "countdown_seconds": max(0.0, float(seconds)),
            }
        )

    def show_letter_confirm(
        self,
        heard_letter: str,
        *,
        prompt_vi: str | None = None,
        allow_skip: bool = False,
        logmar: float = 0.7,
        acuity_label: str | None = None,
        allow_confirm_yes: bool = True,
        countdown_seconds: float | None = None,
    ) -> None:
        """Echo STT hypothesis at the *current* row size (never jump to 2/10)."""
        from ac.scoring import vn_over_10

        heard = str(heard_letter).upper()
        lm = float(logmar)
        label = (acuity_label or "").strip() or vn_over_10(10 ** (-lm))
        cmd: dict[str, Any] = {
            "type": "letter_confirm",
            "mode": "letter_confirm",
            "heard_letter": heard,
            "logmar": lm,
            "acuity_label": label,
            "allow_confirm_yes": bool(allow_confirm_yes),
            "text_vi": prompt_vi
            or f"Hệ thống nghe được chữ {heard}. Bạn có đọc đúng chữ này không?",
            "exam_mode": True,
            "allow_skip": bool(allow_skip),
            "skip_label": "Bỏ qua",
            "skip_action": "skip_letter",
        }
        if countdown_seconds is not None:
            cmd["countdown_seconds"] = max(0.0, float(countdown_seconds))
        self.hub.send(cmd)

    def hide_letter_pad(self) -> None:
        self.hub.send({"type": "letter_pad", "show": False})

    def show_message(
        self,
        text_vi: str,
        *,
        exam_mode: bool = True,
        allow_skip: bool = False,
        skip_label: str = "Bỏ qua",
        skip_action: str = "skip_step",
        queue_number: str | None = None,
        scene: str | None = None,
    ) -> None:
        cmd: dict[str, Any] = {
            "type": "show_message",
            "mode": "idle",
            "text_vi": text_vi,
            "exam_mode": exam_mode,
            "allow_skip": bool(allow_skip),
            "skip_label": skip_label,
            "skip_action": skip_action,
        }
        if queue_number is not None:
            cmd["queue_number"] = queue_number
        if scene:
            cmd["scene"] = scene
        self.hub.send(cmd)

    def show_station_home(self) -> None:
        """Reset patient-facing displays after a session is cancelled."""
        self.hub.send({"type": "station_home"})

    def show_welcome(
        self,
        name: str,
        *,
        allow_skip: bool = False,
        auto_continue_seconds: float = 3.0,
        show_continue: bool = True,
    ) -> None:
        self.hub.send(
            {
                "type": "ui_screen",
                "mode": "welcome",
                "text_vi": f"Xin chào {name}",
                "patient_name": name,
                "exam_mode": True,
                "allow_skip": bool(allow_skip),
                "skip_label": "Bỏ qua",
                "skip_action": "welcome_continue",
                "scene": "welcome",
                "auto_continue_seconds": float(auto_continue_seconds),
                "show_continue": bool(show_continue),
                "input_mode": self.hub.input_mode,
            }
        )

    def show_input_mode_choice(self, default_mode: str) -> None:
        self.hub.begin_input_mode_choice(default_mode)
        self.hub.send({
            "type": "ui_screen",
            "mode": "input_select",
            "text_vi": "Vui lòng chọn cách trả lời trên tablet.",
            "default_input_mode": default_mode,
            "exam_mode": True,
        })

    def finish_input_mode_choice(self) -> str:
        mode = self.hub.finish_input_mode_choice()
        self.hub.send({"type": "input_mode", "input_mode": mode})
        return mode

    def show_countdown(self, seconds: int = 3) -> None:
        self.hub.send(
            {
                "type": "ui_screen",
                "mode": "countdown",
                "scene": "countdown",
                "text_vi": str(int(seconds)),
                "seconds": int(seconds),
                "exam_mode": True,
            }
        )

    def show_register_prompt(self, *, allow_skip: bool = False) -> None:
        self.hub.send(
            {
                "type": "ui_screen",
                "mode": "register_prompt",
                "text_vi": (
                    "Bạn chưa có trong hệ thống. "
                    "Nhập họ tên, bấm \"Đăng ký\", rồi nhìn thẳng máy nhận diện "
                    "(nếu máy đang bận: bước ra 2 giây rồi nhìn lại)."
                ),
                "exam_mode": True,
                "allow_skip": bool(allow_skip),
                "skip_label": "Bỏ qua nhận diện",
                "skip_action": "skip_step",
                "scene": "register",
            }
        )

    def show_service_menu(self, name: str, *, allow_skip: bool = False) -> None:
        self.hub.send(
            {
                "type": "ui_screen",
                "mode": "service_menu",
                "text_vi": f"Xin chào {name}. Chọn dịch vụ:",
                "patient_name": name,
                "services": [{"id": "vision_test", "label": "Kiểm tra thị lực"}],
                "exam_mode": True,
                "allow_skip": bool(allow_skip),
                "skip_label": "Bỏ qua → đo thị lực",
                "skip_action": "service_vision_test",
            }
        )

    def consume_ui_action(self, *actions: Any) -> str | None:
        if len(actions) == 1 and isinstance(actions[0], (set, frozenset, list, tuple)):
            wanted = {str(a) for a in actions[0]}
        else:
            wanted = {str(a) for a in actions}
        return self.hub.consume_ui_action(wanted)

    def drain_ui_actions(self, actions: set[str] | None = None) -> None:
        self.hub.drain_ui_actions(actions)

    def wait_ui_action(
        self,
        *actions: Any,
        timeout: float = 120.0,
        stop_flag: Any = None,
    ) -> str | None:
        if len(actions) == 1 and isinstance(actions[0], (set, frozenset, list, tuple)):
            wanted = {str(a) for a in actions[0]}
        else:
            wanted = {str(a) for a in actions}
        return self.hub.wait_ui_action(wanted, timeout=timeout, stop_flag=stop_flag)

    def wait_ui_event(
        self,
        *actions: Any,
        timeout: float = 120.0,
        stop_flag: Any = None,
    ) -> dict[str, Any] | None:
        if len(actions) == 1 and isinstance(actions[0], (set, frozenset, list, tuple)):
            wanted = {str(a) for a in actions[0]}
        else:
            wanted = {str(a) for a in actions}
        return self.hub.wait_ui_event(wanted, timeout=timeout, stop_flag=stop_flag)

    def play_audio(self, url: str, *, duration_seconds: float | None = None, text_vi: str = "") -> None:
        cmd: dict[str, Any] = {"type": "play_audio", "url": url, "text_vi": text_vi}
        if duration_seconds is not None:
            cmd["duration_seconds"] = duration_seconds
        self.hub.send(cmd)

    def stop_audio(self) -> None:
        self.hub.send({"type": "stop_audio"})

    def clear(self) -> None:
        self.show_message("Nhìn vào máy nhận diện khuôn mặt.", scene="face")

    def summary(self, text_vi: str) -> None:
        self.hub.send(
            {
                "type": "show_message",
                "mode": "confirm",
                "text_vi": text_vi,
                "exam_mode": True,
            }
        )

    def show_results(
        self,
        *,
        text_vi: str,
        session_id: str,
        patient_name: str | None = None,
        patient_id: str | None = None,
        acuity: dict[str, Any] | None = None,
        show_logmar: bool = False,
        layout: str = "cards",
    ) -> None:
        self.hub.send(
            {
                "type": "results",
                "mode": "results",
                "text_vi": text_vi,
                "session_id": session_id,
                "patient_name": patient_name or "",
                "patient_id": patient_id or "",
                "acuity": acuity or {},
                "show_logmar": bool(show_logmar),
                "layout": str(layout or "cards"),
                "exam_mode": True,
            }
        )


def run_display_server(
    hub: DisplayHub,
    host: str,
    port: int,
    *,
    face: Any | None = None,
    face_vector: Any | None = None,
    media: Any | None = None,
    hospital: Any | None = None,
    face_vectordb_cfg: Any | None = None,
    readiness: Any | None = None,
    audio_input: str = "device",
    cfg: Any | None = None,
    config_path: Path | str | None = None,
    orchestrator: Any | None = None,
    audio_player: Any | None = None,
    stt_bridge: Any | None = None,
) -> threading.Thread:
    """Start chart HTTP server. Raises OSError if ``port`` is already bound."""
    import socket
    import uvicorn

    # Fail fast before spawning uvicorn (avoids MQTT-only half-started AC).
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host if host not in ("0.0.0.0", "") else "0.0.0.0", int(port)))
    except OSError as exc:
        raise OSError(
            f"Chart port {port} already in use — stop the other AC "
            f"(pgrep -af ac.main) or open the existing http://<jetson>:{port}/"
        ) from exc
    finally:
        probe.close()

    app = create_display_app(
        hub,
        face=face,
        face_vector=face_vector,
        media=media,
        hospital=hospital,
        face_vectordb_cfg=face_vectordb_cfg,
        readiness=readiness,
        audio_input=audio_input,
        cfg=cfg,
        config_path=config_path,
        orchestrator=orchestrator,
        audio_player=audio_player,
        stt_bridge=stt_bridge,
    )
    ready = threading.Event()
    failed: list[BaseException] = []

    def _run_uvicorn() -> None:
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        ready.set()
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001
            failed.append(exc)
            ready.set()

    t = threading.Thread(target=_run_uvicorn, name="display-server", daemon=True)
    t.start()
    if not ready.wait(timeout=5.0):
        raise OSError(f"Chart display server did not start on {host}:{port}")
    if failed:
        raise OSError(f"Chart display server failed: {failed[0]}") from failed[0]
    # Brief settle; uvicorn logs bind errors asynchronously after Config init
    time.sleep(0.35)
    check = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        check.settimeout(1.0)
        check.connect(("127.0.0.1", int(port)))
    except OSError as exc:
        raise OSError(
            f"Chart did not listen on :{port} after start — "
            "another process may have taken the port"
        ) from exc
    finally:
        check.close()
    return t
