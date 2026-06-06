"""Localhost server: classify accelerometer motion and push directions to the browser.

Pipeline:  source (serial board | simulator) -> MoveDetector -> Server-Sent Events
The browser game (web/index.html) consumes `direction` events to clear combos,
and `sample` events to show the live XYZ. Pure stdlib HTTP + SSE (only pyserial,
and only in serial mode).

    python server.py            # auto: serial board if found, else simulator
    python server.py --sim      # simulator (play with arrow keys in the browser)
    python server.py --auto-sim # simulator that performs random motions itself
    python server.py --port /dev/tty.usbmodemXXXX
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from moves import MoveDetector, VALID_DIRECTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")


class Hub:
    """Fan-out of SSE messages to every connected browser."""

    def __init__(self):
        self._clients = set()
        self._lock = threading.Lock()

    def register(self) -> "queue.Queue":
        q: "queue.Queue" = queue.Queue(maxsize=200)
        with self._lock:
            self._clients.add(q)
        return q

    def unregister(self, q) -> None:
        with self._lock:
            self._clients.discard(q)

    def broadcast(self, event: str, data: dict) -> None:
        msg = (event, json.dumps(data))
        with self._lock:
            for q in list(self._clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass


def worker(hub: Hub, source, detector: MoveDetector, stop: threading.Event) -> None:
    source.start()
    last_sample = 0.0
    while not stop.is_set():
        s = source.read()
        if s is None:
            continue
        ev = detector.feed(s)
        if ev is not None and ev.name in VALID_DIRECTIONS:
            hub.broadcast("direction", {"dir": ev.name, "peak_g": round(ev.peak_g, 2)})
        if s.t - last_sample > 0.05:           # throttle live axes to ~20 Hz
            hub.broadcast("sample", {"x": round(s.ax, 3), "y": round(s.ay, 3),
                                     "z": round(s.az, 3)})
            last_sample = s.t


def make_handler(hub: Hub, status_fn):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):            # quiet console
            pass

        def _send_file(self, name, ctype):
            path = os.path.join(WEB, name)
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_file("index.html", "text/html; charset=utf-8")
            elif self.path == "/status":
                body = json.dumps(status_fn()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self._sse()
            else:
                self.send_error(404)

        def _sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = hub.register()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event, data = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")   # keep-alive
                        self.wfile.flush()
                        continue
                    self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unregister(q)

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Move Mirror — ghost combo game server")
    ap.add_argument("--sim", action="store_true", help="simulator (arrow keys to play)")
    ap.add_argument("--auto-sim", action="store_true", help="simulator that moves itself")
    ap.add_argument("--port", default=None, help="serial port of the STM32 board")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args()

    if args.sim or args.auto_sim:
        from sources import SimSampleSource
        source = SimSampleSource(auto=args.auto_sim)
    else:
        from sources import SimSampleSource, SerialSampleSource
        ser = SerialSampleSource(args.port)
        if ser.port:
            source = ser
        else:
            print("No board found — simulator mode (play with arrow keys).")
            source = SimSampleSource(auto=False)

    hub = Hub()
    detector = MoveDetector()
    stop = threading.Event()
    threading.Thread(target=worker, args=(hub, source, detector, stop), daemon=True).start()

    handler = make_handler(hub, lambda: {"source": source.status_text,
                                         "connected": source.connected})
    httpd = ThreadingHTTPServer(("127.0.0.1", args.http_port), handler)
    url = f"http://localhost:{args.http_port}"
    print(f"Move Mirror running → {url}   ({source.status_text})")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        source.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
