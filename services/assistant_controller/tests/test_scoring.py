"""Unit tests for VN scoring helpers."""

from pathlib import Path

import yaml

from ac.scoring import row_passed, score_eye, vn_chart_logmars, vn_over_10
from ac.session_manager import TrialRecord


def test_all_shipped_configs_use_hospital_ten_levels() -> None:
    config_dir = Path(__file__).resolve().parents[1] / "configs"
    for name in ("clinic.yaml", "clinic_happy_path.yaml", "clinic_confirm.yaml", "default.yaml"):
        protocol = yaml.safe_load((config_dir / name).read_text(encoding="utf-8"))["protocol"]
        assert protocol["row_logmars"] == vn_chart_logmars(), name
        assert protocol["start_logmar"] in protocol["row_logmars"], name


def test_row_passed_max_one_miss() -> None:
    assert row_passed(5, 5, max_misses=1) is True
    assert row_passed(4, 5, max_misses=1) is True
    assert row_passed(3, 5, max_misses=1) is False


def test_vn_over_10() -> None:
    assert vn_chart_logmars() == [1.0, 0.69897, 0.52288, 0.39794, 0.30103, 0.22185, 0.15490, 0.09691, 0.04576, -0.0]
    assert vn_over_10(0.1) == "1/10"
    assert vn_over_10(1.0) == "10/10"
    assert vn_over_10(0.8) == "8/10"
    assert vn_over_10(0.63) == "6/10"
    assert vn_over_10(2.0) == "10/10"


def test_score_eye_prefers_best_passed() -> None:
    trials = [
        TrialRecord("right", 0, 0, 0.5, list("CDHKO"), list("CDHKO"), 5, 5, 0.9, True, "pass"),
        TrialRecord("right", 1, 1, 0.1, list("CDHKO"), list("CDHK?"), 4, 5, 0.9, True, "pass"),
        TrialRecord("right", 2, 2, 0.0, list("CDHKO"), list("?????"), 0, 5, 0.2, False, "fail"),
    ]
    scored = score_eye(trials, "right", max_misses=1)
    assert scored is not None
    assert scored.logmar == 0.1
    assert scored.vn_over_10 == "8/10"


def test_score_eye_ignores_provisional_range_rows() -> None:
    trials = [
        TrialRecord(
            "left", 0, 8, 0.04576, list("CD"), list("CD"), 2, 2, 0.9,
            True, "range_pass", "range",
        ),
        TrialRecord(
            "left", 1, 9, 0.0, list("HK"), list("HK"), 2, 2, 0.9,
            True, "range_pass_begin_verify", "range",
        ),
    ]
    assert score_eye(trials, "left") is None

    trials.append(
        TrialRecord(
            "left", 2, 9, 0.0, list("CDHKO"), list("CD???"), 2, 5, 0.9,
            False, "verify_fail_easier", "verify",
        )
    )
    failed = score_eye(trials, "left")
    assert failed is not None
    assert failed.logmar == 0.0
    assert failed.row_passed is False

    trials.append(
        TrialRecord(
            "left", 3, 8, 0.04576, list("CDHKO"), list("CDH??"), 3, 5, 0.9,
            True, "verify_pass_done", "verify",
        )
    )
    scored = score_eye(trials, "left")
    assert scored is not None
    assert scored.logmar == 0.04576
    assert scored.correct == 3
    assert scored.total == 5


def test_score_eye_preserves_best_chart_level_10_over_10() -> None:
    trials = [
        TrialRecord(
            "both", 1, 9, 0.0, list("CDHKO"), list("CDH??"), 3, 5,
            0.9, True, "verify_pass_done", "verify",
        )
    ]
    scored = score_eye(trials, "both")
    assert scored is not None
    assert scored.vn_over_10 == "10/10"
    assert scored.row_passed is True
