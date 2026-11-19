"""In-process Vietnamese Sloan letter STT — wraps sibling sloan-stt_v2 Recognizer + mic VAD."""

from __future__ import annotations

import queue
import random
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Chart letters shown to patient (X = special skip class, not on board)
LETTER_POOL = ["C", "D", "H", "K", "N", "O", "R", "S", "V", "Z"]
SKIP_LETTER = "X"
UNK_TOKEN = "[UNK]"

# Prefer laptop built-in mic over headset / Continuity defaults
MACBOOK_MIC_MATCH = [
    "macbook air microphone",
    "macbook pro microphone",
    "macbook microphone",
    "built-in microphone",
    "internal microphone",
]


def resolve_macbook_mic(
    prefer: list[str] | None = None,
) -> tuple[int | None, str]:
    """Pick MacBook built-in input; fall back to default input if not found."""
    import sounddevice as sd

    prefs = [p.lower() for p in (prefer or MACBOOK_MIC_MATCH)]
    devices = sd.query_devices()
    for pref in prefs:
        for i, d in enumerate(devices):
            name = str(d.get("name", ""))
            if d.get("max_input_channels", 0) < 1:
                continue
            if pref in name.lower():
                return i, name
    try:
        idx = sd.default.device[0]
        if isinstance(idx, int) and idx >= 0:
            name = str(devices[idx].get("name", f"device {idx}"))
            return idx, name
    except Exception:  # noqa: BLE001
        pass
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) >= 1:
            return i, str(d.get("name", f"device {i}"))
    return None, "no input device"


def list_microphones() -> list[tuple[int, str, int, bool]]:
    """Return [(index, name, max_input_channels, is_default), ...]."""
    import sounddevice as sd

    devices = sd.query_devices()
    default_in = None
    try:
        default_in = sd.default.device[0]
    except Exception:  # noqa: BLE001
        pass
    out: list[tuple[int, str, int, bool]] = []
    for i, d in enumerate(devices):
        ch = int(d.get("max_input_channels", 0) or 0)
        if ch < 1:
            continue
        name = str(d.get("name", f"device {i}"))
        out.append((i, name, ch, i == default_in))
    return out


def print_microphone_list() -> None:
    """Print input devices for --list-mics / user setup with --micro."""
    try:
        mics = list_microphones()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list microphones: {exc}")
        print("Install sounddevice: pip install sounddevice")
        return
    if not mics:
        print("No input microphones found.")
        return
    print("Available INPUT microphones (sounddevice):")
    print(f"{'idx':>4}  {'default':7}  channels  name")
    for idx, name, ch, is_def in mics:
        mark = "*" if is_def else " "
        print(f"{idx:4d}  {mark:7}  {ch:8d}  {name}")
    print()
    print("Note: Bluetooth headsets often have TWO indices — input (mic) and")
    print("      output (speakers). Only INPUT indices are listed above.")
    print("Use:  --micro 5")
    print('  or: --micro "MacBook Air Microphone"')


def _input_sibling(idx: int) -> tuple[int, str] | None:
    """If idx is output-only, return same-name device with input channels."""
    import sounddevice as sd

    try:
        info = sd.query_devices(idx)
    except Exception:  # noqa: BLE001
        return None
    name = str(info.get("name", ""))
    if int(info.get("max_input_channels", 0) or 0) >= 1:
        return idx, name
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if i == idx:
            continue
        if str(d.get("name", "")) != name:
            continue
        if int(d.get("max_input_channels", 0) or 0) >= 1:
            return i, name
    return None


def resolve_mic_arg(
    micro: str | int | None,
    prefer: list[str] | None = None,
) -> tuple[int | None, str]:
    """Resolve --micro index/name, else MacBook prefer list."""
    if micro is None or str(micro).strip() == "":
        return resolve_macbook_mic(prefer=prefer)
    text = str(micro).strip()
    if text.isdigit():
        import sounddevice as sd

        idx = int(text)
        sibling = _input_sibling(idx)
        if sibling is not None:
            real_idx, name = sibling
            if real_idx != idx:
                print(
                    f"Note: device {idx} '{name}' is output-only; "
                    f"using INPUT index {real_idx} instead."
                )
            return real_idx, name
        try:
            info = sd.query_devices(idx, "input")
            return idx, str(info.get("name", f"device {idx}"))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"Invalid mic index {idx}: {exc}. "
                "Run --list-mics (Bluetooth output≠mic)."
            ) from exc
    import sounddevice as sd

    needle = text.lower()
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if int(d.get("max_input_channels", 0) or 0) < 1:
            continue
        name = str(d.get("name", ""))
        if needle in name.lower():
            return i, name
    raise ValueError(
        f"No microphone matching {micro!r}. Run: python scripts/run_webcam_demo.py --list-mics"
    )


