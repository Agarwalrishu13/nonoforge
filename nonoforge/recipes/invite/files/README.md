# {{NAME}}

An invitation page with a live countdown and an RSVP form. Made with
[nonoForge](https://github.com/Agarwalrishu13/nonoforge).

## Start it

```bash
python start.py            # opens http://127.0.0.1:8768
```

Windows: `run.bat`. macOS / Linux: `./run.sh`.

## Two pages

| address | what it is for |
|---|---|
| `/` | the invitation itself, with the countdown and the reply form |
| `/guests.html` | your list: every reply, plus totals of who is coming |

## Changing the date, place and words

- **Date and time** — the lines `WHEN_DATE` and `WHEN_TIME` near the top of
  `start.py`. Use `2026-12-24` and `19:00`.
- **Place, headline and message** — `WHERE`, `HEADLINE` and `MESSAGE` right
  below, or edit the text in `web/index.html` directly.
- **Colour** — `--accent` on the first lines of `web/style.css`.

## Replies

Saved in `data/rsvp.csv` (`when`, `name`, `coming`, `how_many`, `note`) and
downloadable as a CSV from the guests page. The app also serves a real `.ics`
calendar file, so "Add to my calendar" works with Google Calendar, Apple
Calendar and Outlook.

## Letting guests reply from their own phones

Start it with `python start.py --host 0.0.0.0` and give guests
`http://your-computer-ip:8768` while they are on the same network. There is no
password on the form by design, so do this on a network you trust.
