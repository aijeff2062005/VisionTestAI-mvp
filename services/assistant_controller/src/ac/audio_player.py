"""Scenario audio player (interruptible)."""

from __future__ import annotations

import logging
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from ac.audio_device import resolve_sounddevice

logger = logging.getLogger(__name__)

VOICE_DIRS = ("male", "female")
SLOAN_LETTERS = frozenset("CDHKNORSVZ")
# Original clinic placeholders were ~11KB / 0.35s beeps — treat as missing.
_PLACEHOLDER_MAX_BYTES = 20_000


def resolve_voice_gender(
    *,
    patient_sex: str | None = None,
    frappe_setting: str | None = None,
    clinic_setting: str | None = None,
) -> str | None:
    """Pick voice directory: 'male', 'female', or None (use male files).

    Explicit Male/Female on Frappe or clinic.yaml wins. Auto (or empty):
    male patient → female voice; female patient → male voice; unknown → None.
    """
    for raw in (frappe_setting, clinic_setting):
        setting = (raw or "").strip().lower()
        if setting in ("male", "female"):
            return setting
    sex = (patient_sex or "").strip().lower()
    if sex in ("male", "nam", "m"):
        return "female"
    if sex in ("female", "nữ", "nu", "f"):
        return "male"
    return None


def _usable_wav(path: Path | None) -> bool:
    return bool(path and path.is_file() and path.stat().st_size > _PLACEHOLDER_MAX_BYTES)


