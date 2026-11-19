#!/usr/bin/env python3
"""Wait for one Face ID identify event (demo / smoke).

Usage:
  python scripts/demo_face_wait.py
  FACE_HOST=192.168.1.96 FACE_PASSWORD=12345678 python scripts/demo_face_wait.py --timeout 60
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ac.face_client import AiFaceClient  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Poll AiFace until patient match or timeout")
    p.add_argument("--host", default=os.getenv("FACE_HOST", "192.168.1.96"))
    p.add_argument("--password", default=os.getenv("FACE_PASSWORD", "12345678"))
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()

    client = AiFaceClient(host=args.host, password=args.password)
    print(f"Waiting for face on {args.host} (timeout {args.timeout}s)…")
    print("Look at the panel. Unknown faces will ask you to register on the device.")

    def on_stranger(result):  # noqa: ANN001
        print(f"[stranger] {result.message}")

    result = client.wait_for_identify(timeout_seconds=args.timeout, on_stranger=on_stranger)
    print(f"status={result.status} matched={result.matched}")
    print(f"enroll_id={result.enroll_id} name={result.name!r} patient_id={result.patient_id!r}")
    print(f"message={result.message}")
    return 0 if result.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
