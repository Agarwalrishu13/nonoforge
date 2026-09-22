# {{NAME}}

A tiny language model that learns from your writing and then writes in the same
style — trained on your own computer in about a second. Made with
[nonoForge](https://github.com/Agarwalrishu13/nonoforge).

## Start it

```bash
python start.py            # opens http://127.0.0.1:8766
```

Windows: `run.bat`. macOS / Linux: `./run.sh`.

## What it is

A character-level n-gram model with backoff, in plain Python:

- Training counts every "the next letter after these three letters" in your text.
- Writing picks a next letter from those counts, weighted toward the most common
  one; the **creativity** slider flattens the weighting so rarer choices get a
  chance.
- When it does not recognise a context it backs off to two letters, then one,
  then starts a new word.

That is genuinely all of it. `start.py` is about 120 lines and none of it is
magic — which is the point: this is what "a model" means, small enough to hold
in your head.

## What it is not

It has no idea what words mean, and it will not answer questions or follow
instructions. With a few thousand words of input it produces charming,
half-coherent text in your voice. Feed it 100,000 words and it gets noticeably
better — that relationship between data and quality is the real lesson.

## Where your text goes

- Anything you paste is saved as `samples/pasted-writing.txt` and stays on this
  computer. "Forget what I pasted" deletes it.
- Files you drop into `samples/` are read but never modified.

## Knobs

| setting | in | effect |
|---|---|---|
| `ORDER` | `start.py` | how many characters of context it learns from (3 by default) |
| `LENGTHS` | `start.py` | how long "a sentence", "a paragraph" and "a page" are |
| `MAX_CORPUS` | `start.py` | how much text it will read (1.5 MB keeps it snappy) |