@dataclass
class HeardEvent:
    letter: str
    reliable: bool
    confidence: float
    margin: float
    topk: list[dict[str, Any]] = field(default_factory=list)
    ts: float = 0.0
    raw: str = ""


def resolve_sloan_root(cfg_root: str | Path | None = None) -> Path:
    """Locate Sloan STT package (models + runtime.py).

    Preferred layout: ``mvp_platform/services/sloan_stt`` (sibling of smarteyes).
    Also accepts legacy ``sloan-stt_v2`` next to services/ or under VisionTestAI/.
    """
    here = Path(__file__).resolve()
    # smarteyes/src → parents[1]=smarteyes, [2]=services, [3]=mvp_platform, [4]=VisionTestAI
    smart = here.parents[1]
    services = here.parents[2]
    mvp = here.parents[3]
    vision = here.parents[4]

    candidates: list[Path] = []
    if cfg_root:
        p = Path(cfg_root)
        if not p.is_absolute():
            # Relative to SmartEyes project root (parent of src/)
            p = (smart / p).resolve()
        candidates.append(p)
    candidates += [
        services / "sloan_stt",
        services / "sloan-stt_v2",
        mvp / "sloan_stt",
        vision / "sloan-stt_v2",
        vision / "sloan_stt",
    ]
    required = ("encoder.int8.onnx", "classifier.onnx", "labels.txt", "runtime.py")
    for cand in candidates:
        if cand.is_dir() and all((cand / name).exists() for name in required):
            return cand
    # Fall back to the canonical new path (clearer error message)
    return services / "sloan_stt"


def load_recognizer(
    sloan_root: Path | None = None,
    *,
    top_k: int = 3,
) -> Any:
    """Import Recognizer from sloan-stt_v2 with clear errors if missing."""
    root = sloan_root or resolve_sloan_root()
    if not root.is_dir():
        raise FileNotFoundError(
            f"Sloan STT not found at {root}. "
            "Expected mvp_platform/services/sloan_stt (encoder/classifier/runtime)."
        )
    for name in ("encoder.int8.onnx", "classifier.onnx", "labels.txt", "runtime.py"):
        if not (root / name).exists():
            raise FileNotFoundError(f"Missing {name} under {root}")

    missing_pkgs: list[str] = []
    for mod, pkg in (
        ("onnxruntime", "onnxruntime"),
        ("torchaudio", "torchaudio"),
        ("librosa", "librosa"),
        ("sounddevice", "sounddevice"),
    ):
        try:
            __import__(mod)
        except ImportError:
            missing_pkgs.append(pkg)
    if missing_pkgs:
        raise ImportError(
            "Spell mode needs: "
            + ", ".join(missing_pkgs)
            + "\n  conda activate smarteyes && pip install "
            + " ".join(missing_pkgs)
        )

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    # Prefer package path without clobbering forever — still OK for demo
    from runtime import Recognizer  # type: ignore  # noqa: WPS433

    return Recognizer(top_k=top_k)


def new_board(length: int = 5) -> list[str]:
    length = max(1, min(length, len(LETTER_POOL)))
    return random.sample(LETTER_POOL, k=length)


