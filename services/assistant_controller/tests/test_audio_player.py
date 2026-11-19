"""Voice gender resolution and vi/{male|female}/ path lookup."""

from __future__ import annotations

from pathlib import Path

from ac.audio_player import AudioPlayer, resolve_voice_gender


def test_resolve_voice_gender_auto_opposite_sex() -> None:
    assert resolve_voice_gender(patient_sex="Male") == "female"
    assert resolve_voice_gender(patient_sex="Female") == "male"
    assert resolve_voice_gender(patient_sex="Other") is None
    assert resolve_voice_gender(patient_sex="") is None
    assert resolve_voice_gender() is None


def test_resolve_voice_gender_explicit_settings_win() -> None:
    assert (
        resolve_voice_gender(
            patient_sex="Male",
            frappe_setting="Male",
            clinic_setting="auto",
        )
        == "male"
    )
    assert (
        resolve_voice_gender(
            patient_sex="Female",
            frappe_setting="Auto",
            clinic_setting="female",
        )
        == "female"
    )
    assert (
        resolve_voice_gender(
            patient_sex="Female",
            frappe_setting="Female",
            clinic_setting="auto",
        )
        == "female"
    )


def _clinic_tree(tmp_path: Path) -> Path:
    male = tmp_path / "male"
    female = tmp_path / "female"
    male.mkdir()
    female.mkdir()
    (male / "b3_stand.wav").write_bytes(b"RIFFMALE")
    (female / "b3_stand.wav").write_bytes(b"RIFFFEM")
    (male / "b4_cover_right.wav").write_bytes(b"RIFFMCR")
    (female / "b4_cover_right.wav").write_bytes(b"RIFFFCR")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    return manifest


def test_audio_path_uses_gender_directory(tmp_path: Path) -> None:
    manifest = _clinic_tree(tmp_path)
    player = AudioPlayer(manifest)

    player.set_gender(None)
    assert player.audio_path("b3_stand.wav") == tmp_path / "male" / "b3_stand.wav"

    player.set_gender("male")
    assert player.audio_path("b3_stand.wav") == tmp_path / "male" / "b3_stand.wav"

    player.set_gender("female")
    assert player.audio_path("b3_stand.wav") == tmp_path / "female" / "b3_stand.wav"
    assert player.audio_path("b4_cover_right.wav") == tmp_path / "female" / "b4_cover_right.wav"


def test_audio_path_female_falls_back_to_male(tmp_path: Path) -> None:
    male = tmp_path / "male"
    female = tmp_path / "female"
    male.mkdir()
    female.mkdir()
    (male / "b4_cover_right.wav").write_bytes(b"RIFF")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    player = AudioPlayer(manifest)
    player.set_gender("female")
    assert player.audio_path("b4_cover_right.wav") == male / "b4_cover_right.wav"


def test_audio_path_male_manifest_still_finds_sibling_female(tmp_path: Path) -> None:
    male = tmp_path / "male"
    female = tmp_path / "female"
    male.mkdir()
    female.mkdir()
    (male / "b3_stand.wav").write_bytes(b"RIFFM")
    (female / "b3_stand.wav").write_bytes(b"RIFFF")
    manifest = male / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    player = AudioPlayer(manifest)
    player.set_gender("female")
    assert player.audio_path("b3_stand.wav") == female / "b3_stand.wav"


def test_audio_path_legacy_loose_file(tmp_path: Path) -> None:
    (tmp_path / "b3_stand.wav").write_bytes(b"RIFF")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    player = AudioPlayer(manifest)
    player.set_gender("female")
    assert player.audio_path("b3_stand.wav") == tmp_path / "b3_stand.wav"


def test_audio_path_skips_placeholder_for_real_prompt(tmp_path: Path) -> None:
    male = tmp_path / "male"
    female = tmp_path / "female"
    prompts = tmp_path / "prompts"
    male.mkdir()
    female.mkdir()
    prompts.mkdir()
    (female / "letter_C.wav").write_bytes(b"RIFFPLACEHOLDER")
    (prompts / "letter_C.wav").write_bytes(b"R" * 21_000)
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    player = AudioPlayer(manifest, prompts_dir=prompts)
    player.set_gender("female")
    assert player.audio_path("letter_C.wav") == prompts / "letter_C.wav"


def test_browser_url_and_play_callback(tmp_path: Path) -> None:
    male = tmp_path / "male"
    male.mkdir()
    wav = male / "b3_stand.wav"
    wav.write_bytes(b"R" * 21_000)
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("steps: {}\n", encoding="utf-8")
    played: list[str] = []
    player = AudioPlayer(
        manifest,
        output="browser",
        play_browser=lambda url, _dur: played.append(url),
    )
    player.set_gender("male")
    assert player.browser_url(wav) == "/scenarios/vi/male/b3_stand.wav"
    player.play_async("b3_stand.wav")
    assert played == ["/scenarios/vi/male/b3_stand.wav"]


def test_named_audio_does_not_report_completion_while_stream_is_active(tmp_path: Path) -> None:
    manifest = _clinic_tree(tmp_path)
    player = AudioPlayer(manifest)

    class ActiveStream:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float) -> None:
            assert timeout > 0

    player.play_async = lambda *_args, **_kwargs: setattr(player, "_thread", ActiveStream())
    assert not player.play_named("b3_stand.wav", wait=True, timeout=0.01)
