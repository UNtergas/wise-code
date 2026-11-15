"""What gets reviewed, and when: weak concepts recover, low-confidence answers
aren't promoted, retained questions are asked as variants, and the session hook
says how much is due."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The module, not its classes: a test class imported by name is collected again here.
import test_session_start as hooks  # noqa: E402
from test_wise import WiseTestCase  # noqa: E402


class WeakRecoveryTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.run_wise("add", "concept", "name=Strings")

    def qa(self, verdict, day):
        self.run_wise("add", "qa", "q=Q", "a=A", "source=review", f"verdict={verdict}",
                      "--about", "strings", day=day)

    def test_a_miss_followed_by_two_correct_answers_is_no_longer_weak(self):
        self.qa("wrong", "2026-08-02")
        self.qa("correct", "2026-08-03")
        self.assertIn("strings · concept · - · Strings · open misses 1", self.out("weak"))
        self.qa("correct", "2026-08-06")
        self.assertEqual(self.out("weak"), "no weak concepts\n")

    def test_correct_answers_before_the_miss_don_t_recover_it(self):
        self.qa("correct", "2026-08-01")
        self.qa("correct", "2026-08-02")
        self.qa("partial", "2026-08-03")
        self.assertIn("open misses 1", self.out("weak"))

    def test_a_concept_marked_reinforce_stays_listed_and_shows_what_recovered(self):
        self.qa("wrong", "2026-08-02")
        self.qa("correct", "2026-08-03")
        self.qa("correct", "2026-08-06")
        self.run_wise("set", "strings", "status=reinforce")
        self.assertIn("reinforce · Strings · open misses 0 · recovered 1", self.out("weak"))

    def test_mistakes_still_counts_every_miss(self):
        # Correct turns repeats into guardrails: a recovered miss still happened.
        for day in ("2026-08-02", "2026-08-03"):
            self.qa("wrong", day)
        for day in ("2026-08-04", "2026-08-05"):
            self.qa("correct", day)
        self.assertEqual(self.out("weak"), "no weak concepts\n")
        self.assertIn("strings · 2 misses", self.out("mistakes"))


class ConfidenceScheduleTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.qid = self.out("add", "question", "q=Why panic?", "a=Boundary.").strip()

    def test_a_correct_answer_at_low_confidence_stays_in_its_box(self):
        out = self.out("answer", self.qid, "correct", "--confidence", "low", day="2026-10-29")
        self.assertIn("box 1 · due 2026-10-30", out)
        self.assertIn("low confidence", out)

    def test_other_correct_answers_still_move_up(self):
        for confidence, box in ((["--confidence", "mid"], 2), ([], 3),
                                (["--confidence", "high"], 4)):
            out = self.out("answer", self.qid, "correct", *confidence, day="2026-10-29")
            self.assertIn(f"now box {box} ·", out)
            self.assertNotIn("low confidence", out)


class VariantTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.kept = self.out("add", "question", "q=Why bytes?", "a=Core.", "box=3",
                             "due=2026-10-01", "points+=the core indexes bytes").strip()
        self.new = self.out("add", "question", "q=Why panic?", "a=Boundary.",
                            "due=2026-10-01").strip()

    def test_due_marks_retained_questions_for_a_variant(self):
        lines = {line.split(" · ")[0]: line for line in self.out("due").splitlines()}
        self.assertTrue(lines[self.kept].endswith("Why bytes? · ask a variant"), lines)
        self.assertNotIn("variant", lines[self.new])

    def test_answer_records_the_question_actually_asked(self):
        self.run_wise("answer", self.kept, "correct", "--hit", "all", "--asked",
                      "In span.rs, why can't offsets be char counts?")
        history = self.out("history", "--full")
        self.assertIn("Q: In span.rs, why can't offsets be char counts?", history)
        self.assertNotIn("Q: Why bytes?", history)
        # The bank keeps its own wording, and the answer still belongs to it.
        self.assertIn("Why bytes?", self.out("show", self.kept))
        self.assertIn("← answers QA-", self.out("show", self.kept))

    def test_asked_can_t_be_empty(self):
        bad = self.run_wise("answer", self.kept, "correct", "--hit", "all", "--asked", "  ",
                            check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("--asked", bad.stderr)


class DueCountHookTests(hooks.HookCase):
    wise = hooks.GraphHookTests.wise
    graph_state = hooks.GraphHookTests.graph_state

    def add_question(self, text, due):
        self.wise("add", "question", f"q={text}", "a=A", f"due={due}")

    def test_new_sessions_are_told_how_many_questions_are_due(self):
        self.graph_state()
        self.add_question("Why does backoff double?", "2020-01-01")
        self.add_question("Why jitter?", "2020-01-02")
        self.add_question("Not yet", "2999-01-01")
        for source, expected in (("startup", True), ("clear", True), ("resume", False),
                                 ("compact", False)):
            with self.subTest(source=source):
                context = self.context(source=source)
                self.assertEqual("2 questions are due for review" in context, expected)
                self.assertNotIn("backoff", context)  # a count, never the content

    def test_one_due_question_reads_in_the_singular(self):
        self.graph_state()
        self.add_question("Why jitter?", "2020-01-02")
        self.assertIn("1 question is due for review", self.context())

    def test_nothing_due_says_nothing(self):
        self.graph_state()
        self.add_question("Not yet", "2999-01-01")
        self.assertNotIn("due for review", self.context())

    def test_a_broken_graph_says_nothing(self):
        state = self.graph_state()
        (state / "graph" / "nodes.jsonl").write_text("{not json\n", encoding="utf-8")
        self.assertNotIn("due for review", self.context())
