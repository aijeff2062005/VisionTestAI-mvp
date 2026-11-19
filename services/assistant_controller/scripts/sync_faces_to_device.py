#!/usr/bin/env python3
"""Pull face gallery from VectorDB API and load onto AiFace panel (on-device verify).

Examples:
  FACE_VECTORDB_ENABLED=1 FACE_VECTORDB_MODE=mock \\
    python scripts/sync_faces_to_device.py

  FACE_VECTORDB_ENABLED=1 FACE_VECTORDB_MODE=http \\
  FACE_VECTORDB_BASE_URL=http://hospital.local:8100 FACE_VECTORDB_API_KEY=secret \\
    python scripts/sync_faces_to_device.py --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ac.config import load_config  # noqa: E402
from ac.face_client import build_face_client  # noqa: E402
from ac.face_sync import sync_vectordb_to_device  # noqa: E402
from ac.media_client import MediaClient  # noqa: E402
from ac.vector_face_client import build_vector_face_client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_faces")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync VectorDB faces → AiFace device")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--force-enable",
        action="store_true",
        help="Treat face_vectordb.enabled=true for this run",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.force_enable:
        cfg.face_vectordb.enabled = True
        if cfg.face_vectordb.mode in ("off", ""):
            cfg.face_vectordb.mode = "mock"

    face = build_face_client(
        cfg.bridges.face.mode,
        host=cfg.bridges.face.host,
        password=cfg.bridges.face.password,
        port=cfg.bridges.face.port,
        poll_interval_seconds=cfg.bridges.face.poll_interval_seconds,
        accept_recent_seconds=cfg.bridges.face.accept_recent_seconds,
        live_events_url=cfg.bridges.face.live_events_url,
    )
    vector = build_vector_face_client(cfg.face_vectordb)
    media = MediaClient(
        cfg.media.base_url,
        token=cfg.media.token,
        timeout_seconds=cfg.media.timeout_seconds,
        enabled=cfg.media.enabled,
    )
    if not cfg.face_vectordb.enabled or not vector.enabled:
        logger.error("face_vectordb disabled — set FACE_VECTORDB_ENABLED=1 or --force-enable")
        return 2
    if not face.enabled:
        logger.error("AiFace bridge disabled — set bridges.face.mode=aiface / FACE_MODE=aiface")
        return 3

    res = sync_vectordb_to_device(
        vector,
        face,
        max_faces=cfg.face_vectordb.max_faces,
        device_face_backupnum=cfg.face_vectordb.device_face_backupnum,
        media=media,
    )
    logger.info("Done: %s", res.as_dict())
    return 0 if res.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
