/* The form. It asks the little program which questions to show, so changing
   questions.txt changes this page with no code to touch. */

const form = document.getElementById("form");
const box = document.getElementById("questions");
const send = document.getElementById("send");
const note = document.getElementById("note");

let questions = [];

function makeField(question, index) {
  const label = document.createElement("label");
  label.className = "field";
  const span = document.createElement("span");
  span.textContent = question.text;
  const input = document.createElement("input");
  input.type = "text";
  input.name = "q" + index;
  input.dataset.index = index;
  // A question about a phone number gets a phone keyboard on a phone.
  if (/phone|mobile|number|email|mail/i.test(question.text)) {
    input.inputMode = /mail/i.test(question.text) ? "email" : "text";
  }
  label.append(span, input);
  return label;
}

async function boot() {
  const response = await fetch("/api/questions");
  const data = await response.json();
  questions = data.questions || [];
  box.textContent = "";
  questions.forEach((question, index) => box.append(makeField(question, index)));
  note.textContent = data.count
    ? data.count + " " + (data.count === 1 ? "answer" : "answers") + " collected so far."
    : "No answers yet — you will be the first.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  send.disabled = true;
  send.textContent = "Sending…";
  const payload = { name: form.querySelector('[name="name"]').value };
  document.querySelectorAll("#questions input").forEach((input) => {
    payload["q" + input.dataset.index] = input.value;
  });
  try {
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "That did not save.");
    form.hidden = true;
    document.getElementById("thanks").hidden = false;
  } catch (error) {
    note.textContent = error.message;
  }
  send.disabled = false;
  send.textContent = "Send my answers";
});

document.getElementById("again").onclick = () => {
  form.reset();
  document.getElementById("thanks").hidden = true;
  form.hidden = false;
  boot();
};

boot();
