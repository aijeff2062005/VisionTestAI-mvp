"""Camera discovery and capture helpers (webcam, video files)."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

# On macOS, OpenCV AVFoundation indices ≠ ffmpeg device indices when Continuity /
# OBS are present. Always open by ffmpeg *device name* on darwin.


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_pipeline_camera_prefs() -> list[str]:
    """Preferred name substrings for --source macbook (from configs/default.yaml)."""
    path = _project_root() / "configs" / "default.yaml"
    defaults = ["FaceTime HD Camera", "FaceTime", "built-in"]
    if not path.is_file():
        return defaults
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        prefs = (cfg.get("pipeline") or {}).get("macbook_match")
        if isinstance(prefs, list) and prefs:
            return [str(p) for p in prefs]
        if isinstance(prefs, str) and prefs.strip():
            return [prefs.strip()]
    except OSError:
        pass
    return defaults


def _is_screen_capture(name: str) -> bool:
    n = name.lower()
    return "capture screen" in n or n.startswith("screen ")


def _skip_list_device(name: str) -> bool:
    """Devices that inflate AVFoundation lists / OpenCV usually cannot open."""
    n = name.lower()
    if _is_screen_capture(name):
        return True
    if "desk view" in n:
        return True
    return False


def _is_virtual_cam(name: str) -> bool:
    n = name.lower()
    return "obs" in n or "virtual" in n


def _mac_avfoundation_names() -> list[tuple[int, str]]:
    """List video input devices via ffmpeg avfoundation (macOS)."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-f",
                "avfoundation",
                "-list_devices",
                "true",
                "-i",
                "",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    text = (proc.stderr or "") + (proc.stdout or "")
    names: list[tuple[int, str]] = []
    in_video = False
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            in_video = True
            continue
        if "AVFoundation audio devices" in line:
            break
        if not in_video:
            continue
        m = re.search(r"\]\s*\[(\d+)\]\s*(.+)$", line)
        if not m:
            m = re.search(r"\[(\d+)\]\s*(.+)$", line)
        if m:
            names.append((int(m.group(1)), m.group(2).strip()))
    return names


def _opencv_backend() -> int:
	if sys.platform == "darwin":
		return cv2.CAP_AVFOUNDATION
	# Jetson/Linux: prefer V4L2 — CAP_ANY often picks FFMPEG and fails on UVC.
	return getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)


def _linux_v4l_devices() -> list[tuple[int, str, str]]:
	"""Return (opencv_index, name, /dev/videoN) for capture nodes only."""
	base = Path("/sys/class/video4linux")
	if not base.is_dir():
		return []
	out: list[tuple[int, str, str]] = []
	for node in sorted(base.glob("video*"), key=lambda p: int(p.name.replace("video", "") or 0)):
		try:
			idx = int(node.name.replace("video", ""))
		except ValueError:
			continue
		name_path = node / "name"
		try:
			name = name_path.read_text(encoding="utf-8", errors="ignore").strip() or node.name
		except OSError:
			name = node.name
		# Skip pure metadata nodes when possible (name often contains "Metadata")
		if "metadata" in name.lower():
			continue
		dev = f"/dev/{node.name}"
		if not Path(dev).exists():
			continue
		out.append((idx, name, dev))
	return out


def _opencv_can_open(index: int, *, warm_reads: int = 1) -> bool:
	"""True if OpenCV can open this AVFoundation/OpenCV index and read a frame."""
	cap = cv2.VideoCapture(index, _opencv_backend())
	ok = bool(cap.isOpened())
	if ok:
		for _ in range(max(1, warm_reads)):
			ret, _frame = cap.read()
			ok = bool(ret)
			if not ok:
				break
	cap.release()
	return ok


def _probe_opencv_indices(max_index: int = 8) -> list[tuple[int, str]]:
	found: list[tuple[int, str]] = []
	# Prefer real V4L names on Linux
	if sys.platform != "darwin":
		for idx, name, _dev in _linux_v4l_devices():
			if _opencv_can_open(idx):
				found.append((idx, name))
		if found:
			return found
	for idx in range(max_index + 1):
		if _opencv_can_open(idx):
			found.append((idx, f"OpenCV index {idx}"))
	return found


