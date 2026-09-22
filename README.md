<div align="center">

# nonoForge

**Pick a card. Answer two questions. Press one button. You have a working app.**

For people who do not write code, do not use a terminal, and do not want an
account anywhere. One double-click starts it; everything happens on your own
computer and keeps working with the internet switched off.

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9+-58a6ff.svg)]()
[![dependencies](https://img.shields.io/badge/runtime%20deps-0-f0883e.svg)]()
[![tests](https://img.shields.io/badge/tests-40%20passing-3ddc97.svg)]()

</div>

---

## What this is, in one paragraph

Most people who could use a small app — a form for the club trip, a spending
diary, an invitation with an RSVP list — never get one, because getting one
means learning to code first. nonoForge is the missing middle step. You pick one
of six cards, answer a few plain questions, and press one button. It writes a
complete, working, self-contained app into a folder of its own, starts it so you
can see it immediately, and leaves a note called `START-HERE.txt` inside
explaining every file in plain words. Nothing is installed, nothing is uploaded,
and there is no account anywhere in the story.

**Zero dependencies.** The app, the page, and every project it produces are the
Python standard library plus HTML, CSS and JavaScript. There is nothing to
`pip install`, ever.

---

## Use it

1. Install Python if you do not have it — [python.org/downloads](https://www.python.org/downloads/).
   On Windows, tick **“Add python.exe to PATH”** during setup.
2. Download this repo (green **Code** button → *Download ZIP*) and unzip it.
3. **Windows:** double-click `run.bat`. **macOS / Linux:** double-click `run.sh`.
4. Your browser opens at `http://127.0.0.1:8762`. That is the app.

Then either say what you want in your own words — *“a page for my bakery”* —
and nonoForge picks the card for you, or choose a card yourself. Either way it is
one button from there.

<details>
<summary>Prefer the command line? (you do not need to)</summary>

```bash
python start.py                 # start and open the browser
python -m nonoforge             # the same thing
python -m nonoforge doctor      # print what this computer has, then exit
python -m nonoforge --port 9000 --no-browser
```

</details>

---

## The six cards

| card | what you get | good for |
|---|---|---|
| 🪧 **My own website** | a one-page site with your words, your colours, a photo gallery and your contact details | a business, a portfolio, a CV as a link |
| 📋 **Collect answers from people** | a form that saves every reply into a spreadsheet you can open in Excel | sign-ups, feedback, orders, a survey |
| 🔎 **Ask my notes a question** | plain-English search over your own `.txt` and `.md` files, showing the passage *and* which file it came from | study notes, meeting notes, research |
| ✍️ **Teach it my writing** | a small real model, trained on your text in about a second, that writes more in your style | seeing what "training a model" actually means |
| 💰 **Where my money goes** | a spending diary that totals itself by month and group, with an export button | keeping an eye on spending without an app or an account |
| 🎉 **An invitation with a countdown** | a pretty invitation page with a live countdown, an RSVP form, a guest list and an “add to calendar” button | birthdays, weddings, reunions |

Every generated project also gets `run.bat`, `run.sh`, a `START-HERE.txt` and a
`README.md`, because the last thing a newcomer needs is a folder with no
explanation in it.

### What "one button" actually does

```
pick a card  →  answer a few plain questions  →  press Make it ✨
      ↓
nonoForge makes a folder (never overwriting anything: "My site" → "My site 2")
      ↓
writes every file, fills in your words, drops your photos in the right place
      ↓
writes START-HERE.txt, which explains all of it
      ↓
starts it, waits until it is listening, and opens it in your browser
```

The progress panel narrates each of those steps in plain language as it
happens, because a progress bar that explains itself is the difference between
"it worked" and "is it stuck?".

---

## The rules this project holds itself to

- **Nothing is overwritten.** A name clash quietly becomes "My site 2". Your
  files are never touched, only read.
- **Nothing is installed.** No pip, no npm, no build step, no virtualenv. The
  generated projects are the same: double-click and they run.
- **Nothing is uploaded.** No telemetry, no accounts, no network calls. Drop a
  200 MB photo in and it is copied in 1 MB slices straight to your disk.
- **Everything is readable.** The generated projects are small, commented, and
  ordinary HTML/CSS/Python. A beginner can open `start.py` and follow it.
- **The last thing written is the explanation.** `START-HERE.txt` says what the
  thing is, how to start it, how to change it, and what each file is for.
- **It is honest about what it is.** The notes card says plainly that it ranks
  passages rather than understanding them. The writing card says plainly that
  its model is tiny and will sound like a slightly drunk version of you.

---

## Adding your own card

A card is a folder under `nonoforge/recipes/` with a `recipe.json` and a `files/`
folder. Nothing in the Python needs to change — that is the whole plugin system.

```
nonoforge/recipes/chore-chart/
├── recipe.json
└── files/
    ├── start.py            # optional: only if the project needs to run something
    ├── run.bat             # optional: injected automatically when "runs": true
    └── web/
        ├── index.html
        ├── style.css
        └── app.js
```

```json
{
  "id": "chore-chart",
  "emoji": "🧹",
  "title": "A jobs rota for the house",
  "blurb": "A shared list of who is doing what this week.",
  "best_for": "Housemates, families, a small team.",
  "keywords": ["chores", "rota", "jobs", "housework", "who does what"],
  "runs": true,
  "port": 8769,
  "asks": [
    { "key": "name", "type": "text", "label": "What should it be called?", "default": "Jobs rota" },
    { "key": "people", "type": "lines", "label": "Who is in the house?", "default": ["Me", "Sam"] },
    { "key": "accent", "type": "color", "label": "Pick a colour", "default": "#58a6ff" }
  ],
  "text_files": [{ "file": "people.txt", "key": "people" }],
  "changing": ["The names are the lines in people.txt."],
  "map": { "people.txt": "who is in the house", "web/index.html": "the page" }
}
```

Ask types are `text`, `textarea`, `lines`, `color`, `date`, `time`, `number`,
`choice` and `files`. Answers are dropped into the template files by replacing
`{{PLACEHOLDER}}`, escaped correctly for the file it lands in — HTML-escaped in
`.html`, JSON-escaped in `.js`. `files` answers are copied into the folder the
recipe names, so a layman can drag a photo in and find it later.

`tests/test_smoke.py` builds **every** recipe and boots what it produces, so a
new card is covered by the same safety net the moment you add it.

---

## Under the hood

```
nonoforge/
├── nonoforge/
│   ├── server.py       # every address the page can ask for, each one commented
│   ├── forge.py        # recipe + answers → a real project on disk
│   ├── recipes.py      # reading the cards, and guessing which one you meant
│   ├── store.py        # settings, the list of projects, safe folder names
│   ├── httpbase.py     # the mini web toolkit (routing, JSON, SSE, uploads)
│   ├── runtime/serve.py# the ~230-line engine copied into every project it makes
│   └── recipes/        # the six cards
├── tests/test_smoke.py # 40 tests, including "does every card actually work"
└── start.py, run.bat, run.sh
```

- **The guessing is explainable.** No model, no internet: it counts the words
  you used against the words each card lists as its own, and tells you why it
  chose. When it is not sure it offers the runners-up.
- **The build streams.** `/api/create` is a Server-Sent Events stream, so the
  page narrates the build as it happens rather than spinning.
- **Starting a project is a subprocess with a handshake.** nonoForge launches the
  project's own `start.py`, waits for the line `nonoforge-ready: <url>` on
  stdout, and only then opens the browser — so it opens the right page at the
  right moment, even if the port had to move.
- **It will not run a folder it did not make.** Starting an arbitrary folder
  would be a way to run code through a web page, so `/api/start` requires a
  `project.json` written by nonoForge itself.
- **The page is not drivable by other websites.** Requests carrying an `Origin`
  must come from this machine, and the JSON endpoints require an actual JSON
  content type — which makes a browser refuse the cross-site request.

## Tests

```bash
python -m unittest discover tests -v     # 40 tests, no dependencies
```

The interesting ones are not "does this endpoint return 200". They are:
*does every card build with no placeholder left unfilled*, and *does the project
it makes actually start, serve its page, and answer?* The suite builds all six
cards, launches each generated app as a real subprocess, and talks to it over
HTTP — the same thing a person does when they double-click `run.bat`.

CI runs on Windows, macOS and Linux, on Python 3.9 and 3.13.

---

## Where this sits in the family

| repo | role |
|---|---|
| [nanollama.c](https://github.com/Agarwalrishu13/nanollama.c) | the engine — from-scratch C inference |
| [nanobrain](https://github.com/Agarwalrishu13/nanobrain) | the brain factory — trains the model from scratch |
| [nonoForge](https://github.com/Agarwalrishu13/nonoforge) | **this repo** — the front door: make yourself a small app, no code |
| [nanolaama](https://github.com/Agarwalrishu13/nanolaama) | talk to an AI on your own computer, no terminal |
| [nanolearn](https://github.com/Agarwalrishu13/nanolearn) | drop a spreadsheet, get an answer machine |

The same idea runs through all of them: the hard thing should be built properly,
and then it should be handed to somebody who has never had it before.

MIT licensed. Made by [Priyanshu Agarwal](https://github.com/Agarwalrishu13).
