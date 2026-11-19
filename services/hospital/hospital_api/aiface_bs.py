"""AiFace BS WebSocket listener on :7788 + live event HTTP API on :7790.

Runs on the **clinic station (Jetson)** — not the Mac hospital host.
Devices open ``GET /pub/chat`` WebSocket to the configured server and push
``sendlog`` / ``reg`` JSON. This service:

1. Completes the WebSocket handshake and ACKs commands
2. Stores recent face events (for AC polling) at ``http://0.0.0.0:7790/events``

See docs/LAB_TOPOLOGY.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import socket
import socketserver
import struct
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [aiface-bs] %(message)s",
)
logger = logging.getLogger("aiface-bs")

HOST = "0.0.0.0"
WS_PORT = 7788
HTTP_PORT = 7790
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_events_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=200)


def _push_event(ev: dict[str, Any]) -> None:
    with _events_lock:
        _events.appendleft(ev)


def _list_events(since: float | None = None) -> list[dict[str, Any]]:
    with _events_lock:
        items = list(_events)
    if since is None:
        return items
    return [e for e in items if float(e.get("received_at") or 0) > since]


def _ws_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key.strip() + WS_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _read_http_headers(sock: socket.socket) -> tuple[str, dict[str, str], bytes]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("closed during handshake")
        data += chunk
        if len(data) > 65536:
            raise ConnectionError("headers too large")
    head, rest = data.split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1", errors="ignore").split("\r\n")
    request = lines[0] if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return request, headers, rest


def _ws_send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    sock.sendall(bytes(header) + payload)


def _ws_recv_text(sock: socket.socket) -> str | None:
    hdr = _recv_exact(sock, 2)
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    if opcode == 0x8:
        return None
    if opcode == 0x9:
        frame = bytearray([0x8A, len(payload)])
        sock.sendall(bytes(frame) + payload)
        return ""
    if opcode in (0x1, 0x2):
        return payload.decode("utf-8", errors="ignore")
    return ""


def _ack_for(msg: dict) -> dict:
    cmd = str(msg.get("cmd") or msg.get("ret") or "reg")
    out = {
        "ret": cmd,
        "result": True,
        "cloudtime": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if "sn" in msg:
        out["sn"] = msg["sn"]
    return out


def _ingest_message(msg: dict[str, Any], peer: str) -> None:
    cmd = str(msg.get("cmd") or "").lower()
    if cmd != "sendlog":
        return
    records = msg.get("record") or []
    if not isinstance(records, list):
        return
    for rec in records:
        if not isinstance(rec, dict):
            continue
        enroll_raw = rec.get("enrollid")
        try:
            enroll_id = int(enroll_raw)
        except (TypeError, ValueError):
            continue
        image = rec.get("image")
        image_b64 = str(image) if isinstance(image, str) and len(image) > 50 else None
        ev = {
            "received_at": time.time(),
            "peer": peer,
            "enroll_id": enroll_id,
            "name": (str(rec.get("name") or "").strip() or None),
            "event_time": str(rec.get("time") or "") or None,
            "mode": rec.get("mode"),
            "has_image": bool(image_b64),
            # Keep image for enroll; clients may omit if large.
            "image_b64": image_b64,
        }
        _push_event(ev)
        logger.info(
            "live face enroll_id=%s time=%s has_image=%s from %s",
            enroll_id,
            ev["event_time"],
            ev["has_image"],
            peer,
        )


class BsHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        peer = self.client_address
        sock: socket.socket = self.request
        sock.settimeout(180.0)
        logger.info("connect from %s:%s", peer[0], peer[1])
        try:
            request, headers, leftover = _read_http_headers(sock)
            key = headers.get("sec-websocket-key")
            if "websocket" not in headers.get("upgrade", "").lower():
                logger.warning("non-websocket request from %s: %s", peer[0], request)
                return
            if not key:
                logger.warning("missing Sec-WebSocket-Key from %s", peer[0])
                return
            accept = _ws_accept_key(key)
            resp = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            sock.sendall(resp.encode("ascii"))
            logger.info(
                "websocket upgraded for %s path=%s leftover=%d",
                peer[0],
                request,
                len(leftover),
            )

            while True:
                try:
                    text = _ws_recv_text(sock)
                except socket.timeout:
                    continue
                if text is None:
                    break
                if not text:
                    continue
                logger.info("msg from %s: %s", peer[0], text[:240])
                try:
                    msg = json.loads(text)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(msg, dict):
                    continue
                _ingest_message(msg, peer[0])
                ack = _ack_for(msg)
                _ws_send_text(sock, json.dumps(ack, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("handler error %s: %s", peer, exc)
        finally:
            logger.info("disconnect %s:%s", peer[0], peer[1])


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class EventsHttpHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        logger.debug("http " + fmt, *args)

    def _json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        qs = ""
        if "?" in self.path:
            qs = self.path.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)

        if path in ("/health", "/"):
            self._json(200, {"ok": True, "events": len(_events)})
            return
        if path == "/events":
            since = None
            if "since" in params:
                try:
                    since = float(params["since"])
                except ValueError:
                    since = None
            include_image = params.get("image", "0") in ("1", "true", "yes")
            events = _list_events(since)
            out = []
            for e in events:
                item = {k: v for k, v in e.items() if k != "image_b64"}
                if include_image and e.get("image_b64"):
                    item["image_b64"] = e["image_b64"]
                out.append(item)
            self._json(200, {"events": out, "server_time": time.time()})
            return
        self._json(404, {"error": "not found"})


def main() -> None:
    ws_server = ThreadedTCPServer((HOST, WS_PORT), BsHandler)
    http_server = ThreadingHTTPServer((HOST, HTTP_PORT), EventsHttpHandler)

    def _ws() -> None:
        logger.info("listening WebSocket on %s:%s (/pub/chat)", HOST, WS_PORT)
        ws_server.serve_forever()

    def _http() -> None:
        logger.info("listening HTTP events on %s:%s (/events)", HOST, HTTP_PORT)
        http_server.serve_forever()

    threading.Thread(target=_ws, name="aiface-ws", daemon=True).start()
    threading.Thread(target=_http, name="aiface-http", daemon=True).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("shutting down")
        ws_server.shutdown()
        http_server.shutdown()


if __name__ == "__main__":
    main()
