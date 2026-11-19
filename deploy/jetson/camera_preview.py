#!/usr/bin/env python3
"""Minimal Jetson USB camera preview (MJPEG) for lab checks.

  VIDEO_DEVICE=/dev/video0 PREVIEW_PORT=8090 \\
    ~/ImesPro/.../deploy/jetson/.venv-or-ac-venv/python camera_preview.py

Open: http://<jetson-ip>:8090/
"""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

DEVICE = os.environ.get("VIDEO_DEVICE", "/dev/video0")
PORT = int(os.environ.get("PREVIEW_PORT", "8090"))
WIDTH = int(os.environ.get("PREVIEW_WIDTH", "640"))
HEIGHT = int(os.environ.get("PREVIEW_HEIGHT", "480"))

_lock = threading.Lock()
_jpeg: bytes | None = None
_ok = False
_error = ""


def _capture_loop() -> None:
	global _jpeg, _ok, _error
	cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
	if not cap.isOpened():
		cap = cv2.VideoCapture(DEVICE)
	if not cap.isOpened():
		_error = f"cannot open {DEVICE}"
		return
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
	cap.set(cv2.CAP_PROP_FPS, 15)
	_ok = True
	fail = 0
	while True:
		ret, frame = cap.read()
		if not ret or frame is None:
			fail += 1
			if fail > 30:
				_error = "camera read failed"
				_ok = False
				break
			time.sleep(0.05)
			continue
		fail = 0
		# downscale if huge
		h, w = frame.shape[:2]
		if w > WIDTH:
			frame = cv2.resize(frame, (WIDTH, int(h * WIDTH / w)))
		ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
		if not ok:
			continue
		with _lock:
			_jpeg = buf.tobytes()
		time.sleep(0.03)
	cap.release()


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Camera preview</title>
  <style>
    body { margin:0; background:#111; color:#eee; font-family: system-ui, sans-serif; }
    header { padding:12px 16px; background:#1a1a1a; }
    img { display:block; max-width:100%; margin:16px auto; background:#000; }
    .meta { opacity:.7; font-size:13px; }
  </style>
</head>
<body>
  <header>
    <strong>Camera preview</strong>
    <div class="meta">device DEVICE_PLACEHOLDER · stream /stream.mjpg</div>
  </header>
  <img src="/stream.mjpg" alt="camera"/>
</body>
</html>
""".replace("DEVICE_PLACEHOLDER", DEVICE)


class Handler(BaseHTTPRequestHandler):
	def log_message(self, fmt: str, *args) -> None:  # quieter
		return

	def do_GET(self) -> None:  # noqa: N802
		if self.path in ("/", "/index.html"):
			body = HTML.encode()
			self.send_response(200)
			self.send_header("Content-Type", "text/html; charset=utf-8")
			self.send_header("Content-Length", str(len(body)))
			self.end_headers()
			self.wfile.write(body)
			return
		if self.path.startswith("/health"):
			body = (
				f'{{"ok":{_ok!s},"device":"{DEVICE}","error":"{_error}"}}'
			).encode()
			self.send_response(200 if _ok else 503)
			self.send_header("Content-Type", "application/json")
			self.send_header("Content-Length", str(len(body)))
			self.end_headers()
			self.wfile.write(body)
			return
		if self.path.startswith("/stream"):
			self.send_response(200)
			self.send_header(
				"Content-Type", "multipart/x-mixed-replace; boundary=frame"
			)
			self.send_header("Cache-Control", "no-cache")
			self.end_headers()
			try:
				while True:
					with _lock:
						frame = _jpeg
					if frame:
						self.wfile.write(b"--frame\r\n")
						self.wfile.write(b"Content-Type: image/jpeg\r\n")
						self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
						self.wfile.write(frame)
						self.wfile.write(b"\r\n")
					time.sleep(0.05)
			except (BrokenPipeError, ConnectionResetError):
				return
		self.send_error(404)


def main() -> None:
	t = threading.Thread(target=_capture_loop, daemon=True)
	t.start()
	time.sleep(0.8)
	server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
	print(f"camera preview http://0.0.0.0:{PORT}/ device={DEVICE} ok={_ok} err={_error!r}", flush=True)
	server.serve_forever()


if __name__ == "__main__":
	main()
