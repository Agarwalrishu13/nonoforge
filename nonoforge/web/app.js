/* nonoForge — the page. Plain JavaScript, no framework, no build step.
   Everything here is written to be read by whoever wants to change it. */

const $ = (id) => document.getElementById(id);

const state = {
  recipes: [],
  chosen: null,        // the recipe (card) currently on the table
  attachments: [],     // files the person dropped in: {key, name, path, bytes}
  settings: {},
  parent: "",
  busy: false,
  lastProject: null,
  lastUrl: "",
};

/* ------------------------------------------------------------------ helpers */
async function api(path, payload) {
  const options = payload === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload || {}) };
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function toast(message, kind) {
  const box = document.createElement("div");
  box.className = "toast" + (kind ? " " + kind : "");
  const close = document.createElement("button");
  close.className = "x";
  close.textContent = "✕";
  close.onclick = () => box.remove();
  box.append(close, document.createTextNode(message));
  $("toasts").append(box);
  setTimeout(() => box.remove(), kind === "bad" ? 11000 : 7000);
}

function line(parent, className, text) {
  const element = document.createElement("div");
  if (className) element.className = className;
  if (text) element.textContent = text;
  parent.append(element);
  return element;
}

function humanSize(bytes) {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

/* -------------------------------------------------------------------- start */
async function boot() {
  try {
    const [recipes, settings, projects] = await Promise.all([
      api("/api/recipes"), api("/api/settings"), api("/api/projects"),
    ]);
    state.recipes = recipes.recipes || [];
    state.settings = settings.settings || {};
    state.parent = settings.parent || "";
    renderCards();
    $("parentInput").value = state.settings.parent || "";
    $("parentHint").textContent = state.settings.parent
      ? "Leave it as it is to keep them together."
      : "Leave it empty and new apps go to " + state.parent;
    $("gitInput").checked = !!state.settings.git;
    $("startInput").checked = state.settings.start_when_done !== false;
    $("openInput").checked = !!state.settings.open_when_done;
    renderProjects(projects);
  } catch (error) {
    toast("I could not start properly: " + error.message, "bad");
  }
}

/* -------------------------------------------------------------------- cards */
function renderCards() {
  const grid = $("cards");
  grid.textContent = "";
  state.recipes.forEach((recipe) => {
    const card = document.createElement("button");
    card.className = "card";
    card.type = "button";
    card.draggable = true;
    card.dataset.id = recipe.id;

    const top = line(card, "card-top");
    line(top, "card-emoji", recipe.emoji);
    line(top, "card-title", recipe.title);
    line(card, "card-blurb", recipe.blurb);
    if (recipe.best_for) line(card, "card-best", "Good for: " + recipe.best_for);

    card.onclick = () => chooseCard(recipe.id);
    card.addEventListener("dragstart", (event) => {
      card.classList.add("dragging");
      event.dataTransfer.setData("text/nonoforge-card", recipe.id);
      event.dataTransfer.effectAllowed = "copy";
    });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
    grid.append(card);
  });
}

function findRecipe(id) {
  return state.recipes.find((item) => item.id === id) || null;
}

/* ------------------------------------------------------------- the questions */
function chooseCard(id) {
  const recipe = findRecipe(id);
  if (!recipe) return;
  state.chosen = recipe;
  state.attachments = [];

  document.querySelectorAll(".card").forEach((card) => {
    card.classList.toggle("chosen", card.dataset.id === id);
  });

  $("forge").hidden = false;
  $("donePanel").hidden = true;
  $("progressPanel").hidden = true;
  $("dropEmpty").hidden = true;
  $("dropFilled").hidden = false;
  $("questionsPanel").hidden = false;
  $("chosenEmoji").textContent = recipe.emoji;
  $("chosenTitle").textContent = recipe.title;
  $("chosenBlurb").textContent = recipe.blurb;
  $("forgeTitle").textContent = "Making: " + recipe.title;

  renderQuestions(recipe);
  renderPreview();
  $("forge").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderQuestions(recipe) {
  const form = $("questions");
  form.textContent = "";
  if (!recipe.asks.length) {
    line(form, "muted", "Nothing to fill in — this one just makes itself. Press the button.");
    return;
  }
  recipe.asks.forEach((ask) => {
    const field = document.createElement("label");
    field.className = "field";
    const label = document.createElement("span");
    label.textContent = ask.label + (ask.required ? "" : "");
    field.append(label);

    let input;
    if (ask.type === "textarea" || ask.type === "lines") {
      input = document.createElement("textarea");
      input.rows = ask.type === "lines" ? 5 : 4;
      input.value = ask.default || "";
      if (ask.type === "lines" && !ask.help) {
        line(field, "hint", "One per line. Blank lines are ignored.");
      }
    } else if (ask.type === "color") {
      const row = line(field, "color-row");
      input = document.createElement("input");
      input.type = "color";
      input.value = ask.default || "#f0883e";
      row.append(input);
      line(row, "muted small", "Pick any colour you like.");
      input.oninput = renderPreview;
      input.onchange = renderPreview;
      if (ask.help) line(field, "hint", ask.help);
      form.append(field);
      return;
    } else if (ask.type === "choice") {
      input = document.createElement("select");
      (ask.options || []).forEach((option) => {
        const item = document.createElement("option");
        item.value = option;
        item.textContent = option;
        input.append(item);
      });
      input.value = ask.default || (ask.options || [])[0] || "";
    } else if (ask.type === "files") {
      input = makeFileDrop(ask, field);
      form.append(field);
      return;
    } else {
      input = document.createElement("input");
      input.type = ask.type === "number" ? "number" : (ask.type === "date" ? "date" : (ask.type === "time" ? "time" : "text"));
      if (ask.type === "date") input.type = "date";
      input.value = ask.default ?? "";
      if (ask.placeholder) input.placeholder = ask.placeholder;
    }
    input.dataset.key = ask.key;
    input.dataset.type = ask.type;
    field.append(input);
    if (ask.help && ask.type !== "color") line(field, "hint", ask.help);
    form.append(field);
  });
}

function makeFileDrop(ask, field) {
  const drop = document.createElement("div");
  drop.className = "file-drop";
  drop.dataset.key = ask.key;
  drop.textContent = "Drop files here, or click to choose them";
  const picker = document.createElement("input");
  picker.type = "file";
  picker.multiple = true;
  picker.hidden = true;
  if (ask.accept) picker.accept = ask.accept;
  const list = document.createElement("div");
  list.className = "dropped-list";
  list.dataset.list = ask.key;

  drop.onclick = () => picker.click();
  picker.onchange = () => {
    addFiles(ask.key, picker.files);
    picker.value = "";
  };
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    drop.classList.remove("over");
    addFiles(ask.key, event.dataTransfer.files);
  });

  field.append(drop, picker, list);
  return drop;
}

