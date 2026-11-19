from types import SimpleNamespace

import pytest

from ac.display_client import _auto_px_per_mm, _display_config_payload


def test_auto_px_per_mm_for_32_inch_4k() -> None:
    value = _auto_px_per_mm(32.0, {"screen_width": 3840, "screen_height": 2160})
    assert value is not None
    assert value == pytest.approx(5.42054, rel=1e-4)


def test_manual_calibration_is_authoritative() -> None:
    cfg = SimpleNamespace(
        display=SimpleNamespace(
            calibration_mode="manual",
            diagonal_inches=32.0,
            px_per_mm=4.321,
            calibration_target_mm=100.0,
            calibrated_at="",
        ),
        protocol=SimpleNamespace(distance_m=4.0),
    )
    payload = _display_config_payload(
        cfg, {"screen_width": 3840, "screen_height": 2160}
    )
    assert payload["effective_px_per_mm"] == 4.321
    assert payload["auto_px_per_mm"] is None
    assert payload["distance_m"] == 4.0


def test_auto_uses_configured_inches_and_chart_css_geometry() -> None:
    cfg = SimpleNamespace(
        display=SimpleNamespace(
            calibration_mode="auto", diagonal_inches=40.0,
            px_per_mm=4.3364, calibration_target_mm=100.0,
            calibrated_at="",
        ),
        protocol=SimpleNamespace(distance_m=3.8),
    )
    payload = _display_config_payload(cfg, {"screen_width": 3840, "screen_height": 2160})
    assert payload["effective_px_per_mm"] == pytest.approx(4.3364, rel=1e-3)
    assert payload["distance_m"] == 3.8