def list_cameras(*, include_screen: bool = False) -> list[dict[str, Any]]:
	"""
	Cameras from ffmpeg AVFoundation (macOS) or V4L2/OpenCV probe (elsewhere).

	Indices are **ffmpeg** indices. On macOS they often do NOT match OpenCV —
	SmartEyes opens by device name via ffmpeg so Continuity cannot steal C270.
	"""
	if sys.platform == "darwin":
		ffmpeg = _mac_avfoundation_names()
		if ffmpeg:
			devices: list[dict[str, Any]] = []
			for idx, name in ffmpeg:
				if _skip_list_device(name) and not include_screen:
					continue
				if _skip_list_device(name) and include_screen:
					devices.append({"index": idx, "name": name})
					continue
				if not _skip_list_device(name):
					devices.append({"index": idx, "name": name})
			return devices
	return [
		{"index": idx, "name": name}
		for idx, name in _probe_opencv_indices()
	]


def find_camera_index(name_substring: str) -> int | None:
	"""Find camera index whose name contains substring (ffmpeg on macOS, V4L on Linux)."""
	needle = name_substring.lower().strip()
	if not needle:
		return None

	for idx, name in _mac_avfoundation_names() or []:
		if _skip_list_device(name):
			continue
		if needle in name.lower():
			return idx

	if sys.platform != "darwin":
		for idx, name, _dev in _linux_v4l_devices():
			if needle in name.lower():
				return idx

	for cam in list_cameras(include_screen=False):
		if needle in cam["name"].lower() and not _is_screen_capture(cam["name"]):
			return int(cam["index"])
	return None


def find_camera_name(name_substring: str) -> str | None:
    """Full ffmpeg device name containing substring (macOS)."""
    needle = name_substring.lower().strip()
    if not needle:
        return None
    for _idx, name in _mac_avfoundation_names():
        if _skip_list_device(name):
            continue
        if needle in name.lower():
            return name
    return None


def ffmpeg_name_for_index(index: int) -> str | None:
    for idx, name in _mac_avfoundation_names():
        if idx == index:
            return name
    return None


def find_macbook_camera_index(prefer: list[str] | None = None) -> int | None:
    """
    Resolve MacBook webcam by preferred name substrings (config: pipeline.macbook_match).

    Skips OBS / virtual cams. ``facetime`` alias forces FaceTime separately.
    """
    prefs = prefer if prefer is not None else _load_pipeline_camera_prefs()
    cams = list_cameras()

    for needle in prefs:
        n = needle.lower()
        for cam in cams:
            name = cam["name"].lower()
            if _is_virtual_cam(name) or "desk view" in name:
                continue
            if n in name:
                return int(cam["index"])

    # Fallbacks
    for cam in cams:
        name = cam["name"].lower()
        if _is_virtual_cam(name) or "desk view" in name:
            continue
        if "facetime" in name or "built-in" in name:
            return int(cam["index"])
    return None


def find_facetime_camera_index() -> int | None:
    cams = list_cameras()
    for cam in cams:
        if "facetime" in cam["name"].lower():
            return int(cam["index"])
    return None


def camera_label(resolved: str | int) -> str:
    """Name for a resolved index — ffmpeg only (never re-open cams)."""
    if isinstance(resolved, int):
        name = ffmpeg_name_for_index(resolved)
        return name if name else f"camera {resolved}"
    return str(resolved)


def resolve_source(source: str | int) -> str | int:
    """
    Resolve config/CLI source to an OpenCV capture index or file path.

    ``macbook`` uses ``pipeline.macbook_match`` from config (name preference).
    ``facetime`` always targets FaceTime HD Camera by name.
    """
    if isinstance(source, int):
        return source

    s = str(source).strip()
    if not s:
        s = "macbook"

    # Network streams (MJPEG/RTSP) pass straight through to OpenCV
    if s.lower().startswith(("http://", "https://", "rtsp://", "udp://", "tcp://")):
        return s

    key = s.lower()
    if key in ("macbook", "builtin", "built-in", "default"):
        idx = find_macbook_camera_index()
        if idx is not None:
            return idx
        return 0

    if key == "facetime":
        idx = find_facetime_camera_index()
        if idx is not None:
            return idx
        idx = find_macbook_camera_index()
        return idx if idx is not None else 0

    path = Path(s)
    if not path.is_absolute():
        candidate = _project_root() / path
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    if path.exists() and path.is_file():
        return str(path.resolve())
    # Linux V4L device nodes (/dev/video0) are not regular files
    if path.exists() and s.startswith("/dev/video"):
        return str(path)

    if s.isdigit():
        return int(s)

    idx = find_camera_index(s)
    if idx is not None:
        return idx

    return s


