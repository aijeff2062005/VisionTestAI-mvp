"""MQTT control bus for media grants / ready events."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MediaMqtt:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        stations: list[str] | None = None,
        on_request: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.stations = stations or ["station-01"]
        self.on_request = on_request
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="visiontestai-media",
        )
        if username:
            self._client.username_pw_set(username, password or None)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._client.connect(self.host, self.port, keepalive=60)
        except Exception:  # noqa: BLE001
            logger.exception("MQTT connect failed (%s:%s) — HTTP store still works", self.host, self.port)
            return
        self._thread = threading.Thread(target=self._client.loop_forever, daemon=True)
        self._thread.start()
        logger.info("Media MQTT connected to %s:%s", self.host, self.port)

    def stop(self) -> None:
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _on_connect(self, client: mqtt.Client, *_args: Any) -> None:
        for station in self.stations:
            topic = f"qlbn/media/{station}/object/request"
            client.subscribe(topic, qos=1)
            logger.info("Subscribed %s", topic)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        if self.on_request is None:
            return
        parts = msg.topic.split("/")
        # qlbn / media / {station} / object / request
        if len(parts) < 5 or parts[-1] != "request":
            return
        station = parts[2]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            logger.warning("Bad MQTT JSON on %s", msg.topic)
            return
        if not isinstance(payload, dict):
            return
        try:
            self.on_request(station, payload)
        except Exception:  # noqa: BLE001
            logger.exception("on_request failed")

    def publish_grant(self, station_id: str, payload: dict[str, Any]) -> None:
        self._publish(f"qlbn/media/{station_id}/object/grant", payload)

    def publish_ready(self, station_id: str, payload: dict[str, Any]) -> None:
        self._publish(f"qlbn/media/{station_id}/object/ready", payload)

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
        except Exception:  # noqa: BLE001
            logger.exception("MQTT publish failed topic=%s", topic)
