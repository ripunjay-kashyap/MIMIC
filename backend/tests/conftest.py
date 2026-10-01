import functools
import http.server
import socket
import threading
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_site"


@pytest.fixture(scope="session")
def demo_site_url():
    """Serve backend/demo_site on a free localhost port for the whole test session."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(DEMO_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/"
    server.shutdown()


@pytest.fixture
async def pool():
    from app.browser.pool import BrowserPool

    p = BrowserPool()
    await p.start()
    yield p
    await p.stop()
