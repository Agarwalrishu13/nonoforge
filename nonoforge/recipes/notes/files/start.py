"""Ask your notes a question — a search that runs entirely on this computer.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

How it works, honestly: it does not understand your question. It looks for the
passages in your files that share the most words with it, counts how rare each
of those words is across the whole collection, and puts the best passage first.
That is called TF-IDF ranking, it is about sixty years old, and it is genuinely
useful — especially because unlike a chatbot it can always show you where the
answer came from.
"""

import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Bytes, Json, run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(HERE, "notes")
READABLE = (".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".text")

# Words so common that they would match everything and mean nothing.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "have", "has", "had",
    "i", "me", "my", "you", "your", "we", "our", "it", "its", "this", "that", "these", "those",
    "what", "which", "who", "whom", "how", "when", "where", "why", "any", "some", "about",
    "from", "by", "as", "so", "than", "then", "there", "here", "can", "could", "should", "would",
    "will", "just", "not", "no", "yes", "all", "more", "most", "much", "many", "also", "into",
}

app = App("{{PROJECT}}", default_port=8765)
_cache = {"signature": None, "passages": [], "files": []}


def _signature():
    """Cheap summary of the notes folder: if it changes, re-read the files.

    Names starting with a dot or an underscore are ignored, which is how the
    "put your notes here" note keeps itself out of your search results. Rename
    it if you would rather it were searched too.
    """
    parts = []
    if not os.path.isdir(NOTES):
        return ()
    for name in sorted(os.listdir(NOTES)):
        if name.startswith((".", "_")):
            continue
        path = os.path.join(NOTES, name)
        if name.lower().endswith(READABLE) and os.path.isfile(path):
            info = os.stat(path)
            parts.append((name, info.st_size, int(info.st_mtime)))
    return tuple(parts)


def words(text: str) -> list:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def read_notes():
    """Every passage in every note, with the words counted once per passage."""
    signature = _signature()
    if signature == _cache["signature"]:
        return _cache["passages"], _cache["files"]

    passages = []
    files = []
    for name, size, _mtime in signature:
        path = os.path.join(NOTES, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        # A passage is a paragraph: text between blank lines. Small enough to
        # read, big enough to hold an idea.
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
        found = 0
        for index, chunk in enumerate(chunks):
            counted = words(chunk)
            if len(counted) < 3:
                continue
            passages.append({
                "file": name,
                "index": index,
                "text": chunk[:4000],
                "counts": {word: counted.count(word) for word in set(counted)},
                "length": len(counted),
            })
            found += 1
        files.append({"name": name, "bytes": size, "passages": found, "words": len(words(text))})

    _cache.update({"signature": signature, "passages": passages, "files": files})
    return passages, files


def search(question: str, limit: int = 6) -> list:
    """Rank passages against the question. Rare shared words count for more."""
    passages, _files = read_notes()
    wanted = [word for word in words(question) if word not in STOPWORDS and len(word) > 2]
    if not wanted or not passages:
        return []
    wanted = list(dict.fromkeys(wanted))  # keep the order, drop repeats

    total = len(passages)
    document_frequency = {}
    for word in wanted:
        document_frequency[word] = sum(1 for passage in passages if word in passage["counts"])

    phrase = " ".join(wanted)
    results = []
    for passage in passages:
        score = 0.0
        matched = []
        for word in wanted:
            count = passage["counts"].get(word, 0)
            if not count:
                continue
            rarity = math.log(1 + total / (1 + document_frequency[word]))
            # A word that appears twice is worth more than once, but not twice as much.
            score += rarity * (1 + math.log(count))
            matched.append(word)
        if not score:
            continue
        # Long paragraphs should not win just for being long.
        score = score / (1 + math.log(passage["length"]))
        flat = " ".join(words(passage["text"]))
        if phrase in flat:
            score += 1.5
        if len(matched) > 1:
            score += 0.4 * len(matched)
        results.append({
            "file": passage["file"],
            "text": passage["text"],
            "score": round(score, 3),
            "matched": matched,
            "words": passage["length"],
        })

    results.sort(key=lambda item: -item["score"])
    if not results:
        return []
    best = results[0]["score"] or 1.0
    for item in results[:limit]:
        item["strength"] = max(0.12, min(1.0, item["score"] / best))
    return results[:limit]


@app.get("/api/stats")
def api_stats(_request):
    passages, files = read_notes()
    return Json({
        "files": files,
        "passages": len(passages),
        "words": sum(item["words"] for item in files),
        "folder": NOTES,
    })


@app.post("/api/ask")
def api_ask(request):
    question = request.field("question")
    if not question:
        return Json({"error": "Type a question first."}, 400)
    started = time.time()
    results = search(question)
    return Json({
        "question": question,
        "results": results,
        "took_ms": int((time.time() - started) * 1000),
        "terms": [word for word in words(question) if word not in STOPWORDS and len(word) > 2],
    })


@app.get("/api/file/{name}")
def api_file(_request, name):
    """The whole of one note, for when a passage is not enough."""
    safe = os.path.basename(name)
    path = os.path.join(NOTES, safe)
    if not os.path.isfile(path) or not safe.lower().endswith(READABLE):
        return Bytes(b"", "text/plain", 404)
    with open(path, "rb") as handle:
        return Bytes(handle.read(), "text/plain; charset=utf-8")


if __name__ == "__main__":
    run(app, "{{PROJECT}} — ask your notes a question")
