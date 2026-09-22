"""Turning a recipe plus a few answers into a real project on disk.

The rules this file lives by:

* **Nothing is ever overwritten.** A name clash quietly becomes "My site 2".
* **Nothing lands outside the project folder**, whatever arrives in a file name.
* **Every step says what it is doing in plain words**, because a progress bar
  that explains itself is the difference between "it worked" and "is it stuck?".
* **A finished project explains itself.** START-HERE.txt is written last, so a
  newcomer who comes back in a month knows what they are looking at.

Answers are dropped into the template files by replacing ``{{PLACEHOLDER}}``
with what the person typed. Everything else is a straight copy.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import APP_NAME, __version__, store

PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

# Which files get their text rewritten, and how values must be escaped for them.
_HTML_SUFFIXES = {".html", ".htm", ".svg", ".xml", ".css"}
_JSON_SUFFIXES = {".js", ".json", ".webmanifest"}
_SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


# --------------------------------------------------------------------------
# Answers → placeholder values
# --------------------------------------------------------------------------
def clean_answers(recipe: dict, answers: dict) -> dict:
    """Tidy what somebody typed into the shapes the templates expect."""
    answers = answers if isinstance(answers, dict) else {}
    values = {}
    for ask in recipe["asks"]:
        raw = answers.get(ask["key"], ask["default"])
        kind = ask["type"]
        if kind == "files":
            continue  # attachments are copied, not typed into a file
        if kind == "lines":
            items = raw if isinstance(raw, list) else str(raw or "").splitlines()
            values[ask["key"]] = [str(item).strip() for item in items if str(item).strip()]
        elif kind == "number":
            try:
                values[ask["key"]] = int(float(str(raw).strip() or 0))
            except (TypeError, ValueError):
                values[ask["key"]] = 0
        else:
            text = str(raw if raw is not None else "").strip()
            values[ask["key"]] = text[:4000]
    return values


def _escape(value, suffix: str) -> str:
    """Make a value safe to drop into this kind of file."""
    text = "" if value is None else str(value)
    if suffix in _HTML_SUFFIXES:
        return html.escape(text, quote=True)
    if suffix in _JSON_SUFFIXES:
        # json.dumps gives a correctly quoted body; "<" is escaped so that a
        # stray "</script>" in someone's text cannot break the page it lands in.
        body = json.dumps(text)[1:-1]
        return body.replace("<", "\\u003c")
    return text


def placeholder_values(recipe: dict, values: dict, folder_name: str) -> dict:
    today = time.localtime()
    built = {
        "PROJECT": folder_name,
        "RECIPE": recipe["title"],
        "DATE": "%d %s %d" % (today.tm_mday, MONTHS[today.tm_mon - 1], today.tm_year),
        "TODAY": time.strftime("%Y-%m-%d", today),
        "YEAR": str(today.tm_year),
        "MADE_BY": APP_NAME,
    }
    for key, value in values.items():
        if isinstance(value, list):
            continue  # a list has no sensible single-line form; see data_files
        built[key.upper()] = value
    return built


def _fill(text: str, values: dict, suffix: str) -> str:
    def replace(match):
        key = match.group(1)
        if key in values:
            return _escape(values[key], suffix)
        if key.upper() in values:
            return _escape(values[key.upper()], suffix)
        return ""  # an unknown placeholder becomes nothing, never "{...}"

    return PLACEHOLDER.sub(replace, text)


# --------------------------------------------------------------------------
# Planning: what would happen if you pressed the button
# --------------------------------------------------------------------------
def plan(recipe: dict, answers: dict, parent: Path | str | None = None) -> dict:
    """Describe the project that would be made, without making it."""
    from . import recipes as recipe_book  # local import: avoids a cycle

    values = clean_answers(recipe, answers)
    parent_path = Path(parent).expanduser() if parent else store.default_parent()
    wanted = str(values.get("name") or answers.get("name") or "").strip()
    folder_name = store.safe_folder_name(wanted or recipe["title"], fallback=recipe["title"])
    folder = store.unique_dir(parent_path, folder_name)

    files = recipe_book.files_for(recipe)
    return {
        "folder": str(folder),
        "folder_name": folder.name,
        "parent": str(parent_path),
        "recipe": recipe["id"],
        "recipe_title": recipe["title"],
        "files": files,
        "file_count": len(files),
        "made_a_second_copy": folder.name != folder_name,
        "runs": recipe["runs"],
    }


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def _copy_template(recipe: dict, folder: Path, values: dict, progress) -> list:
    """Copy the recipe's files in, filling in the placeholders as we go."""
    root = Path(recipe["files_dir"])
    written = []
    if not root.is_dir():
        return written

    for source in sorted(root.rglob("*")):
        relative = source.relative_to(root)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in relative.parts):
            continue
        target = (folder / relative).resolve()
        try:
            # Belt and braces: a template can never write outside the project.
            target.relative_to(folder.resolve())
        except ValueError:
            continue
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        if suffix in _HTML_SUFFIXES or suffix in _JSON_SUFFIXES or suffix in {".md", ".txt", ".py", ".sh", ".bat", ".csv"}:
            try:
                text = source.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                shutil.copy2(source, target)  # not text after all; copy as-is
            else:
                target.write_text(_fill(text, values, suffix), encoding="utf-8")
        else:
            shutil.copy2(source, target)
        written.append(relative.as_posix())
        if len(written) % 5 == 0:
            progress("Writing files… (%d so far)" % len(written))
    return written