class AudioPlayer:
    def __init__(
        self,
        manifest_path: Path,
        *,
        output: str = "sounddevice",
        output_device: str = "",
        prompts_dir: Path | None = None,
        play_browser: Callable[[str, float | None], None] | None = None,
        stop_browser: Callable[[], None] | None = None,
    ) -> None:
        # Manifest may live at scenarios/vi/manifest.yaml or vi/{male|female}/manifest.yaml.
        parent = manifest_path.parent
        self.lang_root = parent.parent if parent.name in VOICE_DIRS else parent
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        self.steps: dict[str, dict[str, Any]] = dict(data.get("steps") or {})
        self.gender: str | None = None
        self.output = (output or "sounddevice").strip().lower() or "sounddevice"
        self.output_device = (output_device or "").strip()
        self.prompts_dir = Path(prompts_dir) if prompts_dir else None
        self.play_browser = play_browser
        self.stop_browser = stop_browser
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._playback_deadline = 0.0

    def set_gender(self, gender: str | None) -> None:
        raw = (gender or "").strip().lower()
        self.gender = raw if raw in VOICE_DIRS else None

    def _voice_dir(self) -> str:
        return self.gender if self.gender in VOICE_DIRS else "male"

    def audio_path(
        self,
        filename: str,
        *,
        step_id: str | None = None,
        eye: str | None = None,
    ) -> Path:
        """Resolve scenarios/vi/{male|female}/<clip>.wav. Missing female → male, then prompts, then legacy."""
        del step_id, eye
        if not filename:
            return self.lang_root / self._voice_dir() / ""
        candidates = [
            self.lang_root / self._voice_dir() / filename,
            self.lang_root / "male" / filename,
            (self.prompts_dir / filename) if self.prompts_dir else None,
            self.lang_root / filename,
        ]
        first_existing: Path | None = None
        for cand in candidates:
            if cand is None or not cand.is_file():
                continue
            if first_existing is None:
                first_existing = cand
            if _usable_wav(cand):
                if cand != candidates[0] and candidates[0] is not None:
                    logger.warning(
                        "Voice wav missing/placeholder for %s/%s; using %s",
                        self._voice_dir(),
                        filename,
                        cand,
                    )
                return cand
        return first_existing or (self.lang_root / self._voice_dir() / filename)

    def browser_url(self, path: Path) -> str | None:
        """HTTP path the chart tab can fetch (same origin as :8088)."""
        if not path or not path.is_file():
            return None
        resolved = path.resolve()
        if self.prompts_dir:
            try:
                resolved.relative_to(self.prompts_dir.resolve())
                return f"/prompts/vi/{path.name}"
            except ValueError:
                pass
        try:
            rel = resolved.relative_to(self.lang_root.resolve())
            return f"/scenarios/vi/{rel.as_posix()}"
        except ValueError:
            return None

    def resolve_step(self, step_id: str, *, eye: str | None = None, queue_number: str | None = None) -> dict[str, Any]:
        step = dict(self.steps.get(step_id) or {})
        if eye and isinstance(step.get("audio_by_eye"), dict):
            step["audio"] = step["audio_by_eye"].get(eye, step.get("audio"))
        if eye and isinstance(step.get("message_by_eye"), dict):
            step["message_vi"] = step["message_by_eye"].get(eye, step.get("message_vi"))
        msg = step.get("message_vi") or ""
        if queue_number and "{queue_number}" in msg:
            step["message_vi"] = msg.replace("{queue_number}", queue_number)
        return step

    def play_async(
        self,
        filename: str | None,
        *,
        step_id: str | None = None,
        eye: str | None = None,
    ) -> None:
        if not filename:
            return
        path = self.audio_path(filename, step_id=step_id, eye=eye)
        if not path.is_file():
            logger.warning("Audio missing: %s", path)
            return
        try:
            with wave.open(str(path), "rb") as wav:
                duration = wav.getnframes() / float(wav.getframerate() or 1)
        except (OSError, wave.Error):
            duration = 0.0
        use_browser = self.output in ("browser", "both") and self.play_browser
        use_device = self.output in ("sounddevice", "device", "both", "")
        if use_browser:
            url = self.browser_url(path)
            if url:
                logger.info(
                    "Browser output: play %s (%d bytes) -> %s",
                    path,
                    path.stat().st_size,
                    url,
                )
                self.stop()
                self._stop.clear()
                self._playback_deadline = time.monotonic() + duration
                self.play_browser(url, None)
                if not use_device:
                    return
            else:
                logger.info(
                    "Browser output: scenario WAV %s has no URL; using sounddevice",
                    path.name,
                )
                use_device = True
        if not use_device:
            return
        if not use_browser:
            self.stop()
            self._stop.clear()
        self._playback_deadline = time.monotonic() + duration

        def _run() -> None:
            try:
                self._play_wav(path)
            except Exception:  # noqa: BLE001
                logger.exception("Audio playback failed for %s", path)
                fallback = self.lang_root / "male" / filename
                if fallback.is_file() and fallback != path:
                    logger.warning("Retrying male clinic wav %s", fallback)
                    try:
                        self._play_wav(fallback)
                    except Exception:  # noqa: BLE001
                        logger.exception("Fallback audio playback failed for %s", fallback)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def playback_remaining_seconds(self, *, tail_seconds: float = 0.0) -> float:
        """Return the current prompt interval that must not reach speech inference."""
        remaining = max(0.0, self._playback_deadline - time.monotonic())
        return remaining + max(0.0, float(tail_seconds)) if remaining > 0.0 else 0.0

    def play_step(self, step_id: str, *, eye: str | None = None, queue_number: str | None = None) -> dict[str, Any]:
        step = self.resolve_step(step_id, eye=eye, queue_number=queue_number)
        self.play_async(step.get("audio"), step_id=step_id, eye=eye)
        return step

    def play_letter_name(self, letter: str | None) -> bool:
        """Play letter clip when the voice directory has that Sloan letter."""
        ch = (letter or "").strip().upper()
        if ch not in SLOAN_LETTERS:
            return False
        filename = f"letter_{ch}.wav"
        path = self.audio_path(filename)
        if not path.is_file():
            return False
        self.play_async(filename)
        return True

    def play_named(self, filename: str | None, *, wait: bool = True, timeout: float = 30.0) -> bool:
        """Play a pack WAV by filename (welcome_ready.wav, cover_left_eye.wav, …)."""
        if not filename:
            return False
        path = self.audio_path(filename)
        if not path.is_file():
            logger.warning("Named audio missing: %s", path)
            return False
        self.play_async(filename)
        if wait and not self.wait_done(timeout=timeout):
            logger.warning("Audio did not finish within %.1fs: %s", timeout, filename)
            return False
        return True

    def wait_done(self, timeout: float = 30.0) -> bool:
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=max(0.05, float(timeout)))
            return not t.is_alive()
        if self.output == "browser":
            remaining = min(max(0.0, float(timeout)), self.playback_remaining_seconds())
            if remaining:
                self._stop.wait(timeout=remaining)
            return self.playback_remaining_seconds() <= 0.0
        return True

    def stop(self) -> None:
        self._stop.set()
        self._playback_deadline = 0.0
        if self.output == "browser" and self.stop_browser:
            try:
                self.stop_browser()
            except Exception:  # noqa: BLE001
                logger.exception("Browser stop_audio failed")
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=0.2)
            if t.is_alive():
                try:
                    import sounddevice as sd

                    sd.stop()
                except Exception:  # noqa: BLE001
                    logger.debug("Forced audio stop failed", exc_info=True)
                t.join(timeout=0.2)
        self._thread = None

    def _play_wav(self, path: Path) -> None:
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            # No sounddevice: simulate duration by sleeping based on WAV length
            with wave.open(str(path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate() or 16000
                duration = frames / float(rate)
            logger.info("sounddevice missing; simulating audio %.2fs (%s)", duration, path.name)
            self._stop.wait(timeout=min(duration, 2.0))
            return

        with wave.open(str(path), "rb") as w:
            rate = w.getframerate()
            channels = w.getnchannels()
            sw = w.getsampwidth()
            raw = w.readframes(w.getnframes())
        if sw == 1:
            audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        elif sw == 2:
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError(f"Unsupported WAV sample width {sw} for {path}")
        if channels > 1:
            audio = audio.reshape(-1, channels)
        if self._stop.is_set():
            return
        device = resolve_sounddevice(self.output_device, kind="output")
        play_rate = int(rate)
        try:
            info = sd.query_devices(device if device is not None else sd.default.device[1])
            native = int(float(info.get("default_samplerate") or 0))
        except Exception:  # noqa: BLE001
            native = 0
        if native and native != play_rate:
            n_in = int(audio.shape[0])
            n_out = max(1, int(round(n_in * native / play_rate)))
            x = np.linspace(0.0, 1.0, n_in, endpoint=False)
            xo = np.linspace(0.0, 1.0, n_out, endpoint=False)
            if audio.ndim == 1:
                audio = np.interp(xo, x, audio).astype(np.float32)
            else:
                audio = np.stack(
                    [np.interp(xo, x, audio[:, c]) for c in range(audio.shape[1])],
                    axis=1,
                ).astype(np.float32)
            logger.info(
                "Resampled %s %sHz → %sHz for device %s",
                path.name,
                play_rate,
                native,
                device,
            )
            play_rate = native
        try:
            sd.play(audio, play_rate, device=device)
        except Exception:
            logger.warning("Play on %s failed; retry Pulse plugin", device, exc_info=True)
            sd.play(audio, play_rate, device="pulse")
        # poll for interrupt
        while sd.get_stream() is not None and sd.get_stream().active:
            if self._stop.is_set():
                sd.stop()
                break
            self._stop.wait(0.05)
        sd.wait()
