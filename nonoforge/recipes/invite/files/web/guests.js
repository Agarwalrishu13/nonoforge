/* The host's list: every reply, newest first. */

async function load() {
  const [list, invite] = await Promise.all([
    (await fetch("/api/guests")).json(),
    (await fetch("/api/invite")).json(),
  ]);

  document.getElementById("summary").textContent = invite.replies
    ? invite.replies + (invite.replies === 1 ? " reply" : " replies") + " so far."
    : "No replies yet.";

  const figures = document.getElementById("figures");
  figures.textContent = "";
  [["Coming", invite.yes + " replies"], ["People in total", invite.people],
   ["Not sure yet", invite.maybe], ["Cannot make it", invite.no]]
    .forEach(([label, value]) => {
      const box = document.createElement("div");
      box.className = "figure";
      box.innerHTML = "<b>" + value + "</b><span class='muted'>" + label + "</span>";
      figures.append(box);
    });

  const rows = list.rows || [];
  const body = document.getElementById("rows");
  body.textContent = "";
  document.getElementById("empty").hidden = rows.length > 0;

  rows.forEach((row) => {
    const line = document.createElement("tr");
    const coming = String(row.coming || "").toLowerCase();
    line.className = coming.startsWith("y") ? "yes" : (coming.startsWith("n") ? "no" : "maybe");
    [row.when, row.name, row.coming, row.how_many, row.note].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value || "";
      line.append(cell);
    });
    body.append(line);
  });
}

load();
