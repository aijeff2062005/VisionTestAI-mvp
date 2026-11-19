from __future__ import annotations

import sys
import threading
import wave
from types import SimpleNamespace

import numpy as np

from ac.letter_clip import LetterClipRecorder
from ac.microphone_stream import SharedMicrophoneStream
from ac.readiness_bridge import SloanSttBridge


def test_shared_microphone_opens_portaudio_only_once(monkeypatch) -> None:  # noqa: ANN001
    streams = []

    class FakeStream:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs
            self.active = False
            streams.append(self)

        def start(self) -> None:
            self.active = True

        def stop(self) -> None:
            self.active = False

        def close(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=FakeStream))
    microphone = SharedMicrophoneStream(samplerate=16000)

    assert microphone.start() is True
    assert microphone.start() is True
    assert len(streams) == 1
    microphone.close()


def test_letter_clip_uses_shared_microphone_samples(tmp_path) -> None:  # noqa: ANN001
    class FakeMicrophone:
        samplerate = 16000

        def cursor(self) -> int:
            return 41

        def samples_since(self, cursor: int) -> np.ndarray:
            assert cursor == 41
            return np.full(1600, 0.1, dtype=np.float32)

    recorder = LetterClipRecorder(shared_microphone=FakeMicrophone())
    output = tmp_path / "letter.wav"

    assert recorder.start() is True
    assert recorder.save_wav(output) == 0.1
    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnframes() == 1600


def test_sloan_vad_matches_filtered_adaptive_frontend() -> None:
    samplerate = 16000
    block = 480
    silence = [np.zeros(block, dtype=np.float32) for _ in range(8)]
    phase = np.arange(block, dtype=np.float32) / samplerate
    voiced_chunk = (0.08 * np.sin(2 * np.pi * 500 * phase)).astype(np.float32)
    voiced = [voiced_chunk.copy() for _ in range(12)]
    ending = [np.zeros(block, dtype=np.float32) for _ in range(6)]
    pending = silence + voiced + ending

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.energy_threshold = 0.004
    bridge.silence_duration = 0.14
    bridge.min_voiced_seconds = 0.16

    def read_chunks(_wait_seconds: float) -> list[np.ndarray]:
        return [pending.pop(0)] if pending else []

    audio, used_rate = bridge._record_vad(
        1.0,
        samplerate=samplerate,
        read_chunks=read_chunks,
    )

    assert used_rate == samplerate
    assert audio.dtype == np.float32
    assert 0.35 <= audio.size / samplerate <= 0.7
    assert float(np.sqrt(np.mean(audio * audio))) > 0.01


def test_chunk_vad_splits_repeated_speech_after_short_pause() -> None:
    samplerate = 16000
    block = 480
    phase = np.arange(block, dtype=np.float32) / samplerate
    voice = (0.08 * np.sin(2 * np.pi * 500 * phase)).astype(np.float32)
    silence = np.zeros(block, dtype=np.float32)
    chunks = [silence] * 4 + [voice] * 10 + [silence] * 8 + [voice] * 10 + [silence] * 8

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.energy_threshold = 0.018
    bridge.silence_duration = 0.20
    bridge.min_voiced_seconds = 0.25
    bridge.vad_padding_seconds = 0.12
    bridge._vad_noise_floor = {}

    segments = bridge._split_vad_segments(chunks, samplerate=samplerate)

    assert len(segments) == 2


