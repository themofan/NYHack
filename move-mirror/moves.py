"""Gesture classification from raw XYZ accelerometer motion. Pure / testable.

A move is detected when the linear (gravity-removed) acceleration spikes past a
threshold. The dominant axis + sign at the peak maps to a named move. Gravity is
tracked with a slow per-axis baseline so the device can be held in any orientation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# (axis_index, sign) -> direction.   axis: 0=x 1=y 2=z
# This is the ONLY place the physical motion <-> direction relationship lives.
# Flip a sign or swap axes here once you see how the sensor is actually held.
AXIS_MOVES = {
    (0, 1): "Right",
    (0, -1): "Left",
    (1, 1): "Up",
    (1, -1): "Down",
}

# Z-axis jerks aren't one of the four play directions — they're ignored upstream.
VALID_DIRECTIONS = {"Up", "Down", "Left", "Right"}


def move_for(axis: int, sign: int):
    return AXIS_MOVES.get((axis, sign))   # None for unmapped (e.g. z axis)


@dataclass
class Sample:
    t: float
    ax: float; ay: float; az: float       # acceleration in g
    gx: float = 0.0; gy: float = 0.0; gz: float = 0.0   # deg/s (unused in v1)


@dataclass
class MoveEvent:
    name: str
    peak_g: float
    axis: str            # e.g. "x+"
    t: float


class MoveDetector:
    def __init__(self, threshold_g=0.8, min_peak_g=1.0, end_debounce_s=0.09,
                 baseline_alpha=0.03):
        self.threshold = threshold_g
        self.min_peak = min_peak_g
        self.end_debounce = end_debounce_s
        self.alpha = baseline_alpha
        self.baseline = [0.0, 0.0, 1.0]    # gravity estimate (g)
        self._have_baseline = False
        self._in_move = False
        self._peak_mag = 0.0
        self._peak_vec = (0.0, 0.0, 0.0)
        self._last_above = 0.0

    def feed(self, s: Sample) -> Optional[MoveEvent]:
        a = [s.ax, s.ay, s.az]
        if not self._have_baseline:
            self.baseline = a[:]
            self._have_baseline = True

        lin = [a[i] - self.baseline[i] for i in range(3)]
        mag = math.sqrt(sum(v * v for v in lin))

        if mag > self.threshold:
            if not self._in_move or mag > self._peak_mag:
                if not self._in_move:
                    self._in_move = True
                self._peak_mag = mag
                self._peak_vec = (lin[0], lin[1], lin[2])
            self._last_above = s.t
            return None

        # quiescent: let the baseline drift toward current gravity
        for i in range(3):
            self.baseline[i] = (1 - self.alpha) * self.baseline[i] + self.alpha * a[i]

        if self._in_move and (s.t - self._last_above) >= self.end_debounce:
            self._in_move = False
            peak_mag, peak_vec = self._peak_mag, self._peak_vec
            self._peak_mag = 0.0
            if peak_mag >= self.min_peak:
                axis = max(range(3), key=lambda i: abs(peak_vec[i]))
                sign = 1 if peak_vec[axis] >= 0 else -1
                name = move_for(axis, sign)
                if name is not None:          # ignore z-dominant jerks
                    return MoveEvent(
                        name=name,
                        peak_g=peak_mag,
                        axis="xyz"[axis] + ("+" if sign > 0 else "-"),
                        t=s.t,
                    )
        return None
