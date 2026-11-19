"""AiFace log polling — fresh scan only, stranger handling."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx

from ac.face_client import STRANGER_ENROLL_ID, AiFaceClient, FaceMatchResult


def _rec(enroll_id: int, *, name: str = "", time: str = "2026-07-27 16:00:00") -> dict:
    return {
        "enrollid": enroll_id,
        "name": name,
        "time": time,
        "mode": 1,
        "photourl": "",
    }


def test_wait_ignores_baseline_known_match() -> None:
    """Old Vu Pham log on device must not greet when nobody scans."""
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05, live_events_url="")
    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]

    with (
        patch.object(client, "sync_device_time", return_value=True),
        patch.object(client, "_merge_records", side_effect=[baseline, baseline, baseline]),
    ):
        result = client.wait_for_identify(timeout_seconds=0.25)

    assert result.matched is False
    assert result.status == "timeout"


def test_panel_api_reuses_http_client() -> None:
    calls = []

    def reply(request):  # noqa: ANN001
        calls.append(request)
        return httpx.Response(200, json={"result": True, "record": []})

    client = AiFaceClient(host="127.0.0.1")
    client._api_http = httpx.Client(transport=httpx.MockTransport(reply))
    try:
        assert client.get_logs() == client.get_logs() == []
        assert len(calls) == 2
        assert client._api_client() is client._api_http
    finally:
        client.close()


def test_live_poll_cursor_advances_without_changing_match_rule() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05)
    seen_since = []

    def live(*, since, include_image):  # noqa: ANN001
        seen_since.append(since)
        return [{"received_at": seen_since[0] + 0.02, "enroll_id": STRANGER_ENROLL_ID,
                 "event_time": "2026-10-07 12:00:00"}]

    with patch.object(client, "_merge_records", return_value=[]), patch.object(client, "fetch_live_events", side_effect=live):
        result = client.wait_for_identify(timeout_seconds=0.35, ignore_stranger=True, sync_clock=False)
    assert not result.matched
    assert len(seen_since) >= 2 and seen_since[-1] > seen_since[0]


def test_healthy_live_bridge_uses_slow_log_safety_poll() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05)
    polls = []

    def logs():
        polls.append(time.monotonic())
        return []

    def live(*, since, include_image):  # noqa: ANN001
        client._live_healthy = True
        return []

    with patch.object(client, "_merge_records", side_effect=logs), patch.object(client, "fetch_live_events", side_effect=live):
        result = client.wait_for_identify(timeout_seconds=0.4, sync_clock=False)
    assert not result.matched
    assert len(polls) <= 2  # baseline and at most one safety poll


def test_wait_replays_only_scan_after_results_checkpoint() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05, live_events_url="")
    checkpoint = time.time()
    old = _rec(1, name="Old", time=(datetime.now() - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S"))
    new = _rec(2, name="New", time=(datetime.now() + timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S"))
    with patch.object(client, "_merge_records", return_value=[old]):
        result = client.wait_for_identify(
            timeout_seconds=0.2, accept_existing_recent=True,
            sync_clock=False, min_event_epoch=checkpoint,
        )
    assert not result.matched
    with patch.object(client, "_merge_records", return_value=[new, old]):
        result = client.wait_for_identify(
            timeout_seconds=0.2, accept_existing_recent=True,
            sync_clock=False, min_event_epoch=checkpoint,
        )
    assert result.matched and result.enroll_id == 2


def test_wait_detects_new_stranger() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05, live_events_url="")
    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]
    stranger = _rec(STRANGER_ENROLL_ID, time="2026-07-27 16:01:00")
    seen: list[FaceMatchResult] = []

    def on_stranger(r: FaceMatchResult) -> None:
        seen.append(r)

    with (
        patch.object(client, "sync_device_time", return_value=True),
        patch.object(
            client,
            "_merge_records",
            side_effect=[baseline, baseline + [stranger], baseline + [stranger]],
        ),
    ):
        result = client.wait_for_identify(timeout_seconds=0.35, on_stranger=on_stranger)

    assert len(seen) == 1
    assert seen[0].status == "stranger"
    assert result.matched is False
    assert result.status == "stranger"


def test_wait_prefers_fresh_known_over_old_baseline() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05, live_events_url="")
    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]
    fresh = _rec(1, name="Vu Pham", time="2026-07-27 16:02:00")

    with (
        patch.object(client, "sync_device_time", return_value=True),
        patch.object(
            client,
            "_merge_records",
            side_effect=[baseline, baseline + [fresh]],
        ),
    ):
        result = client.wait_for_identify(timeout_seconds=0.35)

    assert result.matched is True
    assert result.name == "Vu Pham"
    assert result.status == "matched"


def test_wait_uses_live_bs_stranger() -> None:
    client = AiFaceClient(
        host="127.0.0.1",
        relax_reverify=False,
        poll_interval_seconds=0.05,
        live_events_url="http://127.0.0.1:7790/events",
    )
    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]
    live = [
        {
            "received_at": time.time(),
            "enroll_id": STRANGER_ENROLL_ID,
            "event_time": "2026-07-27 17:50:00",
            "image_b64": "aaa",
        }
    ]
    seen: list[FaceMatchResult] = []

    with (
        patch.object(client, "sync_device_time", return_value=True),
        patch.object(client, "_merge_records", return_value=baseline),
        patch.object(client, "fetch_live_events", return_value=live),
    ):
        result = client.wait_for_identify(timeout_seconds=0.35, on_stranger=seen.append)

    assert seen and seen[0].status == "stranger"
    assert seen[0].image_b64 == "aaa"
    assert result.status == "stranger"


def test_enroll_user_starts_adduser_and_waits_for_device_match() -> None:
    client = AiFaceClient(
        host="127.0.0.1",
        relax_reverify=False,
        poll_interval_seconds=0.05,
        live_events_url="",
    )
    calls: list[dict] = []
    progress: list[str] = []

    def fake_api(payload, *, timeout=None):  # noqa: ANN001
        calls.append(dict(payload))
        cmd = payload.get("cmd")
        if cmd == "deleteuser":
            return {"result": True}
        if cmd == "setuserinfo":
            return {"result": True, "backupnum": payload.get("backupnum"), "enrollid": payload.get("enrollid")}
        if cmd == "adduser":
            return {"result": True, "enrollid": payload.get("enrollid")}
        if cmd == "getuserinfo":
            return {"result": True, "enrollid": payload.get("enrollid"), "name": "Nguyen Van A", "record": ""}
        if cmd == "settime":
            return {"result": True}
        if cmd == "getdevinfo":
            return {"result": True, "reverifytime": 5}
        return {"result": False}

    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]
    matched = _rec(4242, name="Nguyen Van A", time="2026-07-27 16:05:00")

    with (
        patch.object(client, "_api", side_effect=fake_api),
        patch.object(client, "_merge_records", side_effect=[baseline, baseline + [matched]]),
        patch("ac.face_client.time.sleep", return_value=None),
    ):
        out = client.enroll_user(
            "Nguyen Van A",
            photo_bytes=b"\xff\xd8\xff" + b"x" * 200,
            enroll_id=4242,
            verify_timeout_seconds=5.0,
            on_progress=progress.append,
        )

    assert out["success"] is True
    assert out["enroll_id"] == 4242
    assert any(c.get("cmd") == "adduser" for c in calls)
    assert any(c.get("cmd") == "adduser" and c.get("backupnum") == 50 for c in calls)
    assert progress  # UI countdown messages
    assert out["match"].enroll_id == 4242


def test_wait_ignores_other_users_when_expect_enroll_id() -> None:
    client = AiFaceClient(host="127.0.0.1", relax_reverify=False, poll_interval_seconds=0.05, live_events_url="")
    baseline = [_rec(1, name="Vu Pham", time="2026-07-27 15:00:00")]
    other = _rec(2, name="Other", time="2026-07-27 16:01:00")
    target = _rec(4242, name="New Patient", time="2026-07-27 16:02:00")

    with (
        patch.object(client, "sync_device_time", return_value=True),
        patch.object(
            client,
            "_merge_records",
            side_effect=[baseline, baseline + [other], baseline + [other, target]],
        ),
    ):
        result = client.wait_for_identify(timeout_seconds=0.5, expect_enroll_id=4242)

    assert result.matched is True
    assert result.enroll_id == 4242
    assert result.name == "New Patient"
