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
