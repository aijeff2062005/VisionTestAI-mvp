#!/usr/bin/env python3
"""Forward host :18088 through Tailscale userspace SOCKS to Jetson AC.

Coder/VPS runs tailscaled --tun=userspace-networking, so Docker/Frappe cannot
dial 100.x directly. SOCKS5 on 127.0.0.1:1055 can. This proxy is reachable
from the Frappe compose network at http://172.18.0.1:18088.
"""
from __future__ import annotations

import os
import select
import socket
import struct
import threading

SOCKS = (
    os.environ.get("TS_SOCKS_HOST", "127.0.0.1"),
    int(os.environ.get("TS_SOCKS_PORT", "1055")),
)
DEST = (
    os.environ.get("JETSON_HOST", "100.97.186.106"),
    int(os.environ.get("JETSON_PORT", "8088")),
)
LISTEN = (
    os.environ.get("LISTEN_HOST", "0.0.0.0"),
    int(os.environ.get("LISTEN_PORT", "18088")),
)


def socks_connect() -> socket.socket:
    sock = socket.create_connection(SOCKS, timeout=8)
    sock.sendall(b"\x05\x01\x00")
    hello = sock.recv(2)
    if len(hello) < 2 or hello[1] != 0:
        sock.close()
        raise RuntimeError(f"socks greeting {hello!r}")
    host, port = DEST
    req = b"\x05\x01\x00\x01" + socket.inet_aton(host) + struct.pack("!H", port)
    sock.sendall(req)
    resp = sock.recv(10)
    if len(resp) < 2 or resp[1] != 0:
        sock.close()
        raise RuntimeError(f"socks connect status={resp[1:]!r}")
    return sock


def pump(left: socket.socket, right: socket.socket) -> None:
    try:
        while True:
            ready, _, _ = select.select([left, right], [], [], 120)
            if not ready:
                break
            for src in ready:
                data = src.recv(65536)
                if not data:
                    return
                (right if src is left else left).sendall(data)
    except OSError:
        pass
    finally:
        for sock in (left, right):
            try:
                sock.close()
            except OSError:
                pass


def handle(client: socket.socket) -> None:
    try:
        upstream = socks_connect()
    except Exception:
        try:
            client.close()
        except OSError:
            pass
        return
    pump(client, upstream)


def main() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    print(f"jetson proxy {LISTEN[0]}:{LISTEN[1]} -> socks {SOCKS} -> {DEST[0]}:{DEST[1]}", flush=True)
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
