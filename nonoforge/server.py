"""The nonoForge page and the addresses behind it.

Everything the browser can ask for is listed here, and each one says what it is
for in one line. Two details worth knowing if you are reading this to change it:

* ``/api/create`` answers as a **stream**. Each step of the build is sent the
  moment it happens, so the page can narrate "making the folder… writing the
  files… putting your photos in place" instead of showing a spinner and hoping.
* ``/api/start`` runs a project you already made and waits for it to say it is
  ready, so the button can open the right page at the right moment.
"""

from __future__ import annotations

import atexit
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__, forge, recipes, store
from .httpbase import App, Error, Json, Stream, free_port

WEB_DIR = Path(__file__).resolve().parent / "web"
READY_PREFIX = "nonoforge-ready: "
# Where a started project listens, if it cannot use this one it takes the next.
FIRST_PORT = 8770


# --------------------------------------------------------------------------
# Projects that are currently running
# --------------------------------------------------------------------------
class Running:
    """A project this app started, and the page it is listening on."""

    def __init__(self, process: subprocess.Popen, folder: str):
        self.process = process
        self.folder = folder
        self.url = ""
        self.log: list = []

    def alive(self) -> bool:
        return self.process.poll() is None

    def tail(self, lines: int = 3) -> str:
        """The last few things it said, for when something went wrong."""
        return " / ".join(self.log[-lines:]) or "it stopped straight away"


_RUNNING: dict = {}
_LOCK = threading.Lock()


def _watch(project: Running) -> None:
    """Read the child's output so it never blocks on a full pipe."""
    try:
        for line in project.process.stdout:  # type: ignore[union-attr]
            text = line.rstrip()
            if text.startswith(READY_PREFIX):
                project.url = text[len(READY_PREFIX):].strip()
            else:
                project.log.append(text)
                del project.log[:-60]  # keep the last few lines, for error messages
    except Exception:
        pass


