"""Record Yealink/Pulse audio from letter-on-screen until patient says đúng."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_SECONDS = 120.0
_SAMPLERATE = 16000


class LetterClipRecorder:
    """Archive a letter interaction from the STT microphone timeline."""

    def __init__(
        self,
        input_device: str = "",
        *,
        shared_microphone: Any | None = None,
    ) -> None:
        self.input_device = input_device
        self.shared_microphone = shared_microphone
        self._shared_cursor: int | None = None
        self._lock = threading.Lock()
        self._chunks: list[Any] = []
        self._stream: Any = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sr = _SAMPLERATE
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        self.discard()
        if self.shared_microphone is not None:
            try:
                self._shared_cursor = int(self.shared_microphone.cursor())
            except Exception:  # noqa: BLE001
                logger.exception("Letter clip could not mark shared microphone")
                return False
            self._sr = int(getattr(self.shared_microphone, "samplerate", _SAMPLERATE))
            self._running = True
            logger.info(
                "Letter clip marked shared microphone cursor=%s",
                self._shared_cursor,
            )
            return True
        source = (os.environ.get("PULSE_SOURCE") or "").strip()
        if source and shutil.which("parec"):
            if self._start_parec(source):
                return True
        return self._start_sounddevice()

    def discard(self) -> None:
        self._stop_capture()
        self._shared_cursor = None
        with self._lock:
            self._chunks = []
        self._running = False

    def save_wav(self, path: Path) -> float:
        """Stop capture and write 16-bit PCM WAV. Returns duration seconds."""
        if self.shared_microphone is not None and self._shared_cursor is not None:
            audio = self.shared_microphone.samples_since(self._shared_cursor)
            self._shared_cursor = None
            chunks: list[Any] = []
        else:
            self._stop_capture()
            with self._lock:
                chunks = self._chunks
                self._chunks = []
            audio = _concat_float32(chunks) if chunks else None
        self._running = False
        if audio is None or getattr(audio, "size", 0) == 0:
            logger.warning("Letter clip empty — not writing %s", path)
            return 0.0
        duration = float(len(audio)) / float(self._sr or _SAMPLERATE)
        clipped = _clip_unit(audio)
        pcm = (clipped * 32767.0).astype("int16")
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(int(self._sr or _SAMPLERATE))
            fh.writeframes(pcm.tobytes())
        logger.info("Letter clip wrote %s (%.2fs)", path, duration)
        return duration

    def _start_parec(self, source: str) -> bool:
        cmd = [
            "parec",
            "-d",
            source,
            "--format=s16le",
            "--rate",
            str(self._sr),
            "--channels=1",
            "--latency-msec=30",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Letter clip parec failed source=%s", source)
            return False
        self._proc = proc
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._parec_loop,
            name="letter-clip-parec",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info("Letter clip started via parec source=%s sr=%s", source, self._sr)
        return True

    def _parec_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        max_bytes = int(_MAX_SECONDS * self._sr * 2)
        try:
            while not self._stop.is_set():
                raw = proc.stdout.read(4096)
                if not raw:
                    break
                with self._lock:
                    self._chunks.append(bytes(raw))
                    total = sum(len(c) for c in self._chunks)
                    while total > max_bytes and len(self._chunks) > 1:
                        dropped = self._chunks.pop(0)
                        total -= len(dropped)
        except Exception:  # noqa: BLE001
            logger.debug("Letter clip parec loop ended", exc_info=True)

    def _start_sounddevice(self) -> bool:
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("Letter clip: sounddevice missing")
            return False
        from ac.audio_device import resolve_sounddevice

        device = resolve_sounddevice(self.input_device, kind="input")
        block = max(256, int(self._sr * 0.03))
        max_samples = int(_MAX_SECONDS * self._sr)

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            del frames, time_info
            if status:
                logger.debug("Letter clip status %s", status)
            mono = indata[:, 0].copy()
            with self._lock:
                self._chunks.append(mono)
                total = sum(len(c) for c in self._chunks)
                while total > max_samples and len(self._chunks) > 1:
                    dropped = self._chunks.pop(0)
                    total -= len(dropped)

        try:
            stream = sd.InputStream(
                device=device,
                samplerate=self._sr,
                channels=1,
                dtype="float32",
                blocksize=block,
                callback=callback,
            )
            stream.start()
        except Exception:  # noqa: BLE001
            logger.exception("Letter clip could not open mic device=%s", device)
            return False
        self._stream = stream
        self._running = True
        logger.info("Letter clip started device=%s sr=%s", device, self._sr)
        return True

    def _stop_capture(self) -> None:
        self._stop.set()
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass


def _concat_float32(chunks: list[Any]) -> Any:
    import numpy as np

    if chunks and isinstance(chunks[0], (bytes, bytearray)):
        raw = b"".join(chunks)
        if len(raw) % 2:
            raw = raw[:-1]
        pcm = np.frombuffer(raw, dtype="<i2")
        return pcm.astype(np.float32) / 32768.0
    return np.concatenate(chunks).astype(np.float32, copy=False)


def _clip_unit(audio: Any) -> Any:
    import numpy as np

    return np.clip(audio, -1.0, 1.0)
