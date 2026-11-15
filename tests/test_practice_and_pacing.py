"""Practice that is done, not described, and help that fades: task questions
judged by a command's exit code, a prerequisite check before building, and
advice on where the learner is ready for less help."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402

SAID = "the owner frees it when it goes out of scope"


class TaskQuestionTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.run_wise("add", "concept", "name=Ownership")
        self.task = self.out(
            "add", "question", "q=Make take_names compile without clone",
            "a=Borrow the slice instead of taking the Vec",
            "check=cargo test --manifest-path .wise-code/scratch/own/Cargo.toml",
            "due=2026-10-01", "--tests", "ownership").strip()

    def answer(self, verdict, *args):
        return self.run_wise("answer", self.task, verdict, *args, check=False)

    def test_a_task_needs_no_key_points_and_due_shows_how_to_check_it(self):
        due = self.out("due")
        self.assertIn("Make take_names compile without clone · task: cargo test "
                      "--manifest-path .wise-code/scratch/own/Cargo.toml", due)
        self.assertNotIn("no key points", due)

    def test_the_exit_code_is_required_and_bounds_the_verdict(self):
        bad = self.answer("correct")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("--exit", bad.stderr)
        for verdict in ("correct", "partial"):
            bad = self.answer(verdict, "--exit", "101")
            self.assertEqual(bad.returncode, 2, verdict)
            self.assertIn("the check exited 101: the verdict can only be wrong", bad.stderr)
        self.assertEqual(self.out("history"), "no matching history\n")

    def test_a_passing_check_is_correct_without_a_quote(self):
        out = self.answer("correct", "--exit", "0").stdout
        self.assertIn("now box 2", out)
        history = self.out("history", "--full")
        self.assertIn("quiz · correct", history)
        self.assertIn("  check: exit 0", history)

    def test_a_failing_check_is_wrong_and_a_confusion(self):
        out = self.answer("wrong", "--exit", "101").stdout
        self.assertIn("now box 1", out)
        self.assertIn("confusion:", out)
        self.assertIn("  check: exit 101", self.out("history", "--full"))

    def test_lint_does_not_ask_a_task_answer_for_a_quote(self):
        self.answer("correct", "--exit", "0")
        self.run_wise("add", "session", "goal=G", "checkpoints+=A?", "checkpoints+=B?",
                      "checkpoints+=C?")
        self.assertNotIn("without the learner's words", self.out("lint-session"))

    def test_a_task_answer_is_not_counted_as_missing_a_confidence_prefix(self):
        self.answer("correct", "--exit", "0")
        self.run_wise("add", "qa", "source=checkpoint", "q=Q", "a=A", "verdict=correct",
                      f"said={SAID}")
        self.assertIn("no confidence: 1 of 1 ", self.out("calibration"))
        self.run_wise("add", "session", "goal=G", "checkpoints+=A?", "checkpoints+=B?",
                      "checkpoints+=C?")
        self.assertIn("flag: 1 of 1 answers without a confidence prefix",
                      self.out("lint-session"))

    def test_passing_after_a_hint_can_be_recorded_as_partial(self):
        self.assertEqual(self.answer("partial", "--exit", "0", "--hints", "1").returncode, 0)

    def test_key_point_flags_don_t_apply_to_a_task(self):
        bad = self.answer("correct", "--exit", "0", "--hit", "all")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("--hit", bad.stderr)

    def test_exit_is_refused_on_a_question_that_is_not_a_task(self):
        plain = self.out("add", "question", "q=Why?", "a=Because.", "points+=the point").strip()
        bad = self.run_wise("answer", plain, "correct", "--hit", "all", "--said", SAID,
                            "--exit", "0", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("is not a task", bad.stderr)

    def test_an_empty_check_is_not_a_task(self):
        bad = self.run_wise("add", "question", "q=Do it", "a=Done", "check= ", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("points", bad.stderr)


class ReadyTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        for name in ("Lifetimes", "Borrowing", "Ownership"):
            self.run_wise("add", "concept", f"name={name}")
        self.run_wise("link", "lifetimes", "prereq", "borrowing")
        self.run_wise("link", "borrowing", "prereq", "ownership")

    def test_undemonstrated_prerequisites_come_first_deepest_first(self):
        out = self.out("ready", "lifetimes")
        lines = out.splitlines()
        self.assertEqual(lines[0], "lifetimes · not ready: 2 prerequisites to cover first")
        self.assertIn("first: ownership · introduced", lines[1])
        self.assertIn("first: borrowing · introduced", lines[2])

    def test_demonstrated_prerequisites_make_it_ready(self):
        for concept in ("ownership", "borrowing"):
            self.run_wise("set", concept, "status=demonstrated")
        self.assertEqual(self.out("ready", "lifetimes"), "lifetimes · ready\n")

    def test_an_open_confusion_on_a_demonstrated_prerequisite_blocks(self):
        for concept in ("ownership", "borrowing"):
            self.run_wise("set", concept, "status=demonstrated")
        self.run_wise("add", "qa", "source=checkpoint", "q=Who frees it?", "a=gist",
                      "verdict=wrong", f"said={SAID}", "--about", "ownership")
        out = self.out("ready", "lifetimes")
        self.assertIn("not ready: 1 prerequisites to cover first", out)
        self.assertIn("first: ownership · demonstrated · open confusion", out)

    def test_a_concept_without_prerequisites_is_ready(self):
        self.assertEqual(self.out("ready", "ownership"), "ownership · ready\n")

    def test_an_unknown_concept_is_refused(self):
        self.assertEqual(self.run_wise("ready", "monads", check=False).returncode, 2)


class LevelAdviceTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.run_wise("add", "concept", "name=Ownership")
        self.run_wise("add", "concept", "name=Lifetimes")

    def qa(self, concept, verdict="correct", confidence="high", day="2026-10-20", *extra):
        self.run_wise("add", "qa", "source=checkpoint", "q=Q", "a=A", f"verdict={verdict}",
                      f"confidence={confidence}", f"said={SAID}", *extra, "--about", concept,
                      day=day)

    def clean(self, concept, count=5):
        for n in range(count):
            self.qa(concept, day=f"2026-10-{10 + n}")

    def test_clean_recent_answers_mean_ready_for_less_help(self):
        self.clean("ownership")
        self.assertEqual(self.out("level-advice"),
                         "less help: ownership · 5 answers · 5 correct · no hints\n")

    def test_too_few_answers_is_not_evidence(self):
        self.clean("ownership", count=4)
        self.assertEqual(self.out("level-advice"), "no concept is ready for less help yet\n")
        self.assertIn("less help: ownership · 4 answers", self.out("level-advice", "--min", "4"))

    def test_hints_misses_and_open_confusions_hold_it_back(self):
        cases = {"hint": ("correct", "high", ["hints=1"]),
                 "low confidence": ("correct", "low", []),
                 "miss": ("wrong", "mid", [])}
        for name, (verdict, confidence, extra) in cases.items():
            with self.subTest(name=name):
                self.setUp_graph()
                self.clean("ownership")
                self.qa("ownership", verdict, confidence, "2026-10-21", *extra)
                self.assertEqual(self.out("level-advice"),
                                 "no concept is ready for less help yet\n")

    def setUp_graph(self):
        import shutil
        shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
        self.run_wise("add", "concept", "name=Ownership")

    def test_old_answers_don_t_count(self):
        for n in range(5):
            self.qa("ownership", day=f"2026-08-{10 + n}")
        self.assertEqual(self.out("level-advice"), "no concept is ready for less help yet\n")
        self.assertIn("less help: ownership", self.out("level-advice", "--days", "120"))

    def test_only_the_learners_own_answers_count(self):
        self.clean("ownership", count=4)
        self.run_wise("add", "qa", "source=asked", "q=Q", "a=A", "verdict=n/a",
                      "--about", "ownership", day="2026-10-20")
        self.assertEqual(self.out("level-advice"), "no concept is ready for less help yet\n")
