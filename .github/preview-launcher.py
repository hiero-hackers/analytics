#!/usr/bin/env python3
"""Serve a dashboard preview locally and open it in your browser.

Shipped into every dashboard-preview artifact as ``preview.py``. The dashboard
loads its data (JSON documents and chart images) over HTTP, so it cannot run
from a ``file://`` URL — this starts a local static server on a free port,
rooted next to this file, and opens the page.
"""

import contextlib
import os
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def main() -> None:
    """Serve the directory this file sits in, then open the page."""
    root = os.path.dirname(os.path.abspath(__file__))
    port = int(os.environ.get("PREVIEW_PORT", "0"))  # 0 = any free port
    handler = partial(SimpleHTTPRequestHandler, directory=root)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Dashboard preview: {url}  (Ctrl+C to stop)")
    if not os.environ.get("PREVIEW_NO_OPEN"):
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
