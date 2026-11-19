"""Age-derived visual-acuity starting rows."""

from __future__ import annotations

from datetime import date

from ac.age_va import (
    age_years,
    parse_dob,
    start_logmar_from_dob,
    start_tenths_from_dob,
)


ROWS = [
    1.0,
    0.69897,
    0.52288,
    0.39794,
    0.30103,
    0.22185,
    0.15490,
    0.09691,
    0.04576,
    0.0,
]


def test_missing_or_invalid_dob_starts_at_four_tenths() -> None:
    for value in (None, "", "not-a-date"):
        assert start_tenths_from_dob(value) == 4
        assert start_logmar_from_dob(value, ROWS) == 0.39794


def test_age_bands_use_requested_start_levels() -> None:
    today = date(2026, 9, 28)
    cases = {
        "2012-09-28": 5,
        "1989-09-15": 5,
        "1981-01-01": 5,
        "1971-01-01": 4,
        "1961-01-01": 3,
        "1951-01-01": 3,
        "1941-01-01": 2,
    }
    for dob, expected in cases.items():
        assert start_tenths_from_dob(dob, today=today) == expected


def test_age_uses_completed_years() -> None:
    today = date(2026, 9, 28)
    assert age_years(parse_dob("1966-09-28"), today=today) == 60
    assert age_years(parse_dob("1966-09-29"), today=today) == 59
