"""Every number rests on a record that can be checked: an answer carries the
learner's words, a new question carries its key points, and calibration says
how many answers had no confidence."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402

SAID = "because the core indexes bytes"


class AnswerNeedsTheLearnersWordsTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.qid = self.out("add", "question", "q=Why bytes?", "a=Core.",
                            "points+=the core indexes bytes").strip()

    def test_an_answer_without_said_is_refused_and_nothing_is_recorded(self):
        for extra in ([], ["--answer", "a gist is not a quote"], ["--said", "  "]):
            bad = self.run_wise("answer", self.qid, "correct", "--hit", "all", *extra,
                                check=False)
            self.assertEqual(bad.returncode, 2, extra)
            self.assertIn("--said", bad.stderr)
        self.assertEqual(self.out("history"), "no matching history\n")
        self.assertIn('"box": 1', self.out("show", self.qid))

    def test_said_is_stored_unchecked_and_shown(self):
        self.run_wise("answer", self.qid, "correct", "--hit", "all", "--said", SAID)
        history = self.out("history", "--full")
        self.assertIn(f"learner said «{SAID}» · check unchecked", history)

    def test_the_quote_keeps_the_usual_length_rule(self):
        bad = self.run_wise("answer", self.qid, "correct", "--hit", "all", "--said", "bytes",
                            check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("quote at least 3", bad.stderr)


class NewQuestionsNeedKeyPointsTests(WiseTestCase):
    def test_add_question_without_points_is_refused(self):
        bad = self.run_wise("add", "question", "q=Why?", "a=Because.", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn('points+="', bad.stderr)
        self.assertNotIn("QB-", self.out("list", "question"))

    def test_points_must_say_something(self):
        bad = self.run_wise("add", "question", "q=Why?", "a=Because.", "points+= ",
                            check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("points", bad.stderr)

    def test_questions_from_before_the_rule_still_load_and_answer(self):
        # Imports and older graphs hold questions without points.
        (self.project / ".wise-code").mkdir(exist_ok=True)
        notes = self.project / ".wise-code" / "questions.md"
        notes.write_text("# Question Bank\n\n## QB-0001 · topic\nQ: Old question?\n"
                         "A: Old answer.\nBox: 1\nDue: 2026-01-01\n", encoding="utf-8")
        self.run_wise("import-md")
        due = self.out("due")
        self.assertIn("Old question?", due)
        self.assertIn("no key points", due)
        old = due.split(" · ")[0]
        self.assertIn("box 2", self.out("answer", old, "correct", "--said", SAID))


class UnprefixedAnswersTests(WiseTestCase):
    def qa(self, source, *fields):
        self.run_wise("add", "qa", f"source={source}", "q=Q", "a=A", "verdict=correct",
                      f"said={SAID}", *fields)

    def test_calibration_counts_answers_without_confidence(self):
        self.qa("checkpoint", "confidence=high")
        self.qa("checkpoint")
        self.qa("repair")
        self.qa("quiz")
        out = self.out("calibration")
        self.assertIn("no confidence: 3 of 4 checkpoint, quiz, repair and explain-back answers", out)

    def test_sources_that_carry_no_prefix_are_not_counted(self):
        self.qa("checkpoint", "confidence=mid")
        self.run_wise("add", "qa", "source=asked", "q=Q", "a=A", "verdict=n/a")
        self.run_wise("add", "qa", "source=start-check", "q=Q", "a=A", "verdict=wrong")
        self.assertIn("no confidence: 0 of 1 checkpoint, quiz, repair and explain-back answers",
                      self.out("calibration"))

    def test_since_applies_to_the_count(self):
        self.run_wise("add", "qa", "source=quiz", "q=Q", "a=A", "verdict=correct",
                      day="2026-10-01")
        self.assertNotIn("no confidence", self.out("calibration", "--since", "2026-10-20"))
