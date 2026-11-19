"""Acuity scoring helpers (VN x/10 + logMAR)."""

from __future__ import annotations

import math

from ac.models import EyeAcuity
from ac.session_manager import TrialRecord

# Hospital decimal chart lines (large → small).
VN_CHART_TENTHS: tuple[int, ...] = tuple(range(1, 11))


def vn_chart_logmars() -> list[float]:
    """logMAR for each hospital chart line (1/10 … 10/10)."""
    return [round(-math.log10(t / 10.0), 5) for t in VN_CHART_TENTHS]


def decimal_from_logmar(logmar: float) -> float:
    return float(10 ** (-logmar))


def snellen_approx(decimal: float) -> str:
    """Rough 6/x approximation for display only."""
    if decimal <= 0:
        return "6/?"
    x = 6.0 / decimal
    if abs(x - round(x)) < 0.05:
        return f"6/{int(round(x))}"
    return f"6/{x:.1f}"


def vn_over_10(decimal: float) -> str:
    """Hospital decimal label snapped to its 1/10 … 10/10 chart lines."""
    if decimal <= 0:
        return "0/10"
    tenths = float(decimal) * 10.0
    best = min(VN_CHART_TENTHS, key=lambda t: abs(t - tenths))
    return f"{best}/10"


def row_passed(correct: int, total: int, *, max_misses: int = 1) -> bool:
    """BQP-aligned: ≤ max_misses wrong letters on the row."""
    if total <= 0:
        return False
    return (total - correct) <= max_misses


def min_correct_for(total: int, *, max_misses: int = 1) -> int:
    return max(0, total - max_misses)


def score_eye(
    trials: list[TrialRecord],
    eye: str,
    *,
    max_misses: int = 1,
) -> EyeAcuity | None:
    """Best (lowest) logMAR among rows that passed ≤max_misses."""
    # Smart range rows only locate a candidate boundary. They are deliberately
    # excluded from the reported acuity; only clinical verify rows may score.
    # Legacy records remain eligible for backwards compatibility.
    eye_trials = [
        t for t in trials
        if t.eye == eye and getattr(t, "phase", "legacy") != "range"
    ]
    eligible = [t for t in eye_trials if t.passed]
    if not eligible:
        if not eye_trials:
            return None
        t = eye_trials[-1]
        dec = decimal_from_logmar(t.logmar)
        return EyeAcuity(
            logmar=t.logmar,
            decimal=dec,
            snellen_approx=snellen_approx(dec),
            vn_over_10=vn_over_10(dec),
            correct=t.correct,
            total=t.total,
            row_passed=False,
        )
    best = min(eligible, key=lambda t: t.logmar)
    dec = decimal_from_logmar(best.logmar)
    return EyeAcuity(
        logmar=best.logmar,
        decimal=dec,
        snellen_approx=snellen_approx(dec),
        vn_over_10=vn_over_10(dec),
        correct=best.correct,
        total=best.total,
        row_passed=True,
    )
