"""HUD and visual overlays for SmartEyes readiness demo."""

from __future__ import annotations

import cv2
import numpy as np

from src.eye_cover import (
    EYE_STATE_COVERED,
    EYE_STATE_OPEN,
    EYE_STATE_PARTIAL,
    EyeCoverResult,
)
from src.headphone_checker import HeadphoneDetection
from src.line_detector import LineBand
from src.pose_body import POSE_EDGES, BodyPose
from src.readiness_rules import ReadinessState
from src.spell_session import (
    PHASE_READY_HOLD,
    PHASE_SPELLING,
    PHASE_TRIAL_DONE,
    PHASE_WAITING,
    SpellSessionState,
)


def _pass_color(ok: bool) -> tuple[int, int, int]:
    return (0, 200, 0) if ok else (0, 0, 220)


def _eye_color(state: str) -> tuple[int, int, int]:
    if state == EYE_STATE_OPEN:
        return (0, 220, 0)
    if state == EYE_STATE_COVERED:
        return (0, 140, 255)
    if state == EYE_STATE_PARTIAL:
        return (0, 200, 255)
    return (160, 160, 160)


def draw_person_box(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    conf: float,
) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 80), 2)
    cv2.putText(
        frame,
        f"person {conf:.2f}",
        (x1, max(20, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 180, 80),
        1,
        cv2.LINE_AA,
    )


def draw_pose(frame: np.ndarray, pose: BodyPose) -> None:
    if not pose.visible:
        return
    for a, b in POSE_EDGES:
        if a in pose.landmarks and b in pose.landmarks:
            xa, ya, va = pose.landmarks[a]
            xb, yb, vb = pose.landmarks[b]
            if va < 0.3 or vb < 0.3:
                continue
            cv2.line(
                frame,
                (int(xa), int(ya)),
                (int(xb), int(yb)),
                (80, 220, 80),
                2,
                cv2.LINE_AA,
            )
    for ankle in (pose.left_ankle, pose.right_ankle):
        if ankle is not None:
            cv2.circle(frame, ankle, 8, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, ankle, 10, (0, 120, 255), 2, cv2.LINE_AA)
    if pose.ankle_midpoint is not None:
        cv2.drawMarker(
            frame,
            pose.ankle_midpoint,
            (0, 255, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=16,
            thickness=2,
        )
    for ear in (pose.left_ear, pose.right_ear):
        if ear is not None:
            cv2.circle(frame, ear, 6, (255, 120, 255), 2, cv2.LINE_AA)
    if pose.head_bbox is not None:
        x1, y1, x2, y2 = pose.head_bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 50), 1)


