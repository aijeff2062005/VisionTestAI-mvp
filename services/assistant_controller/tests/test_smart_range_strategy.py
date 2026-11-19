"""Focused tests for the production 2+1 range / 3-of-5 strategy."""

from __future__ import annotations

from pathlib import Path

from pydantic import HttpUrl

from ac.age_va import SmartRangeSearchState
from ac.audio_player import AudioPlayer
from ac.config import AppConfig, ProtocolConfig
from ac.display_client import DisplayClient, DisplayHub
from ac.dmn_engine import DmnEngine
from ac.http_callback import HttpCallbackClient
from ac.models import ActionName, EyesMode, SessionStart
from ac.orchestrator import Orchestrator
from ac.readiness_bridge import MockReadinessBridge, MockSttBridge, SttResult, UiSttBridge
from ac.session_manager import SessionManager, TrialRecord


ROOT = Path(__file__).resolve().parents[1]


class ScriptedChunkStt:
    def __init__(self, results: list[SttResult]) -> None:
        self.results = list(results)
        self.heads: list[str | None] = []

    def listen_chunk(self, **kwargs) -> SttResult:  # noqa: ANN003
        self.heads.append(kwargs.get("head"))
        assert self.results, "unexpected listen_chunk call"
        return self.results.pop(0)


def _orchestrator(tmp_path: Path) -> tuple[Orchestrator, object]:
    cfg = AppConfig(
        station_id="smart-test",
        protocol=ProtocolConfig(
            letters_per_row=5,
            max_misses=2,
            row_logmars=[0.5, 0.3, 0.1, 0.0, -0.1],
            start_logmar=0.1,
            row_search="binary",
            smart_range_testing=True,
            smart_range_initial_letters=2,
            smart_range_tiebreak_letters=1,
            smart_verify_letters=5,
            max_letter_replacements=1,
            left_eye_start_easier_steps=1,
            start_from_age_norm=False,
            letter_uncertain_threshold=0.45,
            letter_accept_threshold=0.75,
            max_rows_per_eye=12,
        ),
    )
    sessions = SessionManager(cfg.station_id, tmp_path / "journals")
    hub = DisplayHub()
    display = DisplayClient(hub)
    hub.wait_stimulus_ready = lambda *_args, **_kwargs: True
    hub._test_listen_window = None
    display.start_listen_window = lambda window_id, seconds: setattr(  # noqa: E731
        hub, "_test_listen_window", (window_id, seconds)
    )
    orch = Orchestrator(
        cfg=cfg,
        sessions=sessions,
        dmn=DmnEngine(ROOT / "dmn" / "acuity_flow.dmn"),
        display=display,
        audio=AudioPlayer(ROOT / "scenarios" / "vi" / "manifest.yaml"),
        readiness=MockReadinessBridge(delay_seconds=0.0),
        stt=MockSttBridge(),
        http=HttpCallbackClient(timeout_seconds=0.1),
        publish_status=lambda _status: None,
    )
    session, err = sessions.start(
        SessionStart(
            session_id="smart-session",
            patient_id="patient",
            eyes=EyesMode.BOTH,
            callback_url=HttpUrl("http://127.0.0.1:9/results"),
        )
    )
    assert err is None and session is not None
    session.speaker_flow = True
    return orch, session


def test_range_search_never_repeats_and_starts_verify_at_boundary() -> None:
    search = SmartRangeSearchState.seed(12, 6)
    probes = [search.probe]
    assert search.record_range(True) is False
    probes.append(search.probe)
    assert search.record_range(False) is False
    probes.append(search.probe)
    done = search.record_range(False)

    assert done is True
    assert search.is_verify is True
    assert search.probe == 6
    assert len(probes) == len(set(probes))
    assert search.record_verify(True) is True


def test_range_search_handles_chart_extremes() -> None:
    all_pass = SmartRangeSearchState.seed(5, 2)
    while all_pass.is_range:
        all_pass.record_range(True)
    assert all_pass.probe == 4

    all_fail = SmartRangeSearchState.seed(5, 2)
    while all_fail.is_range:
        all_fail.record_range(False)
    assert all_fail.probe == 0
    assert all_fail.record_verify(False) is True

    verify_down = SmartRangeSearchState(
        n_rows=5, probe=4, phase="verify", verify_index=4
    )
    assert verify_down.record_verify(False) is False
    assert verify_down.probe == 3
    assert verify_down.record_verify(False) is True
    assert verify_down.probe == 3


