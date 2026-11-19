"""MediaPipe Pose — full-body landmarks for ankle / stance checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

try:
    import mediapipe as mp

    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None
    MEDIAPIPE_AVAILABLE = False

# MediaPipe Pose landmark indices
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32
NOSE = 0
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_ELBOW = 13
RIGHT_ELBOW = 14


@dataclass
class BodyPose:
    landmarks: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    left_ankle: tuple[int, int] | None = None
    right_ankle: tuple[int, int] | None = None
    ankle_midpoint: tuple[int, int] | None = None
    left_ear: tuple[int, int] | None = None
    right_ear: tuple[int, int] | None = None
    nose: tuple[int, int] | None = None
    left_wrist: tuple[int, int] | None = None
    right_wrist: tuple[int, int] | None = None
    head_bbox: tuple[int, int, int, int] | None = None
    visible: bool = False


class BodyPoseEstimator:
    """MediaPipe Pose on person crop (or full frame)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        pose_cfg = cfg.get("pose", {})
        self.expand_ratio = float(pose_cfg.get("bbox_expand_ratio", 0.1))
        self.mp_pose = None
        if MEDIAPIPE_AVAILABLE:
            self.mp_pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=int(pose_cfg.get("model_complexity", 1)),
                enable_segmentation=False,
                min_detection_confidence=float(
                    pose_cfg.get("min_detection_confidence", 0.5)
                ),
                min_tracking_confidence=float(
                    pose_cfg.get("min_tracking_confidence", 0.5)
                ),
            )

    def close(self) -> None:
        if self.mp_pose is not None:
            self.mp_pose.close()

    @staticmethod
    def _expand_bbox(
        bbox: tuple[int, int, int, int],
        frame_shape: tuple[int, int],
        ratio: float,
    ) -> tuple[int, int, int, int]:
        h, w = frame_shape
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        pad_x = int(bw * ratio)
        pad_y = int(bh * ratio)
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(w - 1, x2 + pad_x),
            min(h - 1, y2 + pad_y),
        )

    def estimate(
        self,
        frame: np.ndarray,
        person_bbox: tuple[int, int, int, int] | None = None,
    ) -> BodyPose:
        if self.mp_pose is None:
            return BodyPose()

        h, w = frame.shape[:2]
        ox, oy = 0, 0
        crop = frame
        if person_bbox is not None:
            x1, y1, x2, y2 = self._expand_bbox(person_bbox, (h, w), self.expand_ratio)
            crop = frame[y1:y2, x1:x2]
            ox, oy = x1, y1
            if crop.size == 0:
                return BodyPose()

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        result = self.mp_pose.process(rgb)
        if not result.pose_landmarks:
            return BodyPose()

        ch, cw = crop.shape[:2]
        landmarks: dict[int, tuple[float, float, float]] = {}
        for idx, lm in enumerate(result.pose_landmarks.landmark):
            px = ox + lm.x * cw
            py = oy + lm.y * ch
            landmarks[idx] = (px, py, lm.visibility)

        def _pt(idx: int, min_vis: float = 0.3) -> tuple[int, int] | None:
            if idx not in landmarks:
                return None
            x, y, vis = landmarks[idx]
            if vis < min_vis:
                return None
            return (int(x), int(y))

        left = _pt(LEFT_ANKLE) or _pt(LEFT_HEEL) or _pt(LEFT_FOOT_INDEX)
        right = _pt(RIGHT_ANKLE) or _pt(RIGHT_HEEL) or _pt(RIGHT_FOOT_INDEX)
        mid = None
        if left and right:
            mid = ((left[0] + right[0]) // 2, (left[1] + right[1]) // 2)
        elif left:
            mid = left
        elif right:
            mid = right

        head_bbox = self._head_bbox_from_landmarks(landmarks, w, h)

        return BodyPose(
            landmarks=landmarks,
            left_ankle=left,
            right_ankle=right,
            ankle_midpoint=mid,
            left_ear=_pt(LEFT_EAR, min_vis=0.2),
            right_ear=_pt(RIGHT_EAR, min_vis=0.2),
            nose=_pt(NOSE, min_vis=0.2),
            left_wrist=_pt(LEFT_WRIST, min_vis=0.25),
            right_wrist=_pt(RIGHT_WRIST, min_vis=0.25),
            head_bbox=head_bbox,
            visible=True,
        )

    @staticmethod
    def _head_bbox_from_landmarks(
        landmarks: dict[int, tuple[float, float, float]],
        frame_w: int,
        frame_h: int,
    ) -> tuple[int, int, int, int] | None:
        head_ids = [NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER]
        pts = []
        for i in head_ids:
            if i in landmarks and landmarks[i][2] >= 0.2:
                pts.append((landmarks[i][0], landmarks[i][1]))
        if len(pts) < 2:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # Expand upward from shoulders to cover headphones
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max(max_x - min_x, 40)
        height = max(max_y - min_y, 40)
        pad_x = width * 0.55
        pad_y_top = height * 0.9
        pad_y_bot = height * 0.35
        x1 = int(max(0, min_x - pad_x))
        y1 = int(max(0, min_y - pad_y_top))
        x2 = int(min(frame_w - 1, max_x + pad_x))
        y2 = int(min(frame_h - 1, max_y + pad_y_bot))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2)


# Pose connections for overlay (subset)
POSE_EDGES = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
    (27, 29),
    (28, 30),
    (27, 31),
    (28, 32),
]
