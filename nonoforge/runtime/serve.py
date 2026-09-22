"""The tiny engine behind this app — about 400 lines of careful comments included,
and this is the whole manual.

It uses nothing except Python's own toolbox, so there is nothing to install and
nothing that can go out of date. Three ideas, and that is all:

  * **routes** — "when the browser asks for this address, run this function"
  * **data**   — two helpers for a spreadsheet (CSV) that other programs can
                 also open in Excel or Numbers
  * **serve**  — switch it on, then open the browser page

You will probably never need to change this file. If you do want to, the
comments below explain everything as it comes up.
"""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import mimetypes
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"          # the pages you look at
DATA = HERE / "data"        # the things you type in — yours, and only yours

mimetypes.add_type("application/javascript", ".js")


# --------------------------------------------------------------------------
# What a route can send back
# --------------------------------------------------------------------------
class Json:
    """Some data, for the page to use."""

    def __init__(self, data, status: int = 200):
        self.body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
        self.status = status
        self.type = "application/json; charset=utf-8"
        self.headers = {}


class Text:
    """A plain answer, not a page."""

    def __init__(self, text: str, status: int = 200):
        self.body = str(text).encode("utf-8")
        self.status = status
        self.type = "text/plain; charset=utf-8"
        self.headers = {}


class Bytes:
    """A file, sent as it is: an image, a photo, a download."""

    def __init__(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200):
        self.body = data
        self.status = status
        self.type = content_type
        self.headers = {}


class Download(Bytes):
    """A file the browser should save rather than display."""

    def __init__(self, data: bytes, filename: str, content_type: str = "application/octet-stream"):
        super().__init__(data, content_type)
        safe = "".join(ch for ch in filename if ch.isalnum() or ch in " ._-")
        self.headers["Content-Disposition"] = 'attachment; filename="%s"' % (safe or "download")


def Page(name: str, status: int = 200):
    """Send one of the files from the web/ folder."""
    path = (WEB / name).resolve()
    if not path.is_file():
        return Text("There is no page called %s" % name, 404)
    return Bytes(path.read_bytes(), mimetypes.guess_type(str(path))[0] or "text/plain", status)


class Bad:
    """Something went wrong, in words the person using it can act on."""

    def __init__(self, message: str, status: int = 400):
        self.body = json.dumps({"error": message}).encode("utf-8")
        self.status = status
        self.type = "application/json; charset=utf-8"


class Redirect:
    def __init__(self, where: str, status: int = 303):
        self.where = where
        self.status = status


# --------------------------------------------------------------------------
# Reading and writing your data
# --------------------------------------------------------------------------
def data_file(name: str) -> Path:
    """The full path of a file in the data/ folder, creating the folder if needed."""
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA / name


