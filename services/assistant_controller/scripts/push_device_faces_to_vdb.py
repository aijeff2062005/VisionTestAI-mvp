#!/usr/bin/env python3
"""Push AiFace panel faces (face>0) into VectorDB + media JPEG objects."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ac.config import load_config  # noqa: E402
from ac.face_client import AiFaceClient, build_face_client  # noqa: E402
from ac.face_sync import push_device_face_to_vectordb  # noqa: E402
from ac.media_client import MediaClient  # noqa: E402
from ac.vector_face_client import build_vector_face_client  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=ROOT / "configs" / "default.yaml")
    args = p.parse_args()
    cfg = load_config(args.config)
    fc = cfg.bridges.face
    face = build_face_client(
        fc.mode,
        host=fc.host,
        password=fc.password,
        port=fc.port,
        poll_interval_seconds=fc.poll_interval_seconds,
        accept_recent_seconds=fc.accept_recent_seconds,
        live_events_url=fc.live_events_url,
    )
    vector = build_vector_face_client(cfg.face_vectordb)
    media = MediaClient(
        cfg.media.base_url,
        token=cfg.media.token,
        timeout_seconds=cfg.media.timeout_seconds,
        station_id=cfg.station_id,
        enabled=cfg.media.enabled,
    )
    if not isinstance(face, AiFaceClient) or not face.enabled:
        print("AiFace client not enabled")
        return 1
    if not vector.enabled:
        print("VectorDB client not enabled")
        return 1
    ulist = face._api({"cmd": "getuserlist", "stn": True})
    rows = ulist.get("record") or []
    n = 0
    for row in rows:
        if int(row.get("face") or 0) <= 0:
            continue
        eid = int(row["id"])
        name = str(row.get("name") or f"user-{eid}")
        ok = push_device_face_to_vectordb(
            face,
            vector,
            enroll_id=eid,
            full_name=name,
            media=media,
            session_id=f"backfill-{eid}",
        )
        print(f"enroll_id={eid} name={name!r} pushed={ok}")
        n += 1
    print(f"done pushed_attempted={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
