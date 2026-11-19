"""VectorDB → AiFace gallery sync."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from ac.face_client import AiFaceClient
from ac.display_client import DisplayHub, create_display_app
from ac.config import FaceVectorDbConfig
from ac.face_gallery_loop import TodayFaceSyncLoop
from ac.face_sync import push_one_face_to_device, sync_today_appointments_to_device, sync_vectordb_to_device
from ac.vector_face_client import FaceRecord, MockVectorFaceClient


def test_sync_loads_mock_gallery_onto_device() -> None:
    vector = MockVectorFaceClient()
    face = MagicMock(spec=AiFaceClient)
    face.enabled = True
    face.upsert_gallery_user.return_value = True
    face._user_has_face_photo.return_value = False
    face._api.return_value = {"result": True, "record": []}

    res = sync_vectordb_to_device(vector, face, max_faces=10)

    assert res.attempted == 2
    assert res.loaded == 2
    assert face.upsert_gallery_user.call_count == 2
    first = face.upsert_gallery_user.call_args_list[0].kwargs
    assert first["enroll_id"] == 10001
    assert first["full_name"] == "Demo Patient A"
    assert first["photo_bytes"]


def test_sync_prefers_jpeg_onto_device() -> None:
    import base64

    jpeg = b"\xff\xd8" + b"\x00" * 500 + b"\xff\xd9"
    b64 = base64.b64encode(jpeg).decode("ascii")

    vector = MockVectorFaceClient(
        [
            FaceRecord(
                enroll_id=55,
                full_name="Template User",
                device_template_b64=b64,
                image_b64=b64,
            )
        ]
    )
    face = MagicMock(spec=AiFaceClient)
    face.enabled = True
    face.upsert_gallery_user.return_value = True
    face._user_has_face_photo.return_value = False
    face._api.return_value = {"result": True, "record": []}

    res = sync_vectordb_to_device(vector, face)
    assert res.loaded == 1
    kw = face.upsert_gallery_user.call_args.kwargs
    assert kw["photo_bytes"] is not None
    assert kw["photo_bytes"][:2] == b"\xff\xd8"


def test_face_record_from_api_aliases() -> None:
    rec = FaceRecord.from_api(
        {
            "aiface_enroll_id": 7,
            "name": "Lan",
            "aiface_record": "TEMPL",
            "get_url": "http://media/x.jpg",
        }
    )
    assert rec.enroll_id == 7
    assert rec.full_name == "Lan"
    assert rec.device_template_b64 == "TEMPL"
    assert rec.media_get_url == "http://media/x.jpg"


def test_today_gallery_does_not_reload_same_verified_photo(tmp_path) -> None:
    import base64

    face = AiFaceClient(host="127.0.0.1")
    face._gallery_versions_path = tmp_path / "versions.json"
    face._gallery_versions = {}
    face.upsert_gallery_user = MagicMock(return_value=True)
    face._api = MagicMock(side_effect=lambda *_args, **_kwargs: {
        "result": True,
        "record": [{"id": 7, "name": "Patient A", "face": 1}]
        if face.upsert_gallery_user.call_count else [],
    })
    image = base64.b64encode(b"\xff\xd8" + b"a" * 120).decode()
    hospital = MagicMock()
    hospital.list_today_face_gallery.return_value = {
        "success": True,
        "faces": [{"enroll_id": 7, "full_name": "Patient A", "image_b64": image}],
    }

    first = sync_today_appointments_to_device(hospital, face, None, prune_not_in_today=False)
    second = sync_today_appointments_to_device(hospital, face, None, prune_not_in_today=False)

    assert (first.loaded, second.skipped, face.upsert_gallery_user.call_count) == (1, 1, 1)


def test_today_gallery_restores_saved_face_after_panel_wipe(tmp_path) -> None:
    import base64

    face = AiFaceClient(host="127.0.0.1")
    face._gallery_versions_path = tmp_path / "versions.json"
    face._gallery_versions = {}
    panel = {"has_face": False}

    def upsert(**_kwargs):
        panel["has_face"] = True
        return True

    face.upsert_gallery_user = MagicMock(side_effect=upsert)
    face._api = MagicMock(side_effect=lambda *_args, **_kwargs: {
        "result": True,
        "record": [{"id": 7, "name": "Patient A", "face": 1}]
        if panel["has_face"] else [],
    })
    hospital = MagicMock()
    hospital.list_today_face_gallery.return_value = {
        "success": True,
        "faces": [{
            "enroll_id": 7, "full_name": "Patient A",
            "image_b64": base64.b64encode(b"\xff\xd8" + b"a" * 120).decode(),
        }],
    }

    assert sync_today_appointments_to_device(hospital, face, None).loaded == 1
    panel["has_face"] = False  # 00:05 panel cleanup, not a Frappe deletion
    assert sync_today_appointments_to_device(hospital, face, None).loaded == 1
    assert face.upsert_gallery_user.call_count == 2


def test_changed_photo_reloads_once(tmp_path) -> None:
    import base64

    face = AiFaceClient(host="127.0.0.1")
    face._gallery_versions_path = tmp_path / "versions.json"
    face._gallery_versions = {}
    face.upsert_gallery_user = MagicMock(return_value=True)
    face._api = MagicMock(side_effect=lambda *_args, **_kwargs: {
        "result": True,
        "record": [{"id": 7, "name": "Patient A", "face": 1}]
        if face.upsert_gallery_user.call_count else [],
    })
    first = base64.b64encode(b"\xff\xd8" + b"a" * 120).decode()
    changed = base64.b64encode(b"\xff\xd8" + b"b" * 120).decode()

    assert push_one_face_to_device(face, None, enroll_id=7, full_name="Patient A", image_b64=first)
    assert push_one_face_to_device(face, None, enroll_id=7, full_name="Patient A", image_b64=first)
    assert push_one_face_to_device(face, None, enroll_id=7, full_name="Patient A", image_b64=changed)
    assert face.upsert_gallery_user.call_count == 2


def test_simultaneous_pushes_do_not_reload_same_face_twice(tmp_path) -> None:
    import base64
    import time
    from concurrent.futures import ThreadPoolExecutor

    face = AiFaceClient(host="127.0.0.1")
    face._gallery_versions_path = tmp_path / "versions.json"
    face._gallery_versions = {}

    def slow_upsert(**_kwargs):
        time.sleep(0.03)
        return True

    face.upsert_gallery_user = MagicMock(side_effect=slow_upsert)
    face._api = MagicMock(side_effect=lambda *_args, **_kwargs: {
        "result": True,
        "record": [{"id": 7, "name": "Patient A", "face": 1}]
        if face.upsert_gallery_user.call_count else [],
    })
    image = base64.b64encode(b"\xff\xd8" + b"a" * 120).decode()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _n: push_one_face_to_device(face, None, enroll_id=7, full_name="Patient A", image_b64=image),
            range(2),
        ))

    assert results == [True, True]
    assert face.upsert_gallery_user.call_count == 1


def test_failed_poll_is_retried(monkeypatch) -> None:
    from ac.face_sync import SyncResult

    hospital = MagicMock()
    hospital.list_today_face_gallery.return_value = {"success": True, "count": 1, "faces": [{"enroll_id": 7}]}
    sync = MagicMock(side_effect=[SyncResult(failed=1), SyncResult(loaded=1)])
    monkeypatch.setattr("ac.face_gallery_loop.sync_today_appointments_to_device", sync)
    loop = TodayFaceSyncLoop(
        hospital=hospital, face=MagicMock(), media=None,
        cfg=FaceVectorDbConfig(sync_today_appointments_only=True),
    )

    assert not loop._sync_once()["success"]
    assert loop._sync_once()["success"]
    assert sync.call_count == 2


def test_overnight_wipe_waits_when_booked_face_cannot_be_restored(monkeypatch) -> None:
    import datetime

    class WipeMinute:
        @staticmethod
        def now():
            return datetime.datetime(2026, 10, 8, 0, 5)

    monkeypatch.setattr("ac.face_gallery_loop.datetime", WipeMinute)
    wipe = MagicMock(return_value={"deleted": 1})
    monkeypatch.setattr("ac.face_gallery_loop.wipe_device_gallery", wipe)
    hospital = MagicMock()
    hospital.list_today_face_gallery.return_value = {
        "success": True, "count": 0, "faces": [],
        "diagnostics": {"appointments": 1, "missing_face_avatar": 1},
    }
    loop = TodayFaceSyncLoop(
        hospital=hospital, face=MagicMock(), media=None,
        cfg=FaceVectorDbConfig(sync_today_appointments_only=True),
    )

    loop._maybe_overnight_wipe()
    wipe.assert_not_called()
    assert loop._last_wipe_date is None

    hospital.list_today_face_gallery.return_value = {
        "success": True, "count": 1, "faces": [{"enroll_id": 7}],
        "diagnostics": {"appointments": 1, "missing_face_avatar": 0},
    }
    loop._maybe_overnight_wipe()
    wipe.assert_called_once()
    assert loop._last_wipe_date == "2026-10-08"


def test_today_sync_preserves_booked_panel_face_while_avatar_is_missing() -> None:
    face = AiFaceClient(host="127.0.0.1")
    face._api = MagicMock(return_value={
        "result": True,
        "record": [
            {"id": 7, "name": "Booked, missing avatar", "face": 1},
            {"id": 8, "name": "Old booking", "face": 1},
        ],
    })
    face.delete_user = MagicMock()
    hospital = MagicMock()
    hospital.list_today_face_gallery.return_value = {
        "success": True, "faces": [], "protected_enroll_ids": [7],
    }

    sync_today_appointments_to_device(hospital, face, None)

    face.delete_user.assert_called_once_with(8)


def test_gallery_status_only_reports_panel_confirmed_version() -> None:
    face = MagicMock(spec=AiFaceClient)
    face.enabled = True
    face.gallery_ready.return_value = True
    client = TestClient(create_display_app(DisplayHub(), face=face))

    assert client.get("/api/face/gallery_status/7", params={"version": "v1"}).json()["ready"] is True
    face.gallery_ready.assert_called_with(7, "v1")
    face.gallery_ready.return_value = False
    assert client.get("/api/face/gallery_status/7", params={"version": "v2"}).json()["ready"] is False


def test_gallery_ready_rechecks_panel_not_only_local_cache() -> None:
    face = AiFaceClient(host="127.0.0.1")
    face._gallery_versions = {face._gallery_key(7): "v1"}
    face._api = MagicMock(return_value={"record": []})
    assert face.gallery_ready(7, "v1") is False
    face._api.return_value = {"record": [{"id": 7, "face": 1}]}
    assert face.gallery_ready(7, "v1") is True
    assert face.gallery_ready(7, "old-version") is False