function filesAsk() {
  if (!state.chosen) return null;
  return state.chosen.asks.find((ask) => ask.type === "files") || null;
}

async function addFiles(key, fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const list = document.querySelector('.dropped-list[data-list="' + key + '"]');
  for (const file of files) {
    const row = line(list, "dropped");
    line(row, "name", file.name);
    const bar = line(row, "bar");
    const fill = document.createElement("span");
    bar.append(fill);
    const remove = document.createElement("button");
    remove.className = "x";
    remove.textContent = "✕";
    remove.type = "button";
    row.append(remove);

    try {
      const started = await api("/api/upload/start", { name: file.name });
      const slice = 1024 * 1024; // a megabyte at a time: big photos do not choke the page
      let offset = 0;
      do {
        const chunk = await file.slice(offset, offset + slice).arrayBuffer();
        const response = await fetch(
          "/api/upload/chunk?id=" + encodeURIComponent(started.id) + "&offset=" + offset,
          { method: "POST", body: chunk, headers: { "Content-Type": "application/octet-stream" } }
        );
        if (!response.ok) throw new Error("that file did not arrive");
        offset += chunk.byteLength || 1;
        fill.style.width = Math.min(100, Math.round((offset / Math.max(1, file.size)) * 100)) + "%";
      } while (offset < file.size);

      const done = await api("/api/upload/finish", { id: started.id, key: key });
      fill.style.width = "100%";
      const attachment = { key: key, name: done.name, path: done.path, bytes: done.bytes };
      state.attachments.push(attachment);
      remove.onclick = () => {
        state.attachments = state.attachments.filter((item) => item !== attachment);
        row.remove();
        renderPreview();
      };
      renderPreview();
    } catch (error) {
      row.remove();
      toast("“" + file.name + "” could not be added: " + error.message, "bad");
    }
  }
}

