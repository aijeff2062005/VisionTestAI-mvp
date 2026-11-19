"""QR decode microservice for CCCD Face ID JPEGs (VPS Docker)."""

from __future__ import annotations

import io
import logging
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [qr_decode] %(message)s")
logger = logging.getLogger("qr_decode")

app = FastAPI(title="VisionTestAI QR Decode", version="0.1.0")


class DecodeResponse(BaseModel):
    success: bool
    raw: str | None = None
    parsed: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


def parse_cccd_payload(raw: str) -> dict[str, Any]:
    """Parse Vietnam CCCD QR pipe-delimited payload.

    Common forms:
      id|old_id|full_name|dob|sex|place_of_residence|issue_date
      id|old_id|full_name|dob|sex|nationality|place_of_origin|place_of_residence|issue_date
    """
    text = (raw or "").strip()
    parts = [p.strip() for p in text.split("|")]
    out: dict[str, Any] = {"raw": text, "field_count": len(parts)}
    if len(parts) < 3:
        out["nationalId"] = parts[0] if parts else ""
        return out

    out["nationalId"] = parts[0]
    out["oldId"] = parts[1] if len(parts) > 1 else ""
    out["fullName"] = parts[2] if len(parts) > 2 else ""

    if len(parts) >= 7 and len(parts) < 9:
        out["birthDate"] = parts[3]
        out["sex"] = parts[4]
        out["address"] = parts[5]
        out["issueDate"] = parts[6]
    elif len(parts) >= 9:
        out["birthDate"] = parts[3]
        out["sex"] = parts[4]
        out["nationality"] = parts[5]
        out["placeOfOrigin"] = parts[6]
        out["address"] = parts[7]
        out["issueDate"] = parts[8]
    else:
        if len(parts) > 3:
            out["birthDate"] = parts[3]
        if len(parts) > 4:
            out["sex"] = parts[4]

    sex = str(out.get("sex") or "").strip().lower()
    if sex in ("nam", "male", "m", "1"):
        out["sex"] = "Male"
    elif sex in ("nữ", "nu", "female", "f", "2"):
        out["sex"] = "Female"

    return out


def _decode_image_bytes(data: bytes) -> str | None:
    if not data:
        return None
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode as zbar_decode
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"qr deps missing: {exc}") from exc

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    results = zbar_decode(img)
    if not results:
        # Try a few scales for small Face ID crops
        w, h = img.size
        for scale in (1.5, 2.0, 3.0):
            scaled = img.resize((int(w * scale), int(h * scale)))
            results = zbar_decode(scaled)
            if results:
                break
    if not results:
        return None
    raw = results[0].data
    if isinstance(raw, bytes):
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
    return str(raw)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "qr_decode"}


@app.post("/v1/decode", response_model=DecodeResponse)
async def decode_upload(file: UploadFile = File(...)) -> DecodeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        raw = _decode_image_bytes(data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("decode failed")
        return DecodeResponse(success=False, error=str(exc))
    if not raw:
        return DecodeResponse(success=False, error="no_qr_found")
    parsed = parse_cccd_payload(raw)
    return DecodeResponse(success=True, raw=raw, parsed=parsed)


class DecodeUrlBody(BaseModel):
    url: str
    media_token: str | None = None


@app.post("/v1/decode_url", response_model=DecodeResponse)
async def decode_url(body: DecodeUrlBody) -> DecodeResponse:
    import httpx

    headers = {}
    if body.media_token:
        headers["X-Media-Token"] = body.media_token
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(body.url, headers=headers)
            r.raise_for_status()
            data = r.content
    except Exception as exc:  # noqa: BLE001
        return DecodeResponse(success=False, error=f"fetch_failed: {exc}")
    try:
        raw = _decode_image_bytes(data)
    except Exception as exc:  # noqa: BLE001
        return DecodeResponse(success=False, error=str(exc))
    if not raw:
        return DecodeResponse(success=False, error="no_qr_found")
    return DecodeResponse(success=True, raw=raw, parsed=parse_cccd_payload(raw))
