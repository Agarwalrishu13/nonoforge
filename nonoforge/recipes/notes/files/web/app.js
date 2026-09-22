/* The page. It only ever asks the little program two things: "what is in the
   folder?" and "which passages match this?". All the searching happens in
   Python, next to your files. */

const results = document.getElementById("results");
const questionBox = document.getElementById("question");
const askBtn = document.getElementById("askBtn");

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (character) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character]
  ));
}

/* Wrap the matched words in a highlight. Careful: highlight the escaped text,
   so somebody's "<b>" in a note cannot become a tag on the page. */
function highlight(text, terms) {
  let safe = escapeHtml(text);
  (terms || []).forEach((term) => {
    if (term.length < 3) return;
    const pattern = new RegExp("\\b(" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")\\w*", "gi");
    safe = safe.replace(pattern, "<mark>$&</mark>");
  });
  return safe;
}

function showResults(data) {
  results.textContent = "";
  if (!data.results || !data.results.length) {
    const box = document.createElement("div");
    box.className = "empty";
    box.innerHTML =
      "<h2>Nothing matched that</h2>" +
      "<p class='muted'>No paragraph in your notes shares enough words with “" +
      escapeHtml(data.question) + "”. Try fewer, more ordinary words — the words you would " +
      "expect to be in the answer.</p>";
    results.append(box);
    return;
  }

  const head = document.createElement("div");
  head.className = "result-head muted small";
  head.textContent = data.results.length + (data.results.length === 1 ? " passage" : " passages")
    + " found in " + data.took_ms + " ms, best first:";
  results.append(head);

  data.results.forEach((result) => {
    const card = document.createElement("article");
    card.className = "hit";

    const top = document.createElement("div");
    top.className = "hit-top";
    const file = document.createElement("span");
    file.className = "file";
    file.textContent = result.file;
    const meter = document.createElement("span");
    meter.className = "meter";
    const fill = document.createElement("span");
    fill.style.width = Math.round((result.strength || 0) * 100) + "%";
    meter.append(fill);
    const read = document.createElement("a");
    read.className = "read";
    read.href = "/api/file/" + encodeURIComponent(result.file);
    read.target = "_blank";
    read.rel = "noreferrer";
    read.textContent = "whole file ↗";
    top.append(file, meter, read);

    const body = document.createElement("p");
    body.className = "snippet";
    body.innerHTML = highlight(result.text, result.matched);

    card.append(top, body);
    if (result.matched && result.matched.length) {
      const why = document.createElement("div");
      why.className = "why muted small";
      why.textContent = "matched: " + result.matched.slice(0, 8).join(", ");
      card.append(why);
    }
    results.append(card);
  });
}

async function ask(text) {
  if (!text.trim()) return;
  askBtn.disabled = true;
  askBtn.textContent = "…";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });
    showResults(await response.json());
  } catch (error) {
    results.textContent = "Something went wrong: " + error.message;
  }
  askBtn.disabled = false;
  askBtn.textContent = "Ask";
}

document.getElementById("askForm").addEventListener("submit", (event) => {
  event.preventDefault();
  ask(questionBox.value);
});

async function boot() {
  const stats = await (await fetch("/api/stats")).json();
  document.getElementById("stats").textContent = stats.files.length
    ? stats.files.length + (stats.files.length === 1 ? " file" : " files") + " · "
      + stats.words.toLocaleString() + " words · " + stats.passages + " passages"
    : "no files yet";

  if (!stats.files.length) {
    document.getElementById("noNotes").hidden = false;
    document.getElementById("askForm").hidden = true;
    document.getElementById("examples").hidden = true;
  }

  const list = document.getElementById("fileList");
  stats.files.forEach((item) => {
    const row = document.createElement("li");
    row.innerHTML = "<span>" + escapeHtml(item.name) + "</span><span class='muted'>"
      + item.words.toLocaleString() + " words</span>";
    list.append(row);
  });
  document.getElementById("fileSummary").textContent =
    "Your notes (" + stats.files.length + " files)";

  // Suggest a couple of words actually present in the notes, so the first
  // question anyone asks has a good chance of matching something.
  const examples = document.getElementById("examples");
  const seen = [];
  stats.files.slice(0, 4).forEach((item) => {
    const word = item.name.replace(/\.[a-z0-9]+$/i, "").replace(/[-_]+/g, " ");
    if (word && word.length > 2) seen.push(word);
  });
  seen.slice(0, 3).forEach((word) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = word;
    chip.onclick = () => {
      questionBox.value = word;
      ask(word);
    };
    examples.append(chip);
  });
}

boot();
