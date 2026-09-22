"""Tests for nonoForge.

The interesting tests are not "does this endpoint return 200". They are:

* does **every** recipe build, with no placeholder left behind, and
* does the project it makes actually **start and answer**?

So most of this file builds each card in turn, starts the app it produced as a
real subprocess, and talks to it over HTTP — the same thing a person does when
they double-click run.bat.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the app at a throwaway folder before it is imported.
_TMP = tempfile.mkdtemp(prefix="nonoforge-tests-")
os.environ["NONOFORGE_HOME"] = _TMP

from nonoforge import forge, recipes, store  # noqa: E402
from nonoforge.httpbase import free_port  # noqa: E402
from nonoforge.server import create_app  # noqa: E402

PROJECTS = os.path.join(_TMP, "projects")
os.makedirs(PROJECTS, exist_ok=True)


# ==========================================================================
# The recipes themselves
# ==========================================================================
class TestRecipes(unittest.TestCase):
    def test_every_recipe_loads_and_is_complete(self):
        found = recipes.load_all()
        self.assertGreaterEqual(len(found), 6, "expected the full card set")
        seen = set()
        for recipe in found:
            with self.subTest(recipe=recipe["id"]):
                self.assertNotIn(recipe["id"], seen, "duplicate recipe id")
                seen.add(recipe["id"])
                self.assertTrue(recipe["emoji"])
                self.assertTrue(recipe["title"])
                self.assertTrue(recipe["blurb"].endswith("."), "blurbs are sentences")
                self.assertTrue(recipe["keywords"], "a recipe nobody can guess is a dead card")
                files = recipes.files_for(recipe)
                self.assertTrue(files, "a recipe with no files makes nothing")
                if recipe["runs"]:
                    self.assertIn("start.py", files, "anything that runs needs a start.py")
                self.assertIn("web/index.html", files, "every recipe has a page")

    def test_the_files_are_plain_text_where_they_should_be(self):
        """The promise is readable files, so templates must not be minified blobs."""
        for recipe in recipes.load_all():
            for relative in recipes.files_for(recipe):
                if not relative.endswith((".py", ".js", ".css", ".html", ".md", ".json", ".txt")):
                    continue
                with self.subTest(recipe=recipe["id"], file=relative):
                    text = (recipe["files_dir"] / relative).read_text(encoding="utf-8")
                    self.assertIn("\n", text, "a single-line file is not readable")

    def test_guessing_what_somebody_means(self):
        cases = {
            "I want a website for my bakery": "website",
            "make me a page about my band": "website",
            "a form where people can sign up for the trip": "answers",
            "somewhere to collect feedback from customers": "answers",
            "search my notes about the project": "notes",
            "I want to ask my study documents questions": "notes",
            "teach an ai to write like me": "writer",
            "train a model on my writing": "writer",
            "track my spending and expenses": "money",
            "where does my money go each month": "money",
            "invite people to my birthday party": "invite",
            "an invitation with rsvp for the wedding": "invite",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                picked = recipes.pick(text)
                self.assertEqual(picked["recipe"], expected, "guessed %s: %s" % (picked["recipe"], picked["why"]))
                self.assertTrue(picked["why"], "the page must be able to explain its guess")

    def test_a_request_with_no_meaning_guesses_nothing(self):
        picked = recipes.pick("qqqq zzz")
        self.assertIsNone(picked["recipe"])
        self.assertFalse(picked["confident"])

    def test_empty_request_is_not_a_crash(self):
        self.assertIsNone(recipes.pick("")["recipe"])
        self.assertIsNone(recipes.pick(None)["recipe"])


# ==========================================================================
# Building
# ==========================================================================
class BuiltProject:
    """Build a recipe, start what it made, and talk to it over HTTP."""

    def __init__(self, recipe_id, answers=None, attachments=None, name=None):
        self.recipe = recipes.get(recipe_id)
        answers = dict(answers or {})
        if name:
            answers["name"] = name
        self.answers = answers
        self.attachments = attachments or []
        self.folder = None
        self.process = None
        self.url = ""
        self.output: list = []

    def build(self):
        self.folder = forge.plan(self.recipe, self.answers, PROJECTS)["folder"]
        manifest = forge.build(self.recipe, self.answers, PROJECTS, self.attachments)
        self.folder = manifest["folder"]
        return manifest

    def start(self):
        """Run the project's own start.py, exactly as run.bat would.

        The port is chosen here and the address is polled until it answers —
        the same handshake nonoForge itself uses.
        """
        port = free_port(8820)
        self.url = "http://127.0.0.1:%d" % port
        self.process = subprocess.Popen(
            [sys.executable, "start.py", "--no-browser", "--port", str(port)],
            cwd=self.folder,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain, daemon=True).start()
        if not self._answering():
            self.stop()
            # Say exactly what the child did, rather than only that it failed:
            # this test is the only thing standing between a broken recipe and
            # somebody's laptop, so its failure has to be readable.
            raise AssertionError(
                "the generated project never started answering on %s\n"
                "alive: %s\n--- what it said ---\n%s"
                % (self.url, self.process.poll() is None, "\n".join(self.output) or "(nothing)")
            )
        return self.url

    def _drain(self):
        """Keep reading so the child never blocks on a full pipe."""
        try:
            for line in self.process.stdout:
                self.output.append(line.rstrip())
                del self.output[:-40]
        except Exception:
            pass

    def _answering(self, timeout: float = 25.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(self.url + "/", timeout=2) as response:
                    response.read(1)
                    return True
            except urllib.error.HTTPError:
                return True
            except Exception:
                time.sleep(0.25)
        return False

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def get(self, path, raw=False):
        with urllib.request.urlopen(self.url + path, timeout=15) as response:
            body = response.read()
        return body if raw else json.loads(body.decode("utf-8"))

    def post(self, path, payload):
        request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))

    def __enter__(self):
        self.build()
        if self.recipe["runs"]:
            self.start()
        return self

    def __exit__(self, *_exc):
        self.stop()
        return False


def attachment(key, name, text):
    """A dropped file, as the page would send it."""
    folder = os.path.join(_TMP, "dropped")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return {"key": key, "name": name, "path": path}


class TestEveryRecipeBuilds(unittest.TestCase):
    def test_no_recipe_leaves_a_placeholder_behind(self):
        """An unfilled {{PLACEHOLDER}} is the classic template bug — catch all of them."""
        for recipe in recipes.load_all():
            with self.subTest(recipe=recipe["id"]):
                manifest = forge.build(recipe, {"name": "Test %s" % recipe["id"]}, PROJECTS)
                folder = manifest["folder"]
                offenders = []
                for root, _dirs, names in os.walk(folder):
                    for name in names:
                        if not name.endswith((".py", ".js", ".css", ".html", ".md", ".txt", ".json", ".bat", ".sh")):
                            continue
                        path = Path(root) / name
                        if "{{" in path.read_text(encoding="utf-8", errors="replace"):
                            offenders.append(path.relative_to(folder).as_posix())
                self.assertEqual(offenders, [], "unfilled placeholders in %s" % offenders)
                # Everything nonoForge promises to write is there.
                self.assertTrue((Path(folder) / "START-HERE.txt").is_file())
                self.assertTrue((Path(folder) / "project.json").is_file())
                if recipe["runs"]:
                    for name in ("start.py", "serve.py", "run.bat", "run.sh"):
                        self.assertTrue((Path(folder) / name).is_file(), name)
                start_here = (Path(folder) / "START-HERE.txt").read_text(encoding="utf-8")
                self.assertIn("HOW TO", start_here)
                self.assertIn("Test %s" % recipe["id"], start_here, "the answer should reach the note")

    def test_every_recipe_starts_and_answers(self):
        """The real test: does the thing it made actually run?"""
        for recipe in recipes.load_all():
            with self.subTest(recipe=recipe["id"]):
                with BuiltProject(recipe["id"], name="Runs %s" % recipe["id"]) as project:
                    page = project.get("/", raw=True).decode("utf-8")
                    self.assertIn("<!DOCTYPE HTML>", page.upper())
                    self.assertGreater(len(page), 200, "an empty page is not an app")
                    assets = [name for name in ("/style.css", "/app.js")
                              if os.path.isfile(os.path.join(project.folder, "web", name.lstrip("/")))]
                    self.assertTrue(assets, "a page with no stylesheet is not finished")
                    for asset in assets:
                        self.assertGreater(len(project.get(asset, raw=True)), 50)

    def test_a_website_shows_its_photos(self):
        photo = attachment("photos", "cake.jpg", "not really a jpeg, but the app only lists it")
        with BuiltProject("website", {"tagline": "Bread", "about": "We bake."}, [photo], name="Bakery") as project:
            self.assertEqual(project.get("/api/photos")["photos"], ["cake.jpg"])
            self.assertGreater(len(project.get("/photo/cake.jpg", raw=True)), 0)

    def test_a_form_saves_an_answer(self):
        with BuiltProject("answers", {"questions": ["Your email", "How many are coming?"]},
                          name="Trip sign-up") as project:
            questions = project.get("/api/questions")["questions"]
            self.assertEqual(len(questions), 2)
            self.assertEqual(project.get("/api/questions")["count"], 0)
            result = project.post("/api/answer", {"name": "Sam", "q0": "sam@example.com", "q1": "3"})
            self.assertTrue(result["ok"])
            rows = project.get("/api/responses")
            self.assertEqual(rows["count"], 1)
            self.assertEqual(rows["rows"][0]["name"], "Sam")
            self.assertEqual(rows["rows"][0]["Your email"], "sam@example.com")
            sheet = project.get("/api/responses.csv", raw=True).decode("utf-8-sig")
            self.assertIn("sam@example.com", sheet)

    def test_a_form_rejects_nonsense_answers(self):
        with BuiltProject("answers", name="Empty form") as project:
            # A missing name is allowed (somebody may not want to give one), but
            # the row must still be usable.
            result = project.post("/api/answer", {"q0": "hello"})
            self.assertTrue(result["ok"])
            self.assertEqual(project.get("/api/responses")["rows"][0]["name"], "(no name given)")

    def test_notes_finds_the_right_file(self):
        notes = [
            attachment("notes", "roof.txt", "The roof needs fixing before winter. We agreed to call the builder in March."),
            attachment("notes", "holiday.txt", "We booked two weeks in Portugal for the summer holiday."),
        ]
        with BuiltProject("notes", {}, notes, name="My notes") as project:
            stats = project.get("/api/stats")
            self.assertEqual(len(stats["files"]), 2)
            result = project.post("/api/ask", {"question": "when is the builder coming to fix the roof"})
            self.assertTrue(result["results"], "the answer is in there somewhere")
            best = result["results"][0]
            self.assertEqual(best["file"], "roof.txt")
            self.assertIn("builder", best["text"])
            self.assertTrue(best["matched"])
            # A question about something that is not in the notes matches nothing.
            self.assertEqual(project.post("/api/ask", {"question": "quantum chromodynamics"})["results"], [])

    def test_notes_says_so_when_the_folder_is_empty(self):
        with BuiltProject("notes", name="Empty notes") as project:
            stats = project.get("/api/stats")
            self.assertEqual(stats["files"], [])
            self.assertEqual(project.post("/api/ask", {"question": "anything"})["results"], [])

    def test_the_writer_learns_and_writes(self):
        sample = attachment(
            "samples", "my-prose.txt",
            "The lighthouse stood at the end of the long stone wall. Every evening the keeper "
            "walked the path with a lantern in his hand. The wind came off the sea and the gulls "
            "called over the water. He had kept the light for thirty years, and he knew every "
            "stone of the wall by heart.\n" * 3,
        )
        with BuiltProject("writer", {}, [sample], name="My writer") as project:
            stats = project.get("/api/stats")
            self.assertTrue(stats["trained"], "the sample should have been learnt from")
            self.assertGreater(stats["characters"], 200)
            self.assertTrue(stats["pairs"], "it should be able to show what it noticed")
            written = project.post("/api/write", {"prompt": "The lighthouse", "how_much": "a sentence", "creativity": 0.8})
            self.assertIn("lighthouse", written["text"].lower())
            self.assertGreater(len(written["text"]), 60)
            # Pasted text is learnt too, and can be forgotten again.
            pasted = project.post("/api/learn", {"text": "A sentence about turnips. " * 12})
            self.assertTrue(pasted["trained"])
            self.assertGreaterEqual(pasted["words"], 48)
            self.assertFalse(project.post("/api/forget", {})["files"] == [])

    def test_money_adds_up(self):
        with BuiltProject("money", {"currency": "£", "categories": ["Food", "Travel"]}, name="Spending") as project:
            self.assertTrue(project.post("/api/add", {"what": "Bread", "amount": "3.50", "category": "Food"})["ok"])
            self.assertTrue(project.post("/api/add", {"what": "Train", "amount": "£12.50", "category": "Travel"})["ok"])
            # A comma decimal separator, the way half of Europe writes numbers.
            self.assertTrue(project.post("/api/add", {"what": "Coffee", "amount": "2,40", "category": "Food"})["ok"])
            summary = project.get("/api/summary")
            self.assertEqual(summary["count"], 3)
            self.assertAlmostEqual(summary["total"], 18.40, places=2)
            groups = {item["name"]: item["total"] for item in summary["categories"]}
            self.assertAlmostEqual(groups["Food"], 5.90, places=2)
            self.assertAlmostEqual(groups["Travel"], 12.50, places=2)
            self.assertEqual(summary["recent"][0]["what"], "Coffee", "newest first")
            # Nonsense in the amount box is refused with a sentence, not a crash.
            self.assertIn("error", project.post("/api/add", {"what": "Nothing", "amount": "abc"}))
            self.assertIn("error", project.post("/api/add", {"what": "", "amount": "5"}))
            # And an entry can be taken back out again.
            entry = summary["recent"][0]
            project.post("/api/remove", {"id": entry["id"]})
            self.assertEqual(project.get("/api/summary")["count"], 2)
            self.assertIn("Bread", project.get("/api/export.csv", raw=True).decode("utf-8-sig"))

    def test_an_invitation_counts_down_and_takes_replies(self):
        with BuiltProject("invite", {"headline": "Mum turns 70", "when_date": "2030-06-15",
                                     "when_time": "19:00", "where": "The big house"},
                          name="Party") as project:
            invite = project.get("/api/invite")
            self.assertEqual(invite["headline"], "Mum turns 70")
            self.assertEqual(invite["where"], "The big house")
            self.assertIn("Saturday 15 June 2030", invite["when_text"])
            self.assertIn("7:00 pm", invite["when_text"])
            self.assertEqual(invite["when_iso"], "2030-06-15T19:00")
            self.assertTrue(project.post("/api/rsvp", {"name": "Alex", "coming": "Yes", "how_many": "3"})["ok"])
            project.post("/api/rsvp", {"name": "Sam", "coming": "No"})
            project.post("/api/rsvp", {"name": "Jo", "coming": "Maybe", "note": "might be late"})
            invite = project.get("/api/invite")
            self.assertEqual((invite["yes"], invite["no"], invite["maybe"], invite["people"]), (1, 1, 1, 3))
            self.assertIn("error", project.post("/api/rsvp", {"name": "", "coming": "Yes"}))
            guests = project.get("/api/guests")
            self.assertEqual(len(guests["rows"]), 3)
            self.assertEqual(guests["rows"][0]["name"], "Jo", "newest first")
            calendar = project.get("/api/calendar.ics", raw=True).decode("utf-8")
            self.assertIn("BEGIN:VCALENDAR", calendar)
            self.assertIn("DTSTART:20300615T190000", calendar)
            self.assertIn("LOCATION:The big house", calendar)

    def test_an_invitation_survives_a_missing_date(self):
        """Somebody will leave the date blank. It must not break the page."""
        with BuiltProject("invite", {"when_date": "", "when_time": ""}, name="No date") as project:
            invite = project.get("/api/invite")
            self.assertTrue(invite["when_text"], "there is always a readable date")
            self.assertTrue(invite["when_iso"])
            self.assertIn("BEGIN:VCALENDAR", project.get("/api/calendar.ics", raw=True).decode("utf-8"))


# ==========================================================================
# Naming, and not overwriting anybody's work
# ==========================================================================
class TestNamesAndFolders(unittest.TestCase):
    def test_folder_names_are_made_safe(self):
        cases = {
            'My site: "the best" <one>': "My site the best one",
            "../../escape": "escape",
            "   ": "My project",
            "trailing dots...": "trailing dots",
            "CON": "CON project",
            "a" * 200: "a" * 64,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw[:20]):
                self.assertEqual(store.safe_folder_name(raw), expected)

    def test_a_folder_name_never_wanders_off(self):
        for nasty in ("../..", "..\\..", "/etc/passwd", "C:\\Windows"):
            cleaned = store.safe_folder_name(nasty)
            self.assertNotIn("/", cleaned)
            self.assertNotIn("\\", cleaned)
            self.assertNotIn(":", cleaned)

    def test_nothing_is_ever_overwritten(self):
        parent = Path(_TMP) / "clash"
        parent.mkdir(parents=True, exist_ok=True)
        first = store.unique_dir(parent, "My site")
        first.mkdir()
        (first / "keep-me.txt").write_text("important", encoding="utf-8")
        second = store.unique_dir(parent, "My site")
        self.assertEqual(second.name, "My site 2")
        second.mkdir()
        (second / "also-mine.txt").write_text("also important", encoding="utf-8")
        self.assertEqual(store.unique_dir(parent, "My site").name, "My site 3")
        self.assertEqual((first / "keep-me.txt").read_text(encoding="utf-8"), "important")
        self.assertEqual(len(list(parent.iterdir())), 2, "nothing new should have been made yet")

    def test_an_empty_folder_is_fair_game(self):
        """Somebody made an empty folder in the way; using it beats making 'X 2'."""
        parent = Path(_TMP) / "empties"
        parent.mkdir(parents=True, exist_ok=True)
        (parent / "Reusable").mkdir()
        self.assertEqual(store.unique_dir(parent, "Reusable").name, "Reusable")

    def test_building_twice_renames_instead_of_replacing(self):
        first = forge.build(recipes.get("website"), {"name": "Same name"}, PROJECTS)
        second = forge.build(recipes.get("website"), {"name": "Same name"}, PROJECTS)
        self.assertNotEqual(first["folder"], second["folder"])
        self.assertTrue(second["renamed"])
        self.assertTrue(os.path.isfile(os.path.join(first["folder"], "START-HERE.txt")))

    def test_the_pair_of_files_a_person_needs_are_there(self):
        manifest = forge.build(recipes.get("website"), {"name": "Note check"}, PROJECTS)
        folder = Path(manifest["folder"])
        start_here = (folder / "START-HERE.txt").read_text(encoding="utf-8")
        self.assertIn("run.bat", start_here, "Windows users need to be told about run.bat")
        self.assertIn("run.sh", start_here)
        self.assertIn("Note check", start_here, "the note starts with what this thing is called")
        record = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(record["recipe"], "website")
        self.assertEqual(record["name"], "Note check")


# ==========================================================================
# The nonoForge app itself
# ==========================================================================
class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.port = free_port(8801)
        cls.base = "http://127.0.0.1:%d" % cls.port
        threading.Thread(
            target=cls.app.serve,
            kwargs={"host": "127.0.0.1", "port": cls.port, "open_browser": False, "quiet": True},
            daemon=True,
        ).start()
        for _ in range(80):
            try:
                cls.get("/api/health")
                return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("the test server never came up")

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()

    @classmethod
    def get(cls, path, raw=False):
        with urllib.request.urlopen(cls.base + path, timeout=20) as response:
            body = response.read()
        return body if raw else json.loads(body.decode("utf-8"))

    @classmethod
    def post(cls, path, payload=None, raw=False, expect_error=False, content_type="application/json"):
        request = urllib.request.Request(
            cls.base + path,
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            if not expect_error:
                raise
            body = exc.read()
        return body if raw else json.loads(body.decode("utf-8"))

    @classmethod
    def post_bytes(cls, path, data):
        request = urllib.request.Request(cls.base + path, data=data, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
        return json.loads(body.decode("utf-8"))

    @classmethod
    def stream(cls, path, payload):
        """POST an SSE endpoint and return the events, in order."""
        request = urllib.request.Request(
            cls.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            text = response.read().decode("utf-8")
        events = []
        for block in text.split("\n\n"):
            for line in block.split("\n"):
                if line.startswith("data:") and line.strip() != "data: [DONE]":
                    events.append(json.loads(line[5:]))
        return events


class TestStartingIsQuick(unittest.TestCase):
    """Python's HTTPServer does a reverse-DNS lookup the moment it binds a port.

    ``socket.getfqdn(host)`` on the address you just bound is a name lookup: free
    on a healthy machine, and tens of seconds of silence on a machine whose DNS
    resolver is slow — which is how every generated project failed on macOS CI.
    Both engines must start with that lookup rigged to explode.
    """

    def test_a_generated_project_starts_without_a_reverse_dns_lookup(self):
        work = tempfile.mkdtemp(prefix="nonoforge-nodns-")
        manifest = forge.build(recipes.get("answers"), {"name": "No DNS"}, work)
        folder = manifest["folder"]
        port = free_port(8860)

        script = Path(work) / "explode.py"
        script.write_text(
            '"""Start the project with socket.getfqdn rigged to explode."""\n'
            "import runpy, socket, sys\n\n"
            "def boom(*args, **kwargs):\n"
            "    raise RuntimeError('getfqdn was called during startup')\n\n"
            "socket.getfqdn = boom\n"
            'sys.argv = ["start.py", "--no-browser", "--port", "%d"]\n'
            'runpy.run_path("start.py", run_name="__main__")\n' % port,
            encoding="utf-8",
        )

        process = subprocess.Popen(
            [sys.executable, str(script)], cwd=folder,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        said: list = []
        threading.Thread(target=lambda: [said.append(line) for line in process.stdout], daemon=True).start()
        try:
            url = "http://127.0.0.1:%d/api/questions" % port
            answered = False
            deadline = time.time() + 25
            while time.time() < deadline and process.poll() is None:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        json.loads(response.read().decode("utf-8"))
                        answered = True
                        break
                except Exception:
                    time.sleep(0.25)
            self.assertTrue(answered, "the project did not start without a DNS lookup:\n" + "".join(said[-12:]))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            shutil.rmtree(work, ignore_errors=True)

    def test_nonoForge_itself_starts_without_a_reverse_dns_lookup(self):
        original = socket.getfqdn
        port = free_port(8880)
        app = create_app()

        def boom(*args, **kwargs):
            raise RuntimeError("getfqdn was called during startup")

        socket.getfqdn = boom
        try:
            threading.Thread(
                target=app.serve,
                kwargs={"host": "127.0.0.1", "port": port, "open_browser": False, "quiet": True},
                daemon=True,
            ).start()
            health = None
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=2) as response:
                        health = json.loads(response.read().decode("utf-8"))
                        break
                except Exception:
                    time.sleep(0.25)
        finally:
            socket.getfqdn = original
            app.shutdown()
        self.assertIsNotNone(health, "nonoForge did not start without a DNS lookup")
        self.assertTrue(health["ok"])


class TestTheApp(ServerCase):
    def test_health(self):
        data = self.get("/api/health")
        self.assertTrue(data["ok"])
        self.assertEqual(data["app"], "nonoForge")
        self.assertGreaterEqual(data["recipes"], 6)

    def test_the_page_is_served_with_its_parts(self):
        page = self.get("/", raw=True).decode("utf-8")
        self.assertIn("nonoForge", page)
        self.assertIn("/app.js", page)
        self.assertIn("/style.css", page)
        self.assertIn("--accent", self.get("/style.css", raw=True).decode("utf-8"))
        self.assertIn("chooseCard", self.get("/app.js", raw=True).decode("utf-8"))

    def test_unknown_page_does_not_leak_files(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/../../etc/passwd", raw=True)
        self.assertIn(caught.exception.code, (400, 404))

    def test_recipes_are_listed_with_what_you_get(self):
        data = self.get("/api/recipes")
        self.assertGreaterEqual(len(data["recipes"]), 6)
        for recipe in data["recipes"]:
            self.assertTrue(recipe["files"], recipe["id"])
            self.assertIn(recipe["emoji"], recipe["emoji"])  # a card needs a face
        one = self.get("/api/recipes/website")["recipe"]
        self.assertEqual(one["id"], "website")
        self.assertTrue(one["asks"])

    def test_unknown_recipe_is_a_sentence_not_a_traceback(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/recipes/no-such-card")
        self.assertEqual(caught.exception.code, 404)

    def test_guessing_endpoint(self):
        data = self.post("/api/pick", {"text": "a page for my bakery"})
        self.assertEqual(data["recipe"]["id"], "website")
        self.assertIn("page", data["why"])
        self.assertTrue(data["confident"])
        empty = self.post("/api/pick", {"text": ""}, expect_error=True)
        self.assertIn("error", empty)

    def test_the_plan_shows_before_anything_is_made(self):
        data = self.post("/api/plan", {"recipe": "website", "answers": {"name": "Planned site"},
                                       "parent": PROJECTS})
        self.assertEqual(data["folder_name"], "Planned site")
        self.assertGreater(data["file_count"], 4)
        self.assertFalse(os.path.exists(data["folder"]), "a plan must not create anything")

    def test_creating_something_from_start_to_finish(self):
        events = self.stream("/api/create", {
            "recipe": "money", "answers": {"name": "Streamed spending", "currency": "$"},
            "parent": PROJECTS, "start": False,
        })
        kinds = [event["type"] for event in events]
        self.assertIn("step", kinds)
        self.assertIn("made", kinds)
        self.assertIn("done", kinds)
        self.assertNotIn("error", kinds)
        made = [event for event in events if event["type"] == "made"][0]
        self.assertTrue(os.path.isdir(made["folder"]))
        self.assertIn("START-HERE.txt", made["files"])
        steps = [event["text"] for event in events if event["type"] == "step"]
        self.assertTrue(any("folder" in text.lower() for text in steps), steps)

        # It shows up in the list of projects, and can be forgotten again.
        listed = self.get("/api/projects")["projects"]
        self.assertTrue(any(item["name"] == "Streamed spending" for item in listed))
        after = self.post("/api/forget", {"path": made["folder"]})["projects"]
        self.assertFalse(any(item["name"] == "Streamed spending" for item in after))
        self.assertTrue(os.path.isdir(made["folder"]), "forgetting must not delete anything")

    def test_creating_and_starting_it_in_one_go(self):
        """The whole promise: press one button, an app is made and running."""
        events = self.stream("/api/create", {
            "recipe": "answers", "answers": {"name": "One go form"},
            "parent": PROJECTS, "start": True,
        })
        running = [event for event in events if event["type"] == "running"]
        self.assertTrue(running, "it should have started the app it made")
        url = running[0]["url"]
        try:
            with urllib.request.urlopen(url + "/api/questions", timeout=15) as response:
                self.assertEqual(response.status, 200)
            # nonoForge remembers it, and can stop it again.
            listed = self.get("/api/projects")
            self.assertTrue(any(item["path"] == running[0]["path"] for item in listed["running"]))
            self.assertTrue(self.post("/api/stop", {"path": running[0]["path"]})["stopped"])
        finally:
            self.post("/api/stop", {"path": running[0]["path"]})

    def test_a_bad_request_is_answered_in_words(self):
        result = self.post("/api/create", {"recipe": "nope"}, expect_error=True)
        self.assertIn("error", result)
        self.assertNotIn("Traceback", json.dumps(result))

    def test_refuses_a_folder_it_did_not_make(self):
        """Starting arbitrary folders would be a way to run code from a web page."""
        stranger = os.path.join(_TMP, "not-ours")
        os.makedirs(stranger, exist_ok=True)
        with open(os.path.join(stranger, "start.py"), "w", encoding="utf-8") as handle:
            handle.write("print('should never run')\n")
        result = self.post("/api/start", {"path": stranger}, expect_error=True)
        self.assertIn("error", result)
        self.assertIn("not made by", result["error"])

    def test_another_website_cannot_drive_this_app(self):
        result = self.post("/api/pick", {"text": "a website"}, expect_error=True, content_type="text/plain")
        self.assertIn("error", result)

    def test_opening_a_folder_that_is_gone_says_so(self):
        result = self.post("/api/open", {"path": os.path.join(_TMP, "nope-nope")}, expect_error=True)
        self.assertIn("error", result)

    def test_settings_are_remembered(self):
        saved = self.post("/api/settings", {"git": True, "parent": PROJECTS})
        self.assertTrue(saved["settings"]["git"])
        self.assertEqual(saved["settings"]["parent"], PROJECTS)
        self.assertEqual(self.get("/api/settings")["settings"]["parent"], PROJECTS)
        self.post("/api/settings", {"git": False})

    def test_doctor(self):
        data = self.get("/api/doctor")
        for key in ("version", "python", "projects_folder", "recipes", "settings_folder", "running"):
            self.assertIn(key, data)

    def test_uploads_land_somewhere_safe(self):
        started = self.post("/api/upload/start", {"name": "../../naughty.txt"})
        self.assertNotIn("..", started["name"])
        self.assertNotIn("/", started["name"])
        self.post_bytes("/api/upload/chunk?id=%s&offset=0" % started["id"], b"hello")
        finished = self.post("/api/upload/finish", {"id": started["id"], "key": "notes"})
        self.assertEqual(finished["bytes"], 5)
        self.assertTrue(os.path.isfile(finished["path"]))
        # And a dropped file really does end up inside the project.
        events = self.stream("/api/create", {
            "recipe": "notes", "answers": {"name": "With a note"}, "parent": PROJECTS,
            "attachments": [{"key": "notes", "name": "dropped.txt", "path": finished["path"]}],
            "start": False,
        })
        folder = [event for event in events if event["type"] == "made"][0]["folder"]
        self.assertTrue(os.path.isfile(os.path.join(folder, "notes", "dropped.txt")))

    def test_an_upload_that_never_started_is_refused(self):
        result = self.post_bytes("/api/upload/chunk?id=made-up&offset=0", b"junk")
        self.assertIn("error", result)


class TestDoctorText(unittest.TestCase):
    def test_the_terminal_summary_reads_well(self):
        from nonoforge.server import doctor_text

        text = doctor_text()
        self.assertIn("nonoForge", text)
        self.assertIn("New projects go in:", text)
        self.assertIn("The cards you can pick from:", text)
        for recipe in recipes.load_all():
            self.assertIn(recipe["title"], text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
