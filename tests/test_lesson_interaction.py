"""Lessons that take typed answers, confidence and questions, and get them to
the graph: the importer's rules, then the real page script through to it."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402

POINTS = ["two mutable borrows could alias the same data",
          "a write through one would invalidate the other"]


def recall(answer_id="r1", hit=(1,), confidence="mid", text="they could both point at the vec",
           **extra):
    return dict({"id": answer_id, "kind": "recall", "q": "Why only one &mut?",
                 "answer": text, "points": POINTS, "hit": list(hit),
                 "confidence": confidence, "correct": len(hit) == len(POINTS)}, **extra)


def choice(answer_id="c1", correct=False, **extra):
    return dict({"id": answer_id, "q": "Which borrows may coexist?", "answer": "Two &mut",
                 "correct": correct, "expected": "Many & or one &mut"}, **extra)


class LessonCase(WiseTestCase):
    def payload(self, *answers, stuck=(), result_id="lesson-0007-1"):
        return {"lesson": "0007-borrowing", "result_id": result_id, "date": "2026-10-28",
                "answers": list(answers), "stuck": list(stuck)}

    def load(self, payload, check=True):
        path = Path(tempfile.mkdtemp(dir=self.temp.name)) / "r.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return self.run_wise("import-lesson", str(path), check=check)

    def of_type(self, kind):
        return [n for n in self.nodes() if n["type"] == kind]


class RecallImportTests(LessonCase):
    def test_the_verdict_comes_from_the_points_ticked_not_from_the_page(self):
        cases = (((1, 2), "correct"), ((2,), "partial"), ((), "wrong"))
        for number, (hit, verdict) in enumerate(cases):
            with self.subTest(hit=hit):
                # The page claims every one of them was correct.
                self.load(self.payload(recall(f"r{number}", hit=hit, correct=True),
                                       result_id=f"res-{number}"))
                [qa] = [n for n in self.of_type("qa") if n.get("answer_id") == f"r{number}"]
                self.assertEqual(qa["verdict"], verdict)
                self.assertEqual(qa["graded"], "self")

    def test_it_keeps_the_typed_text_the_missed_points_and_the_confidence(self):
        out = self.load(self.payload(recall(confidence="high"))).stdout
        [qa] = self.of_type("qa")
        self.assertEqual(qa["a"], "they could both point at the vec")
        self.assertEqual(qa["missed"], [POINTS[1]])
        self.assertEqual(qa["confidence"], "high")
        self.assertNotIn("said", qa)  # typed in a browser: no transcript can confirm it
        self.assertIn(f"review: {qa['id']} · self-graded partial · 1 of 2 points · "
                      "they could both point at the vec", out)

    def test_a_missed_point_becomes_a_question_with_the_lesson_s_points(self):
        self.load(self.payload(recall()))
        [question] = self.of_type("question")
        self.assertEqual(question["points"], POINTS)
        self.assertEqual(question["q"], "Why only one &mut?")
        self.assertNotIn("no key points", self.out("due", "--early"))

    def test_a_fully_correct_recall_adds_no_question(self):
        self.load(self.payload(recall(hit=(1, 2))))
        self.assertEqual(self.of_type("question"), [])

    def test_bad_recall_payloads_are_refused_and_nothing_is_recorded(self):
        bad = {"points must be": recall(points=[]),
               "points must be ": recall(points=["ok", 3]),
               "hit must be": recall(hit=[3]),
               "hit must be ": recall(hit=["1"]),
               "confidence must be": recall(confidence="certain"),
               "kind must be": recall(kind="essay")}
        for message, answer in bad.items():
            with self.subTest(message=message):
                result = self.load(self.payload(answer), check=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message.strip(), result.stderr)
        self.assertFalse((self.project / ".wise-code" / "graph" / "nodes.jsonl").exists())


class ChoiceConfidenceTests(LessonCase):
    def test_a_multiple_choice_answer_can_carry_confidence(self):
        self.load(self.payload(choice(confidence="high")))
        [qa] = self.of_type("qa")
        self.assertEqual((qa["verdict"], qa["confidence"]), ("wrong", "high"))
        self.assertIn("sure but missed", self.out("calibration"))

    def test_results_from_older_lessons_still_import(self):
        self.load(self.payload(choice(), choice("c2", correct=True)))
        self.assertEqual(sorted(n["verdict"] for n in self.of_type("qa")), ["correct", "wrong"])
        self.assertNotIn("confidence", self.of_type("qa")[0])


class StuckTests(LessonCase):
    STUCK = [{"section": "s2", "title": "Aliasing", "text": "Why is Rc not a borrow?"},
             {"section": "s3", "title": "Lifetimes", "text": "What does 'a actually name?"}]

    def test_questions_typed_in_the_lesson_arrive_as_open_questions(self):
        out = self.load(self.payload(choice(), stuck=self.STUCK)).stdout
        asked = [n for n in self.of_type("qa") if n["source"] == "asked"]
        self.assertEqual(sorted(n["q"] for n in asked),
                         ["[0007-borrowing · Aliasing] Why is Rc not a borrow?",
                          "[0007-borrowing · Lifetimes] What does 'a actually name?"])
        self.assertEqual({n["a"] for n in asked}, {"(not answered yet)"})
        self.assertIn("stuck: ", out)
        self.assertIn("Why is Rc not a borrow?", out)
        self.assertIn("2 questions from the learner", out)

    def test_they_can_be_listed_until_answered(self):
        self.load(self.payload(stuck=self.STUCK))
        waiting = self.out("list", "qa", "--where", "a=(not answered yet)")
        self.assertEqual(len(waiting.splitlines()), 2)
        first = waiting.split(" · ")[0]
        self.run_wise("set", first, "a=Rc is shared ownership, counted at run time")
        self.assertEqual(len(self.out("list", "qa", "--where",
                                      "a=(not answered yet)").splitlines()), 1)

    def test_importing_the_same_result_again_adds_no_second_copy(self):
        self.load(self.payload(choice(), stuck=self.STUCK))
        again = self.load(self.payload(choice(), stuck=self.STUCK)).stdout
        self.assertIn("already imported", again)
        self.assertEqual(len(self.of_type("qa")), 3)

    def test_a_later_copy_adds_only_the_new_question(self):
        self.load(self.payload(stuck=self.STUCK[:1]))
        self.load(self.payload(stuck=self.STUCK))
        self.assertEqual(len(self.of_type("qa")), 2)

    def test_bad_stuck_entries_are_refused(self):
        for entry in ("text", {"text": ""}, {"text": 5}, {"text": "x" * 2001}):
            with self.subTest(entry=entry):
                result = self.load(self.payload(stuck=[entry]), check=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("stuck", result.stderr)


class PasteImportTests(LessonCase):
    def paste(self, text, check=True):
        import os
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": "2026-10-28"}
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/wise.py"), "--root", str(self.project),
             "import-lesson", "-"], input=text, text=True, capture_output=True, env=env,
            timeout=30)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_results_pasted_into_the_chat_import_from_stdin(self):
        out = self.paste(json.dumps(self.payload(recall(), choice()))).stdout
        self.assertIn("imported pasted results: 2 answers", out)
        self.assertEqual(len(self.of_type("qa")), 2)
        self.assertIn("already imported", self.paste(json.dumps(self.payload(recall()))).stdout)

    def test_text_around_the_json_is_refused_not_guessed_at(self):
        result = self.paste("here you go: " + json.dumps(self.payload(choice())), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("pasted results: not valid JSON", result.stderr)

    def test_an_oversized_paste_is_refused(self):
        result = self.paste(json.dumps(self.payload(choice(q="x" * 300000))), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("too large", result.stderr)


class RegradeTests(LessonCase):
    def setUp(self):
        super().setUp()
        self.load(self.payload(recall(hit=(1, 2), confidence="high")))
        [self.qa] = [n["id"] for n in self.of_type("qa")]

    def node(self):
        return next(n for n in self.nodes() if n["id"] == self.qa)

    def test_claude_s_reading_replaces_the_verdict_and_keeps_the_learner_s(self):
        out = self.out("regrade", self.qa, "--hit", "1")
        self.assertIn(f"{self.qa} · partial (self-graded correct)", out)
        node = self.node()
        self.assertEqual((node["verdict"], node["self_verdict"], node["graded"]),
                         ("partial", "correct", "claude"))
        self.assertEqual(node["missed"], [POINTS[1]])

    def test_a_lowered_verdict_adds_the_question_the_import_did_not(self):
        self.assertEqual(self.of_type("question"), [])
        self.assertIn("confusion:", self.out("regrade", self.qa, "--hit", "none"))
        [question] = self.of_type("question")
        self.assertEqual(question["points"], POINTS)
        self.assertEqual(question["source"], "lesson 0007-borrowing")
        self.out("regrade", self.qa, "--hit", "1")
        self.assertEqual(len(self.of_type("question")), 1)

    def test_agreeing_marks_it_read_without_changing_the_verdict(self):
        self.out("regrade", self.qa, "--hit", "all")
        node = self.node()
        self.assertEqual((node["verdict"], node["graded"]), ("correct", "claude"))
        self.assertNotIn("missed", node)

    def test_only_an_answer_with_points_can_be_regraded(self):
        plain = self.out("add", "qa", "source=asked", "q=Q", "a=A", "verdict=n/a").strip()
        bad = self.run_wise("regrade", plain, "--hit", "all", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("no key points", bad.stderr)
        bad = self.run_wise("regrade", self.qa, "--hit", "5", check=False)
        self.assertEqual(bad.returncode, 2)


PAGE = r"""
// Loads the real results.js with a stub page and runs the calls in argv[3]
// (a JSON list of [method, ...args]); prints what download and copy produced.
const blobs = [], copied = [];
global.window = {crypto: globalThis.crypto, navigator: {clipboard: {
  writeText: (text) => { copied.push(text); return Promise.resolve(); }}}};
