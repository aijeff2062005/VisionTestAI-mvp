"""Patient media gateway — HTTP bytes + MQTT grants/ready (Mac)."""

from __future__ import annotations

import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.mqtt_bus import MediaMqtt
from app.store import DiskStore, safe_key
from app.tenants import Tenant, match_tenant, parse_tenants

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [media] %(message)s")
logger = logging.getLogger("media")

store = DiskStore(Path(settings.media_root))
TENANTS = parse_tenants(settings.media_tenants, settings.media_tenant_tokens_dir)
_grants: dict[str, dict[str, Any]] = {}
mqtt_bus: MediaMqtt | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_token(token: str | None) -> Tenant | None:
    """Caller's tenant; None means single-tenant mode, where the token covers every station."""
    if TENANTS:
        tenant = match_tenant(TENANTS, token)
        if tenant is None:
            raise HTTPException(401, "invalid or missing X-Media-Token")
        return tenant
    expected = settings.media_token
    if not expected:
        return None
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, "invalid or missing X-Media-Token")
    return None


def _require_station(tenant: Tenant | None, station_id: str) -> None:
    if tenant is not None and station_id not in tenant.stations:
        raise HTTPException(403, f"station {station_id!r} does not belong to tenant {tenant.name!r}")


def _require_key(tenant: Tenant | None, object_key: str) -> None:
    """Object keys start with the station id; a tenant reaches only its own stations."""
    if tenant is None:
        return
    try:
        station = safe_key(object_key).split("/", 1)[0]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _require_station(tenant, station)


def _stations_of(tenant: Tenant | None) -> frozenset[str] | None:
    return None if tenant is None else tenant.stations


def _urls(object_key: str) -> tuple[str, str]:
    base = settings.media_public_base.rstrip("/")
    put_url = f"{base}/v1/objects/{object_key}"
    get_url = put_url
    return put_url, get_url


def _make_grant(station_id: str, body: dict[str, Any]) -> dict[str, Any]:
    kind = str(body.get("kind") or "other")
    session_id = str(body.get("session_id") or "nosession")
    filename = str(body.get("filename") or f"{kind}.bin")
    content_type = str(body.get("content_type") or "application/octet-stream")
    upload_id = uuid.uuid4().hex[:12]
    object_key = f"{station_id}/{session_id}/{kind}/{upload_id}_{filename}"
    put_url, get_url = _urls(object_key)
    expires_at = time.time() + settings.grant_ttl_seconds
    grant = {
        "schema_version": "0.1.0",
        "upload_id": upload_id,
        "station_id": station_id,
        "session_id": session_id,
        "kind": kind,
        "object_key": object_key,
        "put_url": put_url,
        "get_url": get_url,
        "content_type": content_type,
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "token_header": "X-Media-Token",
    }
    _grants[object_key] = {"expires_at": expires_at, "meta": grant}
    return grant


def _on_mqtt_request(station_id: str, payload: dict[str, Any]) -> None:
    grant = _make_grant(station_id, payload)
    assert mqtt_bus is not None
    mqtt_bus.publish_grant(station_id, grant)
    logger.info("Granted upload %s → %s", grant["upload_id"], grant["object_key"])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global mqtt_bus
    mqtt_bus = MediaMqtt(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password,
        stations=sorted(set().union(*(t.stations for t in TENANTS))) if TENANTS else settings.station_list(),
        on_request=_on_mqtt_request,
    )
    mqtt_bus.start()
    yield
    mqtt_bus.stop()


app = FastAPI(title="VisionTestAI Media Gateway", version="0.1.0", lifespan=lifespan)


class GrantBody(BaseModel):
    station_id: str = "station-01"
    session_id: str
    kind: str = Field(default="other", description="face_jpeg | stt_wav | avatar | other")
    content_type: str = "application/octet-stream"
    filename: str | None = None


class PurgeBody(BaseModel):
    object_keys: list[str] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "ts": _now(),
        "public_base": settings.media_public_base,
        "mqtt": f"{settings.mqtt_host}:{settings.mqtt_port}",
        "tenants": [t.name for t in TENANTS],
    }


