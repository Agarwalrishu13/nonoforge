"""Collect answers from people, and keep every one of them in a spreadsheet.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

Your questions live in questions.txt — one per line. Every answer is written
into data/answers.csv, which opens in Excel, Numbers or Google Sheets.
"""

import csv
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Bytes, Download, Json, add_row, load_rows, run, stamp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(HERE, "questions.txt")
SHEET = "answers.csv"

app = App("{{PROJECT}}", default_port=8764)

HEADING = "{{HEADING}}"


def questions():
    """Read questions.txt every time, so edits show up on refresh."""
    if not os.path.isfile(QUESTIONS_FILE):
        return []
    with open(QUESTIONS_FILE, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]


def column_name(question: str, index: int, taken: set) -> str:
    """Turn a question into a spreadsheet column heading a person can read."""
    name = re.sub(r"[,\r\n]+", " ", question).strip()
    name = re.sub(r"\s+", " ", name)[:60].strip()
    if not name:
        name = "answer %d" % (index + 1)
    base, number = name, 2
    while name in taken:
        name = "%s (%d)" % (base, number)
        number += 1
    taken.add(name)
    return name


@app.get("/api/questions")
def api_questions(_request):
    wanted = questions()
    return Json({
        "heading": HEADING,
        "questions": [{"text": text, "column": column_name(text, index, set())} for index, text in enumerate(wanted)],
        "count": len(load_rows(SHEET)),
    })


@app.post("/api/answer")
def take_answer(request):
    """Save one person's answers. The only thing that writes to the spreadsheet."""
    wanted = questions()
    if not wanted:
        return Json({"error": "There are no questions in questions.txt yet."}, 400)
    row = {"name": request.field("name")[:120] or "(no name given)"}
    taken = set()
    for index, question in enumerate(wanted):
        row[column_name(question, index, taken)] = request.field("q%d" % index)[:4000]
    add_row(SHEET, stamp(row))
    return Json({"ok": True, "count": len(load_rows(SHEET))})


@app.get("/api/responses")
def api_responses(_request):
    rows = load_rows(SHEET)
    return Json({
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "count": len(rows),
        "questions": questions(),
    })


@app.get("/api/responses.csv")
def api_spreadsheet(_request):
    """Hand the whole thing over as a file, ready for Excel."""
    rows = load_rows(SHEET)
    columns = list(rows[0].keys()) if rows else ["when", "name"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    # The byte-order mark is what makes Excel open it with the accents intact.
    return Download(
        buffer.getvalue().encode("utf-8-sig"),
        "{{PROJECT}} answers %s.csv" % time.strftime("%Y-%m-%d"),
        "text/csv; charset=utf-8",
    )


@app.get("/api/count")
def api_count(_request):
    return Json({"count": len(load_rows(SHEET))})


if __name__ == "__main__":
    run(app, "{{PROJECT}} — a form that saves every answer")
