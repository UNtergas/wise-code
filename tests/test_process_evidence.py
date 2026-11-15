"""The script sees what happened: the start check is scored from recorded
coverage of the session's check points, and lint-session reports the rules a
session's records show were skipped."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402

SAID = "we doubled the backoff because the broker throttles"


class StartCheckCase(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.sid = self.out(
            "add", "session", "goal=Retry queue",
            "checkpoints+=Why does backoff double?", "checkpoints+=Why add jitter?",
            "checkpoints+=Why cap retries at 5?", "checkpoints+=What is dead-lettered?",
            day="2026-10-27").strip()

    def check(self, *args, ok=True, day="2026-10-28"):
        result = self.run_wise("start-check", *args, check=False, day=day)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stdout + result.stderr)
        return result.stdout if ok else result.stderr

    def node(self, node_id):
        import json
        text = self.out("show", node_id)
        return json.loads(text[text.index("{"):text.rindex("}") + 1])


class RecallTests(StartCheckCase):
    def test_the_verdict_comes_from_the_check_points_covered(self):
        for covers, verdict in (("all", "correct"), ("1,3", "partial"), ("none", "wrong")):
            with self.subTest(covers=covers):
                sid = self.out("add", "session", f"goal=G {covers}", "checkpoints+=A?",
                               "checkpoints+=B?", "checkpoints+=C?").strip()
                out = self.check("recall", sid, "--covers", covers, "--said", SAID)
                self.assertIn(f"· {verdict} ·", out)

    def test_it_lists_the_check_points_still_to_ask(self):
        out = self.check("recall", self.sid, "--covers", "1,3", "--said", SAID,
                         "--confidence", "mid")
        self.assertIn("ask next: 2. Why add jitter?", out)
        self.assertIn("ask next: 4. What is dead-lettered?", out)
        self.assertNotIn("Why cap retries", out)
        history = self.out("history", "--full", "--source", "start-check")
        self.assertIn("Q: Free recall: Retry queue", history)
        self.assertIn(f"learner said «{SAID}»", history)
        self.assertIn("  missed: Why add jitter?", history)

    def test_recall_needs_the_learners_words_and_valid_numbers(self):
        self.assertIn("--said", self.check("recall", self.sid, "--covers", "all", ok=False))
        for bad in ("5", "0", "x"):
            self.assertIn("--covers", self.check("recall", self.sid, "--covers", bad,
                                                 "--said", SAID, ok=False))
        self.assertEqual(self.out("history"), "no matching history\n")

    def test_one_recall_per_session_and_none_once_it_is_closed(self):
        self.check("recall", self.sid, "--covers", "all", "--said", SAID)
        self.assertIn("already has its free recall",
                      self.check("recall", self.sid, "--covers", "none", "--said", SAID, ok=False))
        self.check("done", self.sid)
        self.assertIn("not pending",
                      self.check("point", self.sid, "2", "correct", "--said", SAID, ok=False))


class PointAndScoreTests(StartCheckCase):
    def test_done_computes_the_score_from_recall_and_points(self):
        self.check("recall", self.sid, "--covers", "1", "--said", SAID)
        self.check("point", self.sid, "2", "correct", "--said", "jitter spreads the retries out")
        self.check("point", self.sid, "3", "partial", "--said", "something about the broker")
        self.check("point", self.sid, "4", "wrong", "--picked", "Messages that succeeded")
        out = self.check("done", self.sid, day="2026-10-29")
        self.assertIn(f"{self.sid} · start check done 2026-10-29 · 2/4", out)
        self.assertEqual(self.node(self.sid)["start_check"], "done 2026-10-29 · 2/4")
        self.assertEqual(self.out("session", "--pending"), "no pending start check\n")

    def test_done_is_refused_without_a_free_recall(self):
        self.check("point", self.sid, "2", "correct", "--said", "jitter spreads the retries out")
        self.assertIn("free recall", self.check("done", self.sid, ok=False))
        self.assertEqual(self.node(self.sid)["start_check"], "pending")

    def test_done_twice_ends_in_the_same_state(self):
        self.check("recall", self.sid, "--covers", "all", "--said", SAID)
        self.check("done", self.sid, day="2026-10-29")
        self.check("done", self.sid, day="2026-10-30")
        self.assertEqual(self.node(self.sid)["start_check"], "done 2026-10-29 · 4/4")

    def test_a_point_needs_typed_words_or_the_option_picked(self):
        self.assertIn("--said", self.check("point", self.sid, "2", "correct", ok=False))
        self.assertIn("already answered", (
            self.check("point", self.sid, "2", "wrong", "--picked", "Option B"),
            self.check("point", self.sid, "2", "correct", "--picked", "Option A", ok=False))[1])
        for bad in (("9", "correct"), ("2", "n/a")):
            self.check("point", self.sid, *bad, "--said", SAID, ok=False)

    def test_a_point_already_covered_by_the_recall_is_not_counted_twice(self):
        self.check("recall", self.sid, "--covers", "1,2", "--said", SAID)
        self.check("point", self.sid, "2", "correct", "--said", "jitter spreads the retries out")
        self.assertIn("· 2/4", self.check("done", self.sid))

    def test_pending_lists_the_check_points_with_the_numbers_the_commands_take(self):
        pending = self.out("session", "--pending")
        self.assertIn("  checkpoints: 1. Why does backoff double?", pending)
        self.assertIn("  checkpoints: 4. What is dead-lettered?", pending)

    def test_skip_closes_the_check_without_a_score(self):
        out = self.check("skip", self.sid, day="2026-10-29")
        self.assertIn("skipped 2026-10-29", out)
        self.assertEqual(self.node(self.sid)["start_check"], "skipped 2026-10-29")

    def test_a_wrong_point_is_a_confusion_on_its_concept(self):
        self.run_wise("add", "concept", "name=Jitter")
        out = self.check("point", self.sid, "2", "wrong", "--said", "jitter makes it slower",
                         "--confidence", "high", "--about", "jitter")
        self.assertIn("confusion:", out)
        self.assertIn("jitter", self.out("confusions"))


class LintSessionTests(WiseTestCase):
    def qa(self, source, *fields, day="2026-10-28"):
        return self.out("add", "qa", f"source={source}", "q=Q", "a=A", *fields, day=day).strip()

    def session(self, *fields, day="2026-10-28"):
        return self.out("add", "session", "goal=Work", *fields, day=day).strip()

    def lint(self, *args):
        return self.out("lint-session", *args)

    POINTS = ["checkpoints+=A?", "checkpoints+=B?", "checkpoints+=C?"]

    def test_prefixed_and_quoted_answers_only_need_their_quotes_checked(self):
        self.qa("checkpoint", "verdict=correct", "confidence=high", f"said={SAID}")
        sid = self.session(*self.POINTS)
        out = self.lint()
        self.assertIn(f"{sid} · 2026-10-28 · 1 answers", out)
        self.assertIn("flag: 1 quotes not checked against the transcript", out)
        self.assertNotIn("confidence", out)
        self.assertNotIn("check points", out)

    def test_it_flags_answers_without_a_confidence_prefix(self):
        self.qa("checkpoint", "verdict=correct", f"said={SAID}")
        self.qa("checkpoint", "verdict=wrong", "confidence=low", f"said={SAID}")
        self.session(*self.POINTS)
        self.assertIn("flag: 1 of 2 answers without a confidence prefix", self.lint())

    def test_it_flags_too_few_check_points(self):
        self.session("checkpoints+=Only one?")
        self.assertIn("flag: 1 check points; the next start check needs 3 to 5", self.lint())

    def test_it_flags_full_code_steps_without_an_explain_back(self):
        self.qa("explain-back", "verdict=correct", "confidence=mid", f"said={SAID}")
        self.session(*self.POINTS, "full_steps=3")
        self.assertIn("flag: 3 Full code steps, 1 explain-backs", self.lint())

    def test_no_flag_when_every_full_code_step_was_explained_back(self):
        self.qa("explain-back", "verdict=correct", "confidence=mid", f"said={SAID}")
        self.session(*self.POINTS, "full_steps=1")
        self.assertNotIn("Full code", self.lint())

    def test_it_flags_a_start_check_marked_done_by_hand(self):
        old = self.session(*self.POINTS, day="2026-10-27")
        self.run_wise("set", old, "start_check=done 2026-10-28 · 3/3")
        self.session(*self.POINTS)
        self.assertIn(f"flag: start check on {old} was marked done without a free recall",
                      self.lint())

    def test_a_start_check_closed_by_the_script_is_not_flagged(self):
        old = self.session(*self.POINTS, day="2026-10-27")
        self.run_wise("start-check", "recall", old, "--covers", "all", "--said", SAID,
                      day="2026-10-28")
        self.run_wise("start-check", "done", old, day="2026-10-28")
        self.session(*self.POINTS)
        self.assertNotIn("free recall", self.lint())

    def test_it_lints_the_session_asked_for(self):
        first = self.session("checkpoints+=One?", day="2026-10-27")
        self.session(*self.POINTS)
        self.assertNotIn("check points", self.lint())
        self.assertIn("flag: 1 check points", self.lint(first))

    def test_no_session_yet(self):
        self.run_wise("add", "concept", "name=Strings")
        self.assertEqual(self.lint(), "no sessions yet\n")

    def test_older_answers_without_a_quote_are_flagged(self):
        # Imported history carries quiz answers recorded before --said was required.
        state = self.project / ".wise-code"
        state.mkdir(exist_ok=True)
        (state / "qa-history.md").write_text(
            "# Q/A History\n\n## 2026-10-28 · topic · quiz\nQ: Old?\nA: Old.\nVerdict: correct\n",
            encoding="utf-8")
        self.run_wise("import-md")
        self.session(*self.POINTS)
        self.assertIn("flag: 1 answers without the learner's words", self.lint())
