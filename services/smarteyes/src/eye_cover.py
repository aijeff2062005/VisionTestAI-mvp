"""Per-eye open / cover / partial-cover from MediaPipe Face Mesh.

Maps occlusion to vision-test side (screen L/R after mirror):
  left occluded  (cover or close) → under_test = RIGHT
  right occluded                  → under_test = LEFT
  neither                         → under_test = BOTH

Open East Asian eyes are not confused with lid skin. Hand cover is detected
from skin in the iris disc, not the full eyelid quad.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np

try:
    import mediapipe as mp

    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None
    MEDIAPIPE_AVAILABLE = False

# Face Mesh indices (MediaPipe mesh names; we re-order to screen L/R after)
MP_A_OUTER, MP_A_INNER, MP_A_IRIS = 33, 133, 468
MP_A_EAR_H = (33, 133)
MP_A_EAR_V = (159, 145, 158, 153)
MP_A_RIM = (469, 470, 471, 472)
MP_B_OUTER, MP_B_INNER, MP_B_IRIS = 263, 362, 473
MP_B_EAR_H = (263, 362)
MP_B_EAR_V = (386, 374, 385, 380)
MP_B_RIM = (474, 475, 476, 477)

# Midface skin reference (nose tip → chin), used to anchor occluder darkness
MP_NOSE_TIP = 1
MP_CHIN = 152

EYE_STATE_OPEN = "open"
EYE_STATE_CLOSED = "closed"
EYE_STATE_COVERED = "covered"
EYE_STATE_PARTIAL = "partial"
EYE_STATE_UNKNOWN = "unknown"

UNDER_TEST_LEFT = "LEFT"
UNDER_TEST_RIGHT = "RIGHT"
UNDER_TEST_BOTH = "BOTH"
UNDER_TEST_UNKNOWN = "UNKNOWN"

# Seeing = usable for vision test when the other eye is occluded
_SEEING = frozenset({EYE_STATE_OPEN, EYE_STATE_PARTIAL, EYE_STATE_UNKNOWN})


@dataclass
class EyeSideStatus:
    state: str = EYE_STATE_UNKNOWN
    ear: float | None = None
    iris_like: float = 0.0
    cover_score: float = 0.0
    iris_2d: tuple[int, int] | None = None
    # Fraction of the eye region darker than the midface skin reference.
    # Primary opaque-occluder (paddle/hand) signal at clinic distance where
    # the iris is only a few pixels wide.
    occluder_score: float = 0.0


@dataclass
class EyeCoverResult:
    left: EyeSideStatus
    right: EyeSideStatus
    under_test: str = UNDER_TEST_BOTH
    face_ok: bool = False
    coaching: str = ""


class _EyeStateTracker:
    """Temporal majority + EMA for one eye, with hysteresis on state changes."""

    def __init__(
        self,
        *,
        window: int,
        min_votes: int,
        ema_alpha: float,
    ) -> None:
        self.history: deque[str] = deque(maxlen=max(1, window))
        self.min_votes = max(1, min(min_votes, max(1, window)))
        self.alpha = float(np.clip(ema_alpha, 0.01, 1.0))
        self.stable_state = EYE_STATE_UNKNOWN
        self.ear: float | None = None
        self.iris_like = 0.0
        self.cover_score = 0.0
        self.occluder_score = 0.0
        self.iris_2d: tuple[int, int] | None = None

    def reset(self) -> None:
        self.history.clear()
        self.stable_state = EYE_STATE_UNKNOWN
        self.ear = None
        self.iris_like = 0.0
        self.cover_score = 0.0
        self.occluder_score = 0.0
        self.iris_2d = None

    def update(self, observed: EyeSideStatus) -> EyeSideStatus:
        self.history.append(observed.state)
        counts = Counter(self.history)
        candidate, votes = counts.most_common(1)[0]

        # Initial lock may happen quickly; subsequent changes require a real
        # majority so one bad landmark sample cannot flip the tested side.
        required = min(self.min_votes, len(self.history))
        if self.stable_state == EYE_STATE_UNKNOWN:
            if candidate != EYE_STATE_UNKNOWN and votes >= required:
                self.stable_state = candidate
        elif candidate != self.stable_state and votes >= self.min_votes:
            self.stable_state = candidate

        a = self.alpha
        if observed.ear is not None:
            self.ear = (
                float(observed.ear)
                if self.ear is None
                else (1.0 - a) * self.ear + a * float(observed.ear)
            )
        self.iris_like = (1.0 - a) * self.iris_like + a * observed.iris_like
        self.cover_score = (1.0 - a) * self.cover_score + a * observed.cover_score
        self.occluder_score = (
            (1.0 - a) * self.occluder_score + a * observed.occluder_score
        )
        if observed.iris_2d is not None:
            if self.iris_2d is None:
                self.iris_2d = observed.iris_2d
            else:
                self.iris_2d = (
                    int(round((1.0 - a) * self.iris_2d[0] + a * observed.iris_2d[0])),
                    int(round((1.0 - a) * self.iris_2d[1] + a * observed.iris_2d[1])),
                )

        return self.snapshot()

    def snapshot(self) -> EyeSideStatus:
        return EyeSideStatus(
            state=self.stable_state,
            ear=self.ear,
            iris_like=float(np.clip(self.iris_like, 0.0, 1.0)),
            cover_score=float(np.clip(self.cover_score, 0.0, 1.0)),
            occluder_score=float(np.clip(self.occluder_score, 0.0, 1.0)),
            iris_2d=self.iris_2d,
        )


def _lm_xy(landmarks: Sequence[Any], idx: int, width: int, height: int) -> np.ndarray:
    lm = landmarks[idx]
    return np.array([lm.x * width, lm.y * height], dtype=np.float64)


def _occluder_dark_fraction(
    gray: np.ndarray,
    center: tuple[float, float],
    half: float,
    skin_ref: float,
    dark_rel: float,
) -> float:
    """Fraction of an eye-region box that is much darker than midface skin.

    Opaque occluders (black paddle, hand) read as a large dark blob at the
    eye-region scale. This works where iris sampling fails, because a 6 cm
    pad spans many pixels even when a single iris is only ~3 px wide.
    """
    if skin_ref <= 1.0:
        return 0.0
    h, w = gray.shape[:2]
    hf = max(int(round(half)), 3)
    cx, cy = int(center[0]), int(center[1])
    x1, y1 = max(0, cx - hf), max(0, cy - hf)
    x2, y2 = min(w, cx + hf + 1), min(h, cy + hf + 1)
    if x2 - x1 < 3 or y2 - y1 < 3:
        return 0.0
    roi = gray[y1:y2, x1:x2]
    return float((roi < dark_rel * skin_ref).mean())


def _eye_aspect_ratio(
    landmarks: Sequence[Any],
    width: int,
    height: int,
    h_pair: tuple[int, int],
    v_quad: tuple[int, int, int, int],
) -> float | None:
    p1 = _lm_xy(landmarks, h_pair[0], width, height)
    p4 = _lm_xy(landmarks, h_pair[1], width, height)
    p2 = _lm_xy(landmarks, v_quad[0], width, height)
    p6 = _lm_xy(landmarks, v_quad[1], width, height)
    p3 = _lm_xy(landmarks, v_quad[2], width, height)
    p5 = _lm_xy(landmarks, v_quad[3], width, height)
    horiz = np.linalg.norm(p1 - p4)
    if horiz < 1e-6:
        return None
    vert1 = np.linalg.norm(p2 - p6)
    vert2 = np.linalg.norm(p3 - p5)
    return float((vert1 + vert2) / (2.0 * horiz))


def _patch_stats(
    frame_bgr: np.ndarray, sx: int, sy: int
) -> tuple[float, float, float] | None:
    h, w = frame_bgr.shape[:2]
    if sx < 2 or sy < 2 or sx >= w - 2 or sy >= h - 2:
        return None
    patch = frame_bgr[sy - 2 : sy + 3, sx - 2 : sx + 3]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return (
        float(np.mean(hsv[:, :, 2])),
        float(np.mean(hsv[:, :, 1])),
        float(np.std(gray)),
    )


def _local_skin_v(
    frame_bgr: np.ndarray, center: tuple[float, float], eye_w: float
) -> float:
    """Cheek brightness reference (below the eye — not the hand on the eye)."""
    cx, cy = int(center[0]), int(center[1])
    offset = max(int(eye_w * 0.9), 14)
    refs: list[float] = []
    for dx, dy in ((0, offset), (offset, offset), (-offset, offset), (0, int(offset * 1.45))):
        stats = _patch_stats(frame_bgr, cx + dx, cy + dy)
        if stats is None:
            continue
        mean_v, mean_s, contrast = stats
        if 55 <= mean_v <= 235 and contrast < 32 and mean_s < 135:
            refs.append(mean_v)
    return float(np.median(refs)) if refs else 140.0


def _iris_zone_skin_fraction(
    frame_bgr: np.ndarray,
    center: tuple[float, float],
    radius: float,
) -> float:
    """Skin/hand fill in a small disc at the iris — not the eyelid quad."""
    h, w = frame_bgr.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    r = max(int(radius), 3)
    x1, y1 = max(0, cx - r), max(0, cy - r)
    x2, y2 = min(w, cx + r + 1), min(h, cy + r + 1)
    if x2 <= x1 + 1 or y2 <= y1 + 1:
        return 0.0

    roi = frame_bgr[y1:y2, x1:x2]
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    cv2.circle(mask, (cx - x1, cy - y1), r, 255, -1, lineType=cv2.LINE_AA)
    area = int(cv2.countNonZero(mask))
    if area < 6:
        return 0.0

    ycrcb = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(ycrcb, (0, 125, 70), (255, 180, 135))
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    soft = cv2.inRange(hsv, (0, 0, 75), (179, 100, 255))
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # Low-structure soft skin (typical palm / back of hand under desk light)
    if float(cv2.Laplacian(gray, cv2.CV_32F).var()) < 220.0:
        handish = cv2.bitwise_or(skin, soft)
    else:
        handish = skin
    handish = cv2.bitwise_and(handish, mask)

    # Dark iris pixels must not count as skin
    dark = cv2.inRange(gray, 0, 95)
    handish = cv2.bitwise_and(handish, cv2.bitwise_not(dark))
    return float(np.clip(cv2.countNonZero(handish) / float(area), 0.0, 1.0))


def _sample_iris_like(
    frame_bgr: np.ndarray,
    center: tuple[float, float],
    radius: float,
    rim_pts: list[tuple[float, float]] | None = None,
    eye_w: float | None = None,
) -> float:
    """How iris/pupil-like the landmark center is (high = open eye)."""
    r = max(int(radius), 2)
    cx, cy = int(center[0]), int(center[1])
    ew = float(eye_w) if eye_w is not None else float(r * 4)
    skin_v = _local_skin_v(frame_bgr, center, ew)

    samples: list[tuple[int, int, float]] = [(cx, cy, 1.25)]
    for scale, weight in ((0.30, 1.0), (0.50, 0.7), (0.72, 0.35)):
        for ang in (0, 45, 90, 135, 180, 225, 270, 315):
            rad = np.radians(ang)
            samples.append(
                (
                    int(cx + r * scale * np.cos(rad)),
                    int(cy + r * scale * np.sin(rad)),
                    weight,
                )
            )
    if rim_pts:
        for px, py in rim_pts:
            samples.append((int(px), int(py), 0.25))

    center_stats = _patch_stats(frame_bgr, cx, cy)
    ring_vs: list[float] = []
    for ang in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = np.radians(ang)
        st = _patch_stats(
            frame_bgr,
            int(cx + r * 0.55 * np.cos(rad)),
            int(cy + r * 0.55 * np.sin(rad)),
        )
        if st is not None:
            ring_vs.append(st[0])
    ring_v = float(np.median(ring_vs)) if ring_vs else (
        float(center_stats[0]) if center_stats else skin_v
    )
    pupil_structure = 0.0
    if center_stats is not None:
        pupil_structure = float(np.clip((ring_v - center_stats[0]) / 22.0, -0.5, 1.0))

    iris_hits = 0.0
    total_w = 0.0
    skinish_w = 0.0
    for sx, sy, weight in samples:
        stats = _patch_stats(frame_bgr, sx, sy)
        if stats is None:
            continue
        mean_v, mean_s, contrast = stats
        total_w += weight

        darker_than_skin = (skin_v - mean_v) >= 12.0
        strongly_darker = (skin_v - mean_v) >= 26.0
        skinish = (
            abs(mean_v - skin_v) < 26
            and mean_s < 115
            and contrast < 26
            and not strongly_darker
        )
        if skinish:
            skinish_w += weight
            continue

        irisish = (
            (mean_v < 125 and darker_than_skin)
            or (mean_v < 105)
            or (strongly_darker and mean_v < 160)
        )
        if irisish:
            iris_hits += weight
        elif darker_than_skin and mean_v < 145:
            iris_hits += 0.5 * weight

    if total_w <= 1e-6:
        return 0.0

    raw = iris_hits / total_w
    skin_ratio = skinish_w / total_w
    if skin_ratio >= 0.52 and pupil_structure < 0.12:
        raw *= 0.18
    elif skin_ratio >= 0.38 and pupil_structure < 0.08:
        raw *= 0.4
    elif pupil_structure > 0.12:
        raw = min(1.0, raw + 0.18 * pupil_structure)

    return float(np.clip(raw, 0.0, 1.0))


def _combined_cover_score(iris_like: float, iris_skin_frac: float) -> float:
    """Missing iris → cover; skin at pupil boosts only when iris score is weak."""
    base = 1.0 - float(np.clip(iris_like, 0.0, 1.0))
    if iris_skin_frac >= 0.58 and iris_like < 0.38:
        hand = 0.50 + 0.50 * min(1.0, (iris_skin_frac - 0.58) / 0.42)
        return float(np.clip(max(base, hand), 0.0, 1.0))
    if iris_skin_frac >= 0.72 and iris_like < 0.48:
        return float(np.clip(max(base, 0.58), 0.0, 1.0))
    return float(np.clip(base, 0.0, 1.0))


def _classify_eye(
    *,
    ear: float | None,
    iris_like: float,
    cover_score: float,
    occluder_score: float,
    ear_closed: float,
    cover_thresh: float,
    partial_thresh: float,
    open_iris_min: float,
    occluder_cover: float,
    occluder_partial: float,
) -> str:
    if ear is not None and ear < ear_closed:
        return EYE_STATE_CLOSED
    # Opaque occluder (paddle/hand) is the reliable cover signal at clinic
    # distance — must win before the iris test, which saturates to OPEN when
    # the iris is only a few pixels wide.
    if occluder_score >= occluder_cover:
        return EYE_STATE_COVERED
    if occluder_partial <= occluder_score < occluder_cover:
        return EYE_STATE_PARTIAL
    # Prefer OPEN when iris is visible — do not let soft cover score win
    if iris_like >= open_iris_min:
        if cover_score >= cover_thresh + 0.12 and iris_like < open_iris_min + 0.08:
            return EYE_STATE_COVERED
        return EYE_STATE_OPEN
    if cover_score >= cover_thresh:
        return EYE_STATE_COVERED
    if cover_score >= partial_thresh:
        return EYE_STATE_PARTIAL
    if ear is None:
        return EYE_STATE_UNKNOWN
    return EYE_STATE_OPEN


def _order_sides_screen_left_right(
    a: EyeSideStatus, b: EyeSideStatus
) -> tuple[EyeSideStatus, EyeSideStatus]:
    """Screen-left = LEFT, screen-right = RIGHT (matches mirrored selfie view)."""
    if a.iris_2d is None or b.iris_2d is None:
        return a, b
    if a.iris_2d[0] <= b.iris_2d[0]:
        return a, b
    return b, a


def _refine_pair_states(
    left: EyeSideStatus,
    right: EyeSideStatus,
    *,
    asymmetry_min: float,
    occluder_cover: float = 1.1,
) -> None:
    # Dual false covered on open eyes — but never override a confirmed opaque
    # occluder, whose dark-region signal is reliable even when iris_like is
    # saturated at clinic distance.
    if (
        left.state == EYE_STATE_COVERED
        and right.state == EYE_STATE_COVERED
        and left.iris_like >= 0.20
        and right.iris_like >= 0.20
        and left.occluder_score < occluder_cover
        and right.occluder_score < occluder_cover
    ):
        left.state = EYE_STATE_OPEN
        right.state = EYE_STATE_OPEN
        return

    diff = left.cover_score - right.cover_score
    if abs(diff) < asymmetry_min:
        return

    if diff >= asymmetry_min:
        if left.state != EYE_STATE_CLOSED and left.cover_score >= 0.42 and left.iris_like < 0.40:
            left.state = EYE_STATE_COVERED
        if right.state not in (EYE_STATE_CLOSED, EYE_STATE_COVERED) and right.iris_like >= 0.16:
            right.state = EYE_STATE_OPEN
    else:
        if right.state != EYE_STATE_CLOSED and right.cover_score >= 0.42 and right.iris_like < 0.40:
            right.state = EYE_STATE_COVERED
        if left.state not in (EYE_STATE_CLOSED, EYE_STATE_COVERED) and left.iris_like >= 0.16:
            left.state = EYE_STATE_OPEN


def _is_occluded(side: EyeSideStatus) -> bool:
    return side.state in (EYE_STATE_COVERED, EYE_STATE_CLOSED)


def _under_test_from_sides(left: EyeSideStatus, right: EyeSideStatus) -> tuple[str, str]:
    """Occlude left → test RIGHT; occlude right → test LEFT."""
    left_occ = _is_occluded(left)
    right_occ = _is_occluded(right)
    left_partial = left.state == EYE_STATE_PARTIAL
    right_partial = right.state == EYE_STATE_PARTIAL

    if left_occ and right_occ:
        return UNDER_TEST_UNKNOWN, "Uncover one eye — do not cover both"

    if left_partial and not right_occ and left.cover_score >= right.cover_score - 0.05:
        return UNDER_TEST_BOTH, "Cover left eye fully — no gaps between fingers"
    if right_partial and not left_occ and right.cover_score >= left.cover_score - 0.05:
        return UNDER_TEST_BOTH, "Cover right eye fully — no gaps between fingers"

    if left_occ and right.state in _SEEING:
        how = "closed" if left.state == EYE_STATE_CLOSED else "covered"
        return UNDER_TEST_RIGHT, f"Testing RIGHT eye (left {how})"
    if right_occ and left.state in _SEEING:
        how = "closed" if right.state == EYE_STATE_CLOSED else "covered"
        return UNDER_TEST_LEFT, f"Testing LEFT eye (right {how})"

    if left_partial or right_partial:
        side = "left" if left.cover_score >= right.cover_score else "right"
        return UNDER_TEST_BOTH, f"Cover {side} eye fully — no gaps between fingers"

    if left.state == EYE_STATE_OPEN and right.state == EYE_STATE_OPEN:
        return UNDER_TEST_BOTH, "Testing BOTH eyes"
    if left.state == EYE_STATE_UNKNOWN and right.state == EYE_STATE_UNKNOWN:
        return UNDER_TEST_UNKNOWN, "Face the camera so both eyes are visible"
    return UNDER_TEST_BOTH, "Testing BOTH eyes"


class EyeCoverChecker:
    """Face Mesh refine_landmarks → per-eye cover state + under_test side."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        ec = cfg.get("eye_cover", {})
        self.enabled = bool(ec.get("enabled", True))
        self.ear_closed = float(ec.get("ear_closed_threshold", 0.14))
        self.cover_thresh = float(ec.get("cover_score_threshold", 0.60))
        self.partial_thresh = float(ec.get("partial_cover_threshold", 0.45))
        self.open_iris_min = float(ec.get("open_iris_min", 0.24))
        self.asymmetry_min = float(ec.get("asymmetry_min", 0.14))
        self.min_eye_px = float(ec.get("min_eye_px", 28.0))
        self.expand_ratio = float(ec.get("bbox_expand_ratio", 0.2))
        # Opaque-occluder (paddle/hand) detection — primary cover signal at
        # clinic distance where the iris is only a few pixels wide.
        self.occluder_enabled = bool(ec.get("occluder_enabled", True))
        self.occluder_cover_thresh = float(ec.get("occluder_cover_threshold", 0.40))
        self.occluder_partial_thresh = float(
            ec.get("occluder_partial_threshold", 0.22)
        )
        self.occluder_region_ratio = float(ec.get("occluder_region_ratio", 0.26))
        self.occluder_dark_rel = float(ec.get("occluder_dark_rel", 0.55))
        self.occluder_ref_low = float(ec.get("occluder_ref_low", 40.0))
        tracking_window = max(1, int(ec.get("tracking_window", 5)))
        tracking_votes = max(1, int(ec.get("tracking_min_votes", 3)))
        tracking_alpha = float(ec.get("tracking_ema_alpha", 0.35))
        self.tracking_face_grace = max(0, int(ec.get("tracking_face_grace", 2)))
        self._missing_frames = 0
        self._left_tracker = _EyeStateTracker(
            window=tracking_window,
            min_votes=tracking_votes,
            ema_alpha=tracking_alpha,
        )
        self._right_tracker = _EyeStateTracker(
            window=tracking_window,
            min_votes=tracking_votes,
            ema_alpha=tracking_alpha,
        )
        pose_cfg = cfg.get("pose", {})
        self.mp_face = None
        if self.enabled and MEDIAPIPE_AVAILABLE:
            self.mp_face = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=float(
                    pose_cfg.get("min_detection_confidence", 0.5)
                ),
                min_tracking_confidence=float(
                    pose_cfg.get("min_tracking_confidence", 0.5)
                ),
            )

    def close(self) -> None:
        if self.mp_face is not None:
            self.mp_face.close()

    def _missing_result(self, coaching: str) -> EyeCoverResult:
        """Briefly retain the tracked state across FaceMesh dropouts."""
        self._missing_frames += 1
        if (
            self._missing_frames <= self.tracking_face_grace
            and self._left_tracker.stable_state != EYE_STATE_UNKNOWN
            and self._right_tracker.stable_state != EYE_STATE_UNKNOWN
        ):
            left = self._left_tracker.snapshot()
            right = self._right_tracker.snapshot()
            under, tracked_coach = _under_test_from_sides(left, right)
            return EyeCoverResult(
                left=left,
                right=right,
                under_test=under,
                face_ok=True,
                coaching=tracked_coach,
            )
        if self._missing_frames > self.tracking_face_grace:
            self._left_tracker.reset()
            self._right_tracker.reset()
        return EyeCoverResult(
            left=EyeSideStatus(),
            right=EyeSideStatus(),
            under_test=UNDER_TEST_UNKNOWN,
            face_ok=False,
            coaching=coaching,
        )

    def _tracked_result(
        self, left: EyeSideStatus, right: EyeSideStatus
    ) -> EyeCoverResult:
        self._missing_frames = 0
        left = self._left_tracker.update(left)
        right = self._right_tracker.update(right)
        under, coach = _under_test_from_sides(left, right)
        return EyeCoverResult(
            left=left,
            right=right,
            under_test=under,
            face_ok=True,
            coaching=coach,
        )

    def estimate(
        self,
        frame: np.ndarray,
        person_bbox: tuple[int, int, int, int] | None = None,
        head_bbox: tuple[int, int, int, int] | None = None,
    ) -> EyeCoverResult:
        empty = EyeCoverResult(left=EyeSideStatus(), right=EyeSideStatus())
        if not self.enabled or self.mp_face is None:
            empty.coaching = "Eye cover check disabled"
            return empty

        h, w = frame.shape[:2]
        crop_box = head_bbox or person_bbox
        ox, oy = 0, 0
        crop = frame
        if crop_box is not None:
            x1, y1, x2, y2 = crop_box
            bw, bh = x2 - x1, y2 - y1
            pad_x = int(bw * self.expand_ratio)
            pad_y = int(bh * self.expand_ratio)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w - 1, x2 + pad_x)
            y2 = min(h - 1, y2 + pad_y)
            crop = frame[y1:y2, x1:x2]
            ox, oy = x1, y1
            if crop.size == 0:
                return self._missing_result(
                    "Face the camera so both eyes are visible"
                )

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        result = self.mp_face.process(rgb)
        if not result.multi_face_landmarks:
            return self._missing_result("Face the camera so both eyes are visible")

        lms = result.multi_face_landmarks[0].landmark
        if len(lms) < 478:
            return self._missing_result("Face the camera so both eyes are visible")

        ch, cw = crop.shape[:2]
        a_outer = _lm_xy(lms, MP_A_OUTER, cw, ch)
        b_outer = _lm_xy(lms, MP_B_OUTER, cw, ch)
        inter = float(np.linalg.norm(b_outer - a_outer))
        if inter < self.min_eye_px:
            return self._missing_result("Move closer so eyes are clearer")

        # Midface (nose→chin) skin reference: rarely hidden by an eye paddle,
        # so it anchors the occluder dark-fraction against lighting changes.
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
        skin_ref = 0.0
        if self.occluder_enabled:
            nose = _lm_xy(lms, MP_NOSE_TIP, cw, ch)
            chin = _lm_xy(lms, MP_CHIN, cw, ch)
            mx, my = int((nose[0] + chin[0]) / 2), int((nose[1] + chin[1]) / 2)
            hs = max(int(inter * 0.22), 3)
            ref_roi = gray[
                max(0, my - hs) : my + hs, max(0, mx - hs) : mx + hs
            ]
            if ref_roi.size:
                skin_ref = float(np.median(ref_roi))

        side_a = self._side(
            frame_bgr=crop,
            gray=gray,
            skin_ref=skin_ref,
            inter_eye=inter,
            landmarks=lms,
            width=cw,
            height=ch,
            offset=(ox, oy),
            h_pair=MP_A_EAR_H,
            v_quad=MP_A_EAR_V,
            iris_idx=MP_A_IRIS,
            rim=MP_A_RIM,
            outer=MP_A_OUTER,
            inner=MP_A_INNER,
        )
        side_b = self._side(
            frame_bgr=crop,
            gray=gray,
            skin_ref=skin_ref,
            inter_eye=inter,
            landmarks=lms,
            width=cw,
            height=ch,
            offset=(ox, oy),
            h_pair=MP_B_EAR_H,
            v_quad=MP_B_EAR_V,
            iris_idx=MP_B_IRIS,
            rim=MP_B_RIM,
            outer=MP_B_OUTER,
            inner=MP_B_INNER,
        )
        # Always label by on-screen position so L/R match the mirrored selfie
        left, right = _order_sides_screen_left_right(side_a, side_b)
        _refine_pair_states(
            left,
            right,
            asymmetry_min=self.asymmetry_min,
            occluder_cover=self.occluder_cover_thresh,
        )
        return self._tracked_result(left, right)

    def _side(
        self,
        *,
        frame_bgr: np.ndarray,
        gray: np.ndarray,
        skin_ref: float,
        inter_eye: float,
        landmarks: Sequence[Any],
        width: int,
        height: int,
        offset: tuple[int, int],
        h_pair: tuple[int, int],
        v_quad: tuple[int, int, int, int],
        iris_idx: int,
        rim: tuple[int, int, int, int],
        outer: int,
        inner: int,
    ) -> EyeSideStatus:
        ear = _eye_aspect_ratio(landmarks, width, height, h_pair, v_quad)
        outer_xy = _lm_xy(landmarks, outer, width, height)
        inner_xy = _lm_xy(landmarks, inner, width, height)
        iris = _lm_xy(landmarks, iris_idx, width, height)
        eye_w = float(np.linalg.norm(inner_xy - outer_xy))
        aperture = float(ear) if ear is not None else 0.2
        radius = max(eye_w * (0.11 + 0.32 * min(aperture, 0.28)), 3.0)
        rim_pts = [tuple(_lm_xy(landmarks, i, width, height)) for i in rim]
        center = (float(iris[0]), float(iris[1]))
        iris_like = _sample_iris_like(
            frame_bgr, center, radius, rim_pts=rim_pts, eye_w=eye_w
        )
        iris_skin = _iris_zone_skin_fraction(frame_bgr, center, radius * 0.95)
        cover_score = _combined_cover_score(iris_like, iris_skin)

        # Occluder dark-fraction anchored on the eye-corner midpoint (stable
        # even when the hidden eye's iris landmark drifts onto skin).
        occluder_score = 0.0
        if self.occluder_enabled and skin_ref > self.occluder_ref_low:
            eye_center = ((outer_xy + inner_xy) / 2.0)
            half = self.occluder_region_ratio * inter_eye
            occluder_score = _occluder_dark_fraction(
                gray,
                (float(eye_center[0]), float(eye_center[1])),
                half,
                skin_ref,
                self.occluder_dark_rel,
            )

        state = _classify_eye(
            ear=ear,
            iris_like=iris_like,
            cover_score=cover_score,
            occluder_score=occluder_score,
            ear_closed=self.ear_closed,
            cover_thresh=self.cover_thresh,
            partial_thresh=self.partial_thresh,
            open_iris_min=self.open_iris_min,
            occluder_cover=self.occluder_cover_thresh,
            occluder_partial=self.occluder_partial_thresh,
        )
        ox, oy = offset
        return EyeSideStatus(
            state=state,
            ear=ear,
            iris_like=iris_like,
            cover_score=float(np.clip(cover_score, 0.0, 1.0)),
            occluder_score=float(np.clip(occluder_score, 0.0, 1.0)),
            iris_2d=(int(iris[0] + ox), int(iris[1] + oy)),
        )
