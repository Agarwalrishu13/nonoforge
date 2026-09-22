# {{NAME}}

Ask your own notes a question and get back the passages that answer it.

Made with [nonoForge](https://github.com/Agarwalrishu13/nonoforge). No model, no
internet, no install — a TF-IDF ranking over paragraphs, written in about 200
readable lines in `start.py`.

## Start it

```bash
python start.py            # opens http://127.0.0.1:8765
```

Windows: `run.bat`. macOS / Linux: `./run.sh`.

## Adding notes

Drop `.txt`, `.md`, `.rst` or `.log` files into the `notes/` folder. The app
re-reads the folder on every question, so there is nothing to restart.

PDFs and Word documents are not read directly — open them, copy the text, paste
it into a plain-text editor and save it into `notes/`.

## How the search works

1. Every file is split into paragraphs (blocks of text separated by blank lines).
2. Your question is broken into words, minus common words like "the" and "what".
3. Paragraphs are scored by how many of those words they contain, weighted so
   that **rare** words count for much more than common ones.
4. Anything matching the whole phrase you typed gets a bonus.
5. Scores are divided by paragraph length, so long paragraphs do not win simply
   by being long, and the top few are shown with the matched words highlighted.

That is TF-IDF, and its best property is that it can always show its work: every
result tells you which file it came from and which words matched.

## Tuning it

- `STOPWORDS` in `start.py` — words that are ignored. Add words that are common
  in your notes and match everything.
- `search(question, limit=6)` — how many passages come back.
- Scores below `0.12` of the best match are dropped from the meter; the code is
  in the `strength` calculation if you want to change it.