def test_chunk_uses_later_segment_on_equal_confidence() -> None:
    class Recognizer:
        def __init__(self) -> None:
            self.rows = [
                {"prediction": "K", "confidence": 0.70, "reliable": True},
                {"prediction": "N", "confidence": 0.70, "reliable": True},
            ]

        def predict(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return self.rows.pop(0)

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = Recognizer()
    bridge.min_margin = 0.05
    bridge._record_device_chunk = lambda _timeout, **_kwargs: ([np.ones(8)], 16000)
    bridge._split_vad_segments = lambda _chunks, samplerate: [np.ones(8), np.ones(8)]
    activity: list[bool] = []
    bridge.inference_activity_callback = activity.append

    result = bridge.listen_chunk(timeout=3.0, min_confidence=0.55)

    assert result.letter == "N"
    assert activity == [True, False]


def test_chunk_priority_dung_beats_higher_confidence_false() -> None:
    class Recognizer:
        def __init__(self) -> None:
            self.rows = [
                {
                    "prediction": "FALSE",
                    "detail": "SAI",
                    "confidence": 0.90,
                    "reliable": True,
                    "acceptance_threshold": 0.55,
                },
                {
                    "prediction": "TRUE",
                    "detail": "DUNG",
                    "confidence": 0.41,
                    "reliable": True,
                    "acceptance_threshold": 0.40,
                },
            ]

        def predict(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return self.rows.pop(0)

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = Recognizer()
    bridge.min_margin = 0.05
    bridge.confirm_dung_priority_threshold = 0.40
    bridge._record_device_chunk = lambda _timeout, **_kwargs: ([np.ones(8)], 16000)
    bridge._split_vad_segments = lambda _chunks, samplerate: [np.ones(8), np.ones(8)]
    bridge.inference_activity_callback = None

    result = bridge.listen_chunk(
        timeout=3.0,
        min_confidence=0.55,
        head="three_labels",
    )

    assert result.letter == "TRUE"
    assert result.raw == "DUNG"
    assert result.confidence == 0.41


def test_chunk_accepts_confidence_at_lower_band_boundary() -> None:
    class Recognizer:
        def predict(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return {"prediction": "O", "confidence": 0.55, "reliable": True}

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = Recognizer()
    bridge.min_margin = 0.05
    bridge._record_device_chunk = lambda _timeout, **_kwargs: ([np.ones(8)], 16000)
    bridge._split_vad_segments = lambda _chunks, samplerate: [np.ones(8)]

    result = bridge.listen_chunk(timeout=3.0, min_confidence=0.55)

    assert result.reliable is True
    assert result.letter == "O"


def test_chunk_preserves_rejected_segment_confidence_for_policy_band() -> None:
    class Recognizer:
        def predict(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return {
                "prediction": "[UNK]",
                "detail": "K",
                "confidence": 0.60,
                "reliable": False,
            }

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = Recognizer()
    bridge.min_margin = 0.05
    bridge._record_device_chunk = lambda _timeout, **_kwargs: ([np.ones(8)], 16000)
    bridge._split_vad_segments = lambda _chunks, samplerate: [np.ones(8)]

    result = bridge.listen_chunk(timeout=3.0, min_confidence=0.45)

    assert result.reliable is False
    assert result.confidence == 0.60
    assert result.raw == "K"


def test_chunk_discards_speaker_playback_prefix_before_vad() -> None:
    class Recognizer:
        def predict(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return {"prediction": "TRUE", "confidence": 0.80, "reliable": True}

    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = Recognizer()
    bridge.min_margin = 0.05
    bridge.inference_activity_callback = None
    bridge._record_device_chunk = lambda _timeout, **_kwargs: (
        [np.arange(0, 4), np.arange(4, 8), np.arange(8, 12)],
        4,
    )
    captured: list[np.ndarray] = []

    def split(chunks, *, samplerate):  # noqa: ANN001
        assert samplerate == 4
        captured.extend(chunks)
        return [np.concatenate(chunks)]

    bridge._split_vad_segments = split

    result = bridge.listen_chunk(
        timeout=4.5,
        min_confidence=0.55,
        head="three_labels",
        ignore_initial_seconds=1.5,
    )

    assert result.letter == "TRUE"
    assert np.array_equal(np.concatenate(captured), np.arange(6, 12))


def test_chunk_honors_cancel_before_inference() -> None:
    bridge = SloanSttBridge.__new__(SloanSttBridge)
    bridge.mic_hub = SimpleNamespace(audio_input="device")
    bridge._recognizer = SimpleNamespace()
    bridge._record_device_chunk = lambda _timeout, **_kwargs: ([np.ones(8)], 16000)
    stop = threading.Event()
    stop.set()

    result = bridge.listen_chunk(timeout=3.0, stop_flag=stop)

    assert result.raw == "cancelled"
