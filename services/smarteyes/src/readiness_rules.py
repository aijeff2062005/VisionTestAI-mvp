"""Temporal readiness rules: selective ZONE / HEADPHONES / EYES checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.eye_cover import (
    EYE_STATE_PARTIAL,
    UNDER_TEST_BOTH,
    UNDER_TEST_UNKNOWN,
    EyeCoverResult,
)


@dataclass
class ReadinessState:
    person_present: bool = False
    line_raw: bool = False
    headphones_raw: bool = False
    headphones_on_head: bool = False
    line_pass: bool = False
    headphones_pass: bool = False
    eyes_pass: bool = False
    ready: bool = False
    coaching: str = ""
    line_hold_s: float = 0.0
    headphones_hold_s: float = 0.0
    under_test: str = UNDER_TEST_BOTH
    left_eye_state: str = "unknown"
    right_eye_state: str = "unknown"
    eye_cover_coaching: str = ""
    eye_face_ok: bool = False
    # Which checks are active this run
    check_stand: bool = True
    check_headphones: bool = True
    check_eyes: bool = True


class ReadinessRules:
    def __init__(self, cfg: dict[str, Any]) -> None:
        rules = cfg.get("rules", {})
        checks = cfg.get("checks") or {}
        self.check_stand = bool(checks.get("stand", True))
        self.check_headphones = bool(checks.get("headphones", True))
        self.check_eyes = bool(checks.get("eyes", True))
        self.hold_seconds = float(rules.get("hold_seconds", 1.5))
        self.require_single_person = bool(rules.get("require_single_person", True))
        self.require_both_ankles = bool(rules.get("require_both_ankles", False))
        self.require_headphones_on_head = bool(
            cfg.get("headphones", {}).get("require_on_head", True)
        )
        self._line_since: float | None = None
        self._hp_since: float | None = None
        self._eyes_since: float | None = None

    def update(
        self,
        *,
        timestamp: float,
        num_persons: int,
        line_ok: bool,
        headphones_ok: bool,
        headphones_on_head: bool,
        line_found: bool,
        eye_cover: EyeCoverResult | None = None,
    ) -> ReadinessState:
        person_present = num_persons >= 1

        # Disabled checks auto-pass (N/A)
        if not self.check_stand:
            line_ok = True
            line_found = True
        if not self.check_headphones:
            headphones_ok = True
            headphones_on_head = True

        hp_gate = headphones_on_head if self.require_headphones_on_head else headphones_ok

        if self.check_stand and line_ok and person_present:
            if self._line_since is None:
                self._line_since = timestamp
        else:
            self._line_since = None if self.check_stand else timestamp

        if self.check_headphones and hp_gate and person_present:
            if self._hp_since is None:
                self._hp_since = timestamp
        else:
            self._hp_since = None if self.check_headphones else timestamp

        eyes_ok = True
        under_test = UNDER_TEST_BOTH
        left_state = "n/a"
        right_state = "n/a"
        eye_coach = ""
        face_ok = False
        if self.check_eyes:
            left_state = "unknown"
            right_state = "unknown"
            if eye_cover is not None:
                under_test = eye_cover.under_test
                left_state = eye_cover.left.state
                right_state = eye_cover.right.state
                eye_coach = eye_cover.coaching
                face_ok = eye_cover.face_ok
                # Ready when face visible and side resolved. Peek (partial + BOTH)
                # blocks; one covered + other open/partial still passes.
                peek_block = (
                    under_test == UNDER_TEST_BOTH
                    and (
                        eye_cover.left.state == EYE_STATE_PARTIAL
                        or eye_cover.right.state == EYE_STATE_PARTIAL
                    )
                )
                eyes_ok = bool(
                    person_present
                    and face_ok
                    and under_test != UNDER_TEST_UNKNOWN
                    and not peek_block
                )
            else:
                eyes_ok = False

            if eyes_ok:
                if self._eyes_since is None:
                    self._eyes_since = timestamp
            else:
                self._eyes_since = None
        else:
            self._eyes_since = timestamp
            under_test = "N/A"

        line_hold = (timestamp - self._line_since) if self._line_since else 0.0
        hp_hold = (timestamp - self._hp_since) if self._hp_since else 0.0
        eyes_hold = (timestamp - self._eyes_since) if self._eyes_since else 0.0

        line_pass = (not self.check_stand) or (line_hold >= self.hold_seconds)
        hp_pass = (not self.check_headphones) or (hp_hold >= self.hold_seconds)
        eyes_pass = (not self.check_eyes) or (eyes_hold >= self.hold_seconds)
        ready = line_pass and hp_pass and eyes_pass and person_present

        coaching = self._coach(
            person_present=person_present,
            num_persons=num_persons,
            line_found=line_found,
            line_ok=line_ok,
            line_pass=line_pass,
            headphones_ok=headphones_ok,
            headphones_on_head=headphones_on_head,
            headphones_pass=hp_pass,
            eyes_pass=eyes_pass,
            ready=ready,
            eye_cover=eye_cover,
        )

        return ReadinessState(
            person_present=person_present,
            line_raw=line_ok if self.check_stand else False,
            headphones_raw=headphones_ok if self.check_headphones else False,
            headphones_on_head=headphones_on_head if self.check_headphones else False,
            line_pass=line_pass,
            headphones_pass=hp_pass,
            eyes_pass=eyes_pass,
            ready=ready,
            coaching=coaching,
            line_hold_s=line_hold,
            headphones_hold_s=hp_hold,
            under_test=under_test,
            left_eye_state=left_state,
            right_eye_state=right_state,
            eye_cover_coaching=eye_coach,
            eye_face_ok=face_ok,
            check_stand=self.check_stand,
            check_headphones=self.check_headphones,
            check_eyes=self.check_eyes,
        )

    def _coach(
        self,
        *,
        person_present: bool,
        num_persons: int,
        line_found: bool,
        line_ok: bool,
        line_pass: bool,
        headphones_ok: bool,
        headphones_on_head: bool,
        headphones_pass: bool,
        eyes_pass: bool,
        ready: bool,
        eye_cover: EyeCoverResult | None,
    ) -> str:
        if not person_present:
            return "Step into camera view"
        if self.require_single_person and num_persons > 1:
            return "Only one person should be in frame"

        if self.check_stand:
            if not line_found:
                return "Stand zone not found — check white floor in view"
            if not line_ok:
                return "Stand on the white floor (stand zone)"
            if not line_pass:
                return "Hold position in the stand zone..."

        if self.check_headphones:
            if not headphones_ok:
                return "Put on over-ear headphones"
            if self.require_headphones_on_head and not headphones_on_head:
                return "Place headphones on your head (over both ears)"
            if not headphones_pass:
                return "Keep headphones on your head..."

        if self.check_eyes:
            if eye_cover is None or not eye_cover.face_ok:
                return (
                    (eye_cover.coaching if eye_cover else None)
                    or "Face the camera so both eyes are visible"
                )
            if eye_cover.under_test == UNDER_TEST_BOTH and (
                eye_cover.left.state == EYE_STATE_PARTIAL
                or eye_cover.right.state == EYE_STATE_PARTIAL
            ):
                return eye_cover.coaching or "Cover eye fully — no gaps"
            if eye_cover.under_test == UNDER_TEST_UNKNOWN:
                return eye_cover.coaching or "Adjust eye cover"
            if not eyes_pass:
                return f"Hold eye cover — testing {eye_cover.under_test}..."

        if ready:
            if self.check_eyes and eye_cover is not None:
                if eye_cover.under_test == UNDER_TEST_BOTH:
                    return "READY — testing BOTH eyes"
                return f"READY — testing {eye_cover.under_test} eye"
            return "READY — checks passed"
        return "Adjust position"
