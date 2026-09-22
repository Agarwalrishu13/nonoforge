"""Where nonoForge keeps its own small bits of state.

Nothing here is precious. A settings file, the list of projects you have made,
and a scratch folder for files that are part-way through being dropped in. All
of it lives in one folder (``~/.nonoforge`` by default) so it can be deleted in
one go without leaving anything behind anywhere else.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

# Characters no operating system wants in a folder name, plus control codes.
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Names Windows refuses to create, whatever the extension.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *("COM%d" % n for n in range(1, 10)),
    *("LPT%d" % n for n in range(1, 10)),
}

DEFAULTS = {
    # Where new projects are made. "" means "work it out" (see default_parent).
    "parent": "",
    # Also turn the finished project into a git repository. Off: this is a
    # tool for people who have never heard of git.
    "git": False,
    # What to do the moment a project is finished.
    "open_when_done": True,
    "start_when_done": True,
}


def home() -> Path:
    """The one folder nonoForge owns. Point it elsewhere with NONOFORGE_HOME."""
    root = Path(os.environ.get("NONOFORGE_HOME") or (Path.home() / ".nonoforge"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploads_dir() -> Path:
    """Scratch space for files being dropped in."""
    path = home() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def load_settings() -> dict:
    saved = _read_json(home() / "settings.json", {})
    settings = dict(DEFAULTS)
    if isinstance(saved, dict):
        settings.update({key: saved[key] for key in DEFAULTS if key in saved})
    return settings


def save_settings(patch: dict) -> dict:
    settings = load_settings()
    for key in DEFAULTS:
        if key in patch:
            settings[key] = patch[key]
    _write_json(home() / "settings.json", settings)
    return settings


# --------------------------------------------------------------------------
# The projects you have made
# --------------------------------------------------------------------------
def projects() -> list:
    """Most recent first. Only the ones still on disk are reported."""
    entries = _read_json(home() / "projects.json", [])
    if not isinstance(entries, list):
        return []
    alive = [entry for entry in entries if isinstance(entry, dict) and os.path.isdir(entry.get("path", ""))]
    return alive


def remember_project(entry: dict) -> list:
    """Add a project to the list, newest first, without duplicates."""
    entries = [item for item in projects() if item.get("path") != entry.get("path")]
    entry = dict(entry)
    entry.setdefault("created", time.time())
    entries.insert(0, entry)
    _write_json(home() / "projects.json", entries[:40])
    return entries[:40]


def forget_project(path: str) -> list:
    _write_json(home() / "projects.json", [item for item in projects() if item.get("path") != path])
    return projects()


def note_started(path: str) -> None:
    """Remember that a project was started, so the list can say so."""
    entries = projects()
    for entry in entries:
        if entry.get("path") == path:
            entry["started"] = time.time()
    _write_json(home() / "projects.json", entries)


# --------------------------------------------------------------------------
# Names and places
# --------------------------------------------------------------------------
def safe_folder_name(name: str, fallback: str = "My project") -> str:
    """Turn whatever someone typed into a folder name that is safe everywhere."""
    cleaned = _INVALID.sub("", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _RESERVED:
        cleaned += " project"
    # Long names annoy every file manager; 64 characters is plenty.
    return cleaned[:64].strip(" .") or fallback


def unique_dir(parent: Path, name: str) -> Path:
    """Never overwrite anyone's work: "My site" → "My site 2" → "My site 3"."""

    def taken(path: Path) -> bool:
        # A folder that exists but is empty is fair game.
        try:
            return any(path.iterdir()) if path.is_dir() else path.exists()
        except OSError:
            return True

    candidate = parent / name
    index = 2
    while taken(candidate):
        candidate = parent / ("%s %d" % (name, index))
        index += 1
    return candidate


def default_parent() -> Path:
    """Somewhere a person will actually find their new project later."""
    saved = str(load_settings().get("parent") or "").strip()
    if saved:
        wanted = Path(saved).expanduser()
        if wanted.is_dir():
            return wanted

    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    path = base / "nonoForge"
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = home() / "projects"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
