"""SmartEyes readiness pipeline: zone + headphones-on-head + eye under-test."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from src.camera_utils import camera_label, open_video_capture, resolve_source
from src.config_loader import load_config, project_root
from src.detector import Detection, YOLODetector
from src.eye_cover import EyeCoverChecker, EyeCoverResult
from src.headphone_checker import HeadphoneChecker, HeadphoneDetection
from src.line_detector import FloorLineDetector, LineBand
from src.overlay import render_frame
from src.pose_body import BodyPose, BodyPoseEstimator
from src.readiness_rules import ReadinessRules, ReadinessState
from src.spell_session import SpellSession, SpellSessionState
from src.stand_zone import (
    default_track_box_from_polygon,
    filter_detections_in_zone,
    normalize_polygon,
    normalize_track_box,
    pick_largest,
    track_box_to_pixel_roi,
)


logger = logging.getLogger(__name__)


@dataclass
class FPSCounter:
    window: int = 30

    def __post_init__(self) -> None:
        self._times: list[float] = []

    def tick(self) -> float:
        now = time.perf_counter()
        self._times.append(now)
        if len(self._times) > self.window:
            self._times.pop(0)
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._times) - 1) / elapsed


@dataclass
class PipelineResult:
    frame: np.ndarray
    detections: list[Detection]
    pose: BodyPose | None
    band: LineBand
    headphones: list[HeadphoneDetection]
    eye_cover: EyeCoverResult | None
    state: ReadinessState
    fps: float
    frame_idx: int
    timestamp: float
    person_bbox: tuple[int, int, int, int] | None = None
    person_conf: float = 0.0
    spell: SpellSessionState | None = None


@dataclass
class SmartEyesPipeline:
    cfg: dict[str, Any]
    detector: YOLODetector = field(init=False)
    pose: BodyPoseEstimator = field(init=False)
    line: FloorLineDetector = field(init=False)
    headphones: HeadphoneChecker | None = field(init=False, default=None)
    eye_cover: EyeCoverChecker = field(init=False)
    rules: ReadinessRules = field(init=False)
    fps_counter: FPSCounter = field(init=False)
    spell: SpellSession | None = field(init=False)
    frame_idx: int = 0
    _last_detections: list[Detection] = field(default_factory=list)
    _last_headphones: list[HeadphoneDetection] = field(default_factory=list)
    _last_eye: EyeCoverResult | None = None
    _last_pose: BodyPose | None = None
    _last_detect_log_key: tuple[Any, ...] | None = None

    def __post_init__(self) -> None:
        checks = self.cfg.get("checks") or {}
        self.check_stand = bool(checks.get("stand", True))
        self.check_headphones = bool(checks.get("headphones", True))
        self.check_eyes = bool(checks.get("eyes", True))
        model_cfg = self.cfg.get("model") or {}
        self.detect_in_zone = bool(model_cfg.get("detect_in_zone", False))
        try:
            self.track_box = normalize_track_box(model_cfg.get("track_box"))
        except (TypeError, ValueError):
            line = self.cfg.get("line") or {}
            self.track_box = default_track_box_from_polygon(line.get("fixed_polygon"))
            model_cfg = dict(model_cfg)
            model_cfg["track_box"] = list(self.track_box)
            self.cfg["model"] = model_cfg

        self.detector = YOLODetector(self.cfg)
        self.pose = BodyPoseEstimator(self.cfg)
        self.line = FloorLineDetector(self.cfg)
        self.headphones = HeadphoneChecker(self.cfg) if self.check_headphones else None
        self.eye_cover = EyeCoverChecker(self.cfg)
        if not self.check_eyes:
            self.eye_cover.enabled = False
        self.rules = ReadinessRules(self.cfg)
        self.fps_counter = FPSCounter()
        spell_cfg = self.cfg.get("spell") or {}
        if bool(spell_cfg.get("enabled", False)):
            self.spell = SpellSession(self.cfg)
            if not self.spell.enabled:
                err = self.spell.snapshot().error or "unknown error"
                print()
                print("*** SPELL DISABLED ***", err)
                print("    Run: python scripts/run_webcam_demo.py --list-mics")
                print('    Then: --micro 5   or  --micro "MacBook Air"')
                print("    (Bluetooth playback index is NOT the mic.)")
                print()
        else:
            self.spell = None

    def set_stand_zone(
        self,
        *,
        mode: str | None = None,
        polygon: list[list[float]] | None = None,
        detect_in_zone: bool | None = None,
        track_box: list[float] | None = None,
    ) -> dict[str, Any]:
        """Apply stand-zone + track-box settings live (no pipeline restart)."""
        line_cfg = dict(self.cfg.get("line") or {})
        model_cfg = dict(self.cfg.get("model") or {})
        if mode is not None:
            line_cfg["mode"] = str(mode).lower()
        if polygon is not None:
            if len(polygon) >= 3:
                line_cfg["fixed_polygon"] = normalize_polygon(list(polygon))
            else:
                line_cfg["fixed_polygon"] = []
        if detect_in_zone is not None:
            model_cfg["detect_in_zone"] = bool(detect_in_zone)
            self.detect_in_zone = bool(detect_in_zone)
        if track_box is not None:
            self.track_box = normalize_track_box(list(track_box))
            model_cfg["track_box"] = list(self.track_box)
        elif "track_box" not in model_cfg:
            self.track_box = default_track_box_from_polygon(line_cfg.get("fixed_polygon"))
            model_cfg["track_box"] = list(self.track_box)
        self.cfg["line"] = line_cfg
        self.cfg["model"] = model_cfg
        self.line.apply_stand_zone(
            mode=line_cfg.get("mode"),
            polygon=line_cfg.get("fixed_polygon"),
        )
        # Force a fresh detect tick after zone edits
        self._last_detections = []
        return {
            "mode": str(line_cfg.get("mode") or self.line.mode),
            "detect_in_zone": bool(self.detect_in_zone),
            "polygon": list(self.line.fixed_polygon_norm),
            "track_box": list(self.track_box),
        }

    def get_stand_zone(self) -> dict[str, Any]:
        line_cfg = self.cfg.get("line") or {}
        return {
            "mode": str(line_cfg.get("mode") or self.line.mode),
            "detect_in_zone": bool(self.detect_in_zone),
            "polygon": list(self.line.fixed_polygon_norm),
            "track_box": list(self.track_box),
        }

    def close(self) -> None:
        self.pose.close()
        self.eye_cover.close()
        if self.spell is not None:
            self.spell.close()

    def handle_key(self, key: int) -> None:
        if self.spell is not None:
            self.spell.handle_key(key)

    def process_frame(self, frame: np.ndarray) -> PipelineResult:
        self.frame_idx += 1
        timestamp = time.time()
        detect_every = max(1, int(self.cfg["model"]["detect_every_n_frames"]))
        hp_every = max(1, int(self.cfg.get("headphones", {}).get("detect_every_n_frames", 3)))
        eye_every = max(1, int(self.cfg.get("eye_cover", {}).get("detect_every_n_frames", 2)))
        pose_every = max(
            1,
            int(self.cfg.get("pose", {}).get("estimate_every_n_frames", detect_every)),
        )

        # Stand hull = ankle gate only. YOLO crop = independent track_box.
        # Do NOT drop track-box people whose feet are outside the stand hull —
        # that killed person boxes + eyes while ZONE:FAIL is still correct.
        band = LineBand(found=False)
        if self.check_stand:
            band = self.line.detect(frame)

        if self.frame_idx % detect_every == 1:
            roi = None
            if self.detect_in_zone:
                h, w = frame.shape[:2]
                roi = track_box_to_pixel_roi(self.track_box, w, h)
            detections = self.detector.detect(frame, roi=roi)
            self._last_detections = detections
        else:
            detections = self._last_detections

        # Prefer a person whose feet are in the stand zone when available;
        # otherwise largest detection inside the track crop (for pose/eyes).
        person: Detection | None = None
        if detections:
            if self.check_stand and band.found:
                in_stand = filter_detections_in_zone(detections, band)
                person = pick_largest(in_stand) if in_stand else pick_largest(detections)
            else:
                person = pick_largest(detections)

        pose: BodyPose | None = None
        if person is not None:
            if self.frame_idx % pose_every == 1 or self._last_pose is None:
                pose = self.pose.estimate(frame, person.bbox)
                self._last_pose = pose
            else:
                pose = self._last_pose
        else:
            self._last_pose = None

        line_ok = False
        if self.check_stand and pose is not None and pose.visible:
            line_ok = FloorLineDetector.ankles_in_band(
                band,
                pose.left_ankle,
                pose.right_ankle,
                pose.ankle_midpoint,
                require_both=self.rules.require_both_ankles,
            )

        headphones: list[HeadphoneDetection] = []
        headphones_detected = False
        headphones_on_head = False
        if self.check_headphones and self.headphones is not None:
            if person is not None and self.frame_idx % hp_every == 1:
                head_bbox = pose.head_bbox if pose is not None else None
                left_ear = pose.left_ear if pose is not None else None
                right_ear = pose.right_ear if pose is not None else None
                nose = pose.nose if pose is not None else None
                left_wrist = pose.left_wrist if pose is not None else None
                right_wrist = pose.right_wrist if pose is not None else None
                self._last_headphones = self.headphones.detect_near_head(
                    frame,
                    person.bbox,
                    head_bbox=head_bbox,
                    left_ear=left_ear,
                    right_ear=right_ear,
                    nose=nose,
                    left_wrist=left_wrist,
                    right_wrist=right_wrist,
                )
            headphones = self._last_headphones if person is not None else []
            headphones_detected = len(headphones) > 0
            headphones_on_head = self.headphones.worn_ok(headphones)

        eye: EyeCoverResult | None = None
        if self.check_eyes:
            if person is not None and self.frame_idx % eye_every == 1:
                head_bbox = pose.head_bbox if pose is not None else None
                self._last_eye = self.eye_cover.estimate(
                    frame, person_bbox=person.bbox, head_bbox=head_bbox
                )
            eye = self._last_eye if person is not None else None

        state = self.rules.update(
            timestamp=timestamp,
            num_persons=len(detections),
            line_ok=line_ok,
            headphones_ok=headphones_detected,
            headphones_on_head=headphones_on_head,
            line_found=band.found,
            eye_cover=eye,
        )

        # Log only state transitions to avoid flooding the log every frame.
        detect_key = (
            len(detections),
            bool(person),
            bool(line_ok),
            bool(state.line_pass),
            bool(state.ready),
        )
        if detect_key != self._last_detect_log_key:
            bbox = tuple(round(float(v), 1) for v in person.bbox) if person else None
            logger.info(
                "DETECT_PERSON count=%d present=%s bbox=%s conf=%.3f "
                "line_ok=%s line_pass=%s ready=%s",
                len(detections),
                bool(person),
                bbox,
                float(person.confidence) if person else 0.0,
                bool(line_ok),
                bool(state.line_pass),
                bool(state.ready),
            )
            self._last_detect_log_key = detect_key

        spell_state: SpellSessionState | None = None
        if self.spell is not None:
            spell_state = self.spell.on_frame(state, eye, timestamp)

        fps = self.fps_counter.tick()
        return PipelineResult(
            frame=frame,
            detections=detections,
            pose=pose,
            band=band,
            headphones=headphones,
            eye_cover=eye,
            state=state,
            fps=fps,
            frame_idx=self.frame_idx,
            timestamp=timestamp,
            person_bbox=person.bbox if person else None,
            person_conf=person.confidence if person else 0.0,
            spell=spell_state,
        )

    def render(self, result: PipelineResult) -> np.ndarray:
        return render_frame(
            result.frame,
            person_bbox=result.person_bbox,
            person_conf=result.person_conf,
            pose=result.pose,
            band=result.band,
            headphones=result.headphones,
            state=result.state,
            fps=result.fps,
            frame_idx=result.frame_idx,
            eye_cover=result.eye_cover,
            spell=result.spell,
        )


def build_pipeline(config_path: str | Path | None = None) -> SmartEyesPipeline:
    root = project_root()
    path = Path(config_path) if config_path else root / "configs" / "default.yaml"
    cfg = load_config(path)
    return SmartEyesPipeline(cfg=cfg)


def run_capture_loop(
    source: str | int,
    pipeline: SmartEyesPipeline,
    *,
    display: bool = True,
    max_frames: int | None = None,
    on_frame: Callable[[PipelineResult, np.ndarray], None] | None = None,
) -> None:
    resolved = resolve_source(source)
    # Label from ffmpeg names only — never list_cameras() after open (steals UVC).
    if isinstance(resolved, int):
        print(f"Using camera index {resolved} ({camera_label(resolved)})")
    else:
        print(f"Using source: {camera_label(resolved)}")

    vid = pipeline.cfg.get("video") or {}
    cap = open_video_capture(
        source,
        width=int(vid.get("width") or 1280),
        height=int(vid.get("height") or 720),
        fps=int(vid.get("fps") or 30),
    )
    # Do not re-set resolution after open — renegotiating can steal the device.

    window_name = "SmartEyes"
    if display:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Selfie mirror: left/right on screen match the user's own left/right
            if bool(pipeline.cfg.get("video", {}).get("mirror", True)):
                frame = cv2.flip(frame, 1)

            result = pipeline.process_frame(frame)
            vis = pipeline.render(result)

            if on_frame:
                on_frame(result, vis)

            if display:
                cv2.imshow(window_name, vis)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if key not in (0xFF, 255, 0):
                    pipeline.handle_key(key)

            if max_frames and result.frame_idx >= max_frames:
                break
    finally:
        cap.release()
        if display:
            cv2.destroyAllWindows()
