"""Teach it your writing, then watch it write in your style.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

WHAT THIS ACTUALLY IS
=====================
A real, trained model — just a very small one. It counts which letters tend to
follow which other letters in your text, and then writes new text by following
those counts. Train it, and the numbers change. That is training. No internet,
no GPU, no libraries: a dictionary of counts and a random number generator.

At ORDER = 3 it looks at the last three characters to guess the next one. With a
few thousand words of your writing it will produce something that sounds like a
slightly drunk version of you. Big language models do the same thing with more
context, more layers and a lot more arithmetic — this is the same idea with the
smallest possible budget, and you can read every line of it.
"""

import os
import random
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Json, run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
PASTED = os.path.join(SAMPLES, "pasted-writing.txt")
READABLE = (".txt", ".md", ".markdown", ".text")

ORDER = 3              # how many characters of context it learns from
MAX_CORPUS = 1_500_000  # keep the whole thing quick on a laptop
LENGTHS = {"a sentence": 140, "a paragraph": 520, "a page": 1400}

app = App("{{PROJECT}}", default_port=8766)
_cache = {"signature": None, "model": None, "stats": None, "text": ""}


# --------------------------------------------------------------------------
# Reading what you wrote
# --------------------------------------------------------------------------
def _files():
    """Every readable file in the samples folder.

    Names starting with a dot or an underscore are ignored, so the "put your
    writing here" note never ends up in the training text.
    """
    if not os.path.isdir(SAMPLES):
        return []
    found = []
    for name in sorted(os.listdir(SAMPLES)):
        if name.startswith((".", "_")):
            continue
        path = os.path.join(SAMPLES, name)
        if name.lower().endswith(READABLE) and os.path.isfile(path):
            found.append(path)
    return found


def _signature(paths):
    return tuple((os.path.basename(path), os.path.getsize(path), int(os.path.getmtime(path))) for path in paths)


def corpus():
    paths = _files()
    signature = _signature(paths)
    if signature == _cache["signature"] and _cache["model"] is not None:
        return _cache["text"]
    parts = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                parts.append(handle.read())
        except OSError:
            continue
    text = "\n\n".join(parts)
    if len(text) > MAX_CORPUS:
        text = text[:MAX_CORPUS]
    _cache["text"] = text
    _cache["signature"] = signature
    _cache["model"] = None  # force a retrain for the new text
    return text


# --------------------------------------------------------------------------
# Training: count what follows what
# --------------------------------------------------------------------------
def train(text: str) -> dict:
    """One pass over your text, building tables of "what comes next"."""
    tables = {size: defaultdict(Counter) for size in range(1, ORDER + 1)}
    for index in range(1, len(text)):
        for size in range(1, ORDER + 1):
            if index - size < 0:
                continue
            context = text[index - size:index]
            tables[size][context][text[index]] += 1
    return tables


def model():
    text = corpus()
    if _cache["model"] is None:
        _cache["model"] = train(text) if text else {size: {} for size in range(1, ORDER + 1)}
    return _cache["model"]


# --------------------------------------------------------------------------
# Writing: follow the counts, with a dial for how adventurous to be
# --------------------------------------------------------------------------
def _pick(options: list, temperature: float):
    """Choose the next character. Low temperature = safest choice."""
    letters = [item[0] for item in options]
    counts = [item[1] for item in options]
    if temperature <= 0.05:
        return letters[0]
    weights = [count ** (1.0 / temperature) for count in counts]
    return random.choices(letters, weights=weights, k=1)[0]


def write(prompt: str, length: int, temperature: float) -> str:
    tables = model()
    text = corpus()
    if not text:
        return ""

    # Start from what the person typed when it exists in their own writing, so
    # the model is continuing real text rather than guessing from a cold start.
    if prompt:
        where = text.lower().find(prompt.lower()[:40])
        produced = text[where:where + len(prompt)] if where >= 0 else prompt
    else:
        start = max(0, len(text) // 3)
        produced = text[start:start + 1]

    for _ in range(length):
        for size in range(min(ORDER, len(produced)), 0, -1):
            options = (tables.get(size) or {}).get(produced[-size:])
            if options:
                produced += _pick(options.most_common(12), temperature)
                break
        else:
            produced += " "  # nothing at all known here: start a fresh word
    return produced


def stats() -> dict:
    text = corpus()
    tables = model()
    pairs = []
    if text:
        table = tables.get(ORDER) or tables.get(ORDER - 1) or {}
        everything = Counter()
        for context, options in table.items():
            for letter, count in options.items():
                everything[(context, letter)] = count
        for (context, letter), count in everything.most_common(10):
            pairs.append({"after": context, "comes": letter, "times": count})
    return {
        "characters": len(text),
        "words": len(re.findall(r"\S+", text)),
        "files": [os.path.basename(path) for path in _files()],
        "order": ORDER,
        "patterns": len((tables.get(ORDER) or {})),
        "pairs": pairs,
        "trained": bool(text),
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/api/stats")
def api_stats(_request):
    return Json(stats())


@app.post("/api/learn")
def api_learn(request):
    """Take freshly pasted writing, save it, and learn from everything again."""
    text = str(request.json().get("text") or "")
    if len(text.strip()) < 40:
        return Json({"error": "Paste a bit more than that — a paragraph at least, so it has something to learn from."}, 400)
    os.makedirs(SAMPLES, exist_ok=True)
    with open(PASTED, "w", encoding="utf-8") as handle:
        handle.write(text.strip() + "\n")
    _cache["signature"] = None  # force a re-read and a retrain
    _cache["model"] = None
    started = time.time()
    fresh = stats()
    fresh["trained_ms"] = int((time.time() - started) * 1000)
    return Json(fresh)


@app.post("/api/write")
def api_write(request):
    payload = request.json()
    prompt = str(payload.get("prompt") or "")[:200]
    length = LENGTHS.get(str(payload.get("how_much") or ""), LENGTHS["a paragraph"])
    try:
        temperature = float(payload.get("creativity", 0.9))
    except (TypeError, ValueError):
        temperature = 0.9
    temperature = max(0.2, min(1.8, temperature))
    if not corpus():
        return Json({"error": "There is nothing to learn from yet. Paste some of your writing first."}, 400)
    started = time.time()
    text = write(prompt, length, temperature)
    return Json({"text": text, "took_ms": int((time.time() - started) * 1000),
                 "creativity": temperature, "how_much": payload.get("how_much") or "a paragraph"})


@app.post("/api/forget")
def api_forget(_request):
    """Throw away the pasted text (the files in samples/ are untouched)."""
    try:
        os.remove(PASTED)
    except OSError:
        pass
    _cache["signature"] = None
    _cache["model"] = None
    return Json(stats())


if __name__ == "__main__":
    run(app, "{{PROJECT}} — teach it your writing")
