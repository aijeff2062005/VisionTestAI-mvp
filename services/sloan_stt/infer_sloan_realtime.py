#!/usr/bin/env python3
import argparse
import json
import queue
import sys
import threading

import numpy as np
import sounddevice as sd
from scipy.signal import butter, sosfilt

from runtime import Recognizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None)
    parser.add_argument("--min-confidence", type=float, default=.55)
    parser.add_argument("--min-margin", type=float, default=.05)
    parser.add_argument("--head", choices=["sloan", "three_labels", "both"],
                        default="sloan")

    # These defaults mirror the microphone frontend in web/index.html.
    parser.add_argument("--energy-threshold", type=float, default=.004,
                        help="Minimum adaptive VAD threshold")
    parser.add_argument("--noise-multiplier", type=float, default=2.2)
    parser.add_argument("--silence-duration", type=float, default=.14)
    parser.add_argument("--min-audio-seconds", type=float, default=.16)
    parser.add_argument("--min-voiced-chunks", type=int, default=3)
    parser.add_argument("--min-voiced-ratio", type=float, default=.35)
    parser.add_argument("--max-active-seconds", type=float, default=2.8)
    parser.add_argument("--input-gain", type=float, default=1.2)
    parser.add_argument("--block-size", type=int, default=2048)
    parser.add_argument("--debug-vad", action="store_true")
    return parser.parse_args()


def microphone_filter(sample_rate):
    """Match the browser's 80 Hz high-pass and 3400 Hz low-pass filters."""
    highpass = butter(2, 80.0, btype="highpass", fs=sample_rate, output="sos")
    lowpass_limit = min(3400.0, sample_rate * .45)
    lowpass = butter(2, lowpass_limit, btype="lowpass", fs=sample_rate, output="sos")
    return np.concatenate([highpass, lowpass], axis=0)


def main():
    args = parse_args()
    device = int(args.device) if str(args.device).isdigit() else args.device
    info = sd.query_devices(device, "input")
    rate = int(round(info["default_samplerate"]))

    model = Recognizer()
    chunks = queue.Queue(maxsize=300)
    jobs = queue.Queue(maxsize=32)
    stopping = threading.Event()
    sequence = []

    def callback(indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        try:
            chunks.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def worker():
        while not stopping.is_set() or not jobs.empty():
            try:
                audio = jobs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                result = model.predict(
                    audio, rate, args.min_confidence, args.min_margin,
                    head=args.head,
                )
                if args.head == "both":
                    sequence.append(result["sloan"]["prediction"])
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    sequence.append(result["prediction"])
                    top = " ".join(
                        f"{item['label']}:{item['confidence']:.3f}"
                        for item in result["topk"]
                    )
                    print(
                        f"segment={len(sequence)} raw={result['raw']} "
                        f"prediction={result['prediction']} "
                        f"confidence={result['confidence']:.3f} "
                        f"margin={result['margin']:.3f} topk=[{top}]"
                    )
                print(f"sequence={' '.join(sequence)}")
            except Exception as exc:
                print(f"recognition_error={type(exc).__name__}: {exc}", file=sys.stderr)
            finally:
                jobs.task_done()

    threading.Thread(target=worker, daemon=True).start()

    # The browser starts from this noise-floor estimate and updates it only
    # while no utterance is active.
    noise_floor = .0025
    onset_chunks = 0
    voiced_chunks = 0
    total_chunks = 0
    active_samples = 0
    silence_samples = 0
    active = False
    buffers = []
    pre = []

    sos = microphone_filter(rate)
    filter_state = np.zeros((sos.shape[0], 2), dtype=np.float64)

    print(
        f"Realtime ready | head={args.head} | mic={info['name']} | rate={rate} "
        f"| block={args.block_size} | Ctrl+C to stop"
    )
    try:
        with sd.InputStream(
            device=device, samplerate=rate, channels=1, dtype="float32",
            blocksize=args.block_size, callback=callback,
        ):
            while True:
                raw = chunks.get()
                filtered, filter_state = sosfilt(sos, raw, zi=filter_state)
                chunk = (filtered * args.input_gain).astype(np.float32)
                rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-10))
                gate = max(args.energy_threshold, noise_floor * args.noise_multiplier)

                if not active:
                    if rms < gate:
                        noise_floor = noise_floor * .95 + rms * .05
                    pre = (pre + [chunk])[-3:]
                    onset_chunks = onset_chunks + 1 if rms >= gate else 0

                    if onset_chunks >= 2:
                        active = True
                        buffers = list(pre)
                        silence_samples = 0
                        active_samples = sum(item.size for item in buffers)
                        voiced_chunks = onset_chunks
                        total_chunks = len(pre)
                else:
                    buffers.append(chunk)
                    active_samples += chunk.size
                    total_chunks += 1
                    if rms >= gate:
                        voiced_chunks += 1
                        silence_samples = 0
                    else:
                        silence_samples += chunk.size

                    should_finish = (
                        silence_samples >= rate * args.silence_duration
                        or active_samples >= rate * args.max_active_seconds
                    )
                    if should_finish:
                        audio = np.concatenate(buffers)
                        duration = audio.size / rate
                        voiced_ratio = voiced_chunks / max(1, total_chunks)

                        active = False
                        buffers = []
                        pre = []
                        silence_samples = 0
                        active_samples = 0
                        onset_chunks = 0
                        total_chunks = 0

                        accepted = (
                            duration >= args.min_audio_seconds
                            and voiced_chunks >= args.min_voiced_chunks
                            and voiced_ratio >= args.min_voiced_ratio
                        )
                        if accepted:
                            try:
                                jobs.put_nowait(audio)
                            except queue.Full:
                                print("recognition_queue_full: dropped segment", file=sys.stderr)
                        elif args.debug_vad:
                            print(
                                f"vad_rejected duration={duration:.3f}s "
                                f"voiced_chunks={voiced_chunks} "
                                f"voiced_ratio={voiced_ratio:.3f} "
                                f"rms={rms:.4f} gate={gate:.4f}"
                            )
                        voiced_chunks = 0

                if args.debug_vad:
                    state = "recording" if active else "waiting"
                    print(
                        f"\r{state} rms={rms:.4f} gate={gate:.4f} "
                        f"noise={noise_floor:.4f}",
                        end="", flush=True,
                    )
    except KeyboardInterrupt:
        if active and buffers:
            audio = np.concatenate(buffers)
            if audio.size / rate >= args.min_audio_seconds:
                jobs.put(audio)
        stopping.set()
        jobs.join()
        print("\nStopped")


if __name__ == "__main__":
    main()
