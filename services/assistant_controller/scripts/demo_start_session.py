#!/usr/bin/env python3
"""Publish a provisional session/start MQTT message (local Mosquitto demo)."""

from __future__ import annotations

import argparse
import json
import uuid

import paho.mqtt.client as mqtt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="192.168.1.78")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--username", default="vision")
    p.add_argument("--password", default="mqtt-dev-pass")
    p.add_argument("--station", default="station-01")
    p.add_argument("--patient", default="P001")
    p.add_argument("--queue", default="A012")
    p.add_argument(
        "--callback",
        default="http://192.168.1.78:8000/api/vision/results",
    )
    args = p.parse_args()

    payload = {
        "schema_version": "0.1.0",
        "session_id": str(uuid.uuid4()),
        "patient_id": args.patient,
        "queue_number": args.queue,
        "exam_type": "distance_acuity_5m",
        "eyes": "both",
        "callback_url": args.callback,
        "correlation_id": str(uuid.uuid4()),
        "locale": "vi-VN",
    }
    topic = f"qlbn/station/{args.station}/session/start"
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password or None)
    client.connect(args.host, args.port, 60)
    client.publish(topic, json.dumps(payload), qos=1)
    client.disconnect()
    print(f"Published → {topic}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
