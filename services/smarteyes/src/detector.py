from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from ultralytics import YOLO

from src.device_utils import resolve_torch_device


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    class_id: int


class YOLODetector:
    """Ultralytics YOLO wrapper for person detection."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        model_cfg = cfg["model"]
        self.model = YOLO(model_cfg["weights"])
        self.conf = float(model_cfg["conf_threshold"])
        self.iou = float(model_cfg["iou_threshold"])
        self.person_class_id = int(model_cfg["person_class_id"])
        self.imgsz = int(model_cfg["imgsz"])
        self.device = resolve_torch_device(cfg)
        print(f"YOLO person detector device: {self.device}")

    def detect(
        self,
        frame: np.ndarray,
        *,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[Detection]:
        """
        Run person YOLO on full frame or an ROI crop.

        When ``roi=(x0,y0,x1,y1)`` is set, boxes are remapped to full-frame coords.
        """
        ox = oy = 0
        crop = frame
        if roi is not None:
            x0, y0, x1, y1 = roi
            h, w = frame.shape[:2]
            x0 = int(max(0, min(w - 1, x0)))
            y0 = int(max(0, min(h - 1, y0)))
            x1 = int(max(0, min(w, x1)))
            y1 = int(max(0, min(h, y1)))
            if x1 <= x0 or y1 <= y0:
                return []
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0:
                return []
            ox, oy = x0, y0

        results = self.model.predict(
            crop,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            classes=[self.person_class_id],
            verbose=False,
            device=self.device,
        )
        detections: list[Detection] = []
        if not results:
            return detections

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return detections

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)

        h, w = frame.shape[:2]
        ch, cw = crop.shape[:2]
        for (x1, y1, x2, y2), conf, cls_id in zip(xyxy, confs, cls_ids):
            x1_i = int(max(0, min(cw - 1, x1))) + ox
            y1_i = int(max(0, min(ch - 1, y1))) + oy
            x2_i = int(max(0, min(cw - 1, x2))) + ox
            y2_i = int(max(0, min(ch - 1, y2))) + oy
            x1_i = int(max(0, min(w - 1, x1_i)))
            y1_i = int(max(0, min(h - 1, y1_i)))
            x2_i = int(max(0, min(w - 1, x2_i)))
            y2_i = int(max(0, min(h - 1, y2_i)))
            if x2_i <= x1_i or y2_i <= y1_i:
                continue
            detections.append(
                Detection(
                    bbox=(x1_i, y1_i, x2_i, y2_i),
                    confidence=float(conf),
                    class_id=int(cls_id),
                )
            )
        return detections
