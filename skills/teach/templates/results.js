// WiseCode lesson results: lets what the learner does in a lesson reach the
// learning graph. Copy this file to the workspace's assets/results.js (edit
// the copy, never the plugin template) and load it in every lesson:
//
//   <script src="../assets/results.js"></script>
//   <script>WiseResults.lesson("0007-ownership");</script>
//   <div id="wise-results"></div>     (the Copy and Download buttons go here)
//
// Three kinds of evidence:
//
//   1. A typed answer, judged against key points (the strongest kind):
//        WiseResults.recallWidget(element, {id: "r1", question: "Why …?",
//                                           points: ["…", "…"]});
//      The learner types an answer and picks a confidence, then the key points
//      are revealed and they tick the ones their answer covered.
//
//   2. A multiple-choice answer, from the lesson's own quiz widget:
//        WiseResults.record("q1", questionText, chosenText, isCorrect, correctText,
//                           confidence);        (confidence: "low" | "mid" | "high")
//      Ask for the confidence before showing whether the choice was right.
//
//   3. A question the learner has for Claude, one box per section:
//        WiseResults.stuckWidget(element, {section: "s2", title: "Aliasing"});
//
// "Copy results" puts everything on the clipboard as one line of JSON to paste
// into the chat (`wise.py import-lesson -`). "Download results" saves the same
// JSON as a file for .wise-code/inbox/ (`wise.py import-lesson --inbox`).
// Either way each answer is imported once, however often it is sent.
(function () {
  "use strict";
  var CONFIDENCE = ["low", "mid", "high"];
  var lessonId = "";
  var answers = {};
  var order = [];
  var stuck = [];
  // One page load is one attempt: everything sent from it shares this id, so
  // the importer can tell a repeat from a new try.
  var resultId = "";

  function hex(bytes) {
    var values = new Uint8Array(bytes);
    (window.crypto || window.msCrypto).getRandomValues(values);
    return Array.prototype.map.call(values, function (v) {
      return ("0" + v.toString(16)).slice(-2);
    }).join("");
  }

  function today() {
    var d = new Date();
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function confidenceOf(value) {
    return CONFIDENCE.indexOf(value) >= 0 ? value : null;
  }

  function results() {
    resultId = resultId || "lesson-" + lessonId + "-" + today().replace(/-/g, "") + "-" + hex(4);
    return {
      lesson: lessonId,
      result_id: resultId,
      date: today(),
      answers: order.map(function (id) { return answers[id]; }),
      stuck: stuck.slice()
    };
  }

  function el(tag, text, attrs) {
    var node = document.createElement(tag);
    if (text) node.textContent = text;
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function render(message) {
    var box = document.getElementById("wise-results");
    if (!box) return;
    var total = order.length;
    var asked = stuck.length;
    var count = function (n, word) { return n + " " + word + (n === 1 ? "" : "s"); };
    box.innerHTML = "";
    // No score here: a typed answer is judged from its points when it is
    // imported, and Claude reads it again.
    var parts = [];
    if (total) parts.push(count(total, "answer"));
    if (asked) parts.push(count(asked, "question") + " for Claude");
    var summary = parts.length ? parts.join(", ") + "."
      : "Answer the questions, then send your results to Claude.";
    box.appendChild(el("p", summary + (total || asked
      ? " Copy the results and paste them into your chat with Claude, or download them into your project's .wise-code/inbox/ folder."
      : "")));
    var copyButton = el("button", "Copy results", {type: "button"});
    var downloadButton = el("button", "Download results", {type: "button"});
    copyButton.disabled = downloadButton.disabled = !(total || asked);
    copyButton.addEventListener("click", copy);
    downloadButton.addEventListener("click", download);
    box.appendChild(copyButton);
    box.appendChild(downloadButton);
    if (message) box.appendChild(el("p", message, {class: "wise-note", role: "status"}));
  }

  function download() {
    var data = results();
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = data.result_id + ".json";
    document.body.appendChild(link);
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 0);
  }

  // One line of JSON, so it survives a paste into a chat box unchanged.
  function copy() {
    var text = JSON.stringify(results());
    var done = function () { render("Copied. Paste it into your chat with Claude."); };
    var failed = function () {
      render("Copying was blocked by the browser. Use Download results instead.");
    };
    var clipboard = window.navigator && window.navigator.clipboard;
    if (clipboard && clipboard.writeText) {
      return clipboard.writeText(text).then(done, failed);
    }
    failed();
    return Promise.resolve();
  }

  function store(id, entry) {
    // The first answer counts: the learner's first attempt is the evidence,
    // so later attempts don't overwrite it.
    if (answers[id]) return false;
    answers[id] = entry;
    order.push(id);
    render();
    return true;
  }

  function record(id, question, answer, correct, expected, confidence) {
    var entry = {
      id: String(id), q: String(question), answer: String(answer), correct: !!correct,
      expected: expected == null ? "" : String(expected)
    };
    if (confidenceOf(confidence)) entry.confidence = confidence;
    return store(id, entry);
  }

  // A typed answer and the key points the learner says it covered (numbers
  // from 1). "correct" is only for this page's summary: the importer derives
  // the verdict from the points.
  function recall(id, question, typed, points, hit, confidence) {
    var list = (points || []).map(String);
    var numbers = (hit || []).filter(function (n, i, all) {
      return Number.isInteger(n) && n >= 1 && n <= list.length && all.indexOf(n) === i;
    }).sort(function (a, b) { return a - b; });
    var entry = {
      id: String(id), kind: "recall", q: String(question), answer: String(typed),
      points: list, hit: numbers, correct: list.length > 0 && numbers.length === list.length
    };
    if (confidenceOf(confidence)) entry.confidence = confidence;
    return store(id, entry);
  }

  // A question for Claude. Blank text is ignored; the same text twice is one.
  function askClaude(section, title, text) {
    var clean = String(text == null ? "" : text).replace(/\s+/g, " ").trim().slice(0, 2000);
    if (!clean) return false;
    var same = stuck.some(function (s) { return s.section === String(section) && s.text === clean; });
    if (same) return false;
    stuck.push({section: String(section), title: String(title == null ? "" : title), text: clean});
    render();
    return true;
  }

  function confidencePicker(name) {
    var group = el("fieldset", "", {class: "wise-confidence"});
    group.appendChild(el("legend", "How sure are you?"));
    CONFIDENCE.forEach(function (level) {
      var label = el("label");
      var input = el("input", "", {type: "radio", name: name, value: level});
      label.appendChild(input);
      label.appendChild(document.createTextNode(" " + level));
      group.appendChild(label);
    });
    group.value = function () {
      var picked = group.querySelector("input:checked");
      return picked ? picked.value : null;
    };
    return group;
  }

  // Type first, then see the key points. Nothing is revealed until there is an
  // answer and a confidence, and the answer can't be edited afterwards.
  function recallWidget(container, options) {
    var id = String(options.id), points = (options.points || []).map(String);
    var box = el("div", "", {class: "wise-recall"});
    box.appendChild(el("p", options.question, {class: "wise-question"}));
    var input = el("textarea", "", {rows: "4", "aria-label": "Your answer"});
    var confidence = confidencePicker("wise-confidence-" + id);
    var reveal = el("button", "Show the key points", {type: "button"});
    reveal.disabled = true;
    var after = el("div", "", {class: "wise-reveal"});
    after.hidden = true;
    var ready = function () {
      reveal.disabled = !(input.value.trim().length >= 10 && confidence.value());
    };
    input.addEventListener("input", ready);
    confidence.addEventListener("change", ready);
    reveal.addEventListener("click", function () {
      input.readOnly = true;
      reveal.hidden = true;
      Array.prototype.forEach.call(confidence.querySelectorAll("input"), function (radio) {
        radio.disabled = true;
      });
      after.appendChild(el("p", "Tick each point your answer really made. Be strict: Claude reads your answer too."));
      var boxes = points.map(function (point) {
        var label = el("label", "", {class: "wise-point"});
        var check = el("input", "", {type: "checkbox"});
        label.appendChild(check);
        label.appendChild(document.createTextNode(" " + point));
        after.appendChild(label);
        return check;
      });
      var save = el("button", "Save this answer", {type: "button"});
      save.addEventListener("click", function () {
        var hit = [];
        boxes.forEach(function (check, index) {
          check.disabled = true;
          if (check.checked) hit.push(index + 1);
        });
        recall(id, options.question, input.value.trim(), points, hit, confidence.value());
        save.hidden = true;
        after.appendChild(el("p", hit.length + " of " + points.length + " points. Saved.",
                             {class: "wise-note", role: "status"}));
      });
      after.appendChild(save);
      after.hidden = false;
    });
    box.appendChild(input);
    box.appendChild(confidence);
    box.appendChild(reveal);
    box.appendChild(after);
    container.appendChild(box);
    return box;
  }

  function stuckWidget(container, options) {
    var box = el("details", "", {class: "wise-stuck"});
    box.appendChild(el("summary", "Stuck here? Ask Claude"));
    var input = el("textarea", "", {rows: "2", "aria-label": "Your question for Claude"});
    var send = el("button", "Add to my results", {type: "button"});
    var note = el("p", "", {class: "wise-note", role: "status"});
    send.addEventListener("click", function () {
      if (askClaude(options.section, options.title, input.value)) {
        note.textContent = "Added. It goes to Claude with your results.";
        input.value = "";
      } else {
        note.textContent = "Write your question first.";
      }
    });
    box.appendChild(input);
    box.appendChild(send);
    box.appendChild(note);
    container.appendChild(box);
    return box;
  }

  window.WiseResults = {
    // Name the lesson once per page, e.g. "0007-ownership" (its file name).
    lesson: function (id) { lessonId = String(id); render(); },
    record: record,
    recall: recall,
    stuck: askClaude,
    recallWidget: recallWidget,
    stuckWidget: stuckWidget,
    confidencePicker: confidencePicker,
    copy: copy,
    download: download
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(); });
  } else {
    render();
  }
})();