@dataclass
class LetterTrial:
    target: list[str] = field(default_factory=list)
    heard: list[str] = field(default_factory=list)
    soft_align: bool = True

    def __post_init__(self) -> None:
        if not self.target:
            self.target = new_board(5)

    def reset_board(self, length: int | None = None) -> None:
        n = length if length is not None else len(self.target) or 5
        self.target = new_board(n)
        self.heard.clear()

    def clear_heard(self) -> None:
        self.heard.clear()

    def apply_prediction(
        self,
        prediction: str,
        *,
        reliable: bool,
        topk: list[dict[str, Any]] | None = None,
    ) -> str:
        """Apply one classifier result. Returns action: 'append'|'skip'|'ignore'|'done'."""
        if not reliable or prediction == UNK_TOKEN:
            return "ignore"
        if prediction == SKIP_LETTER:
            self.reset_board()
            return "skip"
        if prediction not in LETTER_POOL:
            return "ignore"

        letter = prediction
        idx = len(self.heard)
        if self.soft_align and idx < len(self.target) and topk:
            want = self.target[idx]
            labels = {str(t.get("label", "")) for t in topk}
            if want in labels and letter != want:
                # Soft correct only when target is in top-k
                letter = want

        self.heard.append(letter)
        if self.is_complete():
            return "done"
        return "append"

    def is_complete(self) -> bool:
        return len(self.heard) >= len(self.target) and len(self.target) > 0

    def score(self) -> tuple[int, int]:
        n = min(len(self.heard), len(self.target))
        correct = sum(1 for i in range(n) if self.heard[i] == self.target[i])
        return correct, len(self.target)


