"""Resolve Pulse/ALSA devices for Jetson USB headset dongles."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def resolve_sounddevice(hint: str | None, *, kind: str) -> int | str | None:
    """Return a sounddevice id for input/output, or None for the Pulse default."""
    raw = str(hint or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    try:
        import sounddevice as sd
    except ImportError:
        return raw
    want_in = kind == "input"
    hint_l = raw.lower()
    fallback: int | None = None
    for idx, info in enumerate(sd.query_devices()):
        name = str(info.get("name") or "")
        if hint_l not in name.lower() and raw not in name:
            continue
        ch = int(info.get("max_input_channels" if want_in else "max_output_channels") or 0)
        if ch < 1:
            continue
        if "monitor" in name.lower():
            continue
        # Direct ALSA hw on USB headsets rejects 24 kHz clinic WAVs and
        # steals the card from Pulse. Prefer the Pulse plugin instead.
        if "hw:" in name.lower():
            continue
        fallback = idx
        if "yealink" in name.lower() or "bt51" in name.lower() or "pulse" in name.lower():
            logger.info("Audio %s device %s → [%s] %s", kind, raw, idx, name)
            return idx
    if fallback is not None:
        name = sd.query_devices(fallback).get("name")
        logger.info("Audio %s device %s → [%s] %s", kind, raw, fallback, name)
        return fallback
    # USB headsets are often held by Pulse, so PortAudio never lists "Yealink".
    # Route through the Pulse plugin; start_station.sh sets PULSE_SINK/PULSE_SOURCE.
    logger.warning(
        "Audio %s device hint %r not in PortAudio; using Pulse plugin (PULSE_%s=%s)",
        kind,
        raw,
        "SINK" if kind == "output" else "SOURCE",
        os.environ.get(
            "PULSE_SINK" if kind == "output" else "PULSE_SOURCE", "<unset>"
        ),
    )
    return "pulse"
