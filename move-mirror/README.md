# Ghost Combo (Move Mirror)

Hold the accelerometer. A ghost mob appears on screen with a sequence of arrows
(↑ ↓ ← →) above it. Move the accelerometer in those directions **in order** to
clear the combo and defeat the mob. Three misses and it's game over. Combos get
longer as you level up.

```
 STM32 + MPU-6050  ──serial(CSV)──▶  server.py  ──Server-Sent Events──▶  browser game
   (your friend)    A,ax,ay,az,...   classifies          /events          ghost + arrows
```

## Run it now (no hardware)

```bash
cd ~/Documents/Code/move-mirror
python3 server.py --sim          # opens http://localhost:8000 in your browser
```
In sim mode you play with the **arrow keys** (or WASD). SPACE / click to start,
R to restart after game over.

## Run with the board

1. Flash `firmware/move_stream/` to the Nucleo (PlatformIO, same env as the
   NYHack repo). It streams `A,ax,ay,az,gx,gy,gz` at 115200 baud.
2. Plug in over USB, then:
   ```bash
   source .venv/bin/activate        # venv has pyserial
   python server.py                 # auto-detects the ST-Link port
   # or: python server.py --port /dev/tty.usbmodemXXXX
   ```
Now physical Up/Down/Left/Right motions clear the combos.

Other flags: `--auto-sim` (sim moves itself, for a hands-off demo),
`--http-port 8001`, `--no-open`.

## How motion becomes a direction

`moves.py` removes gravity with a slow per-axis baseline, then on each motion
spike picks the dominant axis + sign and maps it to a direction:

| motion | direction |
|---|---|
| +X / −X | Right / Left |
| +Y / −Y | Up / Down |
| Z axis | ignored (not a play direction) |

**The mapping is one dict** (`AXIS_MOVES` in `moves.py`). Once you see how the
sensor sits in the hand, flip a sign or swap an axis there — that's the only
place the physical-motion ↔ direction relationship lives. Nothing else changes.

## Tests

```bash
python3 tests/test_moves.py       # classifier: each direction, z ignored, sim pipeline
python3 tests/smoke_server.py     # HTTP serves + SSE delivers direction events
```

## Files

| file | role |
|---|---|
| `moves.py` | gravity removal + gesture → direction classifier (pure, tested) |
| `sources.py` | sample sources: simulator + real serial board |
| `server.py` | localhost HTTP + SSE; runs the classifier worker |
| `web/index.html` | the game — ghost mob, arrow combos, scoring (self-contained) |
| `firmware/move_stream/` | STM32 sketch that streams raw XYZ |
