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


# --- tilt-based detection ----------------------------------------------------
def _norm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v):
    n = _norm(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else (0.0, 0.0, 1.0)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _angle_deg(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(_unit(a), _unit(b))))))


class TiltDetector:
    """Direction from TILT (gravity orientation) — robust, unambiguous.

    Unlike flick detection, this has no accel/decel double-pulse problem: it reads
    where gravity points. The smoothed gravity vector is matched to the nearest of
    four calibrated tilt poses once it leaves neutral. One event per tilt
    (hysteresis), so holding a tilt doesn't repeat-fire. Ships with sensible
    defaults so it works out-of-box; calibration refines the mapping to how the
    sensor is actually held.
    """
    DIRS = ("Up", "Down", "Left", "Right")

    def __init__(self, on_deg=20.0, off_deg=10.0, smooth_alpha=0.15):
        self.on_deg = on_deg
        self.off_deg = off_deg
        self.alpha = smooth_alpha
        self.g = [0.0, 0.0, 1.0]
        self._init = False
        self._tilted = False
        # default mapping (typical flat-ish hold); calibration overrides these
        self.neutral = (0.0, 0.0, 1.0)
        self.templates = {
            "Up": _unit((0.0, 0.5, 0.866)),
            "Down": _unit((0.0, -0.5, 0.866)),
            "Left": _unit((-0.5, 0.0, 0.866)),
            "Right": _unit((0.5, 0.0, 0.866)),
        }

    def feed(self, s: Sample):
        a = (s.ax, s.ay, s.az)
        if not self._init:
            self.g = [a[0], a[1], a[2]]
            self._init = True
        else:
            for i in range(3):
                self.g[i] = (1 - self.alpha) * self.g[i] + self.alpha * a[i]
        if not self.ready:
            return None
        ang = _angle_deg(self.g, self.neutral)
        if not self._tilted and ang >= self.on_deg:
            self._tilted = True
            g_unit = _unit(tuple(self.g))
            name = max(self.DIRS, key=lambda d: _dot(g_unit, self.templates[d]))
            return MoveEvent(name=name, peak_g=ang, axis="tilt", t=s.t)
        if self._tilted and ang <= self.off_deg:
            self._tilted = False
        return None

    def capture(self, name: str):
        """Store the current smoothed gravity as a calibration pose."""
        vec = _unit(tuple(self.g))
        if name == "neutral":
            self.neutral = vec
        elif name in self.DIRS:
            self.templates[name] = vec
        return self.status()

    @property
    def ready(self):
        return self.neutral is not None and all(d in self.templates for d in self.DIRS)

    def status(self):
        captured = (["neutral"] if self.neutral is not None else [])
        captured += [d for d in self.DIRS if d in self.templates]
        return {"captured": captured, "ready": self.ready}
