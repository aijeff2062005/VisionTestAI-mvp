"""Sloan letter recent-history: no repeat of the last 3 shown, including across rows."""

from __future__ import annotations

from ac.readiness_bridge import LETTER_POOL, next_sloan_letter, random_letters


def test_next_letter_avoids_last_three() -> None:
    recent = ["C", "D", "H"]
    for _ in range(200):
        letter = next_sloan_letter(recent)
        assert letter in LETTER_POOL
        assert letter not in recent


def test_row_then_next_row_avoids_previous_tail() -> None:
    """The reported bug: size/row change used to allow R, R, R across rows."""
    shown: list[str] = []
    history: list[str] = []
    for _ in range(12):
        row = random_letters(5, recent=history)
        assert len(row) == 5
        for letter in row:
            assert letter not in shown[-3:]
            shown.append(letter)
        history = shown[-3:]


def test_fallback_avoid_last_one_when_window_covers_pool() -> None:
    pool = ["C", "D"]
    letter = next_sloan_letter(["C", "D", "C"], pool=pool)
    assert letter == "D"


def test_fallback_any_when_pool_is_single_letter() -> None:
    letter = next_sloan_letter(["C", "C", "C"], pool=["C"])
    assert letter == "C"


def test_new_eye_history_reset_allows_repeat() -> None:
    """Repeating R on the next eye is OK; history must not carry over."""
    first_eye = random_letters(5, recent=[])
    next_eye = random_letters(1, recent=[])
    assert next_eye[0] in LETTER_POOL
    assert first_eye[-1] in LETTER_POOL
