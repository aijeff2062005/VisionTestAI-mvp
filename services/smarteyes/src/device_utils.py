"""Shared inference device helpers for Jetson / desktop."""

from __future__ import annotations

from typing import Any


def resolve_torch_device(cfg: dict[str, Any] | None = None) -> str | int:
    """Pick Ultralytics/torch device from config.

    Config keys (first match wins):
      model.device / headphones.device / device: "cuda" | "0" | 0 | "cpu" | "auto"
    Default: auto → cuda:0 if available else cpu.
    """
    raw: Any = None
    if cfg:
        for section in ("model", "headphones", "spell"):
            block = cfg.get(section) or {}
            if isinstance(block, dict) and block.get("device") is not None:
                raw = block.get("device")
                break
        if raw is None:
            raw = cfg.get("device")
    if raw is None or str(raw).strip().lower() in ("", "auto"):
        try:
            import torch

            if torch.cuda.is_available():
                return 0
        except Exception:
            pass
        return "cpu"
    text = str(raw).strip().lower()
    if text in ("cpu", "mps"):
        return text
    if text in ("cuda", "gpu"):
        return 0
    if text.isdigit():
        return int(text)
    return raw


def ort_providers(prefer_gpu: bool = True) -> list[str]:
    """ONNX Runtime provider list: CUDA → CPU (TensorRT opt-in via SLOAN_ORT_TRT=1)."""
    import os

    try:
        import onnxruntime as ort

        available = set(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]
    if not prefer_gpu:
        return ["CPUExecutionProvider"]
    ordered: list[str] = []
    if os.environ.get("SLOAN_ORT_TRT", "").strip() in ("1", "true", "yes"):
        ordered.append("TensorrtExecutionProvider")
    ordered.extend(["CUDAExecutionProvider", "CPUExecutionProvider"])
    return [p for p in ordered if p in available] or ["CPUExecutionProvider"]