def load_rows(name: str) -> list:
    """Read a spreadsheet as a list of dictionaries. Missing file = no rows yet."""
    path = data_file(name)
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def save_rows(name: str, rows: list) -> None:
    """Write a whole spreadsheet. Columns are worked out from the rows."""
    path = data_file(name)
    rows = list(rows)
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    # Keep the usual order for the columns this app always has.
    preferred = ["when", "name", "what", "answer", "note", "amount", "category"]
    columns = [key for key in preferred if key in columns] + [key for key in columns if key not in preferred]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or ["when"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


def add_row(name: str, row: dict) -> dict:
    """Add one row to the end of a spreadsheet, and hand it back."""
    rows = load_rows(name)
    rows.append(dict(row))
    save_rows(name, rows)
    return dict(row)


def stamp(row: dict) -> dict:
    """Put the date and time on a row, in a form anyone can read."""
    row = dict(row)
    row.setdefault("when", time.strftime("%Y-%m-%d %H:%M"))
    return row


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------
class Request:
    def __init__(self, method, path, query, body, params):
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.params = params

    def json(self) -> dict:
        if not self.body:
            return {}
        try:
            value = json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def field(self, name: str, default: str = "") -> str:
        """A piece of text someone typed, cleaned up and never absurdly long."""
        value = self.json().get(name, default)
        return str(value if value is not None else default).strip()[:2000]

    def number(self, name: str, default: float = 0.0) -> float:
        try:
            return float(str(self.json().get(name, default)).replace(",", "").strip())
        except (TypeError, ValueError):
            return default


class App:
    """Your app: a handful of routes and the folder of pages."""

    def __init__(self, name: str, default_port: int = 8763):
        self.name = name
        self.default_port = default_port
        self.routes = []
        self.folder = HERE

    # -- registering routes ------------------------------------------------
    def route(self, method: str, pattern: str, handler):
        self.routes.append((method.upper(), pattern, handler))
        return handler

    def get(self, pattern: str):
        def register(handler):
            return self.route("GET", pattern, handler)

        return register

    def post(self, pattern: str):
        def register(handler):
            return self.route("POST", pattern, handler)

        return register

    # -- looking after files ----------------------------------------------
    def static(self, path: str, method: str = "GET"):
        """Send a file from web/, refusing to wander outside the folder."""
        relative = path.lstrip("/") or "index.html"
        target = (WEB / relative).resolve()
        try:
            target.relative_to(WEB.resolve())
        except ValueError:
            return Bad("Not found", 404)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            if "." in Path(relative).name:
                return Bad("Not found", 404)
            return Page("index.html")  # a page name we do not know: show the app
        return Bytes(target.read_bytes(), mimetypes.guess_type(str(target))[0] or "application/octet-stream")

    # -- switching it on ---------------------------------------------------
    def serve(self, port: int | None = None, host: str = "127.0.0.1", open_browser: bool = True) -> str:
        # No port asked for: use this app's usual one. A port of 0 means "any
        # free port, you pick" - that is what nonoForge asks for, so two
        # projects on one machine never fight over a number.
        port = free_port(self.default_port if port is None else port, host)
        httpd = _Server((host, port), _Handler)
        httpd.app = self
        url = "http://%s:%d" % (host, port)

        print("")
        print("  " + "-" * 58)
        print("   %s is running" % self.name)
        print("   Open this in your browser:  %s" % url)
        print("   Keep this window open while you use it.")
        print("   Close this window when you are finished - that stops it.")
        print("  " + "-" * 58)
        print("")
        # nonoForge (and anything else that started this) watches for this line.
        print("nonoforge-ready: %s" % url, flush=True)

        if open_browser:
            threading.Thread(target=lambda: (time.sleep(0.4), _open(url)), daemon=True).start()
        try:
            httpd.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            print("\n  Stopped. See you next time.")
        finally:
            try:
                httpd.server_close()
            except Exception:
                pass
        return url


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nonoForge-project"

    def log_message(self, fmt, *args):
        pass  # quiet by default; there is a person watching this window

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app: App = self.server.app  # type: ignore[attr-defined]

        handler = None
        params = {}
        allowed = set()
        for route_method, pattern, candidate in app.routes:
            matched = _match(pattern, path)
            if matched is None:
                continue
            if route_method == method or (route_method == "GET" and method == "HEAD"):
                handler, params = candidate, matched
                break
            allowed.add(route_method)

        if handler is None:
            response = app.static(path, method) if not allowed else Bad("Not allowed here", 405)
        else:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            request = Request(method, path, parse_qs(parsed.query), body, params)
            try:
                response = _invoke(handler, request, params)
            except Exception as exc:  # a mistake must never leave a dead page
                import traceback

                traceback.print_exc()
                response = Bad("Something went wrong: %s" % exc, 500)

        self._send(response if response is not None else Json({"ok": True}), head_only=(method == "HEAD"))

    def _send(self, response, head_only: bool = False):
        if isinstance(response, Redirect):
            self.send_response(response.status)
            self.send_header("Location", response.where)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = getattr(response, "body", b"")
        self.send_response(response.status)
        self.send_header("Content-Type", response.type)
        for name, value in getattr(response, "headers", {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only and body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass


def _invoke(handler, request, params: dict):
    """Call a route handler, handing it any {placeholders} it asked for."""
    if not params:
        return handler(request)
    try:
        accepted = set(inspect.signature(handler).parameters)
    except (TypeError, ValueError):
        return handler(request)
    return handler(request, **params) if accepted.issuperset(params) else handler(request)


def _match(pattern: str, path: str):
    """Match "/photo/{name}" against "/photo/dog.jpg" and return {"name": "dog.jpg"}."""
    pattern_parts = [part for part in pattern.split("/") if part]
    path_parts = [part for part in path.split("/") if part]
    if len(pattern_parts) != len(path_parts):
        return None
    params = {}
    for expected, actual in zip(pattern_parts, path_parts):
        if expected.startswith("{") and expected.endswith("}"):
            params[expected[1:-1]] = actual
        elif expected != actual:
            return None
    return params


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    app = None


def free_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Use the preferred door number if it is free, otherwise the next free one.

    A preferred value of 0 means "any free port, pick one for me" — which
    nonoForge uses when it starts a project, so two projects never fight.
    """
    if preferred and preferred > 0:
        for candidate in range(preferred, preferred + 30):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind((host, candidate))
                    return candidate
                except OSError:
                    continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def _open(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run(app: App, description: str = "") -> None:
    """The last four lines of every start.py in every project made by nonoForge."""
    # Somebody may well name their project with an emoji in it; a Windows
    # console on a legacy code page must not crash over that.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=description or app.name)
    parser.add_argument("--port", type=int, default=app.default_port, help="which door number to use")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.add_argument("--host", default="127.0.0.1", help="who may connect (default: this computer only)")
    args = parser.parse_args()
    app.serve(port=args.port, host=args.host, open_browser=not args.no_browser)


if __name__ == "__main__":
    print("This file is the engine for an app; run start.py instead.")
    sys.exit(1)
