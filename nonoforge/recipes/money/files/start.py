"""Where your money goes — a spending diary that adds itself up.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

Everything you write down is saved in data/expenses.csv, which opens in Excel,
Numbers or Google Sheets. Nothing is connected to a bank, and nothing is sent
anywhere: this app only knows what you type into it.
"""

import csv
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Download, Json, load_rows, run, save_rows  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_FILE = os.path.join(HERE, "categories.txt")
SHEET = "expenses.csv"
CURRENCY = "{{CURRENCY}}"
DEFAULT_CATEGORIES = ["Food", "Home", "Travel", "Bills", "Fun", "Other"]

app = App("{{PROJECT}}", default_port=8767)


def categories():
    """The groups to sort things into, read fresh each time so edits show up."""
    if not os.path.isfile(CATEGORIES_FILE):
        return list(DEFAULT_CATEGORIES)
    with open(CATEGORIES_FILE, encoding="utf-8") as handle:
        found = [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]
    return found or list(DEFAULT_CATEGORIES)


def parse_amount(text) -> float:
    """Read a number the way a person writes money: 12.50, 12,50, £12.50, 1 200."""
    raw = str(text or "").strip()
    raw = re.sub(r"[^\d.,\-]", "", raw)  # drop currency symbols and spaces
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        # Whichever comes last is the decimal separator.
        raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        tail = raw.split(",")[-1]
        raw = raw.replace(",", ".") if len(tail) in (1, 2) else raw.replace(",", "")
    try:
        return round(float(raw), 2)
    except ValueError:
        return 0.0


def entries() -> list:
    """All rows, newest first, each with a number to add up."""
    rows = load_rows(SHEET)
    for row in rows:
        try:
            row["value"] = round(float(str(row.get("amount", "0")).replace(",", ".") or 0), 2)
        except ValueError:
            row["value"] = 0.0
    return rows


def summarise(rows: list) -> dict:
    """Totals by month, by category, and how many entries there are."""
    this_month = time.strftime("%Y-%m")
    by_month, by_category = {}, {}
    for row in rows:
        when = str(row.get("when", ""))
        month = when[:7] if len(when) >= 7 else "unknown"
        category = str(row.get("category") or "Other")
        by_month[month] = round(by_month.get(month, 0) + row["value"], 2)
        by_category[category] = round(by_category.get(category, 0) + row["value"], 2)
    months = sorted(by_month.items(), reverse=True)[:12]
    ranked = sorted(by_category.items(), key=lambda item: -item[1])
    best = max(ranked, key=lambda item: item[1])[1] if ranked else 0
    return {
        "currency": CURRENCY,
        "count": len(rows),
        "total": round(sum(row["value"] for row in rows), 2),
        "this_month": by_month.get(this_month, 0.0),
        "month_name": time.strftime("%B %Y"),
        "months": [{"month": month, "total": total} for month, total in months],
        "categories": [
            {"name": name, "total": total, "share": round(total / best, 3) if best else 0}
            for name, total in ranked
        ],
        "categories_offered": categories(),
    }


@app.get("/api/summary")
def api_summary(_request):
    rows = entries()
    data = summarise(rows)
    data["recent"] = list(reversed(rows[-60:]))  # newest first, for the table
    return Json(data)


@app.post("/api/add")
def api_add(request):
    what = request.field("what")[:160]
    amount = parse_amount(request.json().get("amount"))
    category = request.field("category")[:40] or "Other"
    when = request.field("when")[:10] or time.strftime("%Y-%m-%d")
    if not what:
        return Json({"error": "What was it for? A couple of words is enough."}, 400)
    if amount == 0:
        return Json({"error": "I could not read an amount there. Try something like 12.50"}, 400)
    rows = load_rows(SHEET)
    rows.append({"when": when, "what": what, "amount": ("%.2f" % amount), "category": category,
                 "id": "%d" % int(time.time() * 1000)})
    save_rows(SHEET, rows)
    return Json({"ok": True, "added": "%s %s" % (CURRENCY, ("%.2f" % amount))})


@app.post("/api/remove")
def api_remove(request):
    wanted = str(request.json().get("id") or "")
    rows = load_rows(SHEET)
    keep = [row for row in rows if str(row.get("id") or "") != wanted]
    if len(keep) == len(rows):
        # Older rows written before ids existed: fall back to matching the row exactly.
        what = str(request.json().get("what") or "")
        keep = [row for row in rows if not (row.get("what") == what and row.get("when") == request.json().get("when"))]
    save_rows(SHEET, keep)
    return Json({"ok": True})


@app.get("/api/export.csv")
def api_export(_request):
    rows = load_rows(SHEET)
    columns = ["when", "what", "amount", "category"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return Download(buffer.getvalue().encode("utf-8-sig"),
                    "{{PROJECT}} %s.csv" % time.strftime("%Y-%m-%d"), "text/csv; charset=utf-8")


if __name__ == "__main__":
    run(app, "{{PROJECT}} — your spending, added up")
