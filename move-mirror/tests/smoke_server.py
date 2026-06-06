"""Smoke test: boot the server in-process and verify HTTP + SSE work."""
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import ThreadingHTTPServer
from moves import MoveDetector
from sources import SimSampleSource
from server import Hub, worker, make_handler

PORT = 8077
hub = Hub()
detector = MoveDetector()
# auto sim so 'direction' events actually flow through the SSE pipe
source = SimSampleSource(auto=True, gap=(0.3, 0.3))
stop = threading.Event()
threading.Thread(target=worker, args=(hub, source, detector, stop), daemon=True).start()

handler = make_handler(hub, lambda: {"source": source.status_text, "connected": True})
httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
time.sleep(0.3)

try:
    # 1) index page serves
    html = urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=3).read().decode()
    assert "Ghost Combo" in html, "index.html not served"
    assert "EventSource" in html

    # 2) status endpoint
    import json
    st = json.loads(urllib.request.urlopen(f"http://localhost:{PORT}/status", timeout=3).read())
    assert "source" in st

    # 3) SSE stream delivers at least one direction event within a few seconds
    req = urllib.request.urlopen(f"http://localhost:{PORT}/events", timeout=6)
    got_direction = False
    deadline = time.time() + 6
    buf = b""
    while time.time() < deadline and not got_direction:
        line = req.readline()
        if not line:
            break
        buf += line
        if b"event: direction" in buf:
            got_direction = True
    assert got_direction, "no direction event received over SSE"

    print("SMOKE OK: index served, /status ok, SSE delivered a direction event")
finally:
    stop.set()
    httpd.shutdown()
