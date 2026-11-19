"""Age → habitual VA start line + binary-search helpers for speaker_v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Sequence


# Starting chart level (x/10) by patient age.
_AGE_START_TENTHS: tuple[tuple[int | None, int | None, int], ...] = (
    (0, 49, 5),
    (50, 59, 4),
    (60, 79, 3),
    (80, None, 2),
)

# Fallback when DOB is missing or invalid.
_DEFAULT_START_TENTHS = 4


def parse_dob(value: object) -> date | None:
    """Parse Frappe/ISO DOB strings into a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def age_years(dob: date | None, *, today: date | None = None) -> int | None:
    if dob is None:
        return None
    ref = today or date.today()
    years = ref.year - dob.year
    if (ref.month, ref.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def start_tenths_for_age(age: int | None) -> int:
    """Return VN chart start line in tenths (e.g. 8 → 8/10)."""
    if age is None:
        return _DEFAULT_START_TENTHS
    for lo, hi, tenths in _AGE_START_TENTHS:
        if lo is not None and age < lo:
            continue
        if hi is not None and age > hi:
            continue
        return tenths
    return _DEFAULT_START_TENTHS


def start_tenths_from_dob(dob: object, *, today: date | None = None) -> int:
    return start_tenths_for_age(age_years(parse_dob(dob), today=today))


def nearest_row_index(row_logmars: Sequence[float], logmar: float) -> int:
    return min(range(len(row_logmars)), key=lambda i: abs(float(row_logmars[i]) - float(logmar)))


def tenths_to_logmar(tenths: int) -> float:
    """Convert x/10 → logMAR (matches clinic chart)."""
    import math

    return round(-math.log10(max(tenths, 1) / 10.0), 5)


def start_logmar_from_dob(
    dob: object,
    row_logmars: Sequence[float],
    *,
    today: date | None = None,
) -> float:
    """Snap age-norm start tenths onto the configured chart rows."""
    target = tenths_to_logmar(start_tenths_from_dob(dob, today=today))
    if not row_logmars:
        return target
    idx = nearest_row_index(row_logmars, target)
    return float(row_logmars[idx])


@dataclass
class BinarySearchState:
    """Inclusive window on row indices ordered easy→hard (large→small logMAR)."""

    lo: int
    hi: int
    probe: int
    last_passed: int | None = None
    ever_passed: bool = False

    @classmethod
    def seed(cls, n_rows: int, start_index: int) -> BinarySearchState:
        if n_rows <= 0:
            raise ValueError("n_rows must be positive")
        start = max(0, min(int(start_index), n_rows - 1))
        return cls(lo=0, hi=n_rows - 1, probe=start)

    def next_after_pass(self) -> bool:
        """Raise floor after a pass. Returns True if search should continue."""
        self.last_passed = self.probe
        self.ever_passed = True
        self.lo = self.probe
        if self.hi <= self.lo:
            return False
        # Midpoint toward harder (higher index).
        nxt = (self.lo + self.hi + 1) // 2
        if nxt == self.probe:
            nxt = min(self.hi, self.probe + 1)
        if nxt == self.probe or nxt > self.hi:
            return False
        self.probe = nxt
        return True

    def next_after_fail(self) -> bool:
        """Lower ceiling after a fail. Returns True if search should continue.

        Never scores the failed line. Must keep searching until ≥1 pass if possible.
        """
        self.hi = self.probe - 1
        if self.hi < self.lo:
            return False
        if self.hi == self.lo:
            # Only one candidate left — probe it unless we already passed it.
            if self.last_passed == self.lo and self.ever_passed:
                return False
            self.probe = self.lo
            return True
        nxt = (self.lo + self.hi) // 2
        if nxt == self.probe:
            nxt = max(self.lo, self.probe - 1)
        if nxt < self.lo:
            return False
        self.probe = nxt
        return True

    def finished(self) -> bool:
        return self.hi < self.lo or (self.hi == self.lo and self.ever_passed and self.last_passed == self.lo)


@dataclass
class SmartRangeSearchState:
    """Two-phase acuity search: provisional 2+1 range, then clinical 3/5 verify.

    Row indices are ordered easy→hard.  Range observations only narrow the
    monotonic pass/fail boundary; they never become a reported acuity result.
    """

    n_rows: int
    probe: int
    phase: str = "range"
    hardest_passed: int | None = None
    easiest_failed: int | None = None
    verify_index: int | None = None
    verify_fallbacks_used: int = 0
    max_verify_fallbacks: int = 1
    visited: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.n_rows <= 0:
            raise ValueError("n_rows must be positive")
        self.probe = max(0, min(int(self.probe), self.n_rows - 1))
        self.visited = set(self.visited)

    @classmethod
    def seed(cls, n_rows: int, start_index: int) -> SmartRangeSearchState:
        return cls(n_rows=n_rows, probe=start_index)

    @property
    def is_range(self) -> bool:
        return self.phase == "range"

    @property
    def is_verify(self) -> bool:
        return self.phase == "verify"

    def _begin_verify(self) -> None:
        candidate = self.hardest_passed if self.hardest_passed is not None else 0
        self.phase = "verify"
        self.verify_index = max(0, min(candidate, self.n_rows - 1))
        self.probe = self.verify_index

    def record_range(self, passed: bool) -> bool:
        """Record a provisional range row. Return True when verify should start."""
        if not self.is_range:
            raise RuntimeError("range result recorded outside range phase")
        current = self.probe
        self.visited.add(current)
        if passed:
            self.hardest_passed = (
                current
                if self.hardest_passed is None
                else max(self.hardest_passed, current)
            )
        else:
            self.easiest_failed = (
                current
                if self.easiest_failed is None
                else min(self.easiest_failed, current)
            )

        lower = self.hardest_passed if self.hardest_passed is not None else -1
        upper = self.easiest_failed if self.easiest_failed is not None else self.n_rows
        candidates = [
            idx
            for idx in range(lower + 1, upper)
            if idx not in self.visited
        ]
        if not candidates:
            self._begin_verify()
            return True

        # Midpoint of the remaining monotonic interval. This never revisits a row.
        self.probe = candidates[(len(candidates) - 1) // 2]
        return False

    def record_verify(self, passed: bool) -> bool:
        """Record a 3/5 verification. Return True when this eye is complete."""
        if not self.is_verify:
            raise RuntimeError("verify result recorded outside verify phase")
        if passed:
            return True
        # A failed candidate may be checked at one easier row only.  Walking
        # through the whole chart on silence makes replacement appear endless
        # and cannot add trustworthy acuity evidence.
        if self.probe <= 0 or self.verify_fallbacks_used >= self.max_verify_fallbacks:
            return True
        self.verify_fallbacks_used += 1
        self.probe -= 1
        self.verify_index = self.probe
        return False