function answers() {
  const values = {};
  document.querySelectorAll("#questions [data-key]").forEach((input) => {
    const key = input.dataset.key;
    if (!key) return;
    values[key] = input.value;
  });
  return values;
}

/* ------------------------------------------------------------------ preview */
let previewTimer = null;
function renderPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    if (!state.chosen) return;
    try {
      const plan = await api("/api/plan", {
        recipe: state.chosen.id,
        answers: answers(),
        parent: $("parentInput").value.trim(),
      });
      const box = $("preview");
      box.textContent = "";
      const add = (label, value) => {
        const row = line(box, "preview-line");
        const strong = document.createElement("b");
        strong.textContent = label;
        row.append(strong, document.createTextNode(" " + value));
      };
      add("It will be called:", plan.folder_name);
      add("It will live in:", plan.parent);
      if (state.attachments.length) {
        add("Your files:", state.attachments.map((item) => item.name).join(", "));
      }
      line(box, "muted small", (plan.runs ? "It comes with a start button. " : "It opens in your browser. ")
        + plan.file_count + " files are written for you:");
      const chips = line(box, "file-chips");
      (plan.what_you_get || []).forEach((name) => line(chips, "chip", name));
      if ((plan.what_you_get || []).length < plan.file_count) {
        line(chips, "chip", "+" + (plan.file_count - plan.what_you_get.length) + " more");
      }
    } catch (error) {
      /* the preview is a nicety; a failure here must not interrupt anybody */
    }
  }, 220);
}

/* --------------------------------------------------------------- make it ✨ */
async function makeIt() {
  if (!state.chosen || state.busy) return;
  state.busy = true;
  $("makeBtn").disabled = true;
  $("donePanel").hidden = true;
  $("progressPanel").hidden = false;
  $("progressTitle").textContent = "Making “" + state.chosen.title + "”…";
  const steps = $("steps");
  steps.textContent = "";
  let last = null;
  let finished = false;

  const addStep = (text) => {
    if (last) {
      last.className = "ok";
      last.firstChild.textContent = "✓";
    }
    const item = document.createElement("li");
    item.className = "now";
    const mark = line(item, "mark");
    mark.textContent = "•";
    line(item, "", text);
    steps.append(item);
    last = item;
    $("progressPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  try {
    await stream("/api/create", {
      recipe: state.chosen.id,
      answers: answers(),
      parent: $("parentInput").value.trim(),
      attachments: state.attachments,
      git: $("gitInput").checked,
      start: $("startInput").checked,
      open_folder: $("openInput").checked,
    }, (event) => {
      if (event.type === "step") {
        addStep(event.text);
      } else if (event.type === "made") {
        state.lastProject = event.project;
        onMade(event);
      } else if (event.type === "running") {
        state.lastUrl = event.url;
        $("openInBrowser").hidden = false;
        addStep("It is running — opening it for you.");
        toast("“" + (state.lastProject ? state.lastProject.name : "your app") + "” is running. 🎉", "good");
      } else if (event.type === "note") {
        addStep(event.text);
        toast(event.text + " You can still open it from the folder.", "");
      } else if (event.type === "error") {
        toast(event.message, "bad");
        addStep("Something went wrong: " + event.message);
      } else if (event.type === "done") {
        finished = true;
      }
    });
  } catch (error) {
    toast(error.message, "bad");
  }

  if (!finished && !state.lastProject) {
    toast("That did not finish. Nothing was left half-made in your folder.", "bad");
  }
  if (last) {
    last.className = "ok";
    last.firstChild.textContent = "✓";
  }
  $("makeBtn").disabled = false;
  state.busy = false;
  loadProjects();
}

function onMade(event) {
  const project = event.project;
  $("donePanel").hidden = false;
  $("doneTitle").textContent = "“" + project.name + "” is ready.";
  const parts = [humanSize(event.bytes) + " of files", "in " + event.folder];
  if (event.renamed) parts.unshift("I added a number to the name because one was already there");
  $("doneSub").textContent = parts.join(" — ");
  $("openInBrowser").hidden = !state.lastUrl;

  const next = $("whatsNext");
  next.textContent = "";
  line(next, "", "What now?");
  const list = document.createElement("div");
  list.innerHTML =
    "<div>1. To use it later, open the folder and double-click <code>run.bat</code> (Windows) " +
    "or <code>run.sh</code> (macOS / Linux).</div>" +
    "<div>2. <code>START-HERE.txt</code> inside the folder explains every file in plain words.</div>" +
    "<div>3. Nothing was installed and nothing was uploaded. Deleting the folder removes the app completely.</div>";
  next.append(list);
  $("donePanel").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ------------------------------------------------------------------ streams */
async function stream(path, payload, onEvent) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let message = "Something went wrong.";
    try { message = (await response.json()).error || message; } catch (error) { /* keep the default */ }
    throw new Error(message);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split;
    while ((split = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const text of block.split("\n")) {
        if (!text.startsWith("data:")) continue;
        const data = text.slice(5).trim();
        if (data === "[DONE]") return;
        try { onEvent(JSON.parse(data)); } catch (error) { /* ignore a broken line */ }
      }
    }
  }
}