class SloanLetterListener:
    """Background mic VAD → Recognizer.predict; poll HeardEvent from vision thread."""

    def __init__(
        self,
        *,
        recognizer: Any | None = None,
        sloan_root: Path | None = None,
        min_confidence: float = 0.55,
        min_margin: float = 0.05,
        energy_threshold: float = 0.008,
        silence_duration: float = 0.18,
        device: int | str | None = None,
        audio_url: str | None = None,
        audio_sample_rate: int = 48000,
    ) -> None:
        self.sloan_root = sloan_root or resolve_sloan_root()
        self.min_confidence = min_confidence
        self.min_margin = min_margin
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.device = device
        self.audio_url = str(audio_url or "").strip() or None
        self._recognizer = recognizer
        self._events: queue.Queue[HeardEvent] = queue.Queue(maxsize=64)
        self._chunks: queue.Queue[np.ndarray] = queue.Queue(maxsize=300)
        self._jobs: queue.Queue[np.ndarray] = queue.Queue(maxsize=32)
        self._stopping = threading.Event()
        self._enabled = threading.Event()
        self._threads: list[threading.Thread] = []
        self._stream = None
        self._sample_rate = int(audio_sample_rate)
        self._error: str | None = None
        self._last_conf = 0.0
        self._started = False
        self.device_name = ""
        self._network_response = None

    @property
    def last_confidence(self) -> float:
        return self._last_conf

    @property
    def error(self) -> str | None:
        return self._error

    def ensure_recognizer(self) -> Any:
        if self._recognizer is None:
            self._recognizer = load_recognizer(self.sloan_root)
        return self._recognizer

    def start(self) -> None:
        if self._started:
            return
        try:
            self.ensure_recognizer()
            if self.audio_url:
                self.device_name = f"Network mic {self.audio_url}"
                print(
                    f"Spell mic: {self.device_name} @ {self._sample_rate} Hz",
                    flush=True,
                )
            else:
                import sounddevice as sd

                if self.device is None:
                    self.device, self.device_name = resolve_macbook_mic()
                else:
                    info = sd.query_devices(self.device, "input")
                    self.device_name = str(info.get("name", str(self.device)))
                info = sd.query_devices(self.device, "input")
                self._sample_rate = int(round(info["default_samplerate"]))
                block = max(256, int(self._sample_rate * 0.03))
                print(
                    f"Spell mic: [{self.device}] {self.device_name} "
                    f"@ {self._sample_rate} Hz"
                )

                def callback(indata, frames, t, status) -> None:  # noqa: ANN001
                    if status:
                        pass
                    if not self._enabled.is_set():
                        return
                    try:
                        self._chunks.put_nowait(indata[:, 0].copy())
                    except queue.Full:
                        pass

                self._stream = sd.InputStream(
                    device=self.device,
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=block,
                    callback=callback,
                )
                self._stream.start()

            self._stopping.clear()
            source_threads: list[threading.Thread] = []
            if self.audio_url:
                t_source = threading.Thread(
                    target=self._network_audio_loop,
                    daemon=True,
                    name="sloan-network-mic",
                )
                t_source.start()
                source_threads.append(t_source)
            t_vad = threading.Thread(target=self._vad_loop, daemon=True, name="sloan-vad")
            t_pred = threading.Thread(
                target=self._predict_loop, daemon=True, name="sloan-predict"
            )
            t_vad.start()
            t_pred.start()
            self._threads = source_threads + [t_vad, t_pred]
            self._started = True
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._started = False
            raise

    def stop(self) -> None:
        self._enabled.clear()
        self._stopping.set()
        if self._network_response is not None:
            try:
                self._network_response.close()
            except Exception:  # noqa: BLE001
                pass
            self._network_response = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        self._started = False

    def _network_audio_loop(self) -> None:
        """Read little-endian float32 mono PCM from a streaming HTTP endpoint."""
        block_bytes = max(256, int(self._sample_rate * 0.03)) * 4
        pending = b""
        while not self._stopping.is_set():
            try:
                req = urllib.request.Request(
                    self.audio_url,
                    headers={"User-Agent": "SmartEyes-NetworkMic/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    self._network_response = response
                    while not self._stopping.is_set():
                        data = response.read(block_bytes)
                        if not data:
                            raise ConnectionError("MacBook mic stream closed")
                        pending += data
                        usable = len(pending) - (len(pending) % 4)
                        if usable == 0:
                            continue
                        audio = np.frombuffer(pending[:usable], dtype="<f4").copy()
                        pending = pending[usable:]
                        if self._enabled.is_set():
                            try:
                                self._chunks.put_nowait(audio)
                            except queue.Full:
                                pass
            except Exception as exc:  # noqa: BLE001
                if not self._stopping.is_set():
                    self._error = f"Network mic reconnecting: {exc}"
                    time.sleep(1.0)
            finally:
                self._network_response = None

    def set_enabled(self, on: bool) -> None:
        if on:
            self._enabled.set()
        else:
            self._enabled.clear()

    def is_enabled(self) -> bool:
        return self._enabled.is_set()

    def poll(self) -> list[HeardEvent]:
        out: list[HeardEvent] = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
        return out

    def _vad_loop(self) -> None:
        active = False
        buffers: list[np.ndarray] = []
        pre: list[np.ndarray] = []
        quiet = 0.0
        rate = float(self._sample_rate)
        while not self._stopping.is_set():
            try:
                x = self._chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if not self._enabled.is_set():
                active = False
                buffers = []
                pre = []
                quiet = 0.0
                continue
            d = len(x) / rate
            e = float(np.sqrt(np.mean(x * x) + 1e-10))
            pre = (pre + [x])[-3:]
            if e >= self.energy_threshold:
                if not active:
                    active = True
                    buffers = list(pre[:-1])
                buffers.append(x)
                quiet = 0.0
            elif active:
                buffers.append(x)
                quiet += d
                if quiet >= self.silence_duration:
                    if sum(len(b) for b in buffers) / rate >= 0.16:
                        try:
                            self._jobs.put_nowait(np.concatenate(buffers))
                        except queue.Full:
                            pass
                    active = False
                    buffers = []
                    pre = []
                    quiet = 0.0

    def _predict_loop(self) -> None:
        while not self._stopping.is_set() or not self._jobs.empty():
            try:
                audio = self._jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if not self._enabled.is_set():
                    continue
                model = self.ensure_recognizer()
                r = model.predict(
                    audio,
                    self._sample_rate,
                    self.min_confidence,
                    self.min_margin,
                )
                self._last_conf = float(r.get("confidence", 0.0))
                ev = HeardEvent(
                    letter=str(r.get("prediction", UNK_TOKEN)),
                    reliable=bool(r.get("reliable", False)),
                    confidence=float(r.get("confidence", 0.0)),
                    margin=float(r.get("margin", 0.0)),
                    topk=list(r.get("topk") or []),
                    ts=time.time(),
                    raw=str(r.get("raw", "")),
                )
                try:
                    self._events.put_nowait(ev)
                except queue.Full:
                    try:
                        self._events.get_nowait()
                    except queue.Empty:
                        pass
                    self._events.put_nowait(ev)
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
            finally:
                self._jobs.task_done()
