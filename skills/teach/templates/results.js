// WiseCode lesson results: lets in-browser quiz answers reach the learning graph.
// Copy this file to the workspace's assets/results.js (edit the copy, never the
// plugin template) and load it in every lesson with a quiz:
//
//   <script src="../assets/results.js"></script>
//   <script>WiseResults.lesson("0007-ownership");</script>
//   ... on each answer: WiseResults.record("q1", questionText, chosenText, isCorrect, correctText);
//   <div id="wise-results"></div>   (the "Download results" button goes here)
//
// The download is a .json file that `wise.py import-lesson <file>` turns into
// Q/A history; wrong answers enter the question bank. Saving it into
// .wise-code/inbox/ makes the next session import it automatically.
(function () {
  "use strict";
  var lessonId = "";
  var answers = {};
  var order = [];

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

  function render() {
    var box = document.getElementById("wise-results");
    if (!box) return;
    var total = order.length;
    var right = order.filter(function (id) { return answers[id].correct; }).length;
    box.innerHTML = "";
    var note = document.createElement("p");
    note.textContent = total
      ? right + " of " + total + " correct. Download the results and save them in your project's .wise-code/inbox/ folder, or tell Claude where the file is."
      : "Answer the questions, then download your results for Claude.";
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = "Download results";
    button.disabled = !total;
    button.addEventListener("click", download);
    box.appendChild(note);
    box.appendChild(button);
  }

  function download() {
    var stamp = today().replace(/-/g, "");
    var resultId = "lesson-" + lessonId + "-" + stamp + "-" + hex(2);
    var data = {
      lesson: lessonId,
      result_id: resultId,
      date: today(),
      answers: order.map(function (id) { return answers[id]; })
    };
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = resultId + ".json";
    document.body.appendChild(link);
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 0);
  }

  window.WiseResults = {
    // Name the lesson once per page, e.g. "0007-ownership" (its file name).
    lesson: function (id) { lessonId = String(id); render(); },
    // Record or replace one answer. The first answer counts: the learner's
    // first attempt is the evidence, so later attempts don't overwrite it.
    record: function (id, question, answer, correct, expected) {
      if (answers[id]) return;
      answers[id] = {
        q: String(question), answer: String(answer), correct: !!correct,
        expected: expected == null ? "" : String(expected)
      };
      order.push(id);
      render();
    },
    download: download
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