def _wait_until_answering(url: str, project: Running, timeout: float = 25.0) -> bool:
    """Knock on the door until somebody answers.

    Waiting for a line of output works on most systems but not all of them, and
    a line on a pipe is a weaker promise than a page that actually loads. So the
    port is chosen by us and then the address is polled until it answers.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if project.process.poll() is not None:
            return False  # it gave up before it was ready
        try:
            with urllib.request.urlopen(url + "/", timeout=2) as response:
                response.read(1)
                return True
        except urllib.error.HTTPError:
            return True  # it answered, even if it did not like being asked
        except Exception:
            time.sleep(0.25)
    return False


def start_project(folder: str, open_page: bool = True) -> dict:
    """Start a project made by nonoForge and wait until it is answering."""
    folder_path = Path(folder).expanduser()
    if not folder_path.is_dir():
        return {"error": "That project folder is not there any more."}
    if not (folder_path / "project.json").is_file():
        # Only folders this app made can be started this way.
        return {"error": "That folder was not made by %s, so I will not start it." % APP_NAME}
    entry = folder_path / "start.py"
    if not entry.is_file():
        return {"error": "This project has no start.py in it, so there is nothing to start."}

    with _LOCK:
        existing = _RUNNING.get(str(folder_path))
        if existing and existing.alive():
            if open_page and existing.url:
                _open_url(existing.url)
            return {"ok": True, "url": existing.url, "already_running": True}

        # Choose the door number here rather than leaving it to the child, so
        # there is never a disagreement about which address to open.
        port = free_port(FIRST_PORT)
        flags = 0
        if os.name == "nt":
            # No extra black window: it is stopped from this page instead.
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                [sys.executable, str(entry), "--no-browser", "--port", str(port)],
                cwd=str(folder_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            return {"error": "I could not start it: %s" % exc}

        project = Running(process, str(folder_path))
        _RUNNING[str(folder_path)] = project
        threading.Thread(target=_watch, args=(project,), daemon=True).start()

    url = "http://127.0.0.1:%d" % port
    if not _wait_until_answering(url, project):
        tail = project.tail()
        stop_project(str(folder_path))
        return {"error": "It was made, but it did not manage to start. (%s)" % tail}

    project.url = url
    store.note_started(str(folder_path))
    if open_page:
        _open_url(url)
    return {"ok": True, "url": url, "already_running": False}


def stop_project(folder: str) -> dict:
    with _LOCK:
        project = _RUNNING.pop(str(Path(folder).expanduser()), None)
    if not project:
        return {"stopped": False}
    try:
        project.process.terminate()
        try:
            project.process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            project.process.kill()
    except Exception:
        pass
    finally:
        # Let go of the output pipe, or the handle stays open for as long as
        # this app runs.
        if project.process.stdout:
            try:
                project.process.stdout.close()
            except Exception:
                pass
    return {"stopped": True}


def _stop_everything() -> None:
    for folder in list(_RUNNING):
        stop_project(folder)


atexit.register(_stop_everything)


def _open_url(url: str) -> None:
    def later():
        time.sleep(0.3)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=later, daemon=True).start()


def _open_folder(path: str) -> dict:
    folder = Path(path).expanduser()
    if not folder.is_dir():
        return {"error": "That folder is not there any more."}
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as exc:
        return {"error": "I could not open the folder (%s). It is at %s" % (exc, folder)}
    return {"ok": True, "path": str(folder)}


# --------------------------------------------------------------------------
# Uploads: files dropped onto the page
# --------------------------------------------------------------------------
def _upload_target(upload_id: str) -> Path:
    safe = "".join(ch for ch in upload_id if ch.isalnum() or ch in "-_")
    return store.uploads_dir() / (safe or "upload")


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------
def recipe_public(recipe: dict) -> dict:
    """The parts of a recipe the page is allowed to see."""
    files = recipes.files_for(recipe)
    return {
        "id": recipe["id"],
        "emoji": recipe["emoji"],
        "title": recipe["title"],
        "blurb": recipe["blurb"],
        "best_for": recipe["best_for"],
        "asks": [
            {
                "key": ask["key"],
                "type": ask["type"],
                "label": ask["label"],
                "help": ask["help"],
                "placeholder": ask["placeholder"],
                "default": ask["default"],
                "required": ask["required"],
                "folder": ask["folder"],
                "accept": ask["accept"],
                "options": ask.get("options", []),
            }
            for ask in recipe["asks"]
        ],
        "runs": recipe["runs"],
        "file_count": len(files),
        "files": files,
        "what_you_get": files[:8],
    }


def _from_local_page(request, require_json: bool = False) -> bool:
    """A cheap guard against another website poking this app in your browser.

    Two things are checked. Anyone can make a browser send a request to
    localhost, so:

    * if an ``Origin`` is present it must be this machine, and
    * for the addresses that take JSON, the body must actually be JSON —
      which forces a browser to ask permission first (a preflight), and that
      permission is never granted because this app sends no CORS headers.

    Requests with no Origin at all are allowed through: that is the page's own
    ``fetch``, curl, or the test suite.
    """
    origin = request.header("Origin") or ""
    if origin:
        host = origin.split("//")[-1].split("/")[0].split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return False
    if require_json:
        kind = (request.header("Content-Type") or "").split(";")[0].strip().lower()
        if kind and kind != "application/json":
            return False
    return True


def create_app() -> App:
    app = App(APP_NAME, WEB_DIR, version=__version__)

    # -- what this is ------------------------------------------------------
    @app.get("/api/health")
    def health(_request):
        return Json({"ok": True, "app": APP_NAME, "version": __version__, "recipes": len(recipes.load_all())})

    @app.get("/api/recipes")
    def all_recipes(_request):
        return Json({"recipes": [recipe_public(item) for item in recipes.load_all()]})

    @app.get("/api/recipes/{recipe_id}")
    def one_recipe(_request, recipe_id):
        recipe = recipes.get(recipe_id)
        if not recipe:
            return Error("There is no recipe called “%s”." % recipe_id, 404)
        return Json({"recipe": recipe_public(recipe)})

    @app.post("/api/pick")
    def pick_recipe(request):
        """"I want a page for my bakery" → the recipe that fits, and why."""
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        text = str(request.json().get("text") or "").strip()
        if not text:
            return Error("Tell me what you would like to make, in your own words.")
        choice = recipes.pick(text)
        chosen = recipes.get(choice["recipe"]) if choice["recipe"] else None
        runners = [recipes.get(item) for item in choice["runners_up"]]
        return Json(
            {
                "text": text,
                "recipe": recipe_public(chosen) if chosen else None,
                "why": choice["why"],
                "confident": choice["confident"],
                "runners_up": [recipe_public(item) for item in runners if item],
            }
        )

    @app.get("/api/where")
    def where(_request):
        parent = store.default_parent()
        return Json({"parent": str(parent), "is_default": not store.load_settings().get("parent")})

    @app.get("/api/settings")
    def get_settings(_request):
        return Json({"settings": store.load_settings(), "parent": str(store.default_parent())})

    @app.post("/api/settings")
    def put_settings(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        saved = store.save_settings(request.json() or {})
        return Json({"settings": saved, "parent": str(store.default_parent())})

    # -- agreeing the plan before anything is made -------------------------
    @app.post("/api/plan")
    def make_plan(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        payload = request.json()
        recipe = recipes.get(str(payload.get("recipe") or ""))
        if not recipe:
            return Error("Pick one of the cards first, then I will show you what you get.")
        shown = forge.plan(recipe, payload.get("answers") or {}, payload.get("parent") or None)
        shown["what_you_get"] = shown.pop("files")
        return Json(shown)

    # -- making it --------------------------------------------------------
    @app.post("/api/create")
    def create(request):
        """Build the project, narrating every step as it happens."""
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        payload = request.json()
        recipe = recipes.get(str(payload.get("recipe") or ""))
        if not recipe:
            return Error("I need to know which card you picked before I can make anything.")
        answers = payload.get("answers") or {}
        parent = payload.get("parent") or None
        attachments = payload.get("attachments") or []
        want_git = bool(payload.get("git"))
        start_after = bool(payload.get("start", True))
        open_folder_after = bool(payload.get("open_folder", False))

        def events():
            steps: "queue.Queue" = queue.Queue()
            box: dict = {}

            def work():
                try:
                    box["manifest"] = forge.build(
                        recipe,
                        answers,
                        parent,
                        attachments,
                        progress=lambda message: steps.put({"type": "step", "text": message}),
                        git=want_git,
                    )
                except Exception as exc:  # shown in the page, not in a traceback nobody reads
                    box["error"] = str(exc)
                finally:
                    steps.put(None)

            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            yield {"type": "step", "text": "Starting on “%s”." % recipe["title"]}
            while True:
                item = steps.get()
                if item is None:
                    break
                yield item

            if box.get("error"):
                yield {"type": "error", "message": box["error"]}
                return

            manifest = box["manifest"]
            yield {
                "type": "made",
                "project": manifest["project"],
                "folder": manifest["folder"],
                "files": manifest["files"],
                "dropped_in": manifest["dropped_in"],
                "bytes": manifest["bytes"],
                "git": manifest["git"],
                "renamed": manifest["renamed"],
                "runs": manifest["runs"],
            }

            if open_folder_after:
                _open_folder(manifest["folder"])

            if start_after and manifest["runs"]:
                yield {"type": "step", "text": "Starting it so you can see it…"}
                started = start_project(manifest["folder"], open_page=True)
                if started.get("url"):
                    yield {"type": "running", "url": started["url"], "path": manifest["folder"]}
                else:
                    yield {"type": "note", "text": started.get("error", "I could not start it automatically."),
                           "path": manifest["folder"]}
            yield {"type": "done"}

        return Stream.sse(events())

    # -- uploaded files ----------------------------------------------------
    @app.post("/api/upload/start")
    def upload_start(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        name = store.safe_folder_name(str(request.json().get("name") or "file"), fallback="file")
        original_suffix = Path(str(request.json().get("name") or "")).suffix
        if original_suffix and not name.lower().endswith(original_suffix.lower()):
            name += original_suffix
        upload_id = "u%d" % int(time.time() * 1000)
        target = _upload_target(upload_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / ".name").write_text(name, encoding="utf-8")
        return Json({"id": upload_id, "name": name})

    @app.post("/api/upload/chunk")
    def upload_chunk(request):
        """Raw bytes, written where they land, so a 200 MB photo does not hurt.

        The body here is a file, not JSON, so only the origin is checked.
        """
        if not _from_local_page(request):
            return Error("That request did not come from this app.", 403)
        upload_id = request.q("id", "")
        offset = request.q_int("offset", 0)
        target = _upload_target(upload_id)
        name_path = target / ".name"
        if not upload_id or not name_path.is_file():
            return Error("That upload is not one I started.")
        name = name_path.read_text(encoding="utf-8")
        destination = target / name
        mode = "r+b" if destination.exists() else "wb"
        with destination.open(mode) as handle:
            handle.seek(offset)
            handle.write(request.body)
        return Json({"received": offset + len(request.body)})

    @app.post("/api/upload/finish")
    def upload_finish(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        payload = request.json()
        target = _upload_target(str(payload.get("id") or ""))
        name_path = target / ".name"
        if not name_path.is_file():
            return Error("That upload is not one I started.")
        name = name_path.read_text(encoding="utf-8")
        path = target / name
        if not path.is_file():
            return Error("Nothing arrived for “%s”." % name)
        size = path.stat().st_size
        return Json({"name": name, "path": str(path), "bytes": size,
                     "key": str(payload.get("key") or "")})

    # -- the projects you have made ---------------------------------------
    @app.get("/api/projects")
    def list_projects(_request):
        running = {folder for folder, item in _RUNNING.items() if item.alive() and item.url}
        return Json({
            "projects": store.projects(),
            "running": [{"path": folder, "url": _RUNNING[folder].url} for folder in running],
            "parent": str(store.default_parent()),
        })

    @app.post("/api/start")
    def start_again(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        payload = request.json()
        result = start_project(str(payload.get("path") or ""), open_page=bool(payload.get("open", True)))
        return Json(result, status=200 if result.get("ok") else 400)

    @app.post("/api/stop")
    def stop_again(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        return Json(stop_project(str(request.json().get("path") or "")))

    @app.post("/api/open")
    def open_again(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        return Json(_open_folder(str(request.json().get("path") or "")))

    @app.post("/api/forget")
    def forget(request):
        if not _from_local_page(request, require_json=True):
            return Error("That request did not come from this app.", 403)
        return Json({"projects": store.forget_project(str(request.json().get("path") or ""))})

    # -- what this computer has -------------------------------------------
    @app.get("/api/doctor")
    def doctor(_request):
        return Json({
            "app": APP_NAME,
            "version": __version__,
            "python": sys.version.split()[0],
            "system": sys.platform,
            "projects_folder": str(store.default_parent()),
            "recipes": len(recipes.load_all()),
            "recipe_folder": str(recipes.recipes_dir()),
            "settings_folder": str(store.home()),
            "git": bool(shutil.which("git")),
            "running": [folder for folder, item in _RUNNING.items() if item.alive()],
        })

    return app


def doctor_text() -> str:
    """The same information, for the terminal, for when something is not working."""
    app_info = {
        "app": APP_NAME,
        "version": __version__,
        "python": sys.version.split()[0],
    }
    lines = [
        "",
        "  %s %s — what this computer has" % (APP_NAME, __version__),
        "  " + "-" * 56,
        "  Python %s on %s" % (app_info["python"], sys.platform),
        "  New projects go in:   %s" % store.default_parent(),
        "  Recipes available:    %d  (from %s)" % (len(recipes.load_all()), recipes.recipes_dir()),
        "  Settings and list:    %s" % store.home(),
        "  git found:            %s" % ("yes" if shutil.which("git") else "no"),
        "",
        "  The cards you can pick from:",
    ]
    for recipe in recipes.load_all():
        # Pad the title, not the emoji: an emoji is one character but two
        # columns wide, so padding it makes a ragged list.
        lines.append("    %s  %s" % (recipe["emoji"], "%-30s %s" % (recipe["title"], recipe["blurb"][:58])))
    lines.append("")
    made = store.projects()
    lines.append("  Projects you have made: %d" % len(made))
    for entry in made[:8]:
        lines.append("    %s  %s" % (entry.get("name", "?"), entry.get("path", "")))
    lines.append("")
    return "\n".join(lines)
