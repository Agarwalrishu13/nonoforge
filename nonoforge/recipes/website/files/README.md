# {{NAME}}

{{TAGLINE}}

A one-page website, made with [nonoForge](https://github.com/Agarwalrishu13/nonoforge).
It is plain HTML, CSS and a small amount of JavaScript, served by a tiny Python
program that uses nothing but the standard library.

## Start it

```bash
python start.py            # opens http://127.0.0.1:8763
python start.py --port 9000 --no-browser
```

On Windows, `run.bat` does the same thing. On macOS and Linux, `./run.sh`.

## Where things are

| file | what it holds |
|---|---|
| `web/index.html` | every word on the page |
| `web/style.css` | the colours, spacing and type (`--accent` at the top is the whole theme) |
| `web/app.js` | the photo gallery |
| `start.py` | the program that serves the page and lists the photos |
| `serve.py` | the shared mini web engine (about 200 lines, no dependencies) |
| `photos/` | your pictures, read straight off the disk |

## Put it online later

The contents of `web/` are a static site: any web host will take them as they
are. `start.py` is only here so the photo gallery can see the `photos/` folder
while you are working on it locally.
