"""Closed-set headphone detection — worn on ears, not hand-held."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ultralytics import YOLO
from src.device_utils import resolve_torch_device


@dataclass
class HeadphoneDetection:
    bbox: tuple[int, int, int, int]
    confidence: float
    label: str
    on_head: bool = False
    near_left_ear: bool = False
    near_right_ear: bool = False
    # False when held-in-front / hanging (excluded from cup-pair aggregation)
    wear_candidate: bool = True


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _expand_bbox(
    bbox: tuple[int, int, int, int],
    frame_shape: tuple[int, int],
    ratio: float,
    *,
    extra_top: float = 0.0,
) -> tuple[int, int, int, int]:
    h, w = frame_shape
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    pad_x = int(bw * ratio)
    pad_y = int(bh * ratio)
    pad_top = pad_y + int(bh * extra_top)
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_top),
        min(w - 1, x2 + pad_x),
        min(h - 1, y2 + pad_y),
    )


def _head_roi_from_person(
    person_bbox: tuple[int, int, int, int],
    frame_shape: tuple[int, int],
    expand_ratio: float,
) -> tuple[int, int, int, int]:
    h, w = frame_shape
    x1, y1, x2, y2 = person_bbox
    bh = y2 - y1
    # Taller head band — fluffy hair / cups sit above shoulders
    head = (x1, y1, x2, y1 + max(int(bh * 0.42), 48))
    return _expand_bbox(head, (h, w), expand_ratio, extra_top=0.35)


def _ear_band(
    ear: tuple[int, int] | None,
    head_bbox: tuple[int, int, int, int],
    radius_px: int,
    *,
    side: str,
) -> tuple[int, int, int, int]:
    """Band around an ear landmark, or left/right third of the head as fallback."""
    hx1, hy1, hx2, hy2 = head_bbox
    hw = max(hx2 - hx1, 1)
    hh = max(hy2 - hy1, 1)
    if ear is not None:
        ex, ey = ear
        # Tall band: fluffy hair often sits above the ear landmark / cups
        r = max(radius_px, int(min(hw, hh) * 0.28))
        return (ex - r, ey - int(r * 1.35), ex + r, ey + int(r * 1.15))
    mid_y = (hy1 + hy2) // 2
    third = max(hw // 3, 36)
    if side == "left":
        return (hx1 - 8, hy1, hx1 + third + 12, mid_y + hh // 3)
    return (hx2 - third - 12, hy1, hx2 + 8, mid_y + hh // 3)


def _point_in_bbox(
    pt: tuple[int, int], bbox: tuple[int, int, int, int], pad: int = 0
) -> bool:
    x, y = pt
    x1, y1, x2, y2 = bbox
    return (x1 - pad) <= x <= (x2 + pad) and (y1 - pad) <= y <= (y2 + pad)


def _face_center_box(head_bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    hx1, hy1, hx2, hy2 = head_bbox
    hw, hh = max(hx2 - hx1, 1), max(hy2 - hy1, 1)
    return (
        hx1 + int(hw * 0.30),
        hy1 + int(hh * 0.25),
        hx2 - int(hw * 0.30),
        hy1 + int(hh * 0.78),
    )


def _hands_holding(
    bbox: tuple[int, int, int, int],
    left_wrist: tuple[int, int] | None,
    right_wrist: tuple[int, int] | None,
    pad_px: int,
) -> bool:
    for wrist in (left_wrist, right_wrist):
        if wrist is not None and _point_in_bbox(wrist, bbox, pad=pad_px):
            return True
    return False


def _score_detection(
    bbox: tuple[int, int, int, int],
    *,
    head_bbox: tuple[int, int, int, int],
    left_ear: tuple[int, int] | None,
    right_ear: tuple[int, int] | None,
    nose: tuple[int, int] | None,
    left_wrist: tuple[int, int] | None,
    right_wrist: tuple[int, int] | None,
    left_band: tuple[int, int, int, int],
    right_band: tuple[int, int, int, int],
    head_iou_min: float,
    vertical_head_frac: float,
    max_below_head_frac: float,
    wrist_pad_px: int,
    require_center_in_head: bool = False,
    max_head_cover: float = 0.55,
) -> tuple[bool, bool, bool, bool]:
    """Return (wear_candidate, near_left, near_right, wraps_both_ears)."""
    hx1, hy1, hx2, hy2 = head_bbox
    hw = max(hx2 - hx1, 1)
    hh = max(hy2 - hy1, 1)
    head_area = float(hw * hh)
    bw = max(bbox[2] - bbox[0], 1)
    bh = max(bbox[3] - bbox[1], 1)
    box_area = float(bw * bh)
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2

    inside = hx1 <= cx <= hx2 and hy1 <= cy <= hy2
    overlap = _iou(bbox, head_bbox) >= head_iou_min
    if require_center_in_head and not inside:
        return False, False, False, False
    if not (inside or overlap):
        return False, False, False, False

    # Whole-head / chair-sized blob: covers too much of the head → not a cup
    if box_area > max_head_cover * head_area or _iou(bbox, head_bbox) > 0.50:
        return False, False, False, False

    below = max(0, bbox[3] - hy2)
    hanging = below > max_below_head_frac * hh
    hands = _hands_holding(bbox, left_wrist, right_wrist, wrist_pad_px)
    top_low = bbox[1] > hy1 + int(hh * vertical_head_frac)

    face_iou = _iou(bbox, _face_center_box(head_bbox))
    nose_in = nose is not None and _point_in_bbox(nose, bbox, pad=0)
    held_front = hands or (hanging and face_iou >= 0.35 and nose_in)

    if held_front or (top_low and hanging):
        return False, False, False, False

    near_left = (
        _iou(bbox, left_band) > 0.02
        or _point_in_bbox((cx, cy), left_band, pad=10)
        or (left_ear is not None and _point_in_bbox(left_ear, bbox, pad=20))
    )
    near_right = (
        _iou(bbox, right_band) > 0.02
        or _point_in_bbox((cx, cy), right_band, pad=10)
        or (right_ear is not None and _point_in_bbox(right_ear, bbox, pad=20))
    )
    # Side-of-head fallback only when already inside head (never for floor/chair)
    if inside:
        near_left = near_left or (
            cx <= hx1 + hw * 0.42 and hy1 <= cy <= hy1 + int(hh * 0.85)
        )
        near_right = near_right or (
            cx >= hx1 + hw * 0.58 and hy1 <= cy <= hy1 + int(hh * 0.85)
        )

    wraps_both = near_left and near_right
    wear_candidate = not held_front and not (hanging and not wraps_both)
    return wear_candidate, near_left, near_right, wraps_both


class HeadphoneChecker:
    """Detect headphones and verify they sit on the head near the ears."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        hp = cfg.get("headphones", {})
        self.backend = str(hp.get("backend", "yolo"))
        self.conf = float(hp.get("conf_threshold", 0.08))
        self.imgsz = int(hp.get("imgsz", 640))
        self.device = resolve_torch_device({"headphones": hp, **({"device": cfg.get("device")} if isinstance(cfg, dict) else {})})
        self.head_iou_min = float(hp.get("head_iou_min", 0.04))
        self.head_expand_ratio = float(hp.get("head_expand_ratio", 0.45))
        self.require_on_head = bool(hp.get("require_on_head", True))
        self.ear_radius_px = int(hp.get("ear_radius_px", 56))
        self.vertical_head_frac = float(hp.get("vertical_head_frac", 0.75))
        self.max_below_head_frac = float(hp.get("max_below_head_frac", 0.32))
        self.wrist_pad_px = int(hp.get("wrist_pad_px", 28))
        # Fluffy hair may hide one cup — allow a strong single-side hit
        self.allow_single_ear = bool(hp.get("allow_single_ear", True))
        self.single_ear_conf_min = float(hp.get("single_ear_conf_min", 0.18))
        self.crop_to_head = bool(hp.get("crop_to_head", True))
        # Closed-set: don't accept floor/chair boxes from full-frame fallback
        self.full_frame_fallback = bool(hp.get("full_frame_fallback", True))
        self.require_center_in_head = bool(hp.get("require_center_in_head", False))
        self.max_head_cover = float(hp.get("max_head_cover", 0.55))
        if self.backend in ("yolo", "closed_set", "yolov8"):
            # Safer defaults for weak closed-set weights
            if "full_frame_fallback" not in hp:
                self.full_frame_fallback = False
            if "require_center_in_head" not in hp:
                self.require_center_in_head = True
            if "max_head_cover" not in hp:
                self.max_head_cover = 0.42
        self.prompts = list(
            hp.get(
                "prompts",
                [
                    "headphones",
                    "headset",
                    "earphone",
                    "over-ear headphones",
                    "ear muffs",
                    "noise cancelling headphones",
                ],
            )
        )
        self.model = None
        self.enabled = bool((cfg.get("checks") or {}).get("headphones", True))
        self.class_names_accept = {
            str(n).lower()
            for n in hp.get("class_names", ["over_ear", "headphones", "headphone", "headset"])
        }
        if self.enabled:
            self._load_model(hp, cfg)

    def _load_model(self, hp: dict[str, Any], cfg: dict[str, Any]) -> None:
        weights = str(hp.get("weights", "yolov8s-world.pt"))
        # Resolve relative to SmartEyes project root
        wpath = Path(weights)
        if not wpath.is_absolute():
            root = Path(__file__).resolve().parents[1]
            cand = root / weights
            if cand.is_file():
                weights = str(cand)

        if self.backend in ("yolo", "closed_set", "yolov8"):
            # Production uses only the local closed-set detector; there is no
            # open-vocabulary/CLIP fallback.
            cs = hp.get("closed_set_weights")
            if cs and (
                "world" in Path(weights).name.lower()
                or not Path(weights).is_file()
            ):
                cand = Path(cs)
                if not cand.is_absolute():
                    cand = Path(__file__).resolve().parents[1] / cs
                if cand.is_file():
                    weights = str(cand)

            if not Path(weights).is_file():
                print(
                    f"Headphones closed-set weights missing ({weights}); "
                    "headphones check disabled. Train via scripts/train_headphones_yolo.py"
                )
                self.model = None
                self.enabled = False
                return

            self.model = YOLO(weights)
            return

        print(f"Unknown headphones.backend={self.backend!r}; headphones disabled")
        self.model = None
        self.enabled = False

    def detect_near_head(
        self,
        frame: np.ndarray,
        person_bbox: tuple[int, int, int, int] | None,
        head_bbox: tuple[int, int, int, int] | None = None,
        left_ear: tuple[int, int] | None = None,
        right_ear: tuple[int, int] | None = None,
        nose: tuple[int, int] | None = None,
        left_wrist: tuple[int, int] | None = None,
        right_wrist: tuple[int, int] | None = None,
    ) -> list[HeadphoneDetection]:
        if self.model is None or person_bbox is None:
            return []

        h, w = frame.shape[:2]
        if head_bbox is None:
            head_bbox = _head_roi_from_person(
                person_bbox, (h, w), self.head_expand_ratio
            )
        else:
            head_bbox = _expand_bbox(
                head_bbox, (h, w), self.head_expand_ratio, extra_top=0.40
            )

        # Crop to head so small / hair-covered cups fill more of the tensor
        ox, oy = 0, 0
        infer = frame
        if self.crop_to_head:
            hx1, hy1, hx2, hy2 = head_bbox
            crop = frame[hy1 : hy2 + 1, hx1 : hx2 + 1]
            if crop.size > 0 and crop.shape[0] >= 32 and crop.shape[1] >= 32:
                infer = crop
                ox, oy = hx1, hy1

        found = self._predict_boxes(
            infer,
            ox=ox,
            oy=oy,
            frame_hw=(h, w),
            head_bbox=head_bbox,
            left_ear=left_ear,
            right_ear=right_ear,
            nose=nose,
            left_wrist=left_wrist,
            right_wrist=right_wrist,
        )
        # Hair / odd crop: retry full frame if head crop missed (World only by default)
        if (
            not found
            and self.crop_to_head
            and self.full_frame_fallback
            and infer is not frame
        ):
            found = self._predict_boxes(
                frame,
                ox=0,
                oy=0,
                frame_hw=(h, w),
                head_bbox=head_bbox,
                left_ear=left_ear,
                right_ear=right_ear,
                nose=nose,
                left_wrist=left_wrist,
                right_wrist=right_wrist,
            )

        # Do NOT promote unrelated boxes to ON HEAD just because one cup passed
        return found

    def _predict_boxes(
        self,
        infer: np.ndarray,
        *,
        ox: int,
        oy: int,
        frame_hw: tuple[int, int],
        head_bbox: tuple[int, int, int, int],
        left_ear: tuple[int, int] | None,
        right_ear: tuple[int, int] | None,
        nose: tuple[int, int] | None,
        left_wrist: tuple[int, int] | None,
        right_wrist: tuple[int, int] | None,
    ) -> list[HeadphoneDetection]:
        h, w = frame_hw
        results = self.model.predict(
            infer,
            conf=self.conf,
            imgsz=self.imgsz,
            verbose=False,
            device=getattr(self, "device", "cpu"),
        )
        found: list[HeadphoneDetection] = []
        if not results:
            return found

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return found

        names = results[0].names or {}
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)

        left_band = _ear_band(
            left_ear, head_bbox, self.ear_radius_px, side="left"
        )
        right_band = _ear_band(
            right_ear, head_bbox, self.ear_radius_px, side="right"
        )

        for (x1, y1, x2, y2), conf, cls_id in zip(xyxy, confs, cls_ids):
            label = str(
                names.get(
                    int(cls_id), self.prompts[0] if self.prompts else "headphones"
                )
            )
            if self.backend in ("yolo", "closed_set", "yolov8"):
                lab = label.lower()
                if lab not in self.class_names_accept and int(cls_id) != 0:
                    continue
            bbox = (
                int(max(0, min(w - 1, x1 + ox))),
                int(max(0, min(h - 1, y1 + oy))),
                int(max(0, min(w - 1, x2 + ox))),
                int(max(0, min(h - 1, y2 + oy))),
            )
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue

            wear_cand, near_left, near_right, wraps = _score_detection(
                bbox,
                head_bbox=head_bbox,
                left_ear=left_ear,
                right_ear=right_ear,
                nose=nose,
                left_wrist=left_wrist,
                right_wrist=right_wrist,
                left_band=left_band,
                right_band=right_band,
                head_iou_min=self.head_iou_min,
                vertical_head_frac=self.vertical_head_frac,
                max_below_head_frac=self.max_below_head_frac,
                wrist_pad_px=self.wrist_pad_px,
                require_center_in_head=self.require_center_in_head,
                max_head_cover=self.max_head_cover,
            )
            on_head = bool(wear_cand and wraps)
            if (
                not on_head
                and wear_cand
                and self.allow_single_ear
                and float(conf) >= self.single_ear_conf_min
                and (near_left or near_right)
            ):
                on_head = True
            found.append(
                HeadphoneDetection(
                    bbox=bbox,
                    confidence=float(conf),
                    label=label,
                    on_head=on_head,
                    near_left_ear=near_left and wear_cand,
                    near_right_ear=near_right and wear_cand,
                    wear_candidate=wear_cand,
                )
            )
        return found

    def worn_ok(self, detections: list[HeadphoneDetection]) -> bool:
        if not detections:
            return False
        if not self.require_on_head:
            return any(True for _ in detections)
        # Only boxes that individually scored on_head (ear proximity + size gates).
        # Do NOT treat "near ear OR chair FP" as worn via loose aggregation.
        return any(d.on_head and d.wear_candidate for d in detections)