def _copy_attachments(recipe: dict, folder: Path, attachments: list, progress) -> list:
    """Put the files somebody dropped in where the recipe expects them."""
    if not attachments:
        return []
    # Which folder does each dropped file belong in? The recipe decides.
    wanted_folder = {}
    for ask in recipe["asks"]:
        if ask["type"] == "files":
            wanted_folder[ask["key"]] = ask["folder"] or "files"

    placed = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        source = Path(str(item.get("path") or ""))
        if not source.is_file():
            continue
        sub = wanted_folder.get(str(item.get("key") or ""), "files")
        destination_dir = folder / store.safe_folder_name(sub, fallback="files")
        destination_dir.mkdir(parents=True, exist_ok=True)
        name = store.safe_folder_name(item.get("name") or source.name, fallback="file")
        # Keep the extension that safe_folder_name may have trimmed away.
        original_suffix = Path(str(item.get("name") or source.name)).suffix
        if original_suffix and not name.lower().endswith(original_suffix.lower()):
            name += original_suffix
        destination = store.unique_dir(destination_dir, name) if destination_dir.joinpath(name).exists() \
            else destination_dir / name
        shutil.copy2(source, destination)
        placed.append({"name": destination.name, "folder": destination_dir.name,
                       "bytes": destination.stat().st_size})
        progress("Putting your file “%s” in place." % destination.name)
    return placed


def _write_data_files(recipe: dict, folder: Path, values: dict) -> None:
    """Some answers are lists — questions for a form, for example. Write them as data."""
    for item in recipe["data_files"]:
        key = str(item.get("key") or "")
        filename = store.safe_folder_name(str(item.get("file") or ""), fallback="data.json")
        if not filename.lower().endswith(".json"):
            filename += ".json"
        payload = values.get(key, [])
        (folder / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text_files(recipe: dict, folder: Path, values: dict) -> None:
    """Lists a person might want to edit later become ordinary text files.

    A list of questions is the reason this exists: it is much kinder to open
    ``questions.txt`` in Notepad than to edit JSON.
    """
    for item in recipe.get("text_files", []):
        key = str(item.get("key") or "")
        filename = store.safe_folder_name(str(item.get("file") or ""), fallback="list")
        if "." not in filename:
            filename += ".txt"
        value = values.get(key, "")
        body = "\n".join(value) if isinstance(value, list) else str(value)
        (folder / filename).write_text(body.rstrip() + "\n", encoding="utf-8")


def _inject_runtime(recipe: dict, folder: Path, values: dict, progress) -> list:
    """Give every project that runs the same three files: an engine and two launchers.

    They live in the package once instead of in every recipe, so there is one
    place to fix a bug rather than six.
    """
    if not recipe["runs"]:
        return []
    runtime = Path(__file__).resolve().parent / "runtime"
    written = []
    for name in ("serve.py", "run.bat", "run.sh"):
        source = runtime / name
        if not source.is_file():
            continue
        target = folder / name
        if target.exists():
            continue  # a recipe is allowed to bring its own version
        target.write_text(
            _fill(source.read_text(encoding="utf-8"), values, source.suffix.lower()), encoding="utf-8"
        )
        if name.endswith(".sh"):
            try:
                os.chmod(target, 0o755)
            except OSError:
                pass  # Windows has no such thing, and does not need it
        written.append(name)
    progress("Adding the start button (run.bat and run.sh).")
    return written


def _start_here(recipe: dict, folder: Path, values: dict, placed: list) -> str:
    """The note that means nobody ever opens a folder and thinks "now what?"."""
    lines = []
    add = lines.append

    add("WHAT THIS IS")
    add("")
    add("  %s — %s" % (values.get("NAME") or values.get("PROJECT", "Your project"), recipe["title"]))
    for chunk in _wrap(recipe["blurb"], 72):
        add("  " + chunk)
    if recipe["best_for"]:
        add("")
        add("  Made for: %s" % recipe["best_for"])

    if recipe["runs"]:
        add("")
        add("-" * 74)
        add("HOW TO START IT")
        add("")
        add("  Windows:        double-click  run.bat")
        add("  macOS / Linux:  double-click  run.sh   (or type ./run.sh)")
        add("")
        add("  A page opens in your browser. That page IS the app.")
        add("  Keep the little text window open while you use it - closing it stops the app.")
    else:
        add("")
        add("-" * 74)
        add("HOW TO OPEN IT")
        add("")
        add("  Double-click  index.html  - it opens in your browser. Nothing to install.")

    if recipe["changing"]:
        add("")
        add("-" * 74)
        add("HOW TO CHANGE HOW IT LOOKS AND WHAT IT SAYS")
        add("")
        for item in recipe["changing"]:
            for index, chunk in enumerate(_wrap(item, 70)):
                add(("  - " if index == 0 else "    ") + chunk)

    if recipe["map"]:
        add("")
        add("-" * 74)
        add("WHAT THE FILES ARE")
        add("")
        for name, description in recipe["map"].items():
            add("  %-22s %s" % (name, description))

    if placed:
        add("")
        add("  Your dropped-in files are saved inside this folder — see the folders above.")
        for item in placed:
            add("    - %s/%s" % (item["folder"], item["name"]))

    add("")
    add("-" * 74)
    add("HOW THIS WAS MADE")
    add("")
    add("  Recipe:   %s" % recipe["title"])
    add("  Made by:  %s %s on %s" % (APP_NAME, __version__, values.get("DATE", "")))
    add("  Your answers are remembered in project.json, so you can look at what you chose.")
    add("")
    add("  To make another one: start nonoForge again and pick a card.")
    add("")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list:
    """A tiny word-wrapper, so START-HERE.txt reads well in Notepad."""
    words = str(text or "").split()
    lines, current = [], ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _git_setup(folder: Path, name: str) -> bool:
    """Best-effort: never let version control break somebody's project."""
    if not shutil.which("git"):
        return False
    commands = [
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=" + APP_NAME, "-c", "user.email=nonoForge@localhost",
         "commit", "-qm", "Made with %s" % APP_NAME],
    ]
    try:
        for command in commands:
            result = subprocess.run(command, cwd=str(folder), capture_output=True, timeout=30)
            if result.returncode not in (0, 1):
                return False
    except (OSError, subprocess.SubprocessError):
        return False
    return (folder / ".git").is_dir()