/* ---------------------------------------------------------------- the wish */
async function askForIt() {
  const text = $("wish").value.trim();
  if (!text) {
    $("wish").focus();
    return;
  }
  $("wishBtn").disabled = true;
  try {
    const result = await api("/api/pick", { text: text });
    if (!result.recipe) {
      toast("I could not tell what you meant by that — pick a card below and I will take it from there.", "");
      $("cards").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    chooseCard(result.recipe.id);
    const name = result.recipe.emoji + " " + result.recipe.title;
    if (result.confident) {
      toast("Sounds like: " + name + " (" + result.why + "). Not it? Pick another card.", "good");
    } else {
      const others = (result.runners_up || []).map((item) => item.title).join(", ");
      toast("Best guess: " + name + " — " + result.why + "."
        + (others ? " If that is wrong, try: " + others + "." : ""), "");
    }
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    $("wishBtn").disabled = false;
  }
}

/* -------------------------------------------------------------- my projects */
async function loadProjects() {
  try {
    renderProjects(await api("/api/projects"));
  } catch (error) { /* the list is a nicety */ }
}

function renderProjects(data) {
  const box = $("projectsList");
  box.textContent = "";
  const live = {};
  (data.running || []).forEach((item) => { live[item.path] = item.url; });
  const projects = data.projects || [];
  $("projectsWhere").textContent = projects.length
    ? "They live in " + (data.parent || "")
    : "Nothing yet — everything you make will be listed here.";

  if (!projects.length) {
    line(box, "muted", "You have not made anything yet. Pick a card and press one button.");
    return;
  }
  projects.forEach((project) => {
    const row = line(box, "project-row");
    line(row, "emoji", project.emoji || "🧰");
    const meta = line(row, "meta");
    line(meta, "name", project.name);
    line(meta, "path", project.path);
    const pills = line(meta, "");
    if (live[project.path]) {
      const pill = line(pills, "pill live");
      pill.textContent = "running now";
    }
    const acts = line(row, "acts");

    if (live[project.path]) {
      const openLink = document.createElement("a");
      openLink.className = "btn small";
      openLink.href = live[project.path];
      openLink.target = "_blank";
      openLink.rel = "noreferrer";
      openLink.textContent = "Open";
      acts.append(openLink);
      const stop = document.createElement("button");
      stop.className = "btn small";
      stop.textContent = "Stop";
      stop.onclick = async () => {
        await api("/api/stop", { path: project.path });
        toast("Stopped “" + project.name + "”.", "");
        loadProjects();
      };
      acts.append(stop);
    } else if (project.runs !== false) {
      const start = document.createElement("button");
      start.className = "btn small primary";
      start.textContent = "Start it";
      start.onclick = async () => {
        start.disabled = true;
        try {
          const result = await api("/api/start", { path: project.path, open: true });
          if (result.url) toast("Started. It is at " + result.url, "good");
          else if (result.error) toast(result.error, "bad");
        } catch (error) {
          toast(error.message, "bad");
        }
        start.disabled = false;
        loadProjects();
      };
      acts.append(start);
    }

    const folder = document.createElement("button");
    folder.className = "btn small ghost";
    folder.textContent = "Folder";
    folder.onclick = () => api("/api/open", { path: project.path }).catch((error) => toast(error.message, "bad"));
    acts.append(folder);

    const forget = document.createElement("button");
    forget.className = "btn small ghost";
    forget.textContent = "Forget";
    forget.title = "Remove from this list. The folder itself is not touched.";
    forget.onclick = async () => {
      const result = await api("/api/forget", { path: project.path });
      toast("Removed from the list. The folder is still there.", "");
      renderProjects({ projects: result.projects, running: data.running || [], parent: data.parent });
    };
    acts.append(forget);
  });
}

/* --------------------------------------------------------------- drag & drop */
function wireDropping() {
  const table = $("dropTable");
  ["dragenter", "dragover"].forEach((name) => {
    table.addEventListener(name, (event) => {
      event.preventDefault();
      table.classList.add("over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    table.addEventListener(name, () => table.classList.remove("over"));
  });
  table.addEventListener("drop", (event) => {
    event.preventDefault();
    const cardId = event.dataTransfer.getData("text/nonoforge-card");
    if (cardId) {
      chooseCard(cardId);
      return;
    }
    const ask = filesAsk();
    if (ask && event.dataTransfer.files.length) {
      addFiles(ask.key, event.dataTransfer.files);
    }
  });

  // Files dropped anywhere on the page: send them to the card that is chosen.
  let depth = 0;
  window.addEventListener("dragenter", (event) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    depth += 1;
    $("dropveil").classList.add("on");
  });
  window.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) $("dropveil").classList.remove("on");
  });
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    depth = 0;
    $("dropveil").classList.remove("on");
    if (!event.dataTransfer.files.length) return;
    const ask = filesAsk();
    if (ask) {
      addFiles(ask.key, event.dataTransfer.files);
    } else {
      toast("Pick a card first and I will know where to put those files.", "");
    }
  });
}

