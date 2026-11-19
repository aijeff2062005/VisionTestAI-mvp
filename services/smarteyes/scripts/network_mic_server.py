#!/usr/bin/env python3
"""Stream a local microphone as float32 mono PCM over HTTP."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sounddevice as sd


class AudioHub:
    def __init__(self, device: int | str, sample_rate: int) -> None:
        info = sd.query_devices(device, "input")
        self.device = device
        self.device_name = str(info["name"])
        self.sample_rate = sample_rate
        self._clients: set[queue.Queue[bytes]] = set()
        self._lock = threading.Lock()
        block = max(256, int(sample_rate * 0.03))

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            payload = indata[:, 0].astype("<f4", copy=False).tobytes()
            with self._lock:
                clients = tuple(self._clients)
            for client in clients:
                try:
                    client.put_nowait(payload)
                except queue.Full:
                    try:
                        client.get_nowait()
                        client.put_nowait(payload)
                    except (queue.Empty, queue.Full):
                        pass

        self.stream = sd.InputStream(
            device=device,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=block,
            callback=callback,
        )

    def add_client(self) -> queue.Queue[bytes]:
        client: queue.Queue[bytes] = queue.Queue(maxsize=12)
        with self._lock:
            self._clients.add(client)
        return client

    def remove_client(self, client: queue.Queue[bytes]) -> None:
        with self._lock:
            self._clients.discard(client)


class AudioHandler(BaseHTTPRequestHandler):
    hub: AudioHub

    def log_message(self, fmt, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps(
                {
                    "status": "ok",
                    "device": self.hub.device,
                    "name": self.hub.device_name,
                    "sample_rate": self.hub.sample_rate,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path != "/audio.raw":
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Audio-Format", "float32le")
        self.send_header("X-Audio-Channels", "1")
        self.send_header("X-Audio-Sample-Rate", str(self.hub.sample_rate))
        self.end_headers()

        client = self.hub.add_client()
        try:
            while True:
                self.wfile.write(client.get(timeout=5))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, queue.Empty):
            pass
        finally:
            self.hub.remove_client(client)


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="MacBook Air Microphone")
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()
    if args.list_devices:
        print(sd.query_devices())
        return 0

    device: int | str = int(args.device) if str(args.device).isdigit() else args.device
    hub = AudioHub(device, args.sample_rate)
    AudioHandler.hub = hub
    server = ThreadingHTTPServer(("0.0.0.0", args.port), AudioHandler)
    server.daemon_threads = True
    hub.stream.start()
    print(
        f"MacBook mic: [{device}] {hub.device_name} @ {hub.sample_rate} Hz",
        flush=True,
    )
    print(f"Jetson mic URL: http://{lan_ip()}:{args.port}/audio.raw", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        hub.stream.stop()
        hub.stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