def build(recipe: dict, answers: dict, parent=None, attachments=None, progress=None, git: bool = False) -> dict:
    """Make the project. Returns a manifest describing what now exists."""
    progress = progress or (lambda message: None)

    values = clean_answers(recipe, answers)
    parent_path = Path(parent).expanduser() if parent else store.default_parent()
    try:
        parent_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError("I could not use that folder (%s). Try another one." % exc) from exc
    if not parent_path.is_dir():
        raise RuntimeError("That is not a folder I can put things in: %s" % parent_path)

    wanted = str(values.get("name") or "").strip()
    folder_name = store.safe_folder_name(wanted or recipe["title"], fallback=recipe["title"])

    progress("Looking for a free name in %s" % parent_path)
    folder = store.unique_dir(parent_path, folder_name)
    renamed = folder.name != folder_name
    if renamed:
        progress("“%s” was already there, so this one is called “%s”." % (folder_name, folder.name))

    folder.mkdir(parents=True, exist_ok=False)
    progress("Made the folder “%s”." % folder.name)

    display_name = folder.name
    values = dict(values)
    values["name"] = display_name
    placeholders = placeholder_values(recipe, values, display_name)

    progress("Writing the files this recipe makes.")
    written = _copy_template(recipe, folder, placeholders, progress)
    written += _inject_runtime(recipe, folder, placeholders, progress)
    progress("Wrote %d files." % len(written))

    placed = _copy_attachments(recipe, folder, attachments or [], progress)
    _write_data_files(recipe, folder, values)
    _write_text_files(recipe, folder, values)

    if git:
        progress("Setting it up as a git repository (optional extra).")
        _git_setup(folder, display_name)

    (folder / "project.json").write_text(
        json.dumps(
            {
                "recipe": recipe["id"],
                "recipe_title": recipe["title"],
                "name": display_name,
                "made": time.strftime("%Y-%m-%d %H:%M"),
                "answers": {key: value for key, value in values.items()},
                "filenames": written,
                "dropped_in": placed,
                "made_with": "%s %s" % (APP_NAME, __version__),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    progress("Writing START-HERE.txt — the note that explains everything.")
    (folder / "START-HERE.txt").write_text(_start_here(recipe, folder, placeholders, placed), encoding="utf-8")

    total = 0
    for path in folder.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass

    project = {
        "name": display_name,
        "path": str(folder),
        "recipe": recipe["id"],
        "recipe_title": recipe["title"],
        "emoji": recipe["emoji"],
        "created": time.time(),
        "made": time.strftime("%Y-%m-%d %H:%M"),
        "runs": recipe["runs"],
        "port": recipe["port"],
        "renamed_from": folder_name if renamed else "",
    }
    store.remember_project(project)
    progress("Done. “%s” is ready." % display_name)

    return {
        "ok": True,
        "project": project,
        "folder": str(folder),
        "files": written + ["START-HERE.txt", "project.json"],
        "dropped_in": placed,
        "bytes": total,
        "git": bool(git and (folder / ".git").is_dir()),
        "renamed": renamed,
        "runs": recipe["runs"],
    }