/* ------------------------------------------------------------------ buttons */
function wireButtons() {
  $("wishBtn").onclick = askForIt;
  $("wish").addEventListener("keydown", (event) => {
    if (event.key === "Enter") askForIt();
  });
  $("makeBtn").onclick = makeIt;
  $("clearBtn").onclick = () => {
    state.chosen = null;
    state.attachments = [];
    state.lastUrl = "";
    $("forge").hidden = true;
    toast("Cleared. Pick another card whenever you like.", "");
  };
  $("againBtn").onclick = () => {
    $("donePanel").hidden = true;
    $("progressPanel").hidden = true;
    state.lastProject = null;
    $("cards").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("openFolder").onclick = async () => {
    if (!state.lastProject) return;
    try {
      await api("/api/open", { path: state.lastProject.path });
    } catch (error) {
      toast(error.message, "bad");
    }
  };
  $("openInBrowser").onclick = () => {
    if (state.lastUrl) window.open(state.lastUrl, "_blank");
  };
  $("projectsBtn").onclick = () => {
    $("projectsModal").hidden = false;
    loadProjects();
  };
  $("helpBtn").onclick = () => { $("helpModal").hidden = false; };
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.onclick = () => {
      $("projectsModal").hidden = true;
      $("helpModal").hidden = true;
    };
  });
  ["parentInput", "gitInput", "startInput", "openInput"].forEach((id) => {
    const element = $(id);
    element.addEventListener("change", () => {
      if (id === "parentInput") {
        renderPreview();
        return;
      }
      api("/api/settings", {
        parent: $("parentInput").value.trim(),
        git: $("gitInput").checked,
        start_when_done: $("startInput").checked,
        open_when_done: $("openInput").checked,
      }).catch(() => { /* remembering the choice is not worth an error message */ });
    });
    if (id === "parentInput") {
      element.addEventListener("input", renderPreview);
      element.addEventListener("blur", () => {
        api("/api/settings", { parent: $("parentInput").value.trim() }).catch(() => {});
      });
    }
  });
  document.addEventListener("click", (event) => {
    if (event.target.classList.contains("backdrop")) event.target.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      $("projectsModal").hidden = true;
      $("helpModal").hidden = true;
    }
  });
}

wireDropping();
wireButtons();
boot();
