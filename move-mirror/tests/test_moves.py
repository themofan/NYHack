"""Headless tests for the gesture classifier — no hardware, no browser."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moves import MoveDetector, Sample, move_for, AXIS_MOVES, VALID_DIRECTIONS
from sources import SimSampleSource


def test_axis_mapping():
    assert move_for(0, 1) == "Right" and move_for(0, -1) == "Left"
    assert move_for(1, 1) == "Up" and move_for(1, -1) == "Down"
    assert move_for(2, 1) is None          # z is not a play direction


def _feed_burst(det, axis, sign, peak=2.5, t0=0.0):
    """Feed gravity, a half-sine burst on one axis, then gravity again."""
    out = []
    grav = [0.0, 0.0, 1.0]
    dt = 0.01
    t = t0
    for _ in range(20):                    # settle baseline at rest
        ev = det.feed(Sample(t, *grav)); out.append(ev); t += dt
    import math
    for k in range(22):                    # the gesture
        p = k / 22
        a = grav[:]
        a[axis] += sign * peak * math.sin(math.pi * p)
        out.append(det.feed(Sample(t, *a))); t += dt
    for _ in range(15):                    # return to rest -> emits the event
        out.append(det.feed(Sample(t, *grav))); t += dt
    return [e for e in out if e is not None]


def test_detects_each_direction():
    for (axis, sign), name in AXIS_MOVES.items():
        det = MoveDetector()
        events = _feed_burst(det, axis, sign)
        assert len(events) == 1, f"{name}: expected 1 event, got {len(events)}"
        assert events[0].name == name, f"axis {axis} sign {sign}: got {events[0].name}"


def test_z_axis_ignored():
    det = MoveDetector()
    assert _feed_burst(det, 2, 1) == []     # z burst -> no play direction


def test_rest_emits_nothing():
    det = MoveDetector()
    out = [det.feed(Sample(i * 0.01, 0.0, 0.0, 1.0)) for i in range(200)]
    assert all(e is None for e in out)


def test_sim_pipeline_end_to_end():
    """Deterministic sim sequence -> classifier recovers the same directions."""
    seq = list(AXIS_MOVES.keys())          # one of each direction, in order
    src = SimSampleSource(auto=True, sequence=seq, gap=(0.4, 0.4))
    det = MoveDetector()
    src.start()
    detected = []
    t_end = time.perf_counter() + 6.0
    while time.perf_counter() < t_end and len(detected) < len(seq):
        ev = det.feed(src.read())
        if ev:
            detected.append(ev.name)
    expected = [move_for(a, s) for (a, s) in seq]
    assert detected == expected, f"expected {expected}, got {detected}"
    assert all(d in VALID_DIRECTIONS for d in detected)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