class FFmpegAVFoundationCapture:
    """
    macOS webcam via ffmpeg, selected by **device name** (not OpenCV index).

    Continuity / OBS scramble OpenCV indices so ``VideoCapture(2)`` can open
    Kagami Rudo while ffmpeg still lists ``[2] C270 HD WEBCAM``.
    """

    def __init__(
        self,
        device_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
    ) -> None:
        self.device_name = device_name
        self._width = int(width)
        self._height = int(height)
        self._fps = int(fps)
        self._frame_nbytes = self._width * self._height * 3
        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._alive = False
        self._err = ""
        self._open()

    def _build_cmd(self, *, with_size: bool) -> list[str]:
        # Prefer uyvy422 — required by many UVC cams including Logitech C270.
        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-pixel_format",
            "uyvy422",
            "-framerate",
            str(self._fps),
        ]
        if with_size:
            cmd += ["-video_size", f"{self._width}x{self._height}"]
        cmd += [
            "-i",
            f"{self.device_name}:none",
            "-an",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        return cmd

    def _open(self) -> None:
        last_err = ""
        # Try common UVC / Continuity / OBS modes (fps+size must match device).
        attempts: list[tuple[int, int, int, bool]] = [
            (self._width, self._height, self._fps, True),
            (1280, 720, 30, True),
            (1280, 720, 25, True),
            (640, 480, 30, True),
            (1920, 1080, 30, True),
            (1920, 1080, 60, True),
        ]
        native = _ffmpeg_probe_size(self.device_name)
        if native is not None:
            attempts.append((native[0], native[1], 30, True))
            attempts.append((native[0], native[1], 60, True))
        attempts.append((1280, 720, 30, False))  # let ffmpeg pick size (still fixed out)

        seen: set[tuple[int, int, int, bool]] = set()
        for width, height, fps, with_size in attempts:
            key = (width, height, fps, with_size)
            if key in seen:
                continue
            seen.add(key)
            self._width, self._height, self._fps = width, height, fps
            self._frame_nbytes = width * height * 3
            cmd = self._build_cmd(with_size=with_size)
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=self._frame_nbytes * 2,
                )
            except FileNotFoundError as exc:
                self._err = "ffmpeg not found (brew install ffmpeg)"
                raise RuntimeError(self._err) from exc

            assert proc.stdout is not None
            deadline = time.time() + 3.5
            raw = b""
            while time.time() < deadline and len(raw) < self._frame_nbytes:
                chunk = proc.stdout.read(self._frame_nbytes - len(raw))
                if not chunk:
                    break
                raw += chunk

            if len(raw) >= self._frame_nbytes:
                frame = (
                    np.frombuffer(raw[: self._frame_nbytes], dtype=np.uint8)
                    .reshape((self._height, self._width, 3))
                    .copy()
                )
                self._proc = proc
                self._latest = frame
                self._alive = True
                self._thread = threading.Thread(
                    target=self._reader_loop, name="ffmpeg-cam", daemon=True
                )
                self._thread.start()
                # UVC (C270) often streams black for ~0.5–2s after open
                self._wait_for_nonblack(timeout=3.0)
                return

            err = b""
            try:
                if proc.stderr:
                    err = proc.stderr.read(800)
            except OSError:
                pass
            last_err = err.decode(errors="replace").strip() or "no frames"
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

        self._err = last_err
        raise RuntimeError(
            f"ffmpeg cannot open {self.device_name!r}: {last_err}"
        )

    def _wait_for_nonblack(self, *, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                frame = None if self._latest is None else self._latest
            if frame is not None and float(frame.mean()) >= 1.0:
                return
            time.sleep(0.05)

    def _reader_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        while self._alive:
            raw = stdout.read(self._frame_nbytes)
            if not raw or len(raw) < self._frame_nbytes:
                self._alive = False
                break
            frame = (
                np.frombuffer(raw, dtype=np.uint8)
                .reshape((self._height, self._width, 3))
                .copy()
            )
            with self._lock:
                self._latest = frame

    def isOpened(self) -> bool:
        return self._alive and self._proc is not None and self._proc.poll() is None

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._latest is None:
                return False, None
            return True, self._latest.copy()

    def set(self, prop: int, value: float) -> bool:
        # Size/fps fixed at open; accept no-ops for OpenCV API compatibility.
        return True

    def get(self, prop: int) -> float:
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self._width)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self._height)
        if prop == cv2.CAP_PROP_FPS:
            return float(self._fps)
        return 0.0

    def release(self) -> None:
        self._alive = False
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            self._latest = None