def test_range_and_verify_completion_rules(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.row_search = SmartRangeSearchState.seed(5, 2)
    session.current_letters = list("CDH")
    orch._row_shown = True

    session.heard_letters = ["C", "D"]
    assert orch._row_complete(session) is True
    session.heard_letters = ["C", "?"]
    assert orch._row_complete(session) is False
    session.heard_letters = ["C", "?", "H"]
    assert orch._row_complete(session) is True

    session.row_search.record_range(True)
    while session.row_search.is_range:
        session.row_search.record_range(True)
    session.current_letters = list("CDHKO")
    session.heard_letters = ["C", "D", "H"]
    assert orch._row_complete(session) is True
    session.heard_letters = ["?", "?", "?"]
    assert orch._row_complete(session) is True
    session.heard_letters = ["C", "D", "?", "?"]
    assert orch._row_complete(session) is False


def test_replacement_limit_scores_second_unclear_attempt_as_miss(
    tmp_path: Path, monkeypatch,
) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["C", "D", "H"]
    monkeypatch.setattr(orch.audio, "play_named", lambda *args, **kwargs: True)

    orch._replace_unscored_letter(session, 0)
    first = session.current_letters[0]
    assert first != "C"
    assert session.heard_letters == []
    assert session.letter_replacements == 1

    orch._replace_unscored_letter(session, 0)
    assert session.heard_letters == ["?"]
    assert session.letter_replacements == 0


def test_model_a_high_confidence_matching_label_is_correct(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([SttResult("K", 0.92, True, "K")])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == ["K"]
    assert session.last_stt_match is True
    assert orch.stt.heads == [None]


def test_letter_window_uses_selected_source_duration(tmp_path: Path, monkeypatch) -> None:
    speech_orch, speech_session = _orchestrator(tmp_path / "speech")
    speech_session.current_letters = ["K"]
    speech_timeouts = []
    speech_orch.stt = ScriptedChunkStt([SttResult("K", 0.92, True, "K")])
    original_listen = speech_orch.stt.listen_chunk

    def speech_listen(**kwargs):  # noqa: ANN003
        speech_timeouts.append(kwargs["timeout"])
        return original_listen(**kwargs)

    monkeypatch.setattr(speech_orch.stt, "listen_chunk", speech_listen)
    speech_orch._listen_letter_model_a(speech_session, speech_orch.cfg.protocol, target="K", idx=0)
    assert speech_timeouts == [3.0]
    assert speech_orch.display.hub._test_listen_window[1] == 3.0

    tablet_orch, tablet_session = _orchestrator(tmp_path / "tablet")
    tablet_session.current_letters = ["K"]
    tablet_orch.stt = UiSttBridge()
    tablet_timeouts = []

    def tablet_listen(**kwargs):  # noqa: ANN003
        tablet_timeouts.append(kwargs["timeout"])
        return SttResult("K", 0.95, True, "K")

    monkeypatch.setattr(tablet_orch.stt, "listen_chunk", tablet_listen)
    tablet_orch._listen_letter_model_a(tablet_session, tablet_orch.cfg.protocol, target="K", idx=0)
    assert tablet_timeouts == [10.0]
    assert tablet_orch.display.hub._test_listen_window[1] == 10.0


def test_model_a_high_confidence_different_label_is_wrong(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([SttResult("N", 0.93, True, "N")])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == ["?"]
    assert session.last_stt_match is False


def test_tablet_non_sloan_answer_is_scored_wrong_not_discarded(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = UiSttBridge()
    orch.stt.listen_chunk = lambda **kwargs: SttResult("B", 0.95, True, "B")

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.last_stt_letter == "B"
    assert session.heard_letters == ["?"]
    assert session.letter_replacements == 0


def test_model_a_uncertain_boundary_replaces_once_then_scores(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([
        SttResult("K", 0.45, True, "K"),
        SttResult("N", 0.75, True, "N"),
    ])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == []
    replacement = session.current_letters[0]
    assert replacement != "K"
    assert session.letter_replacements == 1
    orch._listen_letter_model_a(
        session, orch.cfg.protocol, target=replacement, idx=0
    )
    assert session.heard_letters == ["?"]
    assert session.letter_replacements == 0


def test_model_a_low_confidence_label_is_wrong_without_replacement(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([
        SttResult("[UNK]", 0.20, False, "K"),
    ])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == ["?"]
    assert session.letter_replacements == 0


def test_model_a_silence_replaces_once_then_scores_miss(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([
        SttResult("[UNK]", 0.0, False, "chunk_unrecognized"),
        SttResult("[UNK]", 0.0, False, "silence"),
    ])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == []
    replacement = session.current_letters[0]
    assert replacement != "K"
    assert session.letter_replacements == 1

    orch._listen_letter_model_a(
        session, orch.cfg.protocol, target=replacement, idx=0
    )

    assert session.heard_letters == ["?"]
    assert session.letter_replacements == 0


def test_model_a_margin_reject_inside_band_still_replaces(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([
        SttResult("[UNK]", 0.60, False, "K"),
    ])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == []
    assert session.current_letters[0] != "K"
    assert session.letter_replacements == 1


def test_model_a_high_confidence_margin_reject_replaces(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.current_letters = ["K"]
    orch.stt = ScriptedChunkStt([
        SttResult("[UNK]", 0.91, False, "K"),
    ])

    orch._listen_letter_model_a(session, orch.cfg.protocol, target="K", idx=0)

    assert session.heard_letters == []
    assert session.current_letters[0] != "K"
    assert session.letter_replacements == 1


def test_record_phases_and_eye_seed_rules(tmp_path: Path) -> None:
    orch, session = _orchestrator(tmp_path)
    session.eye_side = "right"
    session.row_search = SmartRangeSearchState.seed(5, 2)
    session.current_logmar = 0.1
    session.current_letters = list("CDH")
    session.heard_letters = ["C", "D"]
    orch._row_shown = True
    orch._execute(session, ActionName.RECORD, "record")
    assert session.trials[-1].phase == "range"
    assert session.trials[-1].passed is True

    session.trials.extend([
        TrialRecord(
            "right", 10, 3, 0.0, list("CDHKO"), list("CDH??"),
            3, 5, 0.9, True, "verify_pass_done", "verify",
        ),
        TrialRecord(
            "left", 10, 1, 0.3, list("CDHKO"), list("CDH??"),
            3, 5, 0.9, True, "verify_pass_done", "verify",
        ),
    ])

    session.eye_side = "left"
    orch._seed_eye_search(session)
    assert session.row_index == 2  # one easier than right's verified row 3
    assert session.eyes_order() == ["right", "left"]
