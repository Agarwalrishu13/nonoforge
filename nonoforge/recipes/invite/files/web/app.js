/* The countdown runs in the browser, the replies are saved by start.py. */

const $ = (id) => document.getElementById(id);
let whenIso = "";

function pad(number) {
  return String(number).padStart(2, "0");
}

function tick() {
  if (!whenIso) return;
  const target = new Date(whenIso);
  let seconds = Math.floor((target - new Date()) / 1000);
  const box = $("countdown");
  if (seconds <= 0) {
    box.innerHTML = "<div class='passed'>It has happened! Hope it was lovely.</div>";
    return;
  }
  const days = Math.floor(seconds / 86400);
  seconds -= days * 86400;
  const hours = Math.floor(seconds / 3600);
  seconds -= hours * 3600;
  const minutes = Math.floor(seconds / 60);
  seconds -= minutes * 60;
  $("cdDays").textContent = days;
  $("cdHours").textContent = pad(hours);
  $("cdMins").textContent = pad(minutes);
  $("cdSecs").textContent = pad(seconds);
}

async function boot() {
  const data = await (await fetch("/api/invite")).json();
  whenIso = data.when_iso;
  if (data.headline) $("headline").textContent = data.headline;
  if (data.message) $("message").textContent = data.message;
  if (data.where) $("where").textContent = data.where;
  $("when").textContent = data.when_text;
  document.title = data.title;
  tick();
  setInterval(tick, 1000);
}

$("rsvpForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("sendBtn");
  button.disabled = true;
  const note = $("rsvpNote");
  try {
    const response = await fetch("/api/rsvp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("name").value,
        coming: (document.querySelector('input[name="coming"]:checked') || {}).value || "Yes",
        how_many: $("howMany").value,
        note: $("note").value,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "That did not save.");
    $("rsvpForm").hidden = true;
    $("thanks").hidden = false;
    $("thanksTitle").textContent = result.coming === "No"
      ? "Thank you for letting us know"
      : "Thank you — you are on the list";
    $("thanksText").textContent = "We have saved your reply. You can close this page whenever you like.";
  } catch (error) {
    note.textContent = error.message;
  }
  button.disabled = false;
});

$("changeBtn").onclick = () => {
  $("thanks").hidden = true;
  $("rsvpForm").hidden = false;
  $("rsvpNote").textContent = "Sending again replaces nothing — it adds a new reply, so tell the host which is right.";
};

boot();