let link = {};
global.document = {
  readyState: "complete", getElementById: () => null, body: {appendChild() {}},
  createElement: () => (link = {click() {}, remove() {}}),
};
URL.createObjectURL = (blob) => { blobs.push(blob); return "blob:x"; };
URL.revokeObjectURL = () => {};
require(process.argv[2]);
window.WiseResults.lesson("0007-borrowing");
let chain = Promise.resolve();
for (const [method, ...args] of JSON.parse(process.argv[3])) {
  chain = chain.then(() => window.WiseResults[method](...args));
}
chain.then(() => Promise.all(blobs.map((b) => b.text()))).then((texts) =>
  console.log(JSON.stringify({downloads: texts, copied})));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageScriptTests(LessonCase):
    """The real results.js: what the page hands over is what the importer takes."""

    CALLS = [
        ["recall", "r1", "Why only one &mut?", "they could both point at the vec", POINTS,
         [1], "high"],
        ["record", "c1", "Which borrows may coexist?", "Two &mut", False,
         "Many & or one &mut", "low"],
        ["recall", "r1", "Why only one &mut?", "second try", POINTS, [1, 2], "high"],
        ["stuck", "s2", "Aliasing", "Why is Rc not a borrow?"],
        ["stuck", "s2", "Aliasing", "  "],
    ]

    def run_page(self, calls):
        page = Path(self.temp.name) / "page.js"
        page.write_text(PAGE, encoding="utf-8")
        result = subprocess.run(
            ["node", str(page), str(ROOT / "skills/teach/templates/results.js"),
             json.dumps(calls)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_copy_and_download_carry_the_same_results(self):
        produced = self.run_page(self.CALLS + [["copy"], ["download"]])
        self.assertEqual(json.loads(produced["copied"][0]), json.loads(produced["downloads"][0]))

    def test_the_copied_text_imports_as_it_is(self):
        [copied] = self.run_page(self.CALLS + [["copy"]])["copied"]
        self.assertNotIn("\n", copied)  # one line: survives a paste into the chat
        out = PasteImportTests.paste(self, copied).stdout
        self.assertIn("imported pasted results: 2 answers", out)
        self.assertIn("1 questions from the learner", out)
        by_id = {n.get("answer_id"): n for n in self.of_type("qa")}
        # The first attempt is the evidence; the retry and the blank question are not.
        self.assertEqual(by_id["r1"]["a"], "they could both point at the vec")
        self.assertEqual((by_id["r1"]["verdict"], by_id["r1"]["confidence"]), ("partial", "high"))
        self.assertEqual((by_id["c1"]["verdict"], by_id["c1"]["confidence"]), ("wrong", "low"))

    def test_a_point_number_out_of_range_never_leaves_the_page(self):
        [copied] = self.run_page([["recall", "r1", "Q", "text", POINTS, [0, 2, 9, 2], "mid"],
                                  ["copy"]])["copied"]
        self.assertEqual(json.loads(copied)["answers"][0]["hit"], [2])
