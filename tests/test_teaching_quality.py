"""How answers are judged and how the guides teach: key points bound the
verdict; the Example level, the explain-back and the recall-first start check
are stated where Claude reads them."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402


def guide(path):
    return (ROOT / path).read_text(encoding="utf-8")


class KeyPointTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.qid = self.out(
            "add", "question", "q=Why can't the core store a char index?",
            "a=Char indexes count scalar values; UTF-16 counts code units.",
            "points+=char index counts scalar values",
            "points+=UTF-16 counts code units, so they differ, for emoji",
            "points+=convert at the boundary").strip()

    def answer(self, verdict, *args):
        return self.run_wise("answer", self.qid, verdict, *args, check=False)

    def test_points_keep_their_commas_and_order(self):
        shown = self.out("show", self.qid)
        self.assertIn('"points": ["char index counts scalar values", '
                      '"UTF-16 counts code units, so they differ, for emoji", '
                      '"convert at the boundary"]', shown)

    def test_a_question_with_points_needs_the_points_hit(self):
        bad = self.answer("correct")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("--hit", bad.stderr)
        self.assertIn("3 key points", bad.stderr)
        self.assertNotIn("QA-", self.out("history"))

    def test_correct_needs_every_point(self):
        bad = self.answer("correct", "--hit", "1,3")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("2 of 3 key points hit: the verdict can be at most partial", bad.stderr)
        self.assertIn("box 2", self.answer("correct", "--hit", "all").stdout)

    def test_no_point_hit_is_wrong(self):
        for verdict in ("correct", "partial"):
            bad = self.answer(verdict, "--hit", "none")
            self.assertEqual(bad.returncode, 2, verdict)
            self.assertIn("0 of 3 key points hit: the verdict can be at most wrong", bad.stderr)
        self.assertEqual(self.answer("wrong", "--hit", "none").returncode, 0)

    def test_a_lower_verdict_than_the_points_allow_is_accepted(self):
        # All points, but only after a hint: Quiz calls that partial.
        self.assertEqual(self.answer("partial", "--hit", "all", "--hints", "1").returncode, 0)

    def test_the_missed_points_are_recorded_and_shown(self):
        self.assertEqual(self.answer("partial", "--hit", "1,3").returncode, 0)
        history = self.out("history", "--full")
        self.assertIn("  missed: UTF-16 counts code units, so they differ, for emoji", history)
        self.assertNotIn("missed: char index", history)

    def test_hit_refuses_what_is_not_a_point_number(self):
        for bad_value in ("0", "4", "two", "1,,x", ""):
            bad = self.answer("partial", "--hit", bad_value)
            self.assertEqual(bad.returncode, 2, bad_value)
            self.assertIn("--hit", bad.stderr)

    def test_a_question_without_points_is_answered_as_before(self):
        plain = self.out("add", "question", "q=Why?", "a=Because.").strip()
        self.assertIn("box 2", self.out("answer", plain, "correct"))
        refused = self.run_wise("answer", plain, "correct", "--hit", "1", check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("has no key points", refused.stderr)

    def test_due_says_when_a_question_has_no_points_yet(self):
        plain = self.out("add", "question", "q=Why?", "a=Because.", "due=2026-10-01").strip()
        self.run_wise("set", self.qid, "due=2026-10-01")
        lines = {line.split(" · ")[0]: line for line in self.out("due").splitlines()}
        self.assertIn("no key points", lines[plain])
        self.assertNotIn("no key points", lines[self.qid])
