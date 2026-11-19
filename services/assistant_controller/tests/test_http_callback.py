"""Result callback retry policy."""

from __future__ import annotations

import httpx
import pytest

from ac.http_callback import HttpCallbackClient
from ac.models import EyeAcuity, ProtocolInfo, ResultsCallback, SessionState


def _results() -> ResultsCallback:
    return ResultsCallback(
        session_id="session-retry",
        patient_id="PAT-1",
        station_id="station-01",
        state=SessionState.COMPLETED,
        completed_at="2026-09-27T00:00:00Z",
        acuity={
            "right": EyeAcuity(
                logmar=0.0,
                decimal=1.0,
                vn_over_10="10/10",
                correct=3,
                total=5,
                row_passed=True,
            )
        },
        protocol=ProtocolInfo(
            passes_per_eye=3,
            distance_m=5,
            letter_uncertain_threshold=0.45,
            letter_accept_threshold=0.75,
        ),
    )


def test_retries_transient_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(_self, url, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", url)
        if calls < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"success": True}, request=request)

    monkeypatch.setattr(httpx.Client, "post", post)
    client = HttpCallbackClient(max_attempts=3, retry_delay_seconds=0)
    assert client.post_results("http://hospital/results", _results())["success"] is True
    assert calls == 3


def test_does_not_retry_bad_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(_self, url, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", post)
    client = HttpCallbackClient(max_attempts=3, retry_delay_seconds=0)
    with pytest.raises(httpx.HTTPStatusError):
        client.post_results("http://hospital/results", _results())
    assert calls == 1


def test_rejects_auth_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(_self, url, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return httpx.Response(
            303,
            headers={"location": "https://coder.example/login"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    client = HttpCallbackClient(max_attempts=3, retry_delay_seconds=0)
    with pytest.raises(httpx.HTTPStatusError):
        client.post_results("http://hospital/results", _results())
    assert calls == 1


def test_does_not_retry_ambiguous_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(_self, url, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", url)
        raise httpx.ReadTimeout("response lost after request", request=request)

    monkeypatch.setattr(httpx.Client, "post", post)
    client = HttpCallbackClient(max_attempts=3, retry_delay_seconds=0)
    with pytest.raises(httpx.ReadTimeout):
        client.post_results("http://hospital/results", _results())
    assert calls == 1
