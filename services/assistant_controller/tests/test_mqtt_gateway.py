"""MQTT startup/reconnect behavior."""

from __future__ import annotations

from ac.mqtt_gateway import MqttGateway


def test_start_connects_async_and_enables_background_retry(monkeypatch) -> None:  # noqa: ANN001
    gateway = MqttGateway(host="100.113.176.38", port=1883, station_id="station-01")
    calls: list[tuple] = []

    monkeypatch.setattr(
        gateway._client,
        "reconnect_delay_set",
        lambda **kwargs: calls.append(("retry", kwargs)),
    )
    monkeypatch.setattr(
        gateway._client,
        "connect_async",
        lambda host, port, keepalive: calls.append(
            ("connect_async", host, port, keepalive)
        ),
    )
    monkeypatch.setattr(
        gateway._client,
        "loop_start",
        lambda: calls.append(("loop_start",)),
    )

    gateway.start()

    assert calls == [
        ("retry", {"min_delay": 1, "max_delay": 30}),
        ("connect_async", "100.113.176.38", 1883, 60),
        ("loop_start",),
    ]
