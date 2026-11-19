"""DMN-driven exam orchestrator (B3–B10)."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import HttpUrl

from ac.audio_player import AudioPlayer, resolve_voice_gender
from ac.cccd_qr import CccdQrPipeline
from ac.config import AppConfig
from ac.display_client import DisplayClient
from ac.dmn_engine import DmnEngine
from ac.face_client import FaceClient, FaceMatchResult
from ac.face_sync import sync_vectordb_to_device
from ac.hospital_client import HospitalClient
from ac.http_callback import HttpCallbackClient
from ac.letter_clip import LetterClipRecorder
from ac.media_client import MediaClient
from ac.models import (
    ActionName,
    ProtocolInfo,
    ResultsCallback,
    SessionState,
    SessionStatus,
)
from ac.readiness_bridge import (
    ExclusiveInputSttBridge,
    LETTER_RECENT_WINDOW,
    MockReadinessBridge,
    MockSttBridge,
    ReadinessBridge,
    SloanSttBridge,
    SttBridge,
    SttResult,
    UiSttBridge,
    random_letters,
)
from ac.scoring import score_eye, row_passed, vn_over_10
from ac.session_manager import ExamSession, SessionManager, TrialRecord
from ac.age_va import BinarySearchState, SmartRangeSearchState, start_logmar_from_dob
from ac.vector_face_client import VectorFaceClient

logger = logging.getLogger(__name__)


class StimulusNotReady(RuntimeError):
    """The patient display did not confirm the active stimulus in time."""


class Orchestrator:
    def __init__(
        self,
        cfg: AppConfig,
        sessions: SessionManager,
        dmn: DmnEngine,
        display: DisplayClient,
        audio: AudioPlayer,
        readiness: ReadinessBridge,
        stt: SttBridge,
        http: HttpCallbackClient,
        publish_status: Any,
        face: FaceClient | None = None,
        face_vector: VectorFaceClient | None = None,
        media: MediaClient | None = None,
    ) -> None:
        self.cfg = cfg
        self.sessions = sessions
        self.dmn = dmn
        self.display = display
        self.audio = audio
        self.readiness = readiness
        self.stt = stt
        self.http = http
        self.publish_status = publish_status
        self.face = face or FaceClient()
        self.face_vector = face_vector or VectorFaceClient()
        self.media = media
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._row_shown = False
        self._listening = False
        self._confirm_done = False
        self._readiness_forced = False
        self._letter_clip = LetterClipRecorder(
            input_device=str(getattr(cfg.audio, "input_device", "") or ""),
            shared_microphone=getattr(self.stt, "shared_microphone", None),
        )
        self._prematch: FaceMatchResult | None = None

    def _allow_skip(self) -> bool:
        return bool(self.cfg.protocol.allow_step_skip)

    def _speaker_v1(self) -> bool:
        ui = getattr(self.cfg, "ui", None)
        return str(getattr(ui, "patient_flow", "") or "").strip().lower() == "speaker_v1"

    def _chart_cv_coaching(self) -> bool:
        ui = getattr(self.cfg, "ui", None)
        return bool(getattr(ui, "chart_cv_coaching", False))

    @staticmethod
    def _reset_shown_letter_history(session: ExamSession) -> None:
        session.shown_letter_history = []

    @staticmethod
    def _remember_shown_letters(session: ExamSession, letters: list[str]) -> None:
        hist = list(session.shown_letter_history)
        for raw in letters:
            letter = str(raw or "").strip().upper()
            if letter:
                hist.append(letter)
        session.shown_letter_history = hist[-LETTER_RECENT_WINDOW:]

    def _pick_row_letters(self, session: ExamSession) -> list[str]:
        avoid = list(session.shown_letter_history[-LETTER_RECENT_WINDOW:])
        letters = random_letters(self._row_letter_goal(session), recent=avoid)
        self._remember_shown_letters(session, letters)
        return letters

    def _prepare_speaker_session(self, session: ExamSession) -> None:
        session.speaker_flow = self._speaker_v1()
        session.patient_dob = session.patient_dob or getattr(session.start, "dob", None)
        self._reset_shown_letter_history(session)
        if not session.speaker_flow:
            return
        order = session.eyes_order()
        session.eye_side = order[0]
        session.under_test = order[0].upper()
        if isinstance(self.readiness, MockReadinessBridge):
            self.readiness.force_under_test = session.eye_side.upper()

    def _seed_eye_search(self, session: ExamSession) -> None:
        proto = self.cfg.protocol
        rows = list(proto.row_logmars)
        dob = session.patient_dob or getattr(session.start, "dob", None)
        start = (
            start_logmar_from_dob(dob, rows)
            if session.speaker_flow and proto.start_from_age_norm
            else float(proto.start_logmar)
        )
        seed_reason = "age" if session.speaker_flow and proto.start_from_age_norm else "config"
        if (
            session.speaker_flow
            and proto.uses_smart_range_testing()
            and session.eye_side == "left"
        ):
            right = score_eye(session.trials, "right", max_misses=proto.max_misses)
            if right is not None:
                right_idx = self._nearest_logmar_index(float(right.logmar))
                easier_steps = max(0, int(proto.left_eye_start_easier_steps))
                start = float(rows[max(0, right_idx - easier_steps)])
                seed_reason = "right_eye_easier"
        session.current_logmar = start
        session.row_index = self._nearest_logmar_index(start)
        if session.speaker_flow and proto.uses_smart_range_testing():
            session.row_search = SmartRangeSearchState.seed(
                len(rows), session.row_index
            )
        elif session.speaker_flow and proto.uses_binary_row_search():
            session.row_search = BinarySearchState.seed(len(rows), session.row_index)
        else:
            session.row_search = None
        logger.info(
            "Eye search eye=%s start=%s idx=%s dob=%s mode=%s reason=%s",
            session.eye_side,
            session.current_logmar,
            session.row_index,
            dob,
            type(session.row_search).__name__ if session.row_search else "sequential",
            seed_reason,
        )

    def _wait_gate(
        self,
        session: ExamSession,
        *,
        timeout: float,
        predicate: Any,
        on_tick: Any = None,
    ) -> str:
        deadline = time.monotonic() + max(0.2, float(timeout))
        while time.monotonic() < deadline and not self._stop.is_set() and not session.cancelled:
            if self._allow_skip() and self.display.consume_ui_action("skip_step"):
                return "skip"
            snap = self.readiness.snapshot()
            if on_tick:
                on_tick(snap)
            if predicate(snap):
                return "ok"
            time.sleep(0.05)
        if self._stop.is_set() or session.cancelled:
            return "stop"
        return "timeout"

    def _mark_unscored_letter(self, session: ExamSession) -> None:
        session.last_stt_match = False
        session.heard_letters.append("?")
        session.letter_replacements = 0

    def _replace_unscored_letter(self, session: ExamSession, idx: int) -> None:
        """Replace an unclear item in place so it never enters scoring."""
        proto = self.cfg.protocol
        if proto.uses_smart_range_testing():
            max_replacements = max(0, int(proto.max_letter_replacements))
            if session.letter_replacements >= max_replacements:
                logger.info(
                    "Letter replacement limit reached eye=%s idx=%s limit=%s; score miss",
                    session.eye_side,
                    idx,
                    max_replacements,
                )
                session.last_stt_match = False
                session.heard_letters.append("?")
                session.letter_replacements = 0
                return
        recent = list(session.shown_letter_history[-LETTER_RECENT_WINDOW:])
        if 0 <= idx < len(session.current_letters):
            recent.append(session.current_letters[idx])
            replacement = random_letters(1, recent=recent)[0]
            session.current_letters[idx] = replacement
            self._remember_shown_letters(session, [replacement])
        if proto.uses_smart_range_testing():
            session.letter_replacements += 1
            logger.info(
                "Letter replacement eye=%s idx=%s count=%s/%s target=%s",
                session.eye_side,
                idx,
                session.letter_replacements,
                max(0, int(proto.max_letter_replacements)),
                session.current_letters[idx] if 0 <= idx < len(session.current_letters) else "?",
            )
        session.last_stt_match = False

    def _letter_clip_enabled(self) -> bool:
        return self._speaker_v1() and (
            isinstance(self.stt, SloanSttBridge)
            or (isinstance(self.stt, ExclusiveInputSttBridge) and not self._tablet_mode())
        )

    def _tablet_mode(self) -> bool:
        return isinstance(self.stt, UiSttBridge) or (
            isinstance(self.stt, ExclusiveInputSttBridge)
            and self.display.hub.input_mode == "tablet"
        )

    def _start_letter_clip(self) -> None:
        if not self._letter_clip_enabled():
            return
        self._letter_clip.start()

    def _discard_letter_clip(self) -> None:
        try:
            self._letter_clip.discard()
        except Exception:  # noqa: BLE001
            logger.exception("Letter clip discard failed")

    def _save_letter_clip(
        self,
        session: ExamSession,
        *,
        target: str,
        logmar: float,
    ) -> None:
        if not self._letter_clip.running:
            return
        session.letter_clip_index += 1
        seq = session.letter_clip_index
        eye = str(session.eye_side or "eye")
        va = vn_over_10(10 ** (-float(logmar))).replace("/", "-")
        tmp = (
            self.sessions.journal_dir
            / session.start.session_id
            / "letters"
            / f"{seq:02d}_{eye}_{target}_{va}.wav"
        )
        try:
            duration = self._letter_clip.save_wav(tmp)
        except Exception:  # noqa: BLE001
            logger.exception("Letter clip save failed")
            self._discard_letter_clip()
            return
        if duration <= 0:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            return
        ms = int(round(duration * 1000.0))
        final = tmp.with_name(f"{seq:02d}_{eye}_{target}_{va}_{ms}ms.wav")
        try:
            tmp.rename(final)
        except Exception:  # noqa: BLE001
            logger.exception("Letter clip rename failed; left at %s", tmp)

    @staticmethod
    def _stt_is_skip(result: Any) -> bool:
        letter = str(getattr(result, "letter", "") or "").strip().upper()
        raw = str(getattr(result, "raw", "") or "").strip().upper()
        return letter in {"SKIP", "*"} or raw in {"SKIP", "BO_QUA"}

    def start_session_async(
        self,
        session: ExamSession,
        *,
        prematch: FaceMatchResult | None = None,
    ) -> None:
        self._stop.clear()
        self.display.hub.reset_input_mode(self.cfg.ui.input_mode)
        self._row_shown = False
        self._listening = False
        self._confirm_done = False
        self._readiness_forced = False
        self._prematch = prematch
        self._discard_letter_clip()
        if isinstance(self.readiness, MockReadinessBridge):
            self.readiness.reset_timer()
            self.readiness.force_under_test = session.eye_side.upper()
        if isinstance(self.stt, (UiSttBridge, ExclusiveInputSttBridge)):
            self.stt.bind(self.display.hub, stop_flag=self._stop)
        self._thread = threading.Thread(
            target=self._run,
            args=(session.start.session_id,),
            name=f"orch-{session.start.session_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()
        self.audio.stop()
        self._discard_letter_clip()
        try:
            self.readiness.stop()
        except Exception:  # noqa: BLE001
            logger.exception("readiness.stop failed")

    def abort_display(self, reason: str | None = None) -> None:
        """Return patient displays home when a cancellation has no session object."""
        self._abort_session_ui(None, reason=reason)

    def _abort_session_ui(self, session: ExamSession | None, reason: str | None = None) -> None:
        self.audio.stop()
        self._discard_letter_clip()
        try:
            self.readiness.stop()
        except Exception:  # noqa: BLE001
            logger.exception("readiness.stop failed")
        logger.info(
            "Reset patient displays after cancellation session_id=%s reason=%s",
            session.start.session_id if session else "-",
            reason,
        )
        try:
            self.display.show_station_home()
        except Exception:  # noqa: BLE001
            logger.exception("abort station home reset failed")
        if session:
            self.sessions.set_state(
                SessionState.CANCELLED,
                step_id="cancel",
                message_vi=None,
            )
            self._publish(session)

    def _publish(self, session: ExamSession) -> None:
        status = SessionStatus(
            session_id=session.start.session_id,
            station_id=session.station_id,
            state=session.state,
            step_id=session.step_id,
            message_vi=session.message_vi,
            queue_number=session.start.queue_number,
        )
        self.publish_status(status)

    def _facts(self, session: ExamSession) -> dict[str, Any]:
        proto = self.cfg.protocol
        row_complete = self._row_complete(session)
        eye_complete = session.eye_complete
        need_listen = self._row_shown and not row_complete
        snap = self.readiness.snapshot()
        session.readiness_ok = bool(snap.ready or self._readiness_forced)
        session.under_test = snap.under_test
        # Recognizer already applies the active head's confidence threshold,
        # per-letter override and margin. Do not apply a second global DMN gate.
        conf_ok = bool(session.last_stt_reliable)
        return {
            "session_state": session.state.value,
            "readiness_ok": session.readiness_ok,
            "all_eyes_done": session.all_eyes_done,
            "cancelled": session.cancelled or self._stop.is_set(),
            "row_complete": row_complete,
            "pass_complete": False,
            "eye_complete": eye_complete and not row_complete,
            "need_listen": need_listen,
            "stt_match": bool(session.last_stt_match),
            "confidence_ok": conf_ok,
            "eye_side": session.eye_side,
            "pass_index": session.pass_index,
            "row_index": session.row_index,
            "stt_confidence": session.last_stt_confidence,
        }

    def _nearest_logmar_index(self, logmar: float) -> int:
        rows = self.cfg.protocol.row_logmars
        return min(range(len(rows)), key=lambda i: abs(rows[i] - logmar))

    def _step_logmar(self, current: float, *, smaller: bool) -> float | None:
        """Move one step; smaller letters = lower logMAR. None if at end."""
        rows = sorted(self.cfg.protocol.row_logmars, reverse=True)  # 0.5 … -0.2
        # ensure current snaps to grid
        idx = min(range(len(rows)), key=lambda i: abs(rows[i] - current))
        if smaller:
            # toward end of list (lower logmar)
            if idx >= len(rows) - 1:
                return None
            return rows[idx + 1]
        if idx <= 0:
            return None
        return rows[idx - 1]

    def _row_letter_goal(self, session: ExamSession) -> int:
        proto = self.cfg.protocol
        if proto.uses_smart_range_testing() and isinstance(
            session.row_search, SmartRangeSearchState
        ):
            if session.row_search.is_verify:
                return max(3, int(proto.smart_verify_letters))
            return max(
                2,
                int(proto.smart_range_initial_letters)
                + int(proto.smart_range_tiebreak_letters),
            )
        if not proto.adaptive_row_testing:
            return max(1, int(proto.letters_per_row))
        if session.verifying_smaller_row:
            return max(1, int(proto.adaptive_verify_letters))
        return max(
            1,
            int(proto.adaptive_initial_letters) + int(proto.adaptive_tiebreak_letters),
        )

    def _row_progress_goal(self, session: ExamSession) -> int:
        """Visible goal: 2 first, reveal the range tiebreak only on a 1/2 split."""
        proto = self.cfg.protocol
        search = session.row_search
        if proto.uses_smart_range_testing() and isinstance(
            search, SmartRangeSearchState
        ):
            if search.is_verify:
                return max(3, int(proto.smart_verify_letters))
            initial = max(2, int(proto.smart_range_initial_letters))
            if len(session.heard_letters) < initial:
                return initial
            correct = self._correct_answers(session)
            return initial + 1 if 0 < correct < initial else initial
        return self._row_letter_goal(session)

    @staticmethod
    def _acuity_ui(*, left: Any, right: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, scored in (("right", right), ("left", left)):
            if scored is None:
                continue
            out[key] = (
                scored.model_dump(mode="json") if hasattr(scored, "model_dump") else scored
            )
        return out

    @staticmethod
    def _correct_answers(session: ExamSession) -> int:
        attempted = session.current_letters[: len(session.heard_letters)]
        return sum(
            1
            for target, heard in zip(attempted, session.heard_letters, strict=False)
            if target.upper() == heard.upper()
        )

    def _row_complete(self, session: ExamSession) -> bool:
        if not self._row_shown:
            return False
        proto = self.cfg.protocol
        heard_n = len(session.heard_letters)
        search = session.row_search
        if proto.uses_smart_range_testing() and isinstance(
            search, SmartRangeSearchState
        ):
            correct = self._correct_answers(session)
            wrong = heard_n - correct
            if search.is_verify:
                return correct >= 3 or wrong >= 3 or heard_n >= max(
                    3, int(proto.smart_verify_letters)
                )
            initial = max(2, int(proto.smart_range_initial_letters))
            if heard_n < initial:
                return False
            if correct in (0, initial):
                return True
            return heard_n >= initial + max(1, int(proto.smart_range_tiebreak_letters))
        if not proto.adaptive_row_testing:
            return heard_n >= self._row_letter_goal(session)
        if session.verifying_smaller_row:
            return heard_n >= self._row_letter_goal(session)
        # A correct answer at any of the first three attempts advances at once.
        if self._correct_answers(session) > 0:
            return True
        return heard_n >= self._row_letter_goal(session)

    def _run(self, session_id: str) -> None:
        try:
            self._loop(session_id)
        except StimulusNotReady:
            logger.warning("Patient display did not become ready; stopping exam session")
            session = self.sessions.active
            if session and session.start.session_id == session_id:
                self.display.show_message(
                    "Màn hình đo chưa sẵn sàng. Vui lòng báo nhân viên hỗ trợ."
                )
                self.sessions.set_state(
                    SessionState.FAILED,
                    step_id="display_not_ready",
                    message_vi="Màn hình đo chưa sẵn sàng",
                )
                self._publish(session)
                self.sessions.clear_if_terminal()
        except Exception:  # noqa: BLE001
            logger.exception("Orchestrator crashed")
            session = self.sessions.active
            if session and session.start.session_id == session_id:
                self.sessions.set_state(SessionState.FAILED, step_id="error", message_vi="Lỗi điều khiển phiên đo")
                self._publish(session)
                self.sessions.clear_if_terminal()

    def _apply_session_voice(
        self,
        *,
        patient_sex: str | None = None,
        frappe_setting: str | None = None,
    ) -> None:
        clinic = getattr(getattr(self.cfg, "voice", None), "gender", "auto")
        gender = resolve_voice_gender(
            patient_sex=patient_sex,
            frappe_setting=frappe_setting,
            clinic_setting=clinic,
        )
        self.audio.set_gender(gender)
        logger.info(
            "Voice gender=%s (patient_sex=%s frappe=%s clinic=%s)",
            gender or "default",
            patient_sex,
            frappe_setting,
            clinic,
        )

    def _loop(self, session_id: str) -> None:
        session = self.sessions.active
        if not session or session.start.session_id != session_id:
            return
        self._apply_session_voice()
        self._prepare_speaker_session(session)
        # Keep both hospital workflows on the same station controller: Trưng Vương
        # identifies through Face ID; Quân y starts the selected patient directly.
        if self.face.enabled:
            ready = self._run_face_gate(session)
        else:
            ready = self._run_direct_patient_start(session)
        if not ready:
            if session.cancelled or self._stop.is_set() or session.state == SessionState.CANCELLED:
                self._abort_session_ui(session)
            self.sessions.clear_if_terminal()
            return

        # accepted → SHOW_QUEUE …
        while True:
            session = self.sessions.active
            if not session or session.start.session_id != session_id:
                return
            if (
                session.cancelled
                or self._stop.is_set()
                or session.state == SessionState.CANCELLED
            ):
                self._abort_session_ui(session)
                self.sessions.clear_if_terminal()
                return
            if session.state in (SessionState.COMPLETED, SessionState.FAILED):
                self.sessions.clear_if_terminal()
                return

            decision = self.dmn.decide_next_action(self._facts(session))
            logger.info(
                "DMN action=%s step=%s state=%s eye=%s pass=%s row=%s heard=%s",
                decision.action,
                decision.step_id,
                session.state.value,
                session.eye_side,
                session.pass_index,
                session.row_index,
                session.heard_letters,
            )
            done = self._execute(session, decision.action, decision.step_id)
            if done:
                self.sessions.clear_if_terminal()
                return
            time.sleep(0.05)

    def _run_direct_patient_start(self, session: ExamSession) -> bool:
        """Start a desk-selected patient without Face ID or a second measurement."""
        name = (session.start.patient_name or session.face_name or session.start.patient_id).strip()
        session.face_name = name
        # The desk already created the Vision Measurement and uses its identifier
        # as the MQTT session ID; do not create a second record for this workflow.
        session.vision_measurement_id = session.start.session_id
        self._apply_session_voice(patient_sex=session.start.sex)
        self.display.show_welcome(name, auto_continue_seconds=3.0)
        self.sessions.set_state(
            SessionState.GUIDING,
            step_id="patient_selected",
            message_vi=f"Bắt đầu đo cho {name}",
        )
        self._publish(session)
        if self._wait_gate(session, timeout=3.0, predicate=lambda _snap: False) == "stop":
            return False
        if session.cancelled or self._stop.is_set():
            return False

        self.display.show_input_mode_choice(self.cfg.ui.input_mode)
        self.audio.play_step("b1_input_mode_choice")
        choice = self.display.wait_ui_event(
            {"select_input_mode"},
            timeout=(
                self.audio.playback_remaining_seconds()
                + self.cfg.ui.input_mode_choice_seconds
            ),
            stop_flag=self._stop,
        )
        if session.cancelled or self._stop.is_set():
            self.display.finish_input_mode_choice()
            return False
        chosen_mode = self.display.finish_input_mode_choice()
        if choice is not None:
            self.audio.stop()
            instruction_step = (
                "b1_input_mode_tablet" if chosen_mode == "tablet" else "b1_input_mode_speak"
            )
            self.audio.play_step(instruction_step)
            self.audio.wait_done(timeout=30.0)
            remaining_audio = self.audio.playback_remaining_seconds()
            if remaining_audio > 0:
                time.sleep(remaining_audio)
        else:
            logger.info(
                "Input mode choice timed out; using configured default %s", chosen_mode
            )
        return not (session.cancelled or self._stop.is_set())

    def _run_face_gate(self, session: ExamSession) -> bool:
        """B1 Face ID: identify → hospital lookup → welcome → service menu.

        Gallery is appointment-gated (desk enrolls); strangers are sent to reception.
        Returns False if the session should stop (timeout / error / cancel).
        """
        face_gate_started = time.monotonic()
        face_cfg = self.cfg.bridges.face
        face_gate_started_at = time.time()
        hospital = HospitalClient(
            self.cfg.hospital.base_url,
            timeout_seconds=self.cfg.hospital.timeout_seconds,
            api_key=self.cfg.hospital.api_key,
            api_secret=self.cfg.hospital.api_secret,
        )
        desk_msg = (
            "Bạn không có trong danh sách hẹn hôm nay. "
            "Vui lòng đăng ký tại quầy tiếp nhận."
        )
        scan_msg = "Vui lòng nhìn vào máy nhận diện khuôn mặt để xác nhận bệnh nhân."
        prematch = self._prematch
        self._prematch = None
        skip_identify = bool(prematch and prematch.matched)
        logger.info(
            "FACE_GATE_START session_id=%s prematch=%s face_mode=%s timeout_s=%.1f",
            session.start.session_id,
            skip_identify,
            face_cfg.mode,
            float(face_cfg.timeout_seconds),
        )

        if not skip_identify:
            self.display.show_message(
                scan_msg,
                allow_skip=self._allow_skip(),
                skip_label="Bỏ qua Face",
                scene="face",
            )
            step = self.audio.play_step("b1_face_scan")
            msg = step.get("message_vi") or scan_msg
            self.sessions.set_state(SessionState.PREPARING, step_id="b1_face_scan", message_vi=msg)
            self._publish(session)

        if self._allow_skip():
            self.display.drain_ui_actions({"skip_step", "skip_letter"})

        vdb = self.cfg.face_vectordb
        # Today's gallery is maintained by the push job and reconciliation loop.
        # A full sync here delays the scan and can re-upload the same face.
        if (not skip_identify) and vdb.enabled and vdb.sync_before_identify:
            if not vdb.sync_today_appointments_only and self.face_vector.enabled:
                logger.info("Syncing VectorDB gallery onto Face ID before scan…")
                sync_vectordb_to_device(
                    self.face_vector,
                    self.face,
                    max_faces=vdb.max_faces,
                    device_face_backupnum=vdb.device_face_backupnum,
                    media=self.media,
                )

        if session.cancelled or self._stop.is_set():
            logger.info("Face gate aborted during gallery sync")
            return False

        face_phase = {
            "stranger": False,
            "skipped": False,
        }
        result: FaceMatchResult | None = None

        if skip_identify:
            result = prematch
            logger.info(
                "Face gate using walk-in prematch enroll_id=%s name=%s",
                getattr(prematch, "enroll_id", None),
                getattr(prematch, "name", None),
            )
        else:
            face_abort = threading.Event()

            class _StopOrSkip:
                def is_set(inner_self) -> bool:
                    return self._stop.is_set() or face_abort.is_set()

            stop_or_skip = _StopOrSkip()

            def _on_stranger(_result: FaceMatchResult) -> None:
                if face_phase["stranger"]:
                    return
                face_phase["stranger"] = True
                logger.info("Face stranger — not in today's appointment gallery")
                self.display.show_message(
                    desk_msg,
                    allow_skip=self._allow_skip(),
                    skip_label="Bỏ qua Face",
                    scene="nomatch",
                )
                self.sessions.set_state(
                    SessionState.PREPARING,
                    step_id="b1_face_not_in_today",
                    message_vi=desk_msg,
                )
                self._publish(session)
                face_abort.set()

            waiting_msg = "Đang chờ nhận diện… Vui lòng nhìn thẳng vào máy nhận diện khuôn mặt."

            def _on_tick() -> None:
                if face_phase["stranger"]:
                    return
                self.display.show_message(
                    waiting_msg,
                    allow_skip=self._allow_skip(),
                    skip_label="Bỏ qua Face",
                    scene="face",
                )

            result_holder: dict[str, FaceMatchResult | None] = {"result": None}

            def _poll() -> None:
                result_holder["result"] = self.face.wait_for_identify(
                    timeout_seconds=face_cfg.timeout_seconds,
                    stop_flag=stop_or_skip,
                    on_stranger=_on_stranger,
                    on_tick=_on_tick,
                    # A scan during the prompt/device setup still belongs to
                    # this session; old scans before session start do not.
                    accept_existing_recent=True,
                    min_event_epoch=face_gate_started_at,
                    sync_clock=False,
                )

            poll_thread = threading.Thread(target=_poll, name="face-poll", daemon=True)
            poll_thread.start()

            poll_deadline = time.time() + face_cfg.timeout_seconds
            while poll_thread.is_alive() and time.time() < poll_deadline:
                if self._stop.is_set() or session.cancelled:
                    break
                if self._allow_skip() and self.display.consume_ui_action("skip_step"):
                    logger.info("Face gate skipped by operator")
                    face_phase["skipped"] = True
                    face_abort.set()
                    break
                time.sleep(0.05)

            join_timeout = 2.0 if (session.cancelled or self._stop.is_set()) else (face_cfg.timeout_seconds + 5)
            poll_thread.join(timeout=join_timeout)
            result = result_holder["result"]
            logger.info(
                "FACE_GATE_RESULT matched=%s status=%s enroll_id=%s elapsed_ms=%.0f",
                bool(result and result.matched),
                getattr(result, "status", None),
                getattr(result, "enroll_id", None),
                (time.monotonic() - face_gate_started) * 1000.0,
            )

        if session.cancelled or self._stop.is_set():
            logger.info("Face gate aborted by cancel")
            return False

        if face_phase.get("skipped"):
            pid = str(session.start.patient_id or "").strip()
            if not pid:
                self.sessions.set_state(
                    SessionState.FAILED,
                    step_id="b1_face_skipped_no_patient",
                    message_vi="Phiên đo không có bệnh nhân; vui lòng bắt đầu lại từ Trạm điều dưỡng.",
                )
                self._publish(session)
                return False
            result = FaceMatchResult(
                matched=True,
                patient_id=pid,
                name=(session.start.patient_name or "").strip() or pid,
                enroll_id=None,
                status="matched",
                message="Face verification skipped by operator",
            )
            self._apply_session_voice(patient_sex=session.start.sex)
            logger.info("Using skip face patient_id=%s", pid)

        if face_phase.get("stranger") or (result and result.status == "stranger"):
            fail_msg = desk_msg
            self.display.show_message(fail_msg, allow_skip=self._allow_skip())
            self.sessions.set_state(
                SessionState.FAILED,
                step_id="b1_face_not_in_today",
                message_vi=fail_msg,
            )
            self._publish(session)
            return False

        if result is None or not result.matched:
            fail_msg = (result.message if result else None) or "Không nhận diện được khuôn mặt"
            self.display.show_message(fail_msg, allow_skip=self._allow_skip())
            self.sessions.set_state(
                SessionState.FAILED,
                step_id="b1_face_scan",
                message_vi=fail_msg,
            )
            self._publish(session)
            return False

        enroll_id = int(result.enroll_id) if result.enroll_id is not None else None
        patient_id = result.patient_id

        # Update chart immediately — hospital/device name refresh can follow.
        quick_name = (result.name or "").strip() or (
            f"ID {enroll_id}" if enroll_id is not None else "bệnh nhân"
        )
        identity_msg = (
            f"Đã chọn bệnh nhân: {quick_name} (bỏ qua Face)"
            if face_phase["skipped"] else f"Đã nhận diện: {quick_name}"
        )
        self.display.show_message(identity_msg)
        logger.info(
            "FACE_GATE_MATCH enroll_id=%s name=%s elapsed_ms=%.0f -> hospital_lookup",
            enroll_id,
            quick_name,
            (time.monotonic() - face_gate_started) * 1000.0,
        )
        self.sessions.set_state(
            SessionState.PREPARING,
            step_id="b1_face_skipped" if face_phase["skipped"] else "b1_face_matched",
            message_vi=identity_msg,
        )
        self._publish(session)

        # Prefer current name on the Face ID panel (operator may rename there).
        device_name: str | None = None
        if enroll_id is not None and hasattr(self.face, "get_user_name"):
            try:
                device_name = self.face.get_user_name(enroll_id)
            except Exception:  # noqa: BLE001
                logger.debug("get_user_name failed enroll_id=%s", enroll_id, exc_info=True)
        name = (
            (device_name or "").strip()
            or (result.name or "").strip()
            or (f"ID {enroll_id}" if enroll_id is not None else "bệnh nhân")
        )

        # Hospital for patient_id / EMR link — do not let stale hospital name win the UI.
        if enroll_id is not None:
            lookup_started = time.monotonic()
            lookup = hospital.lookup_by_enroll_id(enroll_id)
            logger.info(
                "FACE_GATE_HOSPITAL_LOOKUP enroll_id=%s found=%s elapsed_ms=%.0f",
                enroll_id,
                bool(lookup.get("found")),
                (time.monotonic() - lookup_started) * 1000.0,
            )
            if lookup.get("found") and isinstance(lookup.get("patient"), dict):
                pat = lookup["patient"]
                self._apply_session_voice(
                    patient_sex=str(pat.get("sex") or "") or None,
                    frappe_setting=str(lookup.get("voice_gender") or "") or None,
                )
                patient_id = str(pat.get("name") or patient_id)
                dob = str(pat.get("dob") or pat.get("date_of_birth") or "").strip() or None
                if dob:
                    session.patient_dob = dob
                    try:
                        session.start.dob = dob
                    except Exception:  # noqa: BLE001
                        pass
                # Refresh hospital display name if panel was renamed.
                hosp_name = str(pat.get("patient_name") or pat.get("aiface_display_name") or "").strip()
                if name and hosp_name and name != hosp_name:
                    try:
                        hospital.register_face_patient(enroll_id=enroll_id, full_name=name)
                        logger.info(
                            "Hospital display name updated enroll_id=%s %r → %r",
                            enroll_id,
                            hosp_name,
                            name,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("Hospital name sync failed enroll_id=%s", enroll_id)
            else:
                self._apply_session_voice(
                    frappe_setting=str(lookup.get("voice_gender") or "") or None,
                )
                try:
                    registered = hospital.register_face_patient(
                        enroll_id=enroll_id,
                        full_name=name,
                    )
                    pat = registered.get("patient") or {}
                    patient_id = str(pat.get("name") or patient_id)
                except Exception:  # noqa: BLE001
                    logger.exception("Hospital register_face_patient failed")

        session.face_ok = not face_phase["skipped"]
        session.face_name = name
        session.face_enroll_id = enroll_id
        if patient_id:
            session.start.patient_id = str(patient_id)
            try:
                cin = hospital.check_in_today_appointment(patient_id=str(patient_id))
                logger.info("Appointment check-in patient=%s result=%s", patient_id, cin)
            except Exception:  # noqa: BLE001
                logger.exception("Appointment check-in failed patient=%s", patient_id)

        # CCCD QR: Face ID JPEG → media → VPS qr_decode → Frappe apply_cccd_scan
        # Walk-in auto-test skips this so the chart starts immediately.
        auto_test = bool(getattr(session.start, "auto_enter_test", False))
        cccd_cfg = getattr(self.cfg, "cccd_qr", None)
        if (
            (not auto_test)
            and cccd_cfg
            and getattr(cccd_cfg, "enabled", False)
            and getattr(cccd_cfg, "after_face", True)
            and enroll_id is not None
            and self.media is not None
        ):
            def run_cccd_qr() -> None:
                try:
                    pipe = CccdQrPipeline(
                        face_client=self.face,
                        media_client=self.media,
                        hospital_base_url=hospital.base_url,
                        hospital_headers=hospital._headers(),
                        timeout_seconds=float(getattr(cccd_cfg, "timeout_seconds", 60.0)),
                    )
                    cccd_res = pipe.run(
                        enroll_id=int(enroll_id),
                        patient_id=str(patient_id) if patient_id else None,
                        session_id=session.start.session_id,
                    )
                    logger.info("CCCD QR pipeline enroll_id=%s result=%s", enroll_id, cccd_res)
                except Exception:  # noqa: BLE001
                    logger.exception("CCCD QR pipeline failed enroll_id=%s", enroll_id)

            threading.Thread(target=run_cccd_qr, name="cccd-qr", daemon=True).start()

        # Point results at hospital API
        try:
            session.start.callback_url = HttpUrl(hospital.results_callback_url())
        except Exception:  # noqa: BLE001
            logger.exception("Could not set hospital callback_url")

        welcome_timeout = 3.0
        speaker = self._speaker_v1()
        logger.info(
            "FACE_GATE_TO_WELCOME session_id=%s speaker=%s auto_test=%s elapsed_ms=%.0f",
            session.start.session_id,
            speaker,
            auto_test,
            (time.monotonic() - face_gate_started) * 1000.0,
        )
        self.display.show_welcome(
            name,
            allow_skip=self._allow_skip(),
            auto_continue_seconds=0.0 if speaker else welcome_timeout,
            show_continue=not speaker,
        )
        greet_step = self.audio.resolve_step("b1_face_greet")
        greet_tpl = greet_step.get("message_vi") or "Xin chào {name}."
        greet = greet_tpl.replace("{name}", name)
        greet_audio = greet_step.get("audio")
        if greet_audio:
            logger.info("Welcome audio %s for %s", greet_audio, name)
            self.audio.play_async(greet_audio)
        else:
            logger.warning("Welcome step b1_face_greet has no audio clip")
        self.sessions.set_state(
            SessionState.ACCEPTED,
            step_id="b1_face_skipped" if face_phase["skipped"] else "b1_face_ok",
            message_vi=greet,
        )
        self._publish(session)

        if speaker:
            self.audio.wait_done(timeout=20.0)
            if session.cancelled or self._stop.is_set():
                logger.info("Welcome step aborted by cancel")
                return False
        else:
            # Auto-advance after 3s; Tiếp tục / skip still jumps ahead.
            wait_welcome = {"welcome_continue"}
            if self._allow_skip():
                wait_welcome.add("skip_step")
            cont = self.display.wait_ui_action(
                wait_welcome,
                timeout=welcome_timeout,
                stop_flag=self._stop,
            )
            if cont in (None, "skip_step"):
                cont = "welcome_continue"
            if session.cancelled or self._stop.is_set():
                logger.info("Welcome step aborted by cancel")
                return False
            if cont != "welcome_continue":
                self.display.show_message("Không tiếp tục — kết thúc.")
                self.sessions.set_state(
                    SessionState.CANCELLED,
                    step_id="b1_welcome_cancelled",
                    message_vi="Không tiếp tục",
                )
                self._publish(session)
                return False

        self.display.show_input_mode_choice(self.cfg.ui.input_mode)
        self.audio.play_step("b1_input_mode_choice")
        # The choice window starts after the spoken guidance ends;
        # a patient can still select while the clip is playing.
        choice_timeout = (
            self.audio.playback_remaining_seconds()
            + self.cfg.ui.input_mode_choice_seconds
        )
        choice = self.display.wait_ui_event(
            {"select_input_mode"}, timeout=choice_timeout, stop_flag=self._stop,
        )
        if session.cancelled or self._stop.is_set():
            self.display.finish_input_mode_choice()
            return False
        chosen_mode = self.display.finish_input_mode_choice()
        if choice is not None:
            self.audio.stop()
        if choice is None:
            logger.info("Input mode choice timed out; using configured default %s", chosen_mode)
        logger.info("Input mode session=%s mode=%s", session.start.session_id, chosen_mode)
        if choice is not None:
            instruction_step = (
                "b1_input_mode_tablet" if chosen_mode == "tablet" else "b1_input_mode_speak"
            )
            self.audio.play_step(instruction_step)
            self.audio.wait_done(timeout=30.0)
            # Browser playback has no worker thread to join; honor its WAV deadline too.
            remaining_audio = self.audio.playback_remaining_seconds()
            if remaining_audio > 0:
                time.sleep(remaining_audio)

        if auto_test:
            logger.info("Walk-in: welcome done for %s — skip service menu, start test", name)
        else:
            self.display.show_service_menu(name, allow_skip=self._allow_skip())
            self.sessions.set_state(
                SessionState.ACCEPTED,
                step_id="b1_service_menu",
                message_vi="Chọn dịch vụ",
            )
            self._publish(session)
            service_actions = {"service_vision_test"}
            if self._allow_skip():
                service_actions.add("skip_step")
            service = self.display.wait_ui_action(
                service_actions,
                timeout=120.0,
                stop_flag=self._stop,
            )
            if service == "skip_step":
                service = "service_vision_test"
            if session.cancelled or self._stop.is_set():
                logger.info("Service menu aborted by cancel")
                return False
            if service != "service_vision_test":
                self.display.show_message("Không chọn dịch vụ — kết thúc.")
                self.sessions.set_state(
                    SessionState.CANCELLED,
                    step_id="b1_service_cancelled",
                    message_vi="Không chọn dịch vụ",
                )
                self._publish(session)
                return False

        logger.info(
            "FACE_GATE_DONE session_id=%s elapsed_ms=%.0f -> next=SHOW_QUEUE/WAIT_READY",
            session.start.session_id,
            (time.monotonic() - face_gate_started) * 1000.0,
        )

        # Create Vision Measurement on hospital server
        if session.start.patient_id and session.start.patient_id != "PENDING_FACE":
            started = hospital.start_measurement(
                session.start.patient_id,
                self.cfg.station_id,
            )
            vm = started.get("vision_measurement")
            if vm:
                session.vision_measurement_id = str(vm)

        if not speaker:
            self.display.show_message(f"Bắt đầu kiểm tra thị lực cho {name}.")
            time.sleep(1.0)
        return True

    def _wait_ready_speaker(
        self,
        session: ExamSession,
        proto: Any,
        step_id: str | None,
    ) -> bool:
        """Zone-only 2s hold, then position_stable + on-screen 3-2-1."""
        if self._allow_skip():
            self.display.drain_ui_actions({"skip_step"})
        msg = "Vui lòng đứng vào khu vực chỉ định"
        self.display.show_message(
            msg,
            allow_skip=self._allow_skip(),
            skip_label="Bỏ qua sẵn sàng",
            scene="stand",
        )
        if session.state != SessionState.GUIDING:
            self.sessions.set_state(SessionState.GUIDING, step_id=step_id or "b3_stand", message_vi=msg)
            self._publish(session)

        last_coach = ""
        show_cv = self._chart_cv_coaching()

        def zone_held(snap: Any) -> bool:
            nonlocal last_coach
            snap_key = (
                bool(getattr(snap, "zone_ok", False)),
                bool(getattr(snap, "ready", False)),
                str(getattr(snap, "under_test", "UNKNOWN") or "UNKNOWN"),
                str(getattr(snap, "coaching_vi", "") or ""),
            )
            if snap_key != getattr(zone_held, "_last_log_key", None):
                logger.info(
                    "READINESS_UPDATE zone_ok=%s ready=%s under_test=%s coaching=%r",
                    snap_key[0],
                    snap_key[1],
                    snap_key[2],
                    snap_key[3],
                )
                zone_held._last_log_key = snap_key
            if snap.error and self.cfg.bridges.readiness == "smarteyes" and self.cfg.bridges.smarteyes_strict:
                return False
            if show_cv:
                coach = str(getattr(snap, "coaching_vi", "") or "") or msg
                if "tai nghe" in coach.lower():
                    coach = msg
                if coach and coach != last_coach:
                    self.display.show_message(
                        coach,
                        allow_skip=self._allow_skip(),
                        skip_label="Bỏ qua sẵn sàng",
                        scene="stand",
                    )
                    last_coach = coach
            if bool(getattr(snap, "zone_ok", False) or getattr(snap, "ready", False)):
                logger.info(
                    "READINESS_TRIGGERED zone_ok=%s ready=%s",
                    getattr(snap, "zone_ok", False),
                    getattr(snap, "ready", False),
                )
                return True
            return False

        status = self._wait_gate(
            session,
            timeout=float(proto.readiness_timeout_seconds),
            predicate=zone_held,
        )
        if status == "stop":
            self.readiness.stop()
            return False
        if status == "timeout":
            fail = "Hết thời gian chờ đứng vào vị trí"
            self.display.show_message(fail)
            self.sessions.set_state(SessionState.FAILED, step_id="b3_stand", message_vi=fail)
            self._publish(session)
            self.readiness.stop()
            return True

        session.zone_done = True
        logger.info(
            "READINESS_GATE_PASSED step=%s -> playing position_stable and countdown",
            step_id or "b3_stand",
        )
        self.audio.play_named("position_stable.wav", wait=True, timeout=12.0)
        for n in (3, 2, 1):
            if self._stop.is_set() or session.cancelled:
                self.readiness.stop()
                return False
            self.display.show_countdown(n)
            time.sleep(1.0)
        self._readiness_forced = True
        session.readiness_ok = True
        return False

    def _play_cover_speaker(
        self,
        session: ExamSession,
        proto: Any,
        step_id: str | None,
    ) -> bool:
        """One stable cover screen + WAV, wait silently, then start WAV."""
        eye = str(session.eye_side or "left")
        scene, title, lead = {
            "left": (
                "cover_right",
                "Che mắt phải",
                "Mở mắt trái và nhìn thẳng vào màn hình.",
            ),
            "right": (
                "cover_left",
                "Che mắt trái",
                "Mở mắt phải và nhìn thẳng vào màn hình.",
            ),
        }.get(eye, ("cover_right", "Che mắt phải", "Nhìn thẳng vào màn hình."))
        cover_wav = {
            "left": "cover_right_eye.wav",
            "right": "cover_left_eye.wav",
        }.get(eye, "cover_right_eye.wav")
        start_wav = {
            "left": "start_left_eye.wav",
            "right": "start_right_eye.wav",
        }.get(eye, "start_left_eye.wav")
        if self._allow_skip():
            self.display.drain_ui_actions({"skip_step"})
        self.display.show_message(
            title,
            allow_skip=self._allow_skip(),
            skip_label="Bỏ qua",
            scene=scene,
        )
        self.sessions.set_state(
            SessionState.MEASURING,
            step_id=step_id or "b4_cover",
            message_vi=f"{title}. {lead}",
        )
        self._publish(session)
        self.audio.play_named(cover_wav, wait=True, timeout=16.0)

        want = eye.upper()

        def cover_ok(snap: Any) -> bool:
            got = str(getattr(snap, "under_test", "") or "").upper()
            if want == "BOTH":
                return got in {"BOTH", "UNKNOWN"} or bool(getattr(snap, "ready", False))
            return got == want

        cover_timeout = 8.0 if want == "BOTH" else min(45.0, float(proto.readiness_timeout_seconds))
        status = self._wait_gate(session, timeout=cover_timeout, predicate=cover_ok)
        if status == "stop":
            return False
        if status == "timeout":
            logger.warning("Cover gate timed out eye=%s — continuing", eye)

        self.audio.play_named(start_wav, wait=True, timeout=12.0)
        if not session.rules_played:
            self.display.show_message(
                "Nhìn chữ trên màn hình và đọc to, rõ ràng.",
                allow_skip=False,
                scene="rules",
            )
            session.rules_played = True

        self._row_shown = False
        session.heard_letters = []
        session.letter_cursor = 0
        session.letter_replacements = 0
        session.eye_complete = False
        session.same_size_fail_count = 0
        session.rows_this_eye = 0
        session.verifying_smaller_row = False
        self._reset_shown_letter_history(session)
        self._seed_eye_search(session)
        self._readiness_forced = True
        return False

    def _execute(self, session: ExamSession, action: ActionName, step_id: str | None) -> bool:
        """Return True if session finished."""
        proto = self.cfg.protocol

        if action == ActionName.ABORT:
            self.audio.stop()
            self.readiness.stop()
            self.display.clear()
            self.sessions.set_state(SessionState.CANCELLED, step_id=step_id or "abort", message_vi="Đã hủy")
            self._publish(session)
            return True

        if action == ActionName.SHOW_QUEUE:
            step = self.audio.play_step(
                step_id or "queue_stub",
                queue_number=session.start.queue_number,
            )
            msg = step.get("message_vi") or f"Số {session.start.queue_number or ''}"
            self.display.show_queue(session.start.queue_number, msg)
            self.sessions.set_state(SessionState.PREPARING, step_id=step_id, message_vi=msg)
            self._publish(session)
            time.sleep(0.8)
            self.sessions.set_state(SessionState.GUIDING, step_id="b3_stand", message_vi="Hướng dẫn vào vị trí")
            self._publish(session)
            return False

        if action == ActionName.WAIT_READY:
            self._readiness_forced = False
            try:
                self.readiness.start(exam=True)
            except Exception as exc:  # noqa: BLE001
                fail = f"Không khởi động được SmartEyes: {exc}"
                logger.exception(fail)
                self.display.show_message(fail)
                self.sessions.set_state(SessionState.FAILED, step_id="b3_stand", message_vi=fail)
                self._publish(session)
                return True
            if session.speaker_flow:
                return self._wait_ready_speaker(session, proto, step_id)
            step = self.audio.resolve_step(step_id or "b3_stand")
            msg = step.get("message_vi") or "Vui lòng vào vị trí"
            if self._allow_skip():
                self.display.drain_ui_actions({"skip_step"})
            self.display.show_message(
                msg,
                allow_skip=self._allow_skip(),
                skip_label="Bỏ qua sẵn sàng",
                scene="stand",
            )
            if session.state != SessionState.GUIDING:
                self.sessions.set_state(SessionState.GUIDING, step_id=step_id, message_vi=msg)
                self._publish(session)
            self.audio.play_async(step.get("audio"))
            deadline = time.monotonic() + proto.readiness_timeout_seconds
            last_coach = ""
            skipped = False
            while time.monotonic() < deadline and not self._stop.is_set():
                if self._allow_skip() and self.display.consume_ui_action("skip_step"):
                    logger.info("Readiness skipped by operator step=%s", step_id)
                    skipped = True
                    break
                snap = self.readiness.snapshot()
                if snap.error and self.cfg.bridges.readiness == "smarteyes" and self.cfg.bridges.smarteyes_strict:
                    fail = snap.error
                    self.display.show_message(fail, allow_skip=self._allow_skip())
                    self.sessions.set_state(SessionState.FAILED, step_id="b3_stand", message_vi=fail)
                    self._publish(session)
                    self.readiness.stop()
                    return True
                if self._chart_cv_coaching():
                    coach = snap.coaching_vi or msg
                    if coach and coach != last_coach:
                        self.display.show_message(
                            coach,
                            allow_skip=self._allow_skip(),
                            skip_label="Bỏ qua sẵn sàng",
                            scene="stand",
                        )
                        self.sessions.set_state(SessionState.GUIDING, step_id=step_id or "b3_stand", message_vi=coach)
                        self._publish(session)
                        last_coach = coach
                if snap.ready:
                    break
                time.sleep(0.05)
            else:
                if not self._stop.is_set() and not skipped:
                    fail = "Hết thời gian chờ sẵn sàng (đứng / tai nghe / mắt)"
                    self.display.show_message(fail)
                    self.sessions.set_state(SessionState.FAILED, step_id="b3_stand", message_vi=fail)
                    self._publish(session)
                    self.readiness.stop()
                    return True
            if self._stop.is_set() or session.cancelled:
                self.readiness.stop()
                return False
            if skipped:
                self._readiness_forced = True
                session.readiness_ok = True
                self.sessions.set_state(
                    SessionState.GUIDING,
                    step_id=step_id or "b3_stand",
                    message_vi="Đã bỏ qua kiểm tra sẵn sàng",
                )
                self._publish(session)
            else:
                self._readiness_forced = True  # hold ready through measure until next WAIT_READY
            return False

        if action == ActionName.PLAY_AUDIO:
            if session.speaker_flow:
                return self._play_cover_speaker(session, proto, step_id)
            step = self.audio.play_step(step_id or "b4_cover", eye=session.eye_side)
            msg = step.get("message_vi") or ""
            if self._allow_skip():
                self.display.drain_ui_actions({"skip_step"})
            cover_scene = {
                "left": "cover_right",
                "right": "cover_left",
            }.get(str(session.eye_side or ""), None)
            self.display.show_message(
                msg or "Tiếp tục…",
                allow_skip=self._allow_skip(),
                skip_label="Bỏ qua",
                scene=cover_scene,
            )
            self.sessions.set_state(SessionState.MEASURING, step_id=step_id, message_vi=msg)
            self._publish(session)
            # Short hold so operator can skip; otherwise brief pause
            deadline = time.monotonic() + (0.6 if not self._allow_skip() else 8.0)
            while time.monotonic() < deadline and not self._stop.is_set():
                if self._allow_skip() and self.display.consume_ui_action("skip_step"):
                    break
                time.sleep(0.1)
            self._row_shown = False
            session.heard_letters = []
            session.letter_cursor = 0
            session.letter_replacements = 0
            session.eye_complete = False
            session.same_size_fail_count = 0
            session.rows_this_eye = 0
            session.verifying_smaller_row = False
            self._reset_shown_letter_history(session)
            session.current_logmar = proto.start_logmar
            session.row_index = self._nearest_logmar_index(proto.start_logmar)
            return False

        if action == ActionName.SHOW_ROW:
            logmar = session.current_logmar if session.current_logmar is not None else proto.start_logmar
            session.current_logmar = logmar
            session.row_index = self._nearest_logmar_index(logmar)
            avoid = list(session.shown_letter_history[-LETTER_RECENT_WINDOW:])
            letters = self._pick_row_letters(session)
            session.current_letters = letters
            logger.info(
                "SHOW_ROW eye=%s logmar=%s letters=%s avoided=%s",
                session.eye_side,
                logmar,
                "".join(letters),
                "".join(avoid),
            )
            session.heard_letters = []
            session.letter_cursor = 0
            session.letter_replacements = 0
            use_pad = self._tablet_mode()
            skip_lbl = "Bỏ qua" if session.speaker_flow else "Bỏ qua (đúng)"
            if session.speaker_flow:
                # Model A-only flow always presents and captures one glyph at a time.
                first = letters[0] if letters else "?"
                self.display.show_single_letter(
                    logmar,
                    first,
                    eye_side=session.eye_side,
                    # Tablet owns the answer keyboard; TV only shows the optotype.
                    letter_pad=False,
                    prompt_vi="Đọc chữ trên màn hình",
                    allow_skip=self._allow_skip() and use_pad,
                    skip_label=skip_lbl,
                )
                step = {"message_vi": "Đọc chữ trên màn hình"}
            else:
                self.display.show_row(
                    logmar,
                    letters,
                    # Tablet owns the answer keyboard; TV only shows the row.
                    letter_pad=False,
                    prompt_vi="Chạm chữ bệnh nhân đọc được" if use_pad else None,
                    allow_skip=self._allow_skip() and use_pad,
                    skip_label=skip_lbl,
                )
                step = self.audio.play_step("b6_read", eye=session.eye_side)
            self.sessions.set_state(
                SessionState.MEASURING,
                step_id=step_id or "b5_show",
                message_vi=step.get("message_vi"),
            )
            self._publish(session)
            self._row_shown = True
            if isinstance(self.stt, MockSttBridge) and letters:
                self.stt.expect_letter = letters[0]
            time.sleep(0.3)
            return False

        if action == ActionName.LISTEN:
            if not session.current_letters:
                self._row_shown = False
                return False
            idx = len(session.heard_letters)
            if idx >= len(session.current_letters):
                return False
            target = session.current_letters[idx]
            if session.speaker_flow:
                self._listen_letter_model_a(session, proto, target=target, idx=idx)
                return False
            if isinstance(self.stt, MockSttBridge):
                # Only auto-answer in demo_mode; otherwise mock would fake the whole exam.
                if not proto.demo_mode:
                    self.display.show_message(
                        "STT mock + demo_mode=false — dùng bridges.stt: ui hoặc sloan"
                    )
                    time.sleep(0.5)
                    session.last_stt_letter = "[UNK]"
                    session.last_stt_confidence = 0.0
                    session.last_stt_reliable = False
                    session.last_stt_match = False
                    session.heard_letters.append("?")
                    return False
                self.stt.expect_letter = target
            conf_th = (
                self.cfg.bridges.min_confidence_demo
                if proto.demo_mode
                else proto.letter_uncertain_threshold
            )
            timeout = proto.effective_letter_timeout()
            if isinstance(self.stt, UiSttBridge):
                self.display.show_row(
                    float(
                        session.current_logmar
                        if session.current_logmar is not None
                        else proto.start_logmar
                    ),
                    session.current_letters,
                    # Never render the answer keyboard on the TV.
                    letter_pad=False,
                    prompt_vi=f"Đọc chữ thứ {idx + 1}/{len(session.current_letters)}",
                    allow_skip=self._allow_skip(),
                    skip_label="Bỏ qua (đúng)",
                )
            result = self.stt.listen_one(timeout=timeout, min_confidence=conf_th)
            if self._stt_is_skip(result):
                if session.speaker_flow:
                    logger.info("Letter skip (bỏ qua) target=%s → next letter, unscored", target)
                    session.last_stt_letter = "SKIP"
                    session.last_stt_confidence = 1.0
                    session.last_stt_reliable = True
                    self._mark_unscored_letter(session)
                    return False
                result = SttResult(
                    letter=target.upper(),
                    confidence=1.0,
                    reliable=True,
                    raw="skip",
                )
            session.last_stt_letter = result.letter
            session.last_stt_confidence = result.confidence
            session.last_stt_reliable = result.reliable

            # Timeout / unreliable / wrong → count as miss and advance (BQP-style pace)
            accept = result.reliable
            match = accept and result.letter.upper() == target.upper()
            session.last_stt_match = match
            if match:
                session.heard_letters.append(result.letter.upper())
                session.letter_replacements = 0
            else:
                # miss (timeout, low conf, wrong letter, UNK)
                session.heard_letters.append("?")
                session.letter_replacements = 0
                self.audio.play_step("error_retry")
                time.sleep(0.15)
            if isinstance(self.stt, MockSttBridge) and idx + 1 < len(session.current_letters):
                self.stt.expect_letter = session.current_letters[idx + 1]
            return False

        if action == ActionName.RECORD:
            heard = list(session.heard_letters)
            target = list(session.current_letters[: len(heard)])
            correct = sum(1 for a, b in zip(target, heard, strict=False) if a.upper() == b.upper())
            total = len(target) or proto.letters_per_row
            search = session.row_search if session.speaker_flow else None
            trial_phase = (
                search.phase if isinstance(search, SmartRangeSearchState) else "legacy"
            )
            if isinstance(search, SmartRangeSearchState):
                passed = correct >= (2 if search.is_range else 3)
            else:
                passed = (
                    correct > 0
                    if proto.adaptive_row_testing
                    else row_passed(correct, total, max_misses=proto.max_misses)
                )
            logmar = float(
                session.current_logmar
                if session.current_logmar is not None
                else proto.start_logmar
            )
            tested_row_index = self._nearest_logmar_index(logmar)

            outcome = "pass"
            if isinstance(search, SmartRangeSearchState) and proto.uses_smart_range_testing():
                rows = list(proto.row_logmars)
                session.same_size_fail_count = 0
                if search.is_range:
                    range_done = search.record_range(passed)
                    outcome = "range_pass" if passed else "range_fail"
                    if range_done:
                        outcome += "_begin_verify"
                else:
                    eye_done = search.record_verify(passed)
                    outcome = "verify_pass" if passed else "verify_fail"
                    if eye_done:
                        session.eye_complete = True
                        outcome += "_done"
                    else:
                        outcome += "_easier"
                if not session.eye_complete:
                    session.current_logmar = float(rows[search.probe])
                    session.row_index = int(search.probe)
            elif isinstance(search, BinarySearchState) and proto.uses_binary_row_search():
                rows = list(proto.row_logmars)
                session.same_size_fail_count = 0
                if passed:
                    cont = search.next_after_pass()
                    outcome = "binary_pass"
                else:
                    cont = search.next_after_fail()
                    outcome = "binary_fail"
                if not cont or search.finished():
                    session.eye_complete = True
                    if not search.ever_passed:
                        outcome = "binary_none_passed"
                    else:
                        outcome = "binary_done"
                else:
                    session.current_logmar = float(rows[search.probe])
                    session.row_index = int(search.probe)
            elif proto.adaptive_row_testing and session.verifying_smaller_row:
                # This row only confirms performance below the three-miss threshold.
                # Record what the patient saw, then finish this eye as requested.
                session.eye_complete = True
                session.verifying_smaller_row = False
                outcome = "verify_smaller_stop"
            elif passed:
                session.same_size_fail_count = 0
                nxt = self._step_logmar(logmar, smaller=True)
                if nxt is None:
                    # passed finest row → eye done
                    session.eye_complete = True
                    outcome = "pass_finest"
                else:
                    session.current_logmar = nxt
                    outcome = "pass_go_smaller"
            elif proto.uses_snellen_stop_on_fail():
                # Snellen: fail at line N → stop. Acuity = last passed line (N-1).
                # All larger lines above were already passed to reach this row.
                session.same_size_fail_count = 0
                session.eye_complete = True
                outcome = "fail_stop_snellen"
            elif proto.adaptive_row_testing:
                # Three misses on this row: verify once at the next smaller level.
                verify_logmar = self._step_logmar(logmar, smaller=True)
                if verify_logmar is None:
                    session.eye_complete = True
                    outcome = "fail_three_finest"
                else:
                    session.current_logmar = verify_logmar
                    session.verifying_smaller_row = True
                    outcome = "fail_three_verify_smaller"
            else:
                session.same_size_fail_count += 1
                if session.same_size_fail_count <= proto.same_size_retries:
                    # stay same size
                    outcome = "fail_retry_same"
                else:
                    session.same_size_fail_count = 0
                    bigger = self._step_logmar(logmar, smaller=False)
                    if bigger is None:
                        # already at largest and failed → stop eye
                        session.eye_complete = True
                        outcome = "fail_coarsest"
                    else:
                        session.current_logmar = bigger
                        outcome = "fail_go_bigger"

            trial = TrialRecord(
                eye=session.eye_side,
                pass_index=session.pass_index,
                row_index=tested_row_index,
                logmar=logmar,
                target=list(target),
                heard=list(heard),
                correct=correct,
                total=total,
                confidence_mean=session.last_stt_confidence,
                passed=passed,
                outcome=outcome,
                phase=trial_phase,
            )
            session.trials.append(trial)
            session.rows_this_eye += 1
            session.pass_index = session.rows_this_eye
            if session.rows_this_eye >= proto.max_rows_per_eye:
                session.eye_complete = True

            self._row_shown = False
            session.heard_letters = []
            session.letter_replacements = 0
            msg = f"{'Đạt' if passed else 'Chưa đạt'} {vn_over_10(10 ** (-logmar))} · {outcome}"
            self.sessions.set_state(SessionState.MEASURING, step_id="b9_record", message_vi=msg)
            self._publish(session)
            return False

        if action == ActionName.SWITCH_EYE:
            order = session.eyes_order()
            try:
                i = order.index(session.eye_side)
            except ValueError:
                i = 0
            if i + 1 < len(order):
                finished = session.eye_side
                if session.speaker_flow:
                    done_vi = {
                        "left": ("Đã xong mắt trái", "left_eye_complete.wav"),
                        "right": ("Đã xong mắt phải", "right_eye_complete.wav"),
                    }.get(finished)
                    if done_vi:
                        self.display.show_message(done_vi[0], scene="complete")
                        self.audio.play_named(done_vi[1], wait=True, timeout=12.0)
                session.eye_side = order[i + 1]
                session.pass_index = 0
                session.row_index = 0
                session.heard_letters = []
                session.letter_replacements = 0
                self._reset_shown_letter_history(session)
                session.eye_complete = False
                session.same_size_fail_count = 0
                session.rows_this_eye = 0
                session.verifying_smaller_row = False
                if session.speaker_flow:
                    self._seed_eye_search(session)
                else:
                    session.current_logmar = proto.start_logmar
                    session.row_search = None
                self._row_shown = False
                if isinstance(self.readiness, MockReadinessBridge):
                    self.readiness.force_under_test = session.eye_side.upper()
                    self.readiness.reset_timer()
                if session.speaker_flow:
                    self._readiness_forced = True
                    session.readiness_ok = True
                    next_vi = {
                        "left": "Tiếp theo: mắt trái",
                        "right": "Tiếp theo: mắt phải",
                    }.get(session.eye_side, "Tiếp tục")
                    self.sessions.set_state(
                        SessionState.GUIDING,
                        step_id="switch_eye",
                        message_vi=next_vi,
                    )
                    self._publish(session)
                else:
                    step = self.audio.play_step("switch_eye", eye=session.eye_side)
                    self.sessions.set_state(
                        SessionState.GUIDING,
                        step_id="switch_eye",
                        message_vi=step.get("message_vi"),
                    )
                    self._publish(session)
                    time.sleep(0.5)
            else:
                session.all_eyes_done = True
                session.eye_complete = False
            return False

        if action == ActionName.SHOW_RESULTS:
            if not session.all_eyes_done and session.eye_complete:
                if len(session.eyes_order()) == 1:
                    session.all_eyes_done = True
            right = score_eye(session.trials, "right", max_misses=proto.max_misses)
            left = score_eye(session.trials, "left", max_misses=proto.max_misses)
            acuity_ui = self._acuity_ui(left=left, right=right)
            if session.speaker_flow:
                self.display.show_results(
                    text_vi="Kết quả đo thị lực",
                    session_id=session.start.session_id,
                    patient_name=session.face_name,
                    patient_id=session.start.patient_id,
                    acuity=acuity_ui,
                    show_logmar=False,
                    layout="cards",
                )
                self.sessions.set_state(
                    SessionState.RESULTS,
                    step_id="b10_results",
                    message_vi="Kết quả đo thị lực",
                )
                self._publish(session)
                time.sleep(3.0)
            else:
                parts = []
                if right:
                    parts.append(f"MP {right.vn_over_10}")
                if left:
                    parts.append(f"MT {left.vn_over_10}")
                msg = "Đo xong. " + (" · ".join(parts) if parts else "Không có dữ liệu đủ.")
                self.display.summary(msg)
                self.audio.play_step("b10_results")
                self.sessions.set_state(SessionState.RESULTS, step_id="b10_results", message_vi=msg)
                self._publish(session)
                time.sleep(0.8)
            self._confirm_done = True
            return False

        if action == ActionName.SUBMIT:
            self._submit(session)
            return True

        if action == ActionName.RETRY:
            self.audio.play_step("error_retry")
            return False

        if action == ActionName.IDLE:
            time.sleep(0.1)
            return False

        logger.warning("Unhandled action %s", action)
        time.sleep(0.1)
        return False

    def _listen_letter_model_a(
        self,
        session: ExamSession,
        proto: Any,
        *,
        target: str,
        idx: int,
    ) -> None:
        """Capture one Model A chunk and score it with the two-threshold policy."""
        low = float(proto.letter_uncertain_threshold)
        high = float(proto.letter_accept_threshold)
        if not 0.0 <= low < high <= 1.0:
            raise ValueError(
                f"Invalid letter thresholds: uncertain={low}, accept={high}"
            )
        seconds = float(
            proto.tablet_chunk_seconds if self._tablet_mode()
            else proto.letter_chunk_seconds
        )
        logmar = float(
            session.current_logmar
            if session.current_logmar is not None
            else proto.start_logmar
        )
        target_u = str(target or "").strip().upper()
        window_id = uuid.uuid4().hex
        if self._tablet_mode():
            self.display.drain_ui_actions({"speak_letter", "skip_letter"})
        self.display.show_single_letter(
            logmar,
            target_u,
            eye_side=session.eye_side,
            # The Tablet renders the keyboard; the TV renders only the letter.
            letter_pad=False,
            prompt_vi="Chọn chữ trên tablet" if self._tablet_mode() else "Đọc chữ trên màn hình",
            allow_skip=False,
            window_id=window_id,
        )
        if not self.display.hub.wait_stimulus_ready(
            window_id, timeout=3.0, stop_flag=self._stop
        ):
            if session.cancelled or self._stop.is_set():
                return
            self.display.show_message(
                "Màn hình đo chưa sẵn sàng. Vui lòng báo nhân viên hỗ trợ."
            )
            raise StimulusNotReady(window_id)
        self.display.start_listen_window(window_id, seconds)
        self._start_letter_clip()
        if isinstance(self.stt, MockSttBridge):
            self.stt.expect_letter = self.stt.expect_letter or target_u
        try:
            result = self.stt.listen_chunk(
                timeout=seconds,
                min_confidence=low,
                stop_flag=self._stop,
            )
        finally:
            self.display.hub.active_letter_window_id = None
        if str(result.raw or "") == "cancelled":
            self._discard_letter_clip()
            return

        heard = str(result.letter or "").strip().upper()
        confidence = float(result.confidence or 0.0)
        raw_result = str(result.raw or "").strip().lower()
        valid_label = (
            len(heard) == 1 and "A" <= heard <= "Z"
            if self._tablet_mode()
            else heard in {"C", "D", "H", "K", "N", "O", "R", "S", "V", "Z"}
        )
        session.last_stt_letter = heard if valid_label else "[UNK]"
        session.last_stt_confidence = confidence
        session.last_stt_reliable = bool(result.reliable and valid_label)

        no_speech = raw_result in {"silence", "chunk_unrecognized", "timeout"}
        high_confidence_margin_reject = confidence > high and not result.reliable
        should_replace = (
            low <= confidence <= high
            or no_speech
            or high_confidence_margin_reject
        )
        if should_replace:
            logger.info(
                "Model A unscored eye=%s idx=%s target=%s heard=%s conf=%.3f "
                "raw=%s no_speech=%s margin_reject=%s; replacement=%s/%s",
                session.eye_side,
                idx,
                target_u,
                heard,
                confidence,
                raw_result,
                no_speech,
                high_confidence_margin_reject,
                session.letter_replacements,
                proto.max_letter_replacements,
            )
            self._discard_letter_clip()
            self._replace_unscored_letter(session, idx)
            return

        correct = bool(
            result.reliable
            and valid_label
            and confidence > high
            and heard == target_u
        )
        session.last_stt_match = correct
        session.heard_letters.append(target_u if correct else "?")
        session.letter_replacements = 0
        self._save_letter_clip(session, target=target_u, logmar=logmar)
        logger.info(
            "Model A scored eye=%s idx=%s target=%s heard=%s conf=%.3f "
            "reliable=%s outcome=%s",
            session.eye_side,
            idx,
            target_u,
            heard or "[UNK]",
            confidence,
            result.reliable,
            "correct" if correct else "miss",
        )

    def _submit(self, session: ExamSession) -> None:
        proto = self.cfg.protocol
        acuity: dict[str, Any] = {}
        for eye in ("right", "left"):
            scored = score_eye(session.trials, eye, max_misses=proto.max_misses)
            if scored:
                acuity[eye] = scored
        results = ResultsCallback(
            session_id=session.start.session_id,
            patient_id=session.start.patient_id,
            patient_name=session.face_name,
            face_enroll_id=session.face_enroll_id,
            station_id=session.station_id,
            exam_type=session.start.exam_type,
            completed_at=datetime.now(timezone.utc),
            acuity=acuity,
            protocol=ProtocolInfo(
                passes_per_eye=proto.passes_per_eye,
                distance_m=proto.distance_m,
                letter_uncertain_threshold=proto.letter_uncertain_threshold,
                letter_accept_threshold=proto.letter_accept_threshold,
                max_misses=proto.max_misses,
                # Report the actual Model A capture window.
                letter_timeout_seconds=float(
                    proto.tablet_chunk_seconds if self._tablet_mode()
                    else proto.letter_chunk_seconds
                ),
                letter_chunk_seconds=float(
                    proto.tablet_chunk_seconds if self._tablet_mode()
                    else proto.letter_chunk_seconds
                ),
                letter_protocol="model_a_threshold_band",
                scoring=(
                    "smart_range_2plus1_verify_3of5"
                    if proto.uses_smart_range_testing()
                    else "vn_bqp"
                ),
            ),
            raw_trials=[
                {
                    "eye": t.eye,
                    "pass_index": t.pass_index,
                    "row_index": t.row_index,
                    "logmar": t.logmar,
                    "vn_over_10": vn_over_10(10 ** (-t.logmar)),
                    "target": t.target,
                    "heard": t.heard,
                    "correct": t.correct,
                    "total": t.total,
                    "passed": t.passed,
                    "outcome": t.outcome,
                    "phase": t.phase,
                }
                for t in session.trials
            ],
            vision_measurement=session.vision_measurement_id,
        )
        body = results.model_dump(mode="json")
        journal_dir = self.sessions.journal_dir
        journal_dir.mkdir(parents=True, exist_ok=True)
        out_path = journal_dir / f"{session.start.session_id}_results.json"
        try:
            out_path.write_text(
                json.dumps(body, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            logger.info("Wrote results JSON → %s", out_path)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write results JSON")

        parts = []
        if session.face_name:
            parts.append(session.face_name)
        for eye_key, label in (("right", "Mắt phải"), ("left", "Mắt trái")):
            eye = acuity.get(eye_key)
            if eye is not None:
                vn = getattr(eye, "vn_over_10", None) or (eye.get("vn_over_10") if isinstance(eye, dict) else None)
                if vn:
                    parts.append(f"{label} {vn}")
        summary = "Kết quả: " + (" · ".join(parts) if parts else "Không có dữ liệu đủ.")
        acuity_ui = {
            k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v
            for k, v in acuity.items()
        }
        self.display.show_results(
            text_vi="Cảm ơn bạn đã hoàn thành bài kiểm tra.",
            session_id=session.start.session_id,
            patient_name=session.face_name,
            patient_id=session.start.patient_id,
            acuity=acuity_ui,
            show_logmar=False,
            layout="cards",
        )

        def deliver_results() -> None:
            try:
                self.http.post_results(
                    str(session.start.callback_url),
                    results,
                    correlation_id=session.start.correlation_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "HTTP callback failed after retries; results remain on disk at %s",
                    out_path,
                )

        # Network delivery must never hold the model/microphone state machine
        # or delay the next patient. The immutable JSON journal remains the
        # recovery copy if every bounded retry fails.
        threading.Thread(
            target=deliver_results,
            name=f"results-callback-{session.start.session_id}",
            daemon=True,
        ).start()

        if session.speaker_flow:
            if self.audio.play_named("test_complete.wav", wait=True, timeout=16.0):
                # Pulse/USB can still have the final samples queued when
                # PortAudio reports completion. Give the output time to drain
                # before the next sd.play() stops the previous stream.
                if not self._stop.wait(0.5):
                    self.audio.play_named("return_waiting.wav", wait=True, timeout=12.0)
            self.display.clear()

        self.readiness.stop()
        self.sessions.set_state(SessionState.COMPLETED, step_id="submit", message_vi=summary)
        self._publish(session)
