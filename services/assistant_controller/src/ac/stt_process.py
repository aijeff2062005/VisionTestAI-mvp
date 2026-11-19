"""Sloan STT worker process — runs ONNX inference off the AC/CV GIL.

Parent records mic audio; this child only loads Recognizer and predicts so
SmartEyes YOLO and Sloan encoder can use separate OS processes / cores.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _worker_main(sloan_root: str, request_q: Any, response_q: Any) -> None:
    """Entry point for the STT child process (spawn-safe)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [stt-worker] %(message)s",
    )
    root = Path(sloan_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        import numpy as np
        from runtime import Recognizer  # type: ignore
    except Exception as exc:  # noqa: BLE001
        response_q.put({"type": "fatal", "error": f"STT worker import failed: {exc}"})
        return

    try:
        recognizer = Recognizer(enabled_heads=("sloan",))
    except Exception as exc:  # noqa: BLE001
        response_q.put({"type": "fatal", "error": f"STT worker Recognizer failed: {exc}"})
        return

    response_q.put({"type": "ready"})
    logger.info("STT worker ready root=%s", root)

    while True:
        try:
            job = request_q.get()
        except (EOFError, KeyboardInterrupt):
            break
        if job is None:
            break
        cmd = str(job.get("cmd") or "")
        if cmd == "stop":
            break
        if cmd != "predict":
            response_q.put(
                {
                    "type": "result",
                    "id": job.get("id"),
                    "ok": False,
                    "error": f"unknown cmd {cmd}",
                }
            )
            continue
        try:
            audio = np.frombuffer(job["audio"], dtype=np.float32).copy()
            sr = int(job.get("sample_rate") or 16000)
            pred = recognizer.predict(
                audio,
                sr,
                min_confidence=float(job.get("min_confidence") or 0.55),
                min_margin=float(job.get("min_margin") or 0.05),
                head=str(job.get("head") or "sloan"),
            )
            response_q.put(
                {
                    "type": "result",
                    "id": job.get("id"),
                    "ok": True,
                    "pred": pred,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("STT worker predict failed")
            response_q.put(
                {
                    "type": "result",
                    "id": job.get("id"),
                    "ok": False,
                    "error": str(exc),
                }
            )


class SloanSttProcess:
    """Persistent spawn-process wrapper around Sloan Recognizer.predict."""

    def __init__(self, sloan_root: Path, *, ready_timeout: float = 120.0) -> None:
        self.sloan_root = Path(sloan_root)
        self.ready_timeout = float(ready_timeout)
        self._ctx = mp.get_context("spawn")
        self._request_q: Any = None
        self._response_q: Any = None
        self._proc: Any = None
        self._thread_lock = threading.RLock()
        self._ready = False
        self._fatal: str | None = None

    @property
    def available(self) -> bool:
        return bool(self._ready and self._proc is not None and self._proc.is_alive())

    def start(self) -> None:
        with self._thread_lock:
            if self.available:
                return
            self._stop_unlocked()
            self._request_q = self._ctx.Queue()
            self._response_q = self._ctx.Queue()
            self._proc = self._ctx.Process(
                target=_worker_main,
                args=(str(self.sloan_root), self._request_q, self._response_q),
                name="sloan-stt-worker",
                daemon=True,
            )
            self._proc.start()
            deadline = time.monotonic() + self.ready_timeout
            while time.monotonic() < deadline:
                try:
                    msg = self._response_q.get(timeout=1.0)
                except Exception:  # noqa: BLE001
                    if self._proc is not None and not self._proc.is_alive():
                        self._fatal = "STT worker exited before ready"
                        break
                    continue
                kind = str(msg.get("type") or "")
                if kind == "ready":
                    self._ready = True
                    self._fatal = None
                    logger.info(
                        "Sloan STT worker pid=%s ready",
                        getattr(self._proc, "pid", None),
                    )
                    return
                if kind == "fatal":
                    self._fatal = str(msg.get("error") or "STT worker fatal")
                    logger.error("%s", self._fatal)
                    self._stop_unlocked()
                    return
            if not self._ready:
                self._fatal = self._fatal or "STT worker ready timeout"
                logger.error("%s", self._fatal)
                self._stop_unlocked()

    def predict(
        self,
        mono: Any,
        sample_rate: int,
        *,
        min_confidence: float,
        min_margin: float,
        head: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        import numpy as np

        self.start()
        if not self.available:
            raise RuntimeError(self._fatal or "STT worker not available")
        audio = np.asarray(mono, dtype=np.float32).reshape(-1)
        job_id = uuid.uuid4().hex
        job = {
            "cmd": "predict",
            "id": job_id,
            "audio": audio.tobytes(order="C"),
            "sample_rate": int(sample_rate),
            "min_confidence": float(min_confidence),
            "min_margin": float(min_margin),
            "head": str(head),
        }
        with self._thread_lock:
            assert self._request_q is not None and self._response_q is not None
            self._request_q.put(job)
            deadline = time.monotonic() + max(5.0, float(timeout))
            while time.monotonic() < deadline:
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    msg = self._response_q.get(timeout=min(1.0, remaining))
                except Exception:  # noqa: BLE001
                    if self._proc is not None and not self._proc.is_alive():
                        self._ready = False
                        raise RuntimeError("STT worker died during predict")
                    continue
                if str(msg.get("type") or "") != "result":
                    continue
                if msg.get("id") != job_id:
                    continue
                if not msg.get("ok"):
                    raise RuntimeError(str(msg.get("error") or "STT predict failed"))
                pred = msg.get("pred")
                if not isinstance(pred, dict):
                    raise RuntimeError("STT worker returned bad pred")
                return pred
        raise TimeoutError("STT worker predict timeout")

    def close(self) -> None:
        with self._thread_lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._ready = False
        proc = self._proc
        req = self._request_q
        self._proc = None
        self._request_q = None
        self._response_q = None
        if req is not None:
            try:
                req.put({"cmd": "stop"})
            except Exception:  # noqa: BLE001
                pass
            try:
                req.put(None)
            except Exception:  # noqa: BLE001
                pass
        if proc is not None and proc.is_alive():
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
