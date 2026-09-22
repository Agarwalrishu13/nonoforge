/* The page that lists every answer, newest first. */

async function load() {
  const response = await fetch("/api/responses");
  const data = await response.json();
  const rows = (data.rows || []).slice().reverse(); // newest first

  document.getElementById("count").textContent = rows.length
    ? rows.length + (rows.length === 1 ? " answer" : " answers") + ", newest first."
    : "No answers yet.";

  const table = document.getElementById("table");
  const empty = document.getElementById("empty");
  const head = document.getElementById("head");
  const body = document.getElementById("body");
  head.textContent = "";
  body.textContent = "";

  if (!rows.length) {
    table.hidden = true;
    empty.hidden = false;
    return;
  }
  table.hidden = false;
  empty.hidden = true;

  const columns = data.columns && data.columns.length ? data.columns : Object.keys(rows[0]);
  columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.textContent = column;
    head.append(cell);
  });
  rows.forEach((row) => {
    const line = document.createElement("tr");
    columns.forEach((column) => {
      const cell = document.createElement("td");
      cell.textContent = row[column] || "";
      line.append(cell);
    });
    body.append(line);
  });
}

document.getElementById("refresh").onclick = load;
load();
// Keep it fresh if somebody is filling the form in another tab.
setInterval(load, 5000);
