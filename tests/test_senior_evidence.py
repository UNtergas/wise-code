"""A consult becomes learning evidence: a doubt the teacher went through
leaves a record in the graph, and the session's lint says when it didn't."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The module, not its classes: a test class imported by name is collected again here.
import test_consult as base  # noqa: E402

consult = base.consult


class Case(base.ConsultCase):
    def wise(self, *args, day="2026-11-03", ok=True, pasted=None):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day}
        result = subprocess.run([sys.executable, str(ROOT / "scripts/wise.py"), *args],
                                text=True, capture_output=True, env=env, timeout=30,
                                cwd=self.project, input=pasted)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr + result.stdout)
        return result.stdout if ok else result.stderr

    def senior(self, *args, ok=True, day="2026-11-03"):
        result = self.run_consult(*args, day=day)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr + result.stdout)
        return result.stdout if ok else result.stderr

    def session(self, day="2026-11-03"):
        return self.wise("add", "session", "goal=Work", "checkpoints+=A?", "checkpoints+=B?",
                         "checkpoints+=C?", day=day).strip()

    def node(self, node_id):
        text = self.wise("show", node_id)
        return json.loads(text[text.index("{"):text.rindex("}") + 1])


class ConsultEvidenceTests(Case):
    def doubt(self, disagrees="no", day="2026-11-03"):
        extra = ["--what", "the cap is needed"] if disagrees == "yes" else []
        self.add(*extra, disagrees=disagrees, day=day)
        return consult.entries(self.journal)[-1].id

    def close(self, cid, disagrees="no"):
        outcome = ["--outcome", "stands", "--note", "docs"] if disagrees == "yes" else []
        self.senior("ack", cid, *outcome)

    def record(self, cid):
        return self.wise("add", "qa", "source=consult", "q=Is exponential backoff right here?",
                         "a=Yes; the cap was the missing part", "verdict=n/a",
                         f"consult={cid}").strip()

    def test_a_doubt_gone_through_without_a_record_is_flagged(self):
        cid = self.doubt()
        self.close(cid)
        self.session()
        self.assertIn(f"flag: 1 senior doubts gone through without a record in the graph: {cid}",
                      self.wise("lint-session"))

    def test_the_record_names_its_consult_and_clears_the_flag(self):
        cid = self.doubt(disagrees="yes")
        self.close(cid, disagrees="yes")
        qa = self.record(cid)
        self.assertEqual(self.node(qa)["consult"], cid)
        self.session()
        self.assertNotIn("without a record", self.wise("lint-session"))
        self.assertIn("consult ·", self.wise("history", "--source", "consult"))

    def test_a_consult_record_needs_a_real_looking_consult_id(self):
        for bad in ([], ["consult=the backoff one"]):
            error = self.wise("add", "qa", "source=consult", "q=Q", "a=A", "verdict=n/a", *bad,
                              ok=False)
            self.assertIn("consult=c-", error)

    def test_a_doubt_is_never_recorded_as_a_wrong_answer(self):
        cid = self.doubt()
        error = self.wise("add", "qa", "source=consult", "q=Q", "a=A", "verdict=wrong",
                          f"consult={cid}", ok=False)
        self.assertIn("verdict=n/a", error)
        self.assertEqual(self.wise("history"), "no matching history\n")

    def test_questions_and_pending_or_older_doubts_are_not_flagged(self):
        self.run_consult("add", "--kind", "question", "--topic", "serde", "--level", "Hint",
                         "--asked", "a", "--tried", "b", "--view", "c")
        self.senior("ack", consult.entries(self.journal)[-1].id)
        self.doubt()                                   # still pending: not gone through
        old = self.doubt(day="2026-10-20")
        self.close(old)
        self.session(day="2026-10-25")                 # the old doubt belongs to this one
        self.session()
        self.assertNotIn("without a record", self.wise("lint-session"))


class GuideTests(unittest.TestCase):
    def test_the_teacher_records_a_doubt_after_closing_it(self):
        behavior = (ROOT / "skills/learn/behavior.md").read_text(encoding="utf-8")
        section = behavior[behavior.index("**Senior consults.**"):
                           behavior.index("**Prerequisites.**")]
        for rule in ("source=consult", "consult=<id>", "not a wrong answer",
                     "wise.py add question"):
            self.assertIn(rule, section)
