/* Two buttons and a slider. The learning and the writing both happen in
   Python, in start.py, next to your text file. */

const sampleBox = document.getElementById("sample");
const output = document.getElementById("output");
const written = document.getElementById("written");
const learnNote = document.getElementById("learnNote");

function showStats(stats) {
  document.getElementById("learned").hidden = !stats.trained;
  document.getElementById("figChars").textContent = stats.characters.toLocaleString();
  document.getElementById("figWords").textContent = stats.words.toLocaleString();
  document.getElementById("figPatterns").textContent = stats.patterns.toLocaleString();

  const table = document.getElementById("pairs");
  table.textContent = "";
  (stats.pairs || []).forEach((pair) => {
    const row = document.createElement("tr");
    const left = document.createElement("td");
    left.innerHTML = "after <code>" + pair.after.replace(/</g, "&lt;") + "</code>";
    const right = document.createElement("td");
    right.innerHTML = "comes <code>" + (pair.comes === " " ? "␣" : pair.comes.replace(/</g, "&lt;")) + "</code>";
    const times = document.createElement("td");
    times.className = "muted";
    times.textContent = pair.times.toLocaleString() + "×";
    row.append(left, right, times);
    table.append(row);
  });

  if (stats.files && stats.files.length) {
    learnNote.textContent = "Learning from " + stats.files.length
      + (stats.files.length === 1 ? " file: " : " files: ") + stats.files.join(", ")
      + " — and anything you paste here.";
  }
}

document.getElementById("learnBtn").onclick = async () => {
  const button = document.getElementById("learnBtn");
  button.disabled = true;
  button.textContent = "Learning…";
  try {
    const response = await fetch("/api/learn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sampleBox.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "That did not work.");
    showStats(result);
    learnNote.textContent = "Learned in " + result.trained_ms + " ms. Now press "
      + "“Write something” and see what comes out.";
    document.getElementById("teachCard").classList.add("done");
  } catch (error) {
    learnNote.textContent = error.message;
  }
  button.disabled = false;
  button.textContent = "Learn from this";
};

document.getElementById("forgetBtn").onclick = async () => {
  const stats = await (await fetch("/api/forget", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
  sampleBox.value = "";
  showStats(stats);
  learnNote.textContent = "Forgotten. Files in the samples folder are still there.";
  document.getElementById("teachCard").classList.remove("done");
};

document.getElementById("writeBtn").onclick = async () => {
  const button = document.getElementById("writeBtn");
  button.disabled = true;
  button.textContent = "Writing…";
  try {
    const response = await fetch("/api/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: document.getElementById("prompt").value,
        how_much: document.getElementById("howMuch").value,
        creativity: Number(document.getElementById("creativity").value),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "That did not work.");
    output.hidden = false;
    written.textContent = result.text;
    document.getElementById("writeNote").textContent =
      result.text.length + " characters in " + result.took_ms + " ms · creativity " + result.creativity;
  } catch (error) {
    output.hidden = false;
    written.textContent = error.message;
    document.getElementById("writeNote").textContent = "";
  }
  button.disabled = false;
  button.textContent = "Write something";
};

document.getElementById("copyBtn").onclick = async () => {
  try {
    await navigator.clipboard.writeText(written.textContent);
    document.getElementById("copyBtn").textContent = "Copied ✓";
    setTimeout(() => { document.getElementById("copyBtn").textContent = "Copy"; }, 1500);
  } catch (error) {
    document.getElementById("copyBtn").textContent = "Select it and press Ctrl+C";
  }
};

const creativity = document.getElementById("creativity");
creativity.oninput = () => {
  const notes = ["safe and repetitive", "steady", "steadier than your writing", "about like you", "wilder", "wild"];
  document.getElementById("creativityNote").textContent =
    creativity.value <= 0.5 ? notes[0] + " ←→ wild"
      : creativity.value <= 1.0 ? "more careful ←→ wild"
        : "wild side";
};

(async function boot() {
  const stats = await (await fetch("/api/stats")).json();
  showStats(stats);
  if (!stats.trained) {
    learnNote.textContent = "Paste some writing and press the button. Nothing is uploaded — "
      + "this all happens on your computer.";
  }
})();
