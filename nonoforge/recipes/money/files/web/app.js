/* Where my money goes — the page. All the adding up happens in start.py.
   This file only draws what it is given and posts new entries back. */

const $ = (id) => document.getElementById(id);
let currency = "£";

function money(value) {
  const sign = value < 0 ? "−" : "";
  return sign + currency + Math.abs(value).toFixed(2);
}

function render(data) {
  currency = data.currency || currency;
  $("subtitle").textContent = data.count
    ? data.count + (data.count === 1 ? " thing" : " things") + " written down, added up for you."
    : "Write down what you spend, and the adding up looks after itself.";

  $("monthLabel").textContent = data.month_name;
  $("thisMonth").textContent = money(data.this_month);
  $("total").textContent = money(data.total);
  $("count").textContent = data.count;

  // The group buttons.
  const select = $("category");
  const chosen = select.value;
  select.textContent = "";
  (data.categories_offered || []).forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.append(option);
  });
  if (chosen) select.value = chosen;

  // Bars: how much of your spending each group is.
  const bars = $("bars");
  bars.textContent = "";
  $("groupsCard").hidden = !(data.categories || []).length;
  (data.categories || []).forEach((group) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const name = document.createElement("span");
    name.className = "bar-name";
    name.textContent = group.name;
    const track = document.createElement("span");
    track.className = "track";
    const fill = document.createElement("span");
    fill.style.width = Math.max(2, Math.round((group.share || 0) * 100)) + "%";
    track.append(fill);
    const total = document.createElement("span");
    total.className = "bar-total";
    total.textContent = money(group.total);
    row.append(name, track, total);
    bars.append(row);
  });

  // Recent entries.
  const body = $("rows");
  body.textContent = "";
  const recent = data.recent || [];
  $("recentCard").hidden = !recent.length;
  $("emptyCard").hidden = recent.length > 0;

  recent.forEach((entry) => {
    const row = document.createElement("tr");
    const when = document.createElement("td");
    when.textContent = entry.when || "";
    const what = document.createElement("td");
    what.textContent = entry.what || "";
    const group = document.createElement("td");
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = entry.category || "Other";
    group.append(pill);
    const amount = document.createElement("td");
    amount.className = "right" + (entry.value < 0 ? " incoming" : "");
    amount.textContent = money(entry.value || 0);
    const kill = document.createElement("td");
    const button = document.createElement("button");
    button.className = "x";
    button.textContent = "✕";
    button.title = "Remove this row";
    button.onclick = async () => {
      button.disabled = true;
      await fetch("/api/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: entry.id, what: entry.what, when: entry.when }),
      });
      load();
    };
    kill.append(button);
    row.append(when, what, group, amount, kill);
    body.append(row);
  });

  // Month by month.
  const months = $("months");
  months.textContent = "";
  $("monthsCard").hidden = (data.months || []).length < 2;
  (data.months || []).forEach((item) => {
    const line = document.createElement("div");
    line.className = "month-row";
    const label = document.createElement("span");
    label.textContent = item.month;
    const total = document.createElement("b");
    total.textContent = money(item.total);
    line.append(label, total);
    months.append(line);
  });
}

async function load() {
  try {
    render(await (await fetch("/api/summary")).json());
  } catch (error) {
    $("subtitle").textContent = "I could not read the file: " + error.message;
  }
}

$("addForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("addBtn");
  button.disabled = true;
  const note = $("addNote");
  try {
    const response = await fetch("/api/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        what: $("what").value,
        amount: $("amount").value,
        category: $("category").value,
        when: $("when").value,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "That did not save.");
    note.textContent = "Added " + result.added + ".";
    $("what").value = "";
    $("amount").value = "";
    $("what").focus();
    load();
  } catch (error) {
    note.textContent = error.message;
  }
  button.disabled = false;
});

// Today's date in the form, in the local timezone rather than UTC.
(function () {
  const now = new Date();
  const pad = (number) => String(number).padStart(2, "0");
  $("when").value = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
})();

load();
