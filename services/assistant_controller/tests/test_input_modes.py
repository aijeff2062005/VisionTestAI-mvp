"""A tablet answer and the chart window use the same letter contract."""

from __future__ import annotations

from ac.display_client import DisplayClient, DisplayHub
from ac.readiness_bridge import ExclusiveInputSttBridge, SttResult, UiSttBridge


def test_tablet_answer_uses_only_ui_event() -> None:
    hub = DisplayHub()
    bridge = UiSttBridge()
    bridge.bind(hub)
    hub.push_ui_event({"action": "speak_letter", "payload": {"letter": "D"}})

    result = bridge.listen_chunk(timeout=0.1)

    assert result.letter == "D"
    assert result.reliable


def test_letter_display_carries_eye_and_window_for_tablet() -> None:
    hub = DisplayHub()
    DisplayClient(hub).show_single_letter(
        0.3, "K", eye_side="RIGHT", countdown_seconds=3.0,
    )
    assert hub.last_command["eye_side"] == "RIGHT"
    assert hub.last_command["countdown_seconds"] == 3.0


def test_stimulus_ready_ack_requires_local_kiosk_and_current_window() -> None:
    hub = DisplayHub()
    hub.arm_stimulus_window("current")

    assert not hub.acknowledge_stimulus_ready(
        "current", from_kiosk=False, font_ready=True
    )
    assert not hub.acknowledge_stimulus_ready(
        "current", from_kiosk=True, font_ready=False
    )
    assert not hub.acknowledge_stimulus_ready(
        "stale", from_kiosk=True, font_ready=True
    )
    assert hub.acknowledge_stimulus_ready(
        "current", from_kiosk=True, font_ready=True
    )
    assert hub.wait_stimulus_ready("current", timeout=0.01)


def test_clear_returns_patient_display_to_face_waiting() -> None:
    hub = DisplayHub()
    display = DisplayClient(hub)
    display.show_single_letter(0.3, "K", eye_side="RIGHT")
    display.clear()
    assert hub.last_command["type"] == "show_message"
    assert hub.last_command["scene"] == "face"
    assert hub.last_command["exam_mode"] is True


def test_mode_choice_is_open_only_during_welcome_transition() -> None:
    hub = DisplayHub()
    display = DisplayClient(hub)
    assert not hub.choose_input_mode("tablet")
    display.show_input_mode_choice("speak")
    assert hub.last_command["mode"] == "input_select"
    assert hub.choose_input_mode("tablet")
    assert not hub.choose_input_mode("speak")
    assert display.wait_ui_event({"select_input_mode"}, timeout=0.01) is None
    assert display.finish_input_mode_choice() == "tablet"


def test_tablet_accepts_a_to_z_including_non_sloan_letters() -> None:
    hub = DisplayHub()
    bridge = UiSttBridge()
    bridge.bind(hub)
    for character in ("A", "B", "X", "Y"):
        hub.push_ui_event({"action": "speak_letter", "payload": {"letter": character}})
        result = bridge.listen_chunk(timeout=0.1)
        assert result.letter == character
        assert result.reliable


def test_exclusive_bridge_uses_selected_source_only() -> None:
    class Speech:
        shared_microphone = None

        def __init__(self) -> None:
            self.calls = 0

        def listen_chunk(self, **kwargs):  # noqa: ANN003
            self.calls += 1
            return SttResult("K", 0.9, True, "K")

    hub = DisplayHub()
    speech = Speech()
    bridge = ExclusiveInputSttBridge(speech, UiSttBridge())
    bridge.bind(hub)
    hub.input_mode = "tablet"
    hub.push_ui_event({"action": "speak_letter", "payload": {"letter": "A"}})
    assert bridge.listen_chunk(timeout=0.1).letter == "A"
    assert speech.calls == 0
    hub.input_mode = "speak"
    assert bridge.listen_chunk(timeout=0.1).letter == "K"
    assert speech.calls == 1
