"""Tenant isolation of the media gateway.

Run from services/media_server:  pip install pytest httpx && python -m pytest -q tests
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="media-tenants-"))
(TMP / "tokens").mkdir()
(TMP / "tokens" / "main").write_text("token-main\n")
(TMP / "tokens" / "qdymd").write_text("token-qdymd\n")
os.environ.update(
    MEDIA_ROOT=str(TMP / "data"),
    MEDIA_TENANTS="main:station-01;qdymd:qdymd-01,qdymd-02",
    MEDIA_TENANT_TOKENS_DIR=str(TMP / "tokens"),
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.tenants import parse_tenants  # noqa: E402

client = TestClient(main.app)  # no context manager: lifespan (MQTT) does not start
MAIN = {"X-Media-Token": "token-main"}
QDYMD = {"X-Media-Token": "token-qdymd"}


def put(key: str, headers: dict[str, str], body: bytes = b"jpeg"):
    return client.put(f"/v1/objects/{key}", content=body, headers={**headers, "Content-Type": "image/jpeg"})


def test_health_lists_tenant_names_only():
    body = client.get("/health").json()
    assert body["tenants"] == ["main", "qdymd"]
    assert "token" not in str(body).replace("token_header", "")


def test_unknown_or_missing_token_is_rejected():
    assert client.get("/v1/objects/station-01/x", headers={"X-Media-Token": "nope"}).status_code == 401
    assert client.get("/v1/objects/station-01/x").status_code == 401


def test_grant_only_for_own_station():
    ok = client.post("/v1/grants", json={"station_id": "qdymd-02", "session_id": "s1"}, headers=QDYMD)
    assert ok.status_code == 200 and ok.json()["object_key"].startswith("qdymd-02/s1/")
    other = client.post("/v1/grants", json={"station_id": "station-01", "session_id": "s1"}, headers=QDYMD)
    assert other.status_code == 403 and "qdymd" in other.json()["detail"]


def test_objects_of_another_tenant_are_unreachable():
    assert put("station-01/face-5/avatar/a.jpg", MAIN).status_code == 200
    assert put("qdymd-01/face-5/avatar/a.jpg", QDYMD).status_code == 200
    assert client.get("/v1/objects/qdymd-01/face-5/avatar/a.jpg", headers=QDYMD).content == b"jpeg"
    foreign = "/v1/objects/station-01/face-5/avatar/a.jpg"
    assert client.get(foreign, headers=QDYMD).status_code == 403
    assert put("station-01/face-5/avatar/b.jpg", QDYMD).status_code == 403
    assert client.post(f"{foreign}/ready", headers=QDYMD).status_code == 403
    assert client.delete(foreign, headers=QDYMD).status_code == 403
    assert client.get(foreign, headers=MAIN).status_code == 200


def test_path_tricks_stay_inside_the_tenant():
    assert client.get("/v1/objects/qdymd-01/%2E%2E/station-01/face-5/avatar/a.jpg", headers=QDYMD).status_code == 400
    assert client.get("/v1/objects//station-01/face-5/avatar/a.jpg", headers=QDYMD).status_code in (403, 404)


def test_session_delete_and_purge_touch_only_own_stations():
    for key, h in (("station-01/face-7/x.jpg", MAIN), ("qdymd-01/face-7/x.jpg", QDYMD), ("qdymd-02/face-7/x.jpg", QDYMD)):
        assert put(key, h).status_code == 200
    r = client.delete("/v1/sessions/face-7", headers=QDYMD).json()
    assert sorted(r["deleted"]) == ["qdymd-01/face-7/x.jpg", "qdymd-02/face-7/x.jpg"]
    assert client.get("/v1/objects/station-01/face-7/x.jpg", headers=MAIN).status_code == 200

    assert put("station-01/face-8/x.jpg", MAIN).status_code == 200
    assert put("qdymd-01/face-8/x.jpg", QDYMD).status_code == 200
    r = client.post(
        "/v1/purge",
        json={"object_keys": ["station-01/face-7/x.jpg", "qdymd-01/face-8/x.jpg"], "session_ids": ["face-8"]},
        headers=QDYMD,
    ).json()
    assert r["denied"] == ["station-01/face-7/x.jpg"]
    assert r["deleted"] == ["qdymd-01/face-8/x.jpg"]
    assert client.get("/v1/objects/station-01/face-7/x.jpg", headers=MAIN).status_code == 200
    assert client.get("/v1/objects/station-01/face-8/x.jpg", headers=MAIN).status_code == 200


def test_single_token_mode_is_unchanged(monkeypatch):
    monkeypatch.setattr(main, "TENANTS", [])
    monkeypatch.setattr(main.settings, "media_token", "legacy")
    legacy = {"X-Media-Token": "legacy"}
    assert put("any-station/s/x.jpg", legacy).status_code == 200
    assert client.get("/v1/objects/station-01/face-7/x.jpg", headers=legacy).status_code == 200
    assert client.get("/v1/objects/station-01/face-7/x.jpg", headers=MAIN).status_code == 401


@pytest.mark.parametrize(
    "spec, files, message",
    [
        ("a:s1;b:s1", {"a": "1", "b": "2"}, "listed under both"),
        ("a:s1;b:s2", {"a": "1", "b": "1"}, "share one token"),
        ("a:s1", {}, "no token file"),
        ("a:s1", {"a": " \n"}, "is empty"),
        ("a", {"a": "1"}, "expected <tenant>"),
        ("a:s1;a:s2", {"a": "1"}, "listed twice"),
    ],
)
def test_bad_config_stops_at_start(spec, files, message):
    d = Path(tempfile.mkdtemp())
    for name, token in files.items():
        (d / name).write_text(token)
    with pytest.raises(ValueError, match=message):
        parse_tenants(spec, str(d))


def test_no_tenants_without_spec():
    assert parse_tenants("", "") == []
    importlib.import_module("app.tenants")
