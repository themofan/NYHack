"""Sample sources feeding the classifier: real board (serial) or simulator.

Both expose: .start() / .read() -> Optional[Sample] / .stop() / .status_text /
.connected. The simulator needs no hardware and no extra deps (pyserial is only
imported when a real serial source is used).
"""
from __future__ import annotations

import math
import random
import time
from typing import Optional

from moves import Sample, AXIS_MOVES, move_for


class SimSampleSource:
    """Synthesises gravity, plus (if auto) periodic motion bursts.

    auto=False  -> gravity only; the web app is driven by the keyboard instead
                   (no spurious directions). This is the default for play.
    auto=True   -> emits motion bursts; with `sequence` (list of (axis, sign))
                   they're deterministic, used by tests / a self-running demo.
    """

    def __init__(self, auto=False, sequence=None, move_dur=0.22, gap=(1.0, 1.8),
                 peak=(2.0, 3.0)):
        self.auto = auto
        self.sequence = sequence
        self._seq_i = 0
        self.move_dur = move_dur
        self.gap = gap
        self.peak = peak
        self._in_move = False
        self._move_start = 0.0
        self._axis = 0
        self._sign = 1
        self._peak = 2.5
        self._next_at: Optional[float] = None
        self.connected = True
        self.injected_log = []

    @property
    def status_text(self):
        return "SIMULATOR — arrow keys to play" if not self.auto else "SIMULATOR — auto demo"

    def start(self):
        self._next_at = time.perf_counter() + 0.4

    def _pick(self):
        if self.sequence:
            ax, sg = self.sequence[self._seq_i % len(self.sequence)]
            self._seq_i += 1
        else:
            ax, sg = random.choice(list(AXIS_MOVES.keys()))
        return ax, sg

    def read(self) -> Optional[Sample]:
        time.sleep(0.01)                       # ~100 Hz
        t = time.perf_counter()
        a = [random.gauss(0, 0.02), random.gauss(0, 0.02), 1.0 + random.gauss(0, 0.02)]

        if self.auto:
            if not self._in_move and self._next_at and t >= self._next_at:
                self._in_move = True
                self._move_start = t
                self._axis, self._sign = self._pick()
                self._peak = random.uniform(*self.peak)
                self.injected_log.append(move_for(self._axis, self._sign))
            if self._in_move:
                p = (t - self._move_start) / self.move_dur
                if p >= 1.0:
                    self._in_move = False
                    self._next_at = t + random.uniform(*self.gap)
                else:
                    a[self._axis] += self._sign * self._peak * math.sin(math.pi * p)

        return Sample(t, a[0], a[1], a[2],
                      random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))

    def stop(self):
        pass


class SerialSampleSource:
    """Reads `A,ax,ay,az,gx,gy,gz` CSV lines from the board (g + deg/s)."""

    def __init__(self, port: Optional[str] = None, baud: int = 115200):
        import serial  # noqa: local import so sim mode needs no pyserial
        import serial.tools.list_ports as lp
        self._serial = serial
        self._lp = lp
        self.port = port or self._find_port()
        self.baud = baud
        self._ser = None
        self.connected = False
        self.error: Optional[str] = None

    def _find_port(self):
        for p in self._lp.comports():
            blob = " ".join(str(x) for x in (p.device, p.description, p.manufacturer)).lower()
            if any(k in blob for k in ("stlink", "st-link", "stm", "usbmodem")):
                return p.device
        return None

    def start(self):
        if not self.port:
            self.error = "no serial port found"
            return
        try:
            self._ser = self._serial.Serial(self.port, self.baud, timeout=0.2)
            self.connected = True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"

    def read(self) -> Optional[Sample]:
        if not self._ser:
            time.sleep(0.1)
            return None
        try:
            raw = self._ser.readline()
        except Exception as exc:  # noqa: BLE001
            self.error = f"read failed: {exc}"
            self.connected = False
            time.sleep(0.1)
            return None
        if not raw:
            return None
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line.startswith("A,"):
            return None
        parts = line[2:].split(",")
        if len(parts) < 3:
            return None
        try:
            vals = [float(x) for x in parts]
        except ValueError:
            return None
        vals += [0.0] * (6 - len(vals))
        return Sample(time.perf_counter(), vals[0], vals[1], vals[2],
                      vals[3], vals[4], vals[5])

    def stop(self):
        if self._ser:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass

    @property
    def status_text(self) -> str:
        if self.connected:
            return f"SERIAL {self.port} @ {self.baud}"
        return f"SERIAL (disconnected{': ' + self.error if self.error else ''})"