def _ffmpeg_probe_size(device_name: str) -> tuple[int, int] | None:
    """Grab one JPEG to learn native WxH for a named AVFoundation device."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-framerate",
                "30",
                "-i",
                f"{device_name}:none",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if not proc.stdout:
        return None
    arr = np.frombuffer(proc.stdout, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    return int(w), int(h)


def _resolve_mac_device_name(source: str | int, resolved: str | int) -> str | None:
    """Map CLI source / resolved index → ffmpeg AVFoundation device name."""
    raw = str(source).strip()
    key = raw.lower()

    if key and not key.isdigit() and key not in (
        "macbook",
        "builtin",
        "built-in",
        "default",
        "facetime",
    ):
        # User asked by substring ("C270") — bind to full name
        name = find_camera_name(raw)
        if name:
            return name

    if isinstance(resolved, int):
        return ffmpeg_name_for_index(resolved)

    if isinstance(resolved, str) and not Path(resolved).exists():
        return find_camera_name(resolved) or resolved
    return None


def open_video_capture(
    source: str | int,
    *,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
) -> cv2.VideoCapture | FFmpegAVFoundationCapture:
    """Open camera/file. On macOS, webcams open by ffmpeg device name."""
    resolved = resolve_source(source)
    req_w = int(width) if width else 1280
    req_h = int(height) if height else 720
    req_fps = int(fps) if fps else 30

    # Network stream (MJPEG over HTTP, RTSP) → OpenCV/FFmpeg
    if isinstance(resolved, str) and resolved.lower().startswith(
        ("http://", "https://", "rtsp://", "udp://", "tcp://")
    ):
        cap = cv2.VideoCapture(resolved, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(resolved)
        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            for _ in range(30):
                ok, frame = cap.read()
                if ok and frame is not None and getattr(frame, "size", 0) > 0:
                    h, w = frame.shape[:2]
                    # print(f"Opened stream {resolved} at {w}x{h}")
                    return cap
                time.sleep(0.1)
        cap.release()
        raise RuntimeError(
            f"Cannot open stream: {resolved!r}. "
            "Check the Jetson MJPEG server is running and reachable."
        )

    # File path → OpenCV
    if isinstance(resolved, str) and Path(resolved).is_file():
        cap = cv2.VideoCapture(resolved)
        if cap.isOpened():
            return cap
        cap.release()
        raise RuntimeError(f"Cannot open video file: {resolved!r}")

    # Linux /dev/videoN character device
    if isinstance(resolved, str) and resolved.startswith("/dev/video") and Path(resolved).exists():
        backends = [_opencv_backend(), cv2.CAP_ANY]
        last_err = ""
        size_tries = [
            (req_w, req_h),
            (1280, 720),
            (960, 540),
            (640, 480),
        ]
        # de-dupe while preserving order
        seen: set[tuple[int, int]] = set()
        sizes: list[tuple[int, int]] = []
        for wh in size_tries:
            if wh not in seen:
                seen.add(wh)
                sizes.append(wh)
        for backend in backends:
            for tw, th in sizes:
                cap = cv2.VideoCapture(resolved, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                time.sleep(0.15)
                # MJPG before size: UVC cams (C270) only hit full fps compressed.
                # Uncompressed YUYV caps 720p at ~5 fps.
                try:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                except Exception:
                    pass
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, tw)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, th)
                if req_fps:
                    try:
                        cap.set(cv2.CAP_PROP_FPS, float(req_fps))
                    except Exception:
                        pass
                for _ in range(8):
                    ret, frame = cap.read()
                    if ret and frame is not None and getattr(frame, "size", 0) > 0:
                        aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or tw)
                        ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or th)
                        afps = cap.get(cv2.CAP_PROP_FPS)
                        cc = int(cap.get(cv2.CAP_PROP_FOURCC))
                        cc = "".join(chr((cc >> 8 * i) & 0xFF) for i in range(4))
                        print(
                            f"Opened {resolved} at {aw}x{ah} {cc} @{afps:g}fps "
                            f"(requested {tw}x{th}@{req_fps})"
                        )
                        return cap
                    time.sleep(0.05)
                cap.release()
                last_err = f"no frames from {resolved} at {tw}x{th}"
        raise RuntimeError(
            f"Cannot open video source: {source!r} (resolved: {resolved!r}). {last_err}."
        )

    if sys.platform == "darwin":
        name = _resolve_mac_device_name(source, resolved)
        if name and not _skip_list_device(name):
            try:
                cap = FFmpegAVFoundationCapture(name, width=req_w, height=req_h, fps=req_fps or 30)
                # Warn if USB cam yields a black frame (often in-use / unplugged)
                ok, frame = cap.read()
                if ok and frame is not None and float(frame.mean()) < 1.0:
                    print(
                        f"Warning: {name} opened but frames are black — "
                        "check USB plug, lens cover, or quit apps using the cam."
                    )
                print(f"Opened via ffmpeg by name: {name}")
                return cap
            except RuntimeError as exc:
                last = str(exc)
                # Fall through to OpenCV only for FaceTime-ish devices
                if "facetime" not in name.lower():
                    raise RuntimeError(
                        f"Cannot open {name!r} via ffmpeg ({last}). "
                        "Close Zoom/Chrome/OBS, unplug/replug USB, then "
                        'retry: --source "C270"'
                    ) from exc

    # Non-macOS or FaceTime fallback: OpenCV index
    backends = [_opencv_backend()]
    if sys.platform != "darwin":
        backends.append(cv2.CAP_ANY)
    elif backends[0] != cv2.CAP_ANY:
        backends.append(cv2.CAP_ANY)

    if not isinstance(resolved, int):
        raise RuntimeError(f"Cannot open video source: {source!r}")

    last_err = ""
    for attempt in range(3):
        for backend in backends:
            cap = cv2.VideoCapture(resolved, backend)
            if not cap.isOpened():
                cap.release()
                continue
            time.sleep(0.15 if attempt == 0 else 0.35)
            # MJPG before size: uncompressed YUYV caps 720p ~5 fps on UVC cams
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            except Exception:
                pass
            # Prefer HD for eye-cover; fall back if camera rejects
            for tw, th in ((req_w, req_h), (1280, 720), (640, 480)):
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, tw)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, th)
                if req_fps:
                    try:
                        cap.set(cv2.CAP_PROP_FPS, float(req_fps))
                    except Exception:
                        pass
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                for _ in range(8):
                    ret, frame = cap.read()
                    if ret and frame is not None and getattr(frame, "size", 0) > 0:
                        aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or tw)
                        ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or th)
                        afps = cap.get(cv2.CAP_PROP_FPS)
                        print(f"Opened camera index {resolved} at {aw}x{ah} @{afps:g}fps")
                        return cap
                    time.sleep(0.05)
                last_err = f"no frames from OpenCV index {resolved} at {tw}x{th}"
            cap.release()
            last_err = f"no frames from OpenCV index {resolved}"
        time.sleep(0.35)

    raise RuntimeError(
        f"Cannot open video source: {source!r} (resolved: {resolved!r}). "
        f"{last_err}. "
        'Try: --source "C270" or --list-cameras'
    )


def _macbook_tag_for(name: str, macbook_idx: int | None, this_idx: int) -> str:
    n = name.lower()
    if macbook_idx is not None and this_idx == macbook_idx:
        return "  <- MacBook webcam (use --source macbook)"
    if "facetime" in n:
        return "  <- FaceTime device (use --source facetime)"
    if _is_virtual_cam(n):
        return "  <- virtual"
    if "desk view" in n:
        return "  <- Continuity Desk View"
    if "c270" in n or "logitech" in n:
        return '  <- USB webcam (use --source "C270")'
    # Continuity / other phone cams often named "{iPhone} Camera"
    if n.endswith(" camera") and "facetime" not in n:
        return "  <- Continuity / iPhone"
    return ""


def print_camera_list() -> None:
    cams = list_cameras()
    macbook_idx = find_macbook_camera_index()
    prefs = _load_pipeline_camera_prefs()

    if not cams:
        print("No cameras detected.")
        print("On macOS, install ffmpeg: brew install ffmpeg")
    else:
        print("Available cameras (ffmpeg indices; opened by name on macOS):")
        for cam in cams:
            tag = _macbook_tag_for(cam["name"], macbook_idx, int(cam["index"]))
            print(f"  [{cam['index']}] {cam['name']}{tag}")
        print()
        print(f"macbook_match (configs/default.yaml): {prefs}")
        if macbook_idx is not None:
            print(
                f"--source macbook → [{macbook_idx}] {camera_label(macbook_idx)}"
            )
        print()
        print(
            "Note: OpenCV index ≠ ffmpeg index when Continuity/OBS are present."
        )
        print('Prefer names: --source "C270"  (not bare --source 2).')

    print()
    print("Examples:")
    print('  python scripts/run_webcam_demo.py --source "C270"')
    print("  python scripts/run_webcam_demo.py --source facetime")
    print("  python scripts/run_webcam_demo.py --source macbook")
    print(
        "  python scripts/run_webcam_demo.py "
        "--source data/sample/smoke.mp4 --no-display"
    )
