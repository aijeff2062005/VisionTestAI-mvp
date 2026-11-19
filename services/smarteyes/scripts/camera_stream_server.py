#!/usr/bin/env python3
"""
Serve a local V4L2/USB camera as an MJPEG stream over HTTP.

Runs on the machine physically holding the camera (e.g. the Jetson with the
C270) so another machine can consume it with
``--source http://<host>:8090/stream.mjpg``.

Usage:
    python scripts/camera_stream_server.py --device /dev/video0 \
        --width 1280 --height 720 --fps 30 --port 8090
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

BOUNDARY = "frameboundary"


class FrameGrabber:
    """Continuously reads the camera so HTTP clients always get a fresh frame."""

    def __init__(self, device: str, width: int, height: int, fps: int) -> None:
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._cap = self._open()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open(self) -> cv2.VideoCapture:
        src: str | int = self.device
        if str(self.device).isdigit():
            src = int(self.device)
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.device!r}")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        f = cap.get(cv2.CAP_PROP_FPS)
        print(f"Camera {self.device} opened at {w}x{h} @ {f:.0f} fps", flush=True)
        return cap

    def _loop(self) -> None:
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            with self._lock:
                self._frame = frame

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._cap.release()


class StreamHandler(BaseHTTPRequestHandler):
    grabber: FrameGrabber = None  # injected
    quality: int = 80

    def log_message(self, fmt, *args):  # quieter console
        pass

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("", "/index.html"):
            body = (
                b"<html><body style='margin:0;background:#111'>"
                b"<img src='/stream.mjpg' style='width:100%'>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self.path.startswith("/stream"):
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
        )
        self.end_headers()

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
        try:
            while True:
                frame = self.grabber.read()
                if frame is None:
                    time.sleep(0.02)
                    continue
                ok, buf = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue
                data = buf.tobytes()
                self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                time.sleep(1.0 / max(1, self.grabber.fps))
        except (BrokenPipeError, ConnectionResetError):
            pass


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--quality", type=int, default=80)
    args = ap.parse_args()

    grabber = FrameGrabber(args.device, args.width, args.height, args.fps)
    StreamHandler.grabber = grabber
    StreamHandler.quality = args.quality

    server = ThreadingHTTPServer(("0.0.0.0", args.port), StreamHandler)
    server.daemon_threads = True
    ip = _lan_ip()
    print(f"MJPEG stream:  http://{ip}:{args.port}/stream.mjpg", flush=True)
    print(f"Browser view:  http://{ip}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        grabber.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
