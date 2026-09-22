"""Reading the recipe cards.

A "recipe" is a folder with a ``recipe.json`` in it and the files that recipe
makes. That is the whole plugin system: teaching nonoForge to build something
new means adding a folder under ``recipes/``, and nothing in this file changes.

Two jobs live here: describing recipes to the page, and guessing which recipe
somebody means when they type "a site for my bakery" instead of picking a card.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# The fields every recipe must have to be usable. A recipe missing one is
# skipped rather than half-working — someone's broken folder should never stop
# the app from starting.
REQUIRED = ("id", "emoji", "title", "blurb")

ASK_TYPES = {"text", "textarea", "color", "date", "time", "number", "choice", "files", "lines"}
MAX_ANSWER = 4000


def recipes_dir() -> Path:
    """Where the recipe folders live. Override with NONOFORGE_RECIPES."""
    override = os.environ.get("NONOFORGE_RECIPES")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent / "recipes"


def _clean_ask(raw: dict, index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "text").strip().lower()
    if kind not in ASK_TYPES:
        kind = "text"
    key = str(raw.get("key") or "").strip()
    if not key:
        return None
    ask = {
        "key": key,
        "type": kind,
        "label": str(raw.get("label") or key),
        "help": str(raw.get("help") or ""),
        "placeholder": str(raw.get("placeholder") or ""),
        "default": raw.get("default", "" if kind not in ("files", "lines") else ([] if kind == "files" else "")),
        "required": bool(raw.get("required")),
        "folder": str(raw.get("folder") or "").strip(),
        "accept": str(raw.get("accept") or ""),
        "order": index,
    }
    if kind == "choice":
        options = raw.get("options") or []
        ask["options"] = [str(item) for item in options if str(item).strip()]
        if not ask["options"]:
            ask["type"] = "text"
            ask.pop("options", None)
    return ask


def _load_one(folder: Path) -> dict | None:
    """Read one recipe folder. Returns None if it is not usable."""
    meta_path = folder / "recipe.json"
    if not meta_path.is_file():
        return None
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if any(not str(raw.get(field) or "").strip() for field in REQUIRED):
        return None

    # Files can sit in a subfolder (usually "files") or directly in the recipe.
    files_rel = str(raw.get("files") or "files").strip() or "files"
    files_dir = folder / files_rel
    if not files_dir.is_dir():
        files_dir = folder

    asks = [ask for ask in (_clean_ask(item, i) for i, item in enumerate(raw.get("asks") or [])) if ask]

    recipe = {
        "id": str(raw["id"]).strip(),
        "emoji": str(raw["emoji"]).strip(),
        "title": str(raw["title"]).strip(),
        "blurb": str(raw["blurb"]).strip(),
        "best_for": str(raw.get("best_for") or "").strip(),
        "keywords": [str(word).strip().lower() for word in (raw.get("keywords") or []) if str(word).strip()],
        "asks": asks,
        "runs": bool(raw.get("runs", True)),
        "port": int(raw.get("port") or 8763),
        "changing": [str(line) for line in (raw.get("changing") or [])],
        "map": {str(key): str(value) for key, value in (raw.get("map") or {}).items()},
        "data_files": [item for item in (raw.get("data_files") or []) if isinstance(item, dict) and item.get("file")],
        "text_files": [item for item in (raw.get("text_files") or []) if isinstance(item, dict) and item.get("file")],
        "folder": folder,
        "files_dir": files_dir,
    }
    return recipe


def load_all() -> list:
    """Every usable recipe, in a stable, friendly order."""
    root = recipes_dir()
    if not root.is_dir():
        return []
    found = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        recipe = _load_one(folder)
        if recipe:
            found.append(recipe)
    # The order someone sees first matters more for a newcomer than alphabet:
    # keep whatever order recipe.json declares in "order", then by title.
    for index, recipe in enumerate(found):
        recipe["_order"] = index
    return found


def get(recipe_id: str) -> dict | None:
    wanted = (recipe_id or "").strip().lower()
    for recipe in load_all():
        if recipe["id"].lower() == wanted:
            return recipe
    return None


def files_for(recipe: dict) -> list:
    """The list of files this recipe makes, as plain relative paths."""
    root = Path(recipe["files_dir"])
    if not root.is_dir():
        return []
    paths = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            paths.append(path.relative_to(root).as_posix())
    return paths


# --------------------------------------------------------------------------
# Guessing what somebody means
# --------------------------------------------------------------------------
def _words(text: str) -> list:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def pick(text: str, limit: int = 3) -> dict:
    """Guess the recipe behind a plain-English request.

    Deliberately simple: count the words someone used that each recipe lists as
    its own. No model, no internet, and always explainable — the page can say
    *why* it chose, and offer the runners-up when it guessed wrong.
    """
    wanted = _words(text)
    if not wanted:
        return {"recipe": None, "why": "", "runners_up": [], "confident": False}

    sentence = set(wanted)
    scored = []
    for recipe in load_all():
        score = 0
        hits = []
        for keyword in recipe["keywords"]:
            pieces = _words(keyword)
            if not pieces:
                continue
            if len(pieces) == 1:
                if pieces[0] in sentence:
                    # Longer words are stronger evidence than short ones.
                    score += 2 + min(len(pieces[0]), 10) / 10.0
                    hits.append(pieces[0])
            elif all(piece in sentence for piece in pieces):
                score += 3 + len(pieces) / 2.0
                hits.append(keyword)
        if score:
            scored.append((score, recipe, hits))

    if not scored:
        return {"recipe": None, "why": "", "runners_up": [], "confident": False}

    scored.sort(key=lambda item: (-item[0], item[1]["_order"]))
    best_score, best, best_hits = scored[0]
    why = "you mentioned “%s”" % best_hits[0]
    if len(best_hits) > 1:
        why = "you mentioned “%s” and “%s”" % (best_hits[0], best_hits[1])

    runners = [recipe["id"] for _score, recipe, _hits in scored[1:limit]]
    return {
        "recipe": best["id"],
        "why": why,
        "runners_up": runners,
        "confident": best_score >= 4,
    }
