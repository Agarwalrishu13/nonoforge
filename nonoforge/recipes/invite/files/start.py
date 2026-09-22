"""An invitation with a countdown, and a form where people say if they are coming.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

Every reply is saved in data/rsvp.csv, which opens in Excel. "Add to calendar"
hands out a real .ics file, which works with Google Calendar, Apple Calendar and
Outlook.
"""

import csv
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Download, Json, add_row, load_rows, run, stamp  # noqa: E402

# ---------------------------------------------------------------- your details
WHEN_DATE = "{{WHEN_DATE}}"     # e.g. 2026-12-24
WHEN_TIME = "{{WHEN_TIME}}"     # e.g. 19:00
WHERE = "{{WHERE}}"
HEADLINE = "{{HEADLINE}}"
MESSAGE = "{{MESSAGE}}"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

SHEET = "rsvp.csv"
app = App("{{PROJECT}}", default_port=8768)


def _parts():
    """The date and time as numbers, coping with a blank or odd entry."""
    date_text = (WHEN_DATE or "").strip()
    time_text = (WHEN_TIME or "19:00").strip()
    try:
        year, month, day = (int(piece) for piece in date_text.split("-")[:3])
        hour, minute = (int(piece) for piece in time_text.split(":")[:2])
        time.strptime("%04d-%02d-%02d" % (year, month, day), "%Y-%m-%d")
        return year, month, day, hour, minute
    except (ValueError, TypeError):
        # No usable date: count down to a week from now rather than break the page.
        soon = time.localtime(time.time() + 7 * 86400)
        return soon.tm_year, soon.tm_mon, soon.tm_mday, 19, 0


def when_text() -> str:
    year, month, day, hour, minute = _parts()
    weekday = DAYS[time.strptime("%04d-%02d-%02d" % (year, month, day), "%Y-%m-%d").tm_wday]
    clock = "%d:%02d %s" % ((hour - 1) % 12 + 1, minute, "am" if hour < 12 else "pm")
    return "%s %d %s %d at %s" % (weekday, day, MONTHS[month - 1], year, clock)


def when_iso() -> str:
    year, month, day, hour, minute = _parts()
    return "%04d-%02d-%02dT%02d:%02d" % (year, month, day, hour, minute)


def replies() -> list:
    return load_rows(SHEET)


@app.get("/api/invite")
def api_invite(_request):
    rows = replies()
    coming = [row for row in rows if str(row.get("coming", "")).lower().startswith("y")]
    people = 0
    for row in coming:
        try:
            people += int(str(row.get("how_many") or "1").strip() or 1)
        except ValueError:
            people += 1
    return Json({
        "headline": HEADLINE,
        "message": MESSAGE,
        "where": WHERE,
        "when_text": when_text(),
        "when_iso": when_iso(),
        "title": "{{PROJECT}}",
        "yes": len(coming),
        "maybe": len([row for row in rows if str(row.get("coming", "")).lower().startswith("m")]),
        "no": len([row for row in rows if str(row.get("coming", "")).lower().startswith("n")]),
        "people": people,
        "replies": len(rows),
    })


@app.post("/api/rsvp")
def api_rsvp(request):
    name = request.field("name")[:120]
    if not name:
        return Json({"error": "And your name? So we know who to expect."}, 400)
    coming = request.field("coming")[:20] or "Yes"
    how_many = request.field("how_many")[:6] or "1"
    try:
        how_many = str(max(1, min(30, int(how_many))))
    except ValueError:
        how_many = "1"
    add_row(SHEET, stamp({"name": name, "coming": coming, "how_many": how_many,
                          "note": request.field("note")[:600]}))
    return Json({"ok": True, "name": name, "coming": coming})


@app.get("/api/guests")
def api_guests(_request):
    rows = list(reversed(replies()))  # newest first
    return Json({"rows": rows, "columns": ["when", "name", "coming", "how_many", "note"]})


@app.get("/api/guests.csv")
def api_guests_csv(_request):
    rows = replies()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["when", "name", "coming", "how_many", "note"])
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in ("when", "name", "coming", "how_many", "note")})
    return Download(buffer.getvalue().encode("utf-8-sig"),
                    "{{PROJECT}} replies %s.csv" % time.strftime("%Y-%m-%d"), "text/csv; charset=utf-8")


@app.get("/api/calendar.ics")
def api_calendar(_request):
    """A calendar file anyone can double-click to add the event to their diary."""
    year, month, day, hour, minute = _parts()
    start = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))
    end = start + 4 * 3600  # four hours, a reasonable guess
    stamp_now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//nonoForge//invite//EN", "BEGIN:VEVENT",
        "UID:%d@nonoforge" % int(start), "DTSTAMP:" + stamp_now,
        "DTSTART:" + time.strftime("%Y%m%dT%H%M%S", time.localtime(start)),
        "DTEND:" + time.strftime("%Y%m%dT%H%M%S", time.localtime(end)),
        "SUMMARY:" + _ics_text(HEADLINE or "{{PROJECT}}"),
        "LOCATION:" + _ics_text(WHERE),
        "DESCRIPTION:" + _ics_text(MESSAGE[:400]),
        "END:VEVENT", "END:VCALENDAR", "",
    ]
    return Download("\r\n".join(lines).encode("utf-8"), "{{PROJECT}}.ics", "text/calendar; charset=utf-8")


def _ics_text(text: str) -> str:
    """Calendar files need commas, semicolons and newlines escaped."""
    return str(text or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")[:900]


if __name__ == "__main__":
    run(app, "{{PROJECT}} — your invitation")
