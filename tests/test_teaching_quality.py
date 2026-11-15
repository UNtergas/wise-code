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
        return self.run_wise("answer", self.qid, verdict, "--said", "the learner said this",
                             *args, check=False)

    def question_without_points(self):
        """Only an import can still make one: `add question` requires points."""
        notes = self.project / ".wise-code" / "questions.md"
        notes.write_text("# Question Bank\n\n## QB-0001 · topic\nQ: Why?\nA: Because.\n"
                         "Box: 1\nDue: 2026-10-01\n", encoding="utf-8")
        self.run_wise("import-md")
        [line] = [l for l in self.out("list", "question").splitlines() if "Why?" in l]
        return line.split(" · ")[0]

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
        plain = self.question_without_points()
        said = ("--said", "the learner said this")
        self.assertIn("box 2", self.out("answer", plain, "correct", *said))
        refused = self.run_wise("answer", plain, "correct", "--hit", "1", *said, check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("has no key points", refused.stderr)

    def test_due_says_when_a_question_has_no_points_yet(self):
        plain = self.question_without_points()
        self.run_wise("set", self.qid, "due=2026-10-01")
        lines = {line.split(" · ")[0]: line for line in self.out("due").splitlines()}
        self.assertIn("no key points", lines[plain])
        self.assertNotIn("no key points", lines[self.qid])


class ExampleLevelTests(unittest.TestCase):
    def test_every_guide_that_lists_levels_knows_example(self):
        for path in ("skills/learn/assist-levels.md", "skills/level/SKILL.md",
                     "skills/learn/onboarding.md", "skills/learn/gates.md",
                     "skills/critique/SKILL.md", "skills/correct/SKILL.md",
                     "codex/skills/consult/SKILL.md", "README.md"):
            with self.subTest(path=path):
                self.assertIn("Example", guide(path))

    def test_the_example_is_never_the_learner_s_problem(self):
        text = guide("skills/learn/assist-levels.md")
        section = text[text.index("## Example"):text.index("## Pseudo")]
        for rule in ("a different problem", "never the learner's", "one concept",
                     "explain", "Hint", "`demonstrated`"):
            self.assertIn(rule, section)
        self.assertIn("## Rules for Hint, Example and Pseudo", text)

    def test_the_senior_journal_accepts_the_level(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import consult  # noqa: PLC0415
        self.assertEqual(consult.LEVELS, ("Hint", "Example", "Pseudo", "Full code"))


class ExplainBackTests(unittest.TestCase):
    def test_full_code_asks_before_it_reports(self):
        text = guide("skills/learn/behavior.md")
        self.assertLess(text.index("**Explain-back**"), text.index("give a concise **Implementation report**"))
        section = text[text.index("**Explain-back**"):text.index("give a concise **Implementation report**")]
        for rule in ("one question", "wait", "source=checkpoint", "said=", "skip"):
            self.assertIn(rule, section)
        self.assertIn("`Explain-back`", text)  # a named callout heading
        self.assertIn("Explain-back", guide("skills/learn/assist-levels.md"))


class RecallFirstStartCheckTests(unittest.TestCase):
    def test_free_recall_comes_before_any_question(self):
        text = guide("skills/learn/SKILL.md")
        check = text[text.index("## Start check"):text.index("## Session end")]
        self.assertLess(check.index("Free recall"), check.index("Open questions"))
        self.assertLess(check.index("Open questions"), check.index("multiple-choice"))
        for rule in ("from memory", "Don't show the recap yet", "at most one",
                     "at most 5 questions"):
            self.assertIn(rule, check)

    def test_hook_and_readme_describe_the_same_check(self):
        for path in ("hooks/session_start.py", "README.md"):
            with self.subTest(path=path):
                text = guide(path)
                self.assertIn("from memory", text)
                self.assertNotIn("2–3 multiple-choice", text)
                self.assertNotIn("(QCM)", text)
