"""Self-hosted face gallery API (placeholder VectorDB) for VisionTestAI MVP."""

from __future__ import annotations

import base64
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

DATA_DIR = Path(os.getenv("FACE_VDB_DATA", "./data")).resolve()
DB_PATH = DATA_DIR / "faces.db"
IMG_DIR = DATA_DIR / "images"
API_KEY = os.getenv("FACE_VDB_API_KEY", "dev-face-vdb-key")
SEED_DEMO = os.getenv("FACE_VDB_SEED_DEMO", "0") not in ("0", "false", "no")

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="VisionTestAI Face VectorDB", version="0.1.0")

# Minimal valid JPEG (1x1) for demo seed when no photo supplied
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c213232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232ffc000110800010001030111000211031101ffc40014000100000000000000000000000000000000ffc40014100100000000000000000000000000000000ffda000c03010002110311003f00bf80ffd9"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_key(x_api_key: str | None) -> None:
    if not API_KEY:
        return
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(401, "invalid or missing X-Api-Key")


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS faces (
              enroll_id INTEGER PRIMARY KEY,
              full_name TEXT NOT NULL,
              patient_id TEXT,
              device_template_b64 TEXT,
              image_path TEXT,
              media_get_url TEXT,
              updated_at TEXT NOT NULL
            )
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(faces)").fetchall()}
        if "media_get_url" not in cols:
            conn.execute("ALTER TABLE faces ADD COLUMN media_get_url TEXT")
    if SEED_DEMO:
        with _db() as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM faces").fetchone()["c"]
            if n == 0:
                for eid, name, pid in (
                    (10001, "Demo Patient A", "P-10001"),
                    (10002, "Demo Patient B", "P-10002"),
                ):
                    img = IMG_DIR / f"{eid}.jpg"
                    img.write_bytes(_TINY_JPEG)
                    conn.execute(
                        "INSERT INTO faces (enroll_id, full_name, patient_id, device_template_b64, image_path, updated_at) VALUES (?,?,?,?,?,?)",
                        (eid, name, pid, None, str(img), _now()),
                    )


_init_db()


def _row_to_face(row: sqlite3.Row, *, include_image_b64: bool = False) -> dict[str, Any]:
    enroll_id = int(row["enroll_id"])
    out: dict[str, Any] = {
        "enroll_id": enroll_id,
        "full_name": row["full_name"],
        "name": row["full_name"],
        "patient_id": row["patient_id"],
        "device_template_b64": row["device_template_b64"],
        "aiface_enroll_id": enroll_id,
        "updated_at": row["updated_at"],
        "image_url": f"/v1/faces/{enroll_id}/image",
        "media_get_url": row["media_get_url"] if "media_get_url" in row.keys() else None,
    }
    if include_image_b64 and row["image_path"]:
        p = Path(row["image_path"])
        if p.is_file():
            out["image_b64"] = base64.b64encode(p.read_bytes()).decode("ascii")
    return out


class FaceUpsert(BaseModel):
    enroll_id: int
    full_name: str = Field(min_length=1)
    patient_id: str | None = None
    device_template_b64: str | None = None
    image_b64: str | None = None
    media_get_url: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    with _db() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM faces").fetchone()["c"]
    return {"ok": True, "ts": _now(), "faces": count}


@app.get("/v1/faces")
def list_faces(
    limit: int = 500,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_key(x_api_key)
    limit = max(1, min(limit, 2000))
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM faces ORDER BY enroll_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"faces": [_row_to_face(r) for r in rows], "next_cursor": None}


@app.get("/v1/faces/{enroll_id}")
def get_face(
    enroll_id: int,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_key(x_api_key)
    with _db() as conn:
        row = conn.execute("SELECT * FROM faces WHERE enroll_id=?", (enroll_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    return {"face": _row_to_face(row, include_image_b64=True)}


@app.get("/v1/faces/{enroll_id}/image")
def get_image(
    enroll_id: int,
    x_api_key: str | None = Header(default=None),
) -> Response:
    _check_key(x_api_key)
    with _db() as conn:
        row = conn.execute("SELECT image_path FROM faces WHERE enroll_id=?", (enroll_id,)).fetchone()
    if not row or not row["image_path"]:
        raise HTTPException(404, "no image")
    path = Path(row["image_path"])
    if not path.is_file():
        raise HTTPException(404, "image missing on disk")
    return Response(content=path.read_bytes(), media_type="image/jpeg")


@app.post("/v1/faces")
def upsert_face(
    body: FaceUpsert,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_key(x_api_key)
    img_path: str | None = None
    if body.image_b64:
        try:
            raw = base64.b64decode(body.image_b64)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"bad image_b64: {exc}") from exc
        dest = IMG_DIR / f"{int(body.enroll_id)}.jpg"
        dest.write_bytes(raw)
        img_path = str(dest)
    with _db() as conn:
        existing = conn.execute(
            "SELECT image_path FROM faces WHERE enroll_id=?",
            (int(body.enroll_id),),
        ).fetchone()
        if existing and not img_path:
            img_path = existing["image_path"]
        conn.execute(
            """
            INSERT INTO faces (enroll_id, full_name, patient_id, device_template_b64, image_path, media_get_url, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(enroll_id) DO UPDATE SET
              full_name=excluded.full_name,
              patient_id=excluded.patient_id,
              device_template_b64=COALESCE(excluded.device_template_b64, faces.device_template_b64),
              image_path=COALESCE(excluded.image_path, faces.image_path),
              media_get_url=COALESCE(excluded.media_get_url, faces.media_get_url),
              updated_at=excluded.updated_at
            """,
            (
                int(body.enroll_id),
                body.full_name.strip(),
                body.patient_id,
                body.device_template_b64,
                img_path,
                body.media_get_url,
                _now(),
            ),
        )
        row = conn.execute("SELECT * FROM faces WHERE enroll_id=?", (int(body.enroll_id),)).fetchone()
    return {"ok": True, "face": _row_to_face(row)}


@app.delete("/v1/faces/{enroll_id}")
def delete_face(
    enroll_id: int,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_key(x_api_key)
    with _db() as conn:
        row = conn.execute("SELECT image_path FROM faces WHERE enroll_id=?", (enroll_id,)).fetchone()
        conn.execute("DELETE FROM faces WHERE enroll_id=?", (enroll_id,))
    if row and row["image_path"]:
        Path(row["image_path"]).unlink(missing_ok=True)
    return {"ok": True, "enroll_id": enroll_id}
