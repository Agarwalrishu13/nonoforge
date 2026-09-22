# {{NAME}}

A page with your questions on it. Every answer is saved on this computer in a
spreadsheet. Made with [nonoForge](https://github.com/Agarwalrishu13/nonoforge).

## Start it

```bash
python start.py            # opens http://127.0.0.1:8764
```

On Windows use `run.bat`; on macOS and Linux use `./run.sh`.

## Changing the questions

Open `questions.txt` and edit the lines — one question per line. Save, then
refresh the page. Lines starting with `#` are ignored.

## Getting the answers out

- Click **See all the answers** (or open `/responses.html`) to read them in the
  browser, newest first.
- Click **Spreadsheet** to download a CSV.
- Or open `data/answers.csv` directly — it is an ordinary CSV that Excel,
  Numbers and Google Sheets all read. `serve.py` writes the file with a
  byte-order mark, so Excel gets accented characters right.

## Letting other people fill it in

By default the form only answers on this computer. To let people on the same
home or office network use it, start it with:

```bash
python start.py --host 0.0.0.0
```

and give them `http://your-computer-ip:8764`. Do not do this on a public
network without thinking about it first: there is no password on this form by
design, and anything on your network could fill it in.

## Files

| file | what it holds |
|---|---|
| `questions.txt` | your questions, one per line |
| `web/index.html` | the form page |
| `web/responses.html` | the answers page |
| `web/style.css` | colours and spacing (`--accent` is the theme) |
| `start.py` | reads, saves and exports answers |
| `data/answers.csv` | every answer |
