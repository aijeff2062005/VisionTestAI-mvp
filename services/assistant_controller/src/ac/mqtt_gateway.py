"""MQTT gateway for provisional QLBN session topics."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from ac.models import SessionCancel, SessionStart, SessionStatus

logger = logging.getLogger(__name__)


class MqttGateway:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        station_id: str,
        username: str = "",
        password: str = "",
        tls: bool = False,
        tls_ca_certs: str | None = None,
        keepalive: int = 60,
        on_start: Callable[[SessionStart], None] | None = None,
        on_cancel: Callable[[SessionCancel], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.station_id = station_id
        self.keepalive = keepalive
        self.tls = tls
        self.tls_ca_certs = tls_ca_certs
        self.on_start = on_start
        self.on_cancel = on_cancel
        self.topic_start = f"qlbn/station/{station_id}/session/start"
        self.topic_status = f"qlbn/station/{station_id}/session/status"
        self.topic_cancel = f"qlbn/station/{station_id}/session/cancel"

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"visiontestai-ac-{station_id}",
        )
        if username:
            self._client.username_pw_set(username, password or None)
        if tls:
            # Default to system trust roots and certificate/hostname validation.
            self._client.tls_set(ca_certs=tls_ca_certs)
            self._client.tls_insecure_set(False)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._connected = threading.Event()

    def start(self) -> None:
        logger.info("MQTT connecting %s:%s", self.host, self.port)
        # Do not make station startup depend on the network already being up.
        # connect_async + the Paho network loop keep retrying in the background
        # and automatically re-subscribe via _on_connect after connectivity
        # returns (common when Tailscale comes up after the user service).
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.connect_async(self.host, self.port, self.keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_status(self, status: SessionStatus) -> None:
        payload = status.model_dump(mode="json")
        self._client.publish(self.topic_status, json.dumps(payload), qos=1)

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any = None) -> None:
        rc = getattr(reason_code, "value", reason_code)
        if rc != 0 and str(reason_code) not in ("Success", "0"):
            logger.error("MQTT connect failed: %s", reason_code)
            return
        client.subscribe([(self.topic_start, 1), (self.topic_cancel, 1)])
        self._connected.set()
        logger.info("MQTT subscribed start=%s cancel=%s", self.topic_start, self.topic_cancel)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("Invalid MQTT JSON on %s", msg.topic)
            return
        try:
            if msg.topic == self.topic_start:
                logger.info("MQTT start session_id=%s patient=%s", data.get("session_id"), data.get("patient_id"))
                start = SessionStart.model_validate(data)
                if self.on_start:
                    self.on_start(start)
            elif msg.topic == self.topic_cancel:
                logger.info("MQTT cancel session_id=%s reason=%s", data.get("session_id"), data.get("reason"))
                cancel = SessionCancel.model_validate(data)
                if self.on_cancel:
                    self.on_cancel(cancel)
            else:
                logger.warning("MQTT ignored topic=%s", msg.topic)
        except Exception:  # noqa: BLE001
            logger.exception("Failed handling MQTT message on %s", msg.topic)
