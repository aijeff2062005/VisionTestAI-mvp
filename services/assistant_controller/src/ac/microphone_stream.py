"""One process-wide microphone stream shared by STT and archival recording."""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class SharedMicrophoneStream:
    """Persistent mono input with a bounded, cursor-addressable ring buffer.

    A cursor lets each consumer read its own time range without opening another
    Pulse/ALSA client.  Sloan STT consumes new chunks while ``LetterClipRecorder``
    snapshots the same raw samples for the session archive.
    """

    def __init__(
        self,
        input_device: str = "",
        *,
        samplerate: int = 16000,
        block_seconds: float = 0.03,
        history_seconds: float = 125.0,
    ) -> None:
        self.input_device = str(input_device or "").strip()
        self.samplerate = int(samplerate)
        self.blocksize = max(256, int(self.samplerate * float(block_seconds)))
        history_chunks = max(
            32,
            int(float(history_seconds) * self.samplerate / self.blocksize) + 2,
        )
        self._chunks: deque[tuple[int, Any]] = deque(maxlen=history_chunks)
        self._condition = threading.Condition()
        self._start_lock = threading.Lock()
        self._stream: Any = None
        self._sequence = 0
        self._closed = False

    @property
    def running(self) -> bool:
        stream = self._stream
        return bool(stream is not None and getattr(stream, "active", True))

    def start(self) -> bool:
        """Open the device once. Repeated calls are cheap and idempotent."""
        if self.running:
            return True
        with self._start_lock:
            if self.running:
                return True
            if self._closed:
                return False
            stream: Any = None
            try:
                import sounddevice as sd

                from ac.audio_device import resolve_sounddevice

                device = resolve_sounddevice(self.input_device, kind="input")

                def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
                    del frames, time_info
                    if status:
                        logger.warning("Shared microphone status: %s", status)
                    mono = indata[:, 0].copy()
                    with self._condition:
                        self._sequence += 1
                        self._chunks.append((self._sequence, mono))
                        self._condition.notify_all()

                stream = sd.InputStream(
                    device=device,
                    samplerate=self.samplerate,
                    channels=1,
                    dtype="float32",
                    blocksize=self.blocksize,
                    callback=callback,
                )
                stream.start()
            except Exception:  # noqa: BLE001
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:  # noqa: BLE001
                        pass
                logger.exception("Could not start shared microphone input")
                return False
            self._stream = stream
            logger.info(
                "Shared microphone started device=%s sr=%s block=%s",
                device if device is not None else self.input_device or "default",
                self.samplerate,
                self.blocksize,
            )
            return True

    def cursor(self) -> int:
        """Return a marker immediately after all samples captured so far."""
        if not self.start():
            raise RuntimeError("shared microphone is unavailable")
        with self._condition:
            return self._sequence

    def read_after(self, cursor: int, timeout: float) -> tuple[list[Any], int]:
        """Wait for and return chunks newer than ``cursor``."""
        if not self.start():
            raise RuntimeError("shared microphone is unavailable")
        import time

        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            while self._sequence <= cursor and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return [], cursor
                self._condition.wait(timeout=remaining)
            rows = [(seq, chunk) for seq, chunk in self._chunks if seq > cursor]
        if not rows:
            return [], cursor
        return [chunk for _, chunk in rows], rows[-1][0]

    def samples_since(self, cursor: int) -> Any:
        """Copy all raw samples retained after ``cursor`` into one array."""
        import numpy as np

        with self._condition:
            chunks = [chunk for seq, chunk in self._chunks if seq > cursor]
        if not chunks:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def close(self) -> None:
        """Stop the single underlying audio client."""
        with self._start_lock:
            self._closed = True
            stream = self._stream
            self._stream = None
            with self._condition:
                self._condition.notify_all()
            if stream is None:
                return
            try:
                stream.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Shared microphone stop failed", exc_info=True)
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                logger.debug("Shared microphone close failed", exc_info=True)
            logger.info("Shared microphone stopped")
