"""Command line entry point.

Three ways in, and the first one is the only one most people will ever need::

    python start.py             # start the app and open the browser
    python -m nonoforge         # the same thing
    python -m nonoforge doctor  # print what this computer has, and stop
"""

from __future__ import annotations

import argparse
import sys

from . import APP_NAME, __version__


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nonoforge",
        description="%s — %s" % (APP_NAME, "pick what you want to make, press one button, it exists."),
        epilog="Run it with no arguments and a browser window opens. That is the whole idea.",
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run", "doctor", "version"],
                        help="what to do (default: run)")
    parser.add_argument("--port", type=int, default=8762, help="which port to use (default 8762)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default 127.0.0.1 — this computer only)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.add_argument("--version", action="store_true", help="print the version and stop")
    args = parser.parse_args(argv)

    if args.version or args.command == "version":
        print("%s %s" % (APP_NAME, __version__))
        return 0
    if args.command == "doctor":
        from .server import doctor_text

        print(doctor_text())
        return 0

    from .server import create_app

    app = create_app()
    try:
        app.serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    except OSError as exc:
        print("\n  Could not start on %s:%d (%s).\n  Try a different port: --port 8772\n"
              % (args.host, args.port, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
