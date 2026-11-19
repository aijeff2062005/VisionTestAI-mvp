"""Standing-zone detector: white ceramic floor (default) or optional tape line."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class LineBand:
    """Standing zone in image coordinates (floor region or tape band)."""

    y_center: int = 0
    y_top: int = 0
    y_bottom: int = 0
    x_left: int = 0
    x_right: int = 0
    contour: np.ndarray | None = None
    polygon: np.ndarray | None = None  # Nx1x2 int32 for drawing / point test
    mode: str = "floor"
    found: bool = False
    label: str = "STAND ZONE"


class FloorLineDetector:
    """
    mode=floor  → detect bright white/light ceramic floor as stand zone (MVP default)
    mode=tape   → detect colored floor tape band (optional at some facilities)
    mode=fixed  → use configured normalized polygon only
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        line_cfg = cfg.get("line", {})
        self.mode = str(line_cfg.get("mode", "floor")).lower()

        # White / light ceramic: low saturation, high value
        self.floor_hsv_low = np.array(
            line_cfg.get("floor_hsv_low", [0, 0, 140]), dtype=np.uint8
        )
        self.floor_hsv_high = np.array(
            line_cfg.get("floor_hsv_high", [179, 55, 255]), dtype=np.uint8
        )

        # Optional tape (yellow / green)
        self.hsv_low = np.array(line_cfg.get("hsv_low", [18, 80, 80]), dtype=np.uint8)
        self.hsv_high = np.array(line_cfg.get("hsv_high", [45, 255, 255]), dtype=np.uint8)
        self.hsv_low2 = np.array(line_cfg.get("hsv_low2", [40, 60, 60]), dtype=np.uint8)
        self.hsv_high2 = np.array(line_cfg.get("hsv_high2", [90, 255, 255]), dtype=np.uint8)

        self.band_margin_px = int(line_cfg.get("band_margin_px", 40))
        self.min_length_px = int(line_cfg.get("min_length_px", 80))
        self.min_area = int(line_cfg.get("min_area", 2500))
        self.min_floor_area_ratio = float(line_cfg.get("min_floor_area_ratio", 0.04))
        # Search window as fraction of frame (x0,y0,x1,y1) — corridor tiles in screenshot
        self.search_roi = list(
            line_cfg.get("search_roi", [0.28, 0.42, 0.92, 1.0])
        )
        self.bottom_roi_ratio = float(line_cfg.get("bottom_roi_ratio", 0.58))
        k = int(line_cfg.get("morph_kernel", 7))
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        self.erode_iters = int(line_cfg.get("erode_iters", 1))
        self.dilate_iters = int(line_cfg.get("dilate_iters", 2))

        # Optional fixed polygon in normalized coords [[x,y], ...]
        fixed = line_cfg.get("fixed_polygon") or []
        self.fixed_polygon_norm: list[list[float]] = [
            [float(p[0]), float(p[1])] for p in fixed
        ]

    def apply_stand_zone(
        self,
        *,
        mode: str | None = None,
        polygon: list[list[float]] | None = None,
    ) -> None:
        """Live-update mode / fixed polygon without recreating the detector."""
        if mode is not None:
            self.mode = str(mode).lower()
        if polygon is not None:
            self.fixed_polygon_norm = [
                [float(p[0]), float(p[1])] for p in polygon if len(p) >= 2
            ]

    def detect(self, frame: np.ndarray) -> LineBand:
        if self.mode == "tape":
            return self._detect_tape(frame)
        if self.mode == "fixed":
            return self._detect_fixed(frame)
        # floor (default): prefer auto white floor; fall back to fixed polygon if set
        zone = self._detect_floor(frame)
        if zone.found:
            return zone
        if self.fixed_polygon_norm:
            return self._detect_fixed(frame)
        return zone

    def _roi_slice(self, frame: np.ndarray) -> tuple[int, int, int, int]:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = self.search_roi
        return (
            int(max(0, min(w - 1, w * x0))),
            int(max(0, min(h - 1, h * y0))),
            int(max(0, min(w, w * x1))),
            int(max(0, min(h, h * y1))),
        )

    def _detect_floor(self, frame: np.ndarray) -> LineBand:
        h, w = frame.shape[:2]
        rx0, ry0, rx1, ry1 = self._roi_slice(frame)
        roi = frame[ry0:ry1, rx0:rx1]
        if roi.size == 0:
            return LineBand(mode="floor", found=False)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.floor_hsv_low, self.floor_hsv_high)
        # Drop very dark pixels (door threshold / shadows)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mask = cv2.bitwise_and(mask, cv2.inRange(gray, 120, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel, iterations=1)
        if self.erode_iters > 0:
            mask = cv2.erode(mask, self.kernel, iterations=self.erode_iters)
        if self.dilate_iters > 0:
            mask = cv2.dilate(mask, self.kernel, iterations=self.dilate_iters)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return LineBand(mode="floor", found=False)

        min_area = max(self.min_area, int(h * w * self.min_floor_area_ratio))
        best = None
        best_score = -1.0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Prefer wide floor-like blobs over tall wall patches
            aspect = bw / max(bh, 1)
            if aspect < 0.55 and bh > bw * 1.2:
                continue
            cy = y + bh / 2
            bottom_bias = 1.0 + 1.2 * (cy / max(roi.shape[0], 1))
            score = area * bottom_bias * (1.0 + min(aspect, 3.0) * 0.35)
            if score > best_score:
                best_score = score
                best = cnt

        if best is None:
            return LineBand(mode="floor", found=False)

        # Approximate to a simpler polygon for stable overlay / point tests
        peri = cv2.arcLength(best, True)
        approx = cv2.approxPolyDP(best, 0.02 * peri, True)
        if len(approx) < 3:
            approx = best

        poly = approx.copy()
        poly[:, :, 0] += rx0
        poly[:, :, 1] += ry0

        # Keep zone on the lower floor: clip anything above mid-search ROI
        clip_y = ry0 + int(0.12 * (ry1 - ry0))
        clipped = []
        for p in poly.reshape(-1, 2):
            px, py = int(p[0]), int(p[1])
            clipped.append([[px, max(py, clip_y)]])
        # Rebuild convex hull after clip for a clean box-like zone
        pts = np.array(clipped, dtype=np.int32)
        hull = cv2.convexHull(pts)
        if hull is None or len(hull) < 3:
            hull = poly

        x, y, bw, bh = cv2.boundingRect(hull)
        return LineBand(
            y_center=y + bh // 2,
            y_top=y,
            y_bottom=y + bh,
            x_left=x,
            x_right=x + bw,
            contour=hull,
            polygon=hull,
            mode="floor",
            found=True,
            label="STAND ZONE",
        )

    def _detect_fixed(self, frame: np.ndarray) -> LineBand:
        h, w = frame.shape[:2]
        if len(self.fixed_polygon_norm) < 3:
            return LineBand(mode="fixed", found=False)
        pts = np.array(
            [[int(p[0] * w), int(p[1] * h)] for p in self.fixed_polygon_norm],
            dtype=np.int32,
        ).reshape(-1, 1, 2)
        x, y, bw, bh = cv2.boundingRect(pts)
        return LineBand(
            y_center=y + bh // 2,
            y_top=y,
            y_bottom=y + bh,
            x_left=x,
            x_right=x + bw,
            contour=pts,
            polygon=pts,
            mode="fixed",
            found=True,
            label="STAND ZONE",
        )

    def _detect_tape(self, frame: np.ndarray) -> LineBand:
        h, w = frame.shape[:2]
        y0 = int(h * (1.0 - self.bottom_roi_ratio))
        roi = frame[y0:h, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        mask1 = cv2.inRange(hsv, self.hsv_low, self.hsv_high)
        mask2 = cv2.inRange(hsv, self.hsv_low2, self.hsv_high2)
        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return LineBand(mode="tape", found=False)

        best = None
        best_score = -1.0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < max(200, self.min_area // 10):
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if bw < self.min_length_px:
                continue
            aspect = bw / max(bh, 1)
            score = area * (1.0 + min(aspect, 8.0))
            if score > best_score:
                best_score = score
                best = (cnt, x, y, bw, bh)

        if best is None:
            return LineBand(mode="tape", found=False)

        cnt, x, y, bw, bh = best
        cnt_full = cnt.copy()
        cnt_full[:, :, 1] += y0
        y_center = y0 + y + bh // 2
        y_top = max(0, y_center - self.band_margin_px)
        y_bottom = min(h - 1, y_center + self.band_margin_px)
        # Band rectangle as polygon
        poly = np.array(
            [
                [[max(0, x - 20), y_top]],
                [[min(w - 1, x + bw + 20), y_top]],
                [[min(w - 1, x + bw + 20), y_bottom]],
                [[max(0, x - 20), y_bottom]],
            ],
            dtype=np.int32,
        )
        return LineBand(
            y_center=y_center,
            y_top=y_top,
            y_bottom=y_bottom,
            x_left=x,
            x_right=x + bw,
            contour=cnt_full,
            polygon=poly,
            mode="tape",
            found=True,
            label="TAPE LINE",
        )

    @staticmethod
    def point_in_zone(band: LineBand, pt: tuple[int, int] | None) -> bool:
        if not band.found or pt is None:
            return False
        if band.polygon is not None and len(band.polygon) >= 3:
            # +1 inside, 0 edge, -1 outside
            return cv2.pointPolygonTest(band.polygon, (float(pt[0]), float(pt[1])), False) >= 0
        x, y = pt
        if y < band.y_top or y > band.y_bottom:
            return False
        margin_x = max(40, (band.x_right - band.x_left) // 4)
        return (band.x_left - margin_x) <= x <= (band.x_right + margin_x)

    @staticmethod
    def ankles_in_band(
        band: LineBand,
        left_ankle: tuple[int, int] | None,
        right_ankle: tuple[int, int] | None,
        midpoint: tuple[int, int] | None,
        *,
        require_both: bool = False,
    ) -> bool:
        if not band.found:
            return False

        if require_both:
            return FloorLineDetector.point_in_zone(
                band, left_ankle
            ) and FloorLineDetector.point_in_zone(band, right_ankle)
        if midpoint is not None:
            return FloorLineDetector.point_in_zone(band, midpoint)
        return FloorLineDetector.point_in_zone(
            band, left_ankle
        ) or FloorLineDetector.point_in_zone(band, right_ankle)
