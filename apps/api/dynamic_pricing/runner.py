"""Entrypoint for the packaged desktop build.

One process serves both the API and the exported web app, then opens the
operator's browser at it. That shape is deliberate: it is the same FastAPI
application that would run on a server, so moving this to a hosted web app
later means deleting the browser call, not rewriting anything.

Run it from a checkout with::

    python -m dynamic_pricing.runner
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

from .packaging import user_data_dir, web_dist

#: Tried first so the address stays memorable; any free port works.
PREFERRED_PORT = 8000
HOST = "127.0.0.1"


def find_free_port(preferred: int = PREFERRED_PORT) -> int:
    """The preferred port if it is free, otherwise one the OS picks.

    An operator whose machine already runs something on 8000 should get a
    working app, not a stack trace — which is also why the frontend calls the
    API on a relative path rather than a baked-in port.
    """
    # Deliberately WITHOUT SO_REUSEADDR: this is a "does anyone hold this port"
    # probe, and the option is what would let the bind succeed anyway.
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, candidate))
            except OSError:
                continue
            return sock.getsockname()[1]
    raise RuntimeError("No free port available on 127.0.0.1")


def open_when_ready(url: str, port: int, timeout: float = 30.0) -> None:
    """Open the browser once the port actually accepts a connection.

    A fixed sleep races the first request on a cold start — seeding the demo
    database takes a moment — and the operator sees a connection error on the
    one screen that is supposed to prove the product works.
    """
    def wait_and_open() -> None:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                if sock.connect_ex((HOST, port)) == 0:
                    webbrowser.open(url)
                    return
            time.sleep(0.25)
        print(f"  ! The app did not come up in {timeout:.0f}s. Open {url} yourself.")

    threading.Thread(target=wait_and_open, daemon=True).start()


def main() -> int:
    import uvicorn

    if web_dist() is None:
        print("The web app has not been built.")
        print("  From a checkout, run:  make bundle")
        return 1

    port = find_free_port()
    url = f"http://{HOST}:{port}/"

    print()
    print("  Dynamic Pricing Property")
    print("  Revenue intelligence above Blue Jay PMS — Shadow Mode")
    print()
    print(f"  Opening    {url}")
    print(f"  Data       {user_data_dir()}")
    print()
    print("  Close this window to stop the app.")
    print()

    open_when_ready(url, port)

    from .main import app

    uvicorn.run(app, host=HOST, port=port, log_level="warning")
    return 0



if __name__ == "__main__":
    # `python -m dynamic_pricing.runner` from a checkout. The packaged build
    # enters through packaging/entrypoint.py instead, because a frozen entry
    # script has no package context for this module's relative imports.
    sys.exit(main())
