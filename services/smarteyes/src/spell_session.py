"""Spell-session phase machine: READY → board → mic letters → score by under_test."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.eye_cover import (
    EYE_STATE_PARTIAL,
    UNDER_TEST_BOTH,
    UNDER_TEST_UNKNOWN,
    EyeCoverResult,
)
from src.readiness_rules import ReadinessState
from src.sloan_stt import (
    UNK_TOKEN,
    LetterTrial,
    SloanLetterListener,
    load_recognizer,
    resolve_sloan_root,
)

PHASE_WAITING = "WAITING"
PHASE_READY_HOLD = "READY_HOLD"
PHASE_SPELLING = "SPELLING"
PHASE_TRIAL_DONE = "TRIAL_DONE"


@dataclass
class SpellSessionState:
    phase: str = PHASE_WAITING
    under_test: str = UNDER_TEST_BOTH
    target: list[str] = field(default_factory=list)
    heard: list[str] = field(default_factory=list)
    score_correct: int | None = None
    score_total: int | None = None
    last_letter: str = ""
    last_conf: float = 0.0
    last_reliable: bool = False
    coaching_vi: str = ""
    mic_on: bool = False
    mic_name: str = ""
    enabled: bool = False
    error: str | None = None


class SpellSession:
    """Gates mic listening on readiness; aborts when pose/cover breaks."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        spell = dict(cfg.get("spell") or {})
        self.enabled = bool(spell.get("enabled", False))
        self.board_len = int(spell.get("board_len", 5))
        self.auto_start = bool(spell.get("auto_start_on_ready", True))
        self.ready_delay = float(spell.get("ready_delay_seconds", 0.35))
        # Don't kill a trial on 1-frame READY / peek flicker
        self.lost_ready_grace = float(spell.get("lost_ready_grace_seconds", 0.7))
        self.peek_grace = float(spell.get("peek_grace_seconds", 0.6))
        self.side_grace = float(spell.get("side_change_grace_seconds", 0.6))
        self.timeout_seconds = float(spell.get("timeout_seconds", 60))
        self.soft_align = bool(spell.get("soft_align", True))

        root = resolve_sloan_root(spell.get("sloan_root"))
        self._listener: SloanLetterListener | None = None
        self._trial = LetterTrial(
            soft_align=self.soft_align,
        )
        self._trial.reset_board(self.board_len)

        self._phase = PHASE_WAITING
        self._ready_since: float | None = None
        self._not_ready_since: float | None = None
        self._peek_since: float | None = None
        self._side_mismatch_since: float | None = None
        self._spell_since: float | None = None
        self._snapshot_under: str = UNDER_TEST_BOTH
        self._error: str | None = None
        self._user_muted = False
        self._last_ev_letter = ""
        self._last_ev_conf = 0.0
        self._last_ev_reliable = False
        self._coaching = ""
        self._uncertain_flash = ""
        self._mic_name = ""

        if self.enabled:
            try:
                audio_url = str(spell.get("mic_url") or "").strip() or None
                device = None
                if audio_url:
                    self._mic_name = f"Network mic {audio_url}"
                else:
                    from src.sloan_stt import resolve_mic_arg

                    mic_prefs = spell.get("mic_match")
                    if isinstance(mic_prefs, str):
                        mic_prefs = [mic_prefs]
                    device, name = resolve_mic_arg(
                        spell.get("mic_device"),
                        prefer=list(mic_prefs) if mic_prefs else None,
                    )
                    self._mic_name = name

                recognizer = load_recognizer(root)
                self._listener = SloanLetterListener(
                    recognizer=recognizer,
                    sloan_root=root,
                    min_confidence=float(spell.get("min_confidence", 0.55)),
                    min_margin=float(spell.get("min_margin", 0.05)),
                    energy_threshold=float(spell.get("energy_threshold", 0.008)),
                    silence_duration=float(spell.get("silence_duration", 0.18)),
                    device=device,
                    audio_url=audio_url,
                    audio_sample_rate=int(spell.get("mic_sample_rate", 48000)),
                )
                self._listener.start()
                self._mic_name = self._listener.device_name or self._mic_name
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
                self.enabled = False
                self._listener = None

    def close(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def handle_key(self, key: int) -> None:
        if not self.enabled:
            return
        if key in (ord("n"), ord("N")):
            self._trial.reset_board(self.board_len)
            if self._phase == PHASE_TRIAL_DONE:
                self._phase = PHASE_SPELLING
                self._spell_since = time.time()
                self._set_mic(True)
            self._refresh_coaching()
        elif key in (ord("m"), ord("M")):
            self._user_muted = not self._user_muted
            if self._phase == PHASE_SPELLING:
                self._set_mic(not self._user_muted)
            self._refresh_coaching()
        elif key in (ord("r"), ord("R")):
            self._restart_trial()

    def on_frame(
        self,
        state: ReadinessState,
        eye_cover: EyeCoverResult | None,
        timestamp: float | None = None,
    ) -> SpellSessionState:
        now = timestamp if timestamp is not None else time.time()
        if not self.enabled:
            return SpellSessionState(
                phase=PHASE_WAITING,
                enabled=False,
                error=self._error,
                coaching_vi=self._error or "",
            )

        peek = self._peek_block(state, eye_cover)
        under = state.under_test if state.check_eyes else UNDER_TEST_BOTH

        # Level-triggered: re-arm READY hold whenever STATUS is READY.
        # Rising-edge-only left SPELL WAITING stuck after abort-while-still-READY.
        if state.ready:
            self._not_ready_since = None
            if self._phase in (PHASE_WAITING, PHASE_TRIAL_DONE):
                self._phase = PHASE_READY_HOLD
            if self._phase == PHASE_READY_HOLD and self._ready_since is None:
                self._ready_since = now
        else:
            if self._not_ready_since is None:
                self._not_ready_since = now
            lost_for = now - self._not_ready_since
            if lost_for >= self.lost_ready_grace:
                self._ready_since = None
                if self._phase in (PHASE_READY_HOLD, PHASE_SPELLING):
                    self._abort(now, reason="lost_ready")

        # Spelling aborts — require sustained bad state, not 1-frame flicker
        if self._phase == PHASE_SPELLING:
            if peek or under == UNDER_TEST_UNKNOWN:
                if self._peek_since is None:
                    self._peek_since = now
                elif (now - self._peek_since) >= self.peek_grace:
                    self._abort(now, reason="eye_pose")
            else:
                self._peek_since = None

            if (
                self._phase == PHASE_SPELLING
                and state.check_eyes
                and under != UNDER_TEST_UNKNOWN
                and under != self._snapshot_under
            ):
                if self._side_mismatch_since is None:
                    self._side_mismatch_since = now
                elif (now - self._side_mismatch_since) >= self.side_grace:
                    self._abort(now, reason="side_change")
            else:
                if under == self._snapshot_under or under == UNDER_TEST_UNKNOWN:
                    self._side_mismatch_since = None

            if (
                self._phase == PHASE_SPELLING
                and self._spell_since is not None
                and (now - self._spell_since) >= self.timeout_seconds
            ):
                self._finish_trial(under)

        # Auto-start shortly after READY. Peek is already gated by readiness
        # (ready ⇒ no sustained peek), so don't block again here.
        if (
            self._phase == PHASE_READY_HOLD
            and state.ready
            and self.auto_start
            and self._ready_since is not None
            and (now - self._ready_since) >= self.ready_delay
            and under != UNDER_TEST_UNKNOWN
        ):
            self._start_trial(under, now)

        # Consume mic events
        if self._listener is not None and self._phase == PHASE_SPELLING:
            for ev in self._listener.poll():
                self._on_heard(ev, under)

        self._refresh_coaching(under=under, peek=peek, ready=state.ready)
        return self.snapshot(under)

    def snapshot(self, under: str | None = None) -> SpellSessionState:
        correct, total = self._trial.score()
        score_c = correct if self._phase == PHASE_TRIAL_DONE else None
        score_t = total if self._phase == PHASE_TRIAL_DONE else None
        mic = bool(self._listener and self._listener.is_enabled())
        return SpellSessionState(
            phase=self._phase,
            under_test=under if under is not None else self._snapshot_under,
            target=list(self._trial.target),
            heard=list(self._trial.heard),
            score_correct=score_c,
            score_total=score_t,
            last_letter=self._last_ev_letter or self._uncertain_flash,
            last_conf=self._last_ev_conf,
            last_reliable=self._last_ev_reliable,
            coaching_vi=self._coaching,
            mic_on=mic,
            mic_name=self._mic_name
            or (self._listener.device_name if self._listener is not None else ""),
            enabled=self.enabled,
            error=self._error
            or (self._listener.error if self._listener is not None else None),
        )

    def _set_mic(self, on: bool) -> None:
        if self._listener is None:
            return
        if self._user_muted:
            self._listener.set_enabled(False)
        else:
            self._listener.set_enabled(on)

    def _start_trial(self, under: str, now: float) -> None:
        self._snapshot_under = under
        if not self._trial.target:
            self._trial.reset_board(self.board_len)
        else:
            self._trial.clear_heard()
        self._phase = PHASE_SPELLING
        self._spell_since = now
        self._peek_since = None
        self._side_mismatch_since = None
        self._user_muted = False
        self._uncertain_flash = ""
        self._set_mic(True)

    def _restart_trial(self) -> None:
        if self._phase not in (PHASE_SPELLING, PHASE_TRIAL_DONE, PHASE_READY_HOLD):
            return
        self._trial.reset_board(self.board_len)
        self._phase = PHASE_SPELLING
        self._spell_since = time.time()
        self._peek_since = None
        self._side_mismatch_since = None
        self._user_muted = False
        self._uncertain_flash = ""
        self._set_mic(True)

    def _abort(self, now: float, reason: str) -> None:
        del now, reason  # kept for logging callers
        self._set_mic(False)
        self._phase = PHASE_WAITING
        self._spell_since = None
        self._ready_since = None
        self._peek_since = None
        self._side_mismatch_since = None
        self._trial.clear_heard()
        self._uncertain_flash = ""

    def _finish_trial(self, under: str) -> None:
        self._set_mic(False)
        self._phase = PHASE_TRIAL_DONE
        self._snapshot_under = under
        self._spell_since = None

    def _on_heard(self, ev: Any, under: str) -> None:
        self._last_ev_letter = ev.letter
        self._last_ev_conf = ev.confidence
        self._last_ev_reliable = bool(ev.reliable)
        if not ev.reliable or ev.letter == UNK_TOKEN:
            self._uncertain_flash = "?"
            return
        self._uncertain_flash = ""
        action = self._trial.apply_prediction(
            ev.letter,
            reliable=True,
            topk=ev.topk,
        )
        if action == "skip":
            return
        if action == "done":
            self._finish_trial(under)

    def _peek_block(
        self, state: ReadinessState, eye_cover: EyeCoverResult | None
    ) -> bool:
        if not state.check_eyes or eye_cover is None:
            return False
        if eye_cover.under_test != UNDER_TEST_BOTH:
            return False
        return (
            eye_cover.left.state == EYE_STATE_PARTIAL
            or eye_cover.right.state == EYE_STATE_PARTIAL
        )

    def _refresh_coaching(
        self,
        *,
        under: str | None = None,
        peek: bool = False,
        ready: bool = False,
    ) -> None:
        u = under or self._snapshot_under
        if self._error:
            self._coaching = f"STT error: {self._error}"
            return
        if self._phase == PHASE_WAITING:
            if peek:
                self._coaching = "Cover eye fully — no gaps"
            elif ready:
                self._coaching = "READY — starting spell..."
            else:
                self._coaching = "Wait for READY to start spelling"
            return
        if self._phase == PHASE_READY_HOLD:
            self._coaching = "READY — starting mic..."
            return
        if self._phase == PHASE_SPELLING:
            mute = " (MIC OFF — press m)" if self._user_muted else ""
            self._coaching = (
                f"Spell letters (VN: xe/de/ho) | eye {u}{mute} | "
                "khong thay=X | n=new m=mic r=retry"
            )
            return
        if self._phase == PHASE_TRIAL_DONE:
            c, t = self._trial.score()
            self._coaching = f"Score {c}/{t} — eye {u} | n=new board r=retry"
            return
        self._coaching = ""
