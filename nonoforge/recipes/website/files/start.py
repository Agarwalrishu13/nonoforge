"""Start your website.

Windows:      double-click run.bat
macOS/Linux:  double-click run.sh

A page opens in your browser. That page is your website.
"""

import mimetypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import App, Bytes, Json, run  # noqa: E402

PHOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")
PICTURE_TYPES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".svg")

app = App("{{PROJECT}}", default_port=8763)


def _pictures():
    if not os.path.isdir(PHOTOS):
        return []
    found = []
    for name in sorted(os.listdir(PHOTOS)):
        if name.lower().endswith(PICTURE_TYPES) and not name.startswith("."):
            found.append(name)
    return found


@app.get("/api/photos")
def list_photos(_request):
    """Every picture in the photos folder, newest name order."""
    return Json({"photos": _pictures()})


@app.get("/photo/{name}")
def one_photo(_request, name):
    """Send one picture. Never leaves the photos folder, whatever is asked for."""
    safe = os.path.basename(name)
    path = os.path.join(PHOTOS, safe)
    if not os.path.isfile(path) or not safe.lower().endswith(PICTURE_TYPES):
        return Bytes(b"", "text/plain", 404)
    kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as handle:
        return Bytes(handle.read(), kind)


if __name__ == "__main__":
    run(app, "{{PROJECT}} — your website")