@app.post("/v1/grants")
def create_grant(
    body: GrantBody,
    x_media_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """HTTP alternative to MQTT object/request (same grant shape)."""
    _require_station(_check_token(x_media_token), body.station_id)
    return _make_grant(body.station_id, body.model_dump())


@app.put("/v1/objects/{object_key:path}")
async def put_object(
    object_key: str,
    request: Request,
    x_media_token: str | None = Header(default=None),
    content_type: str | None = Header(default=None, alias="Content-Type"),
) -> dict[str, Any]:
    _require_key(_check_token(x_media_token), object_key)
    grant = _grants.get(object_key)
    if grant and grant["expires_at"] < time.time():
        _grants.pop(object_key, None)
        raise HTTPException(403, "grant expired")
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty body")
    ct = content_type or (grant["meta"]["content_type"] if grant else "application/octet-stream")
    info = store.put(object_key, data, ct)
    put_url, get_url = _urls(object_key)
    meta = grant["meta"] if grant else {}
    ready = {
        "schema_version": "0.1.0",
        "ts": _now(),
        "station_id": meta.get("station_id") or object_key.split("/", 1)[0],
        "session_id": meta.get("session_id"),
        "kind": meta.get("kind") or "other",
        "object_key": info["object_key"],
        "get_url": get_url,
        "content_type": info["content_type"],
        "size": info["size"],
        "sha256": info["sha256"],
    }
    station = ready["station_id"]
    if mqtt_bus is not None:
        mqtt_bus.publish_ready(str(station), ready)
    _grants.pop(object_key, None)
    logger.info("Stored %s (%s bytes)", info["object_key"], info["size"])
    return ready


@app.get("/v1/objects/{object_key:path}")
def get_object(
    object_key: str,
    x_media_token: str | None = Header(default=None),
) -> Response:
    _require_key(_check_token(x_media_token), object_key)
    try:
        data, content_type = store.get(object_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "not found") from exc
    return Response(content=data, media_type=content_type)


@app.post("/v1/objects/{object_key:path}/ready")
def announce_ready(
    object_key: str,
    x_media_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Re-publish MQTT ready for an existing object (hospital catch-up)."""
    _require_key(_check_token(x_media_token), object_key)
    if not store.exists(object_key):
        raise HTTPException(404, "not found")
    data, content_type = store.get(object_key)
    import hashlib

    put_url, get_url = _urls(object_key)
    station = object_key.split("/", 1)[0]
    ready = {
        "schema_version": "0.1.0",
        "ts": _now(),
        "station_id": station,
        "object_key": object_key,
        "get_url": get_url,
        "content_type": content_type,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "kind": "other",
    }
    if mqtt_bus is not None:
        mqtt_bus.publish_ready(station, ready)
    return ready


@app.delete("/v1/objects/{object_key:path}")
def delete_object(
    object_key: str,
    x_media_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_key(_check_token(x_media_token), object_key)
    if not store.delete(object_key):
        raise HTTPException(404, "not found")
    logger.info("Deleted %s", object_key)
    return {"ok": True, "deleted": [object_key]}


@app.delete("/v1/sessions/{session_id:path}")
def delete_session(
    session_id: str,
    x_media_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Remove all objects stored under this upload session (e.g. patient-{name}) of the caller's stations."""
    tenant = _check_token(x_media_token)
    try:
        deleted = store.delete_session(session_id, stations=_stations_of(tenant))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    logger.info("Purged session %s (%s objects)", session_id, len(deleted))
    return {"ok": True, "session_id": session_id, "deleted": deleted, "count": len(deleted)}


@app.post("/v1/purge")
def purge_objects(
    body: PurgeBody,
    x_media_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Batch-delete object keys and/or whole sessions (patient wipe), within the caller's stations."""
    tenant = _check_token(x_media_token)
    deleted: list[str] = []
    missing: list[str] = []
    denied: list[str] = []
    for key in body.object_keys:
        key = (key or "").strip()
        if not key:
            continue
        try:
            _require_key(tenant, key)
        except HTTPException:
            denied.append(key)
            continue
        if store.delete(key):
            deleted.append(key)
        else:
            missing.append(key)
    for session_id in body.session_ids:
        session_id = (session_id or "").strip()
        if not session_id:
            continue
        try:
            deleted.extend(store.delete_session(session_id, stations=_stations_of(tenant)))
        except ValueError:
            missing.append(session_id)
    if denied:
        logger.warning("Purge refused %s keys outside tenant %s", len(denied), tenant.name if tenant else "-")
    logger.info("Purge deleted=%s missing=%s", len(deleted), len(missing))
    return {"ok": True, "deleted": deleted, "missing": missing, "denied": denied, "count": len(deleted)}