def draw_line_band(frame: np.ndarray, band: LineBand) -> None:
    if not band.found:
        return
    overlay = frame.copy()
    poly = band.polygon if band.polygon is not None else band.contour
    if poly is not None and len(poly) >= 3:
        cv2.fillPoly(overlay, [poly], (0, 220, 255))
        cv2.addWeighted(overlay, 0.22, frame, 0.78, 0, frame)
        cv2.polylines(frame, [poly], True, (0, 255, 255), 3, cv2.LINE_AA)
        x, y, bw, bh = cv2.boundingRect(poly)
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 200, 255), 2)
        label = band.label or "STAND ZONE"
        cv2.putText(
            frame,
            label,
            (x + 6, max(24, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.rectangle(
            overlay,
            (band.x_left, band.y_top),
            (band.x_right, band.y_bottom),
            (0, 255, 255),
            -1,
        )
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.rectangle(
            frame,
            (band.x_left, band.y_top),
            (band.x_right, band.y_bottom),
            (0, 255, 255),
            2,
        )


def draw_headphones(frame: np.ndarray, detections: list[HeadphoneDetection]) -> None:
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        color = (80, 220, 80) if det.on_head else (0, 0, 220)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        tag = "ON HEAD" if det.on_head else "NOT ON HEAD"
        cv2.putText(
            frame,
            f"{det.label} {det.confidence:.2f} [{tag}]",
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )


def draw_eye_cover(frame: np.ndarray, eye: EyeCoverResult | None) -> None:
    if eye is None or not eye.face_ok:
        return
    for side, status in (("L", eye.left), ("R", eye.right)):
        if status.iris_2d is None:
            continue
        color = _eye_color(status.state)
        cv2.circle(frame, status.iris_2d, 8, color, 2, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"{side}:{status.state}",
            (status.iris_2d[0] + 10, status.iris_2d[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )


def draw_readiness_hud(
    frame: np.ndarray,
    state: ReadinessState,
    fps: float,
    frame_idx: int,
) -> None:
    panel_h = 150
    panel_w = 520
    # Soft translucent panel (keeps video visible underneath)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (panel_w, panel_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.38, frame, 0.62, 0, frame)

    na = (140, 140, 140)
    if state.check_stand:
        line_txt = "PASS" if state.line_pass else "FAIL"
        line_color = _pass_color(state.line_pass)
    else:
        line_txt = "N/A"
        line_color = na

    if not state.check_headphones:
        hp_txt = "N/A"
        hp_color = na
    elif state.headphones_pass:
        hp_txt = "ON HEAD"
        hp_color = _pass_color(True)
    elif state.headphones_raw and not state.headphones_on_head:
        hp_txt = "DETECTED/OFF"
        hp_color = _pass_color(False)
    else:
        hp_txt = "FAIL"
        hp_color = _pass_color(False)

    if state.check_eyes:
        eye_txt = state.under_test
        eye_color = (0, 220, 255) if state.under_test != "UNKNOWN" else (0, 0, 220)
        lr_txt = f"L:{state.left_eye_state}  R:{state.right_eye_state}"
    else:
        eye_txt = "N/A"
        eye_color = na
        lr_txt = "eyes off"

    status_txt = "READY" if state.ready else "WAITING"
    status_color = (0, 220, 0) if state.ready else (0, 200, 255)

    cv2.putText(
        frame,
        f"ZONE: {line_txt}",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        line_color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"HEADPHONES: {hp_txt}",
        (12, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        hp_color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"EYE TEST: {eye_txt}",
        (12, 78),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        eye_color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        lr_txt,
        (12, 104),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"STATUS: {status_txt}",
        (12, 132),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        status_color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"FPS {fps:.1f}  #{frame_idx}",
        (340, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    if state.coaching:
        cv2.putText(
            frame,
            state.coaching,
            (12, panel_h + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )


def draw_spell_hud(frame: np.ndarray, spell: SpellSessionState | None) -> None:
    """On-screen Sloan board + heard letters (demo, not calibrated acuity)."""
    if spell is None:
        return
    if not spell.enabled:
        err = spell.error or "spell disabled"
        cv2.putText(
            frame,
            f"SPELL FAILED: {err[:70]}",
            (12, frame.shape[0] - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "Fix mic: --list-mics then --micro N  (BT speakers != mic)",
            (12, frame.shape[0] - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 180, 255),
            1,
            cv2.LINE_AA,
        )
        return

    h, w = frame.shape[:2]
    # Compact panel top-right so letters stay inside the dark pad
    panel_w = min(440, max(360, w // 3))
    panel_h = 310
    panel_x = max(8, w - panel_w - 12)
    panel_y = 12
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (panel_x, panel_y),
        (panel_x + panel_w, panel_y + panel_h),
        (18, 18, 18),
        -1,
    )
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
    cv2.rectangle(
        frame,
        (panel_x, panel_y),
        (panel_x + panel_w, panel_y + panel_h),
        (70, 70, 70),
        1,
        cv2.LINE_AA,
    )

    pad = 14
    x0 = panel_x + pad
    y = panel_y + 22
    cv2.putText(
        frame,
        f"SPELL {spell.phase}  eye={spell.under_test}",
        (x0, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )

    n = max(len(spell.target) or 5, 1)
    gap = max(48, (panel_w - 2 * pad) // n)
    glyph = 1.15
    (_tw, glyph_h), baseline = cv2.getTextSize(
        "H", cv2.FONT_HERSHEY_SIMPLEX, glyph, 3
    )
    row_step = glyph_h + baseline + 14

    y += 18
    cv2.putText(
        frame,
        "BOARD",
        (x0, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (150, 150, 150),
        1,
        cv2.LINE_AA,
    )
    y += row_step
    if spell.target:
        for i, ch in enumerate(spell.target):
            cv2.putText(
                frame,
                ch,
                (x0 + i * gap, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                glyph,
                (255, 255, 255),
                3,
                cv2.LINE_AA,
            )

    y += row_step
    cv2.putText(
        frame,
        "HEARD",
        (x0, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (150, 150, 150),
        1,
        cv2.LINE_AA,
    )
    y += row_step
    for i, ch in enumerate(spell.heard):
        want = spell.target[i] if i < len(spell.target) else ""
        color = (0, 220, 0) if want and ch == want else (0, 0, 220)
        cv2.putText(
            frame,
            ch,
            (x0 + i * gap, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            glyph,
            color,
            3,
            cv2.LINE_AA,
        )
    idx = len(spell.heard)
    if spell.phase == PHASE_SPELLING and idx < len(spell.target):
        flash = "?" if spell.last_letter == "?" else "_"
        color = (0, 200, 255) if flash == "?" else (160, 160, 160)
        cv2.putText(
            frame,
            flash,
            (x0 + idx * gap, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            glyph,
            color,
            3,
            cv2.LINE_AA,
        )

    y += max(36, glyph_h // 2 + 20)
    mic = "ON" if spell.mic_on else "OFF"
    mic_color = (0, 220, 0) if spell.mic_on else (0, 0, 220)
    conf_txt = f"MIC {mic}"
    if spell.last_conf > 0:
        conf_txt += f"  {spell.last_conf:.2f}"
    cv2.putText(
        frame,
        conf_txt,
        (x0, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        mic_color,
        1,
        cv2.LINE_AA,
    )
    if spell.mic_name:
        y += 20
        short = spell.mic_name
        if len(short) > 34:
            short = short[:31] + "..."
        cv2.putText(
            frame,
            short,
            (x0, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (170, 170, 170),
            1,
            cv2.LINE_AA,
        )
    if spell.score_correct is not None and spell.score_total is not None:
        y += 24
        cv2.putText(
            frame,
            f"SCORE {spell.score_correct}/{spell.score_total}  eye {spell.under_test}",
            (x0, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 220, 255),
            2,
            cv2.LINE_AA,
        )

    if spell.coaching_vi:
        cv2.putText(
            frame,
            spell.coaching_vi[:90],
            (12, h - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )


def render_frame(
    frame: np.ndarray,
    *,
    person_bbox: tuple[int, int, int, int] | None,
    person_conf: float,
    pose: BodyPose | None,
    band: LineBand,
    headphones: list[HeadphoneDetection],
    state: ReadinessState,
    fps: float,
    frame_idx: int,
    eye_cover: EyeCoverResult | None = None,
    spell: SpellSessionState | None = None,
) -> np.ndarray:
    vis = frame.copy()
    if state.check_stand:
        draw_line_band(vis, band)
    if person_bbox is not None:
        draw_person_box(vis, person_bbox, person_conf)
    if pose is not None and (state.check_stand or state.check_headphones):
        draw_pose(vis, pose)
    if state.check_headphones:
        draw_headphones(vis, headphones)
    if state.check_eyes:
        draw_eye_cover(vis, eye_cover)
    draw_readiness_hud(vis, state, fps, frame_idx)
    draw_spell_hud(vis, spell)
    return vis
