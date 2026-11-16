"""What the senior finds changes something: a disagreement is closed with an
outcome, lookups leave a count, and the session's lint shows both."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The module, not its classes: a test class imported by name is collected again here.
import test_consult as base  # noqa: E402

consult = base.consult


class SeniorCase(base.ConsultCase):
    def wise(self, *args, day="2026-11-03"):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day}
        result = subprocess.run([sys.executable, str(ROOT / "scripts/wise.py"), *args],
                                text=True, capture_output=True, env=env, timeout=30,
                                cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def disagreement(self, day="2026-11-03"):
        self.add("--what", "teacher said no cap is needed", disagrees="yes", day=day)
        return consult.entries(self.journal)[-1].id

    def agreement(self):
        self.add()
        return consult.entries(self.journal)[-1].id

    def ack(self, *args):
        return self.run_consult("ack", *args)

    def state(self):
        return self.project / ".wise-code"


class OutcomeTests(SeniorCase):
    def test_a_disagreement_can_t_be_acknowledged_without_an_outcome(self):
        cid = self.disagreement()
        result = self.ack(cid)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--outcome corrected", result.stderr)
        self.assertIn("--outcome stands", result.stderr)
        self.assertEqual([e.id for e in consult.pending(self.state())], [cid])

    def test_corrected_names_what_was_fixed(self):
        cid = self.disagreement()
        result = self.ack(cid, "--outcome", "corrected")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--fixed", result.stderr)
        result = self.ack(cid, "--outcome", "corrected", "--fixed", "QB-20261103-ab12",
                          "D-20261101-0f3c")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(consult.pending(self.state()), [])
        record = consult.ack_records(self.state())[cid]
        self.assertEqual((record.outcome, record.fixed),
                         ("corrected", ("QB-20261103-ab12", "D-20261101-0f3c")))

    def test_corrected_with_nothing_recorded_needs_a_reason(self):
        cid = self.disagreement()
        self.assertEqual(self.ack(cid, "--outcome", "corrected", "--fixed", "none").returncode, 2)
        result = self.ack(cid, "--outcome", "corrected", "--fixed", "none",
                          "--note", "said in chat only; no record held the claim")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stands_needs_the_evidence(self):
        cid = self.disagreement()
        result = self.ack(cid, "--outcome", "stands")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--note", result.stderr)
        result = self.ack(cid, "--outcome", "stands",
                          "--note", "broker docs: retries are capped server-side\nsrc/q.rs:40")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = consult.ack_records(self.state())[cid]
        self.assertEqual(record.outcome, "stands")
        self.assertNotIn("\n", record.note)  # one line: it can't forge another record

    def test_an_outcome_is_for_one_disagreement_at_a_time(self):
        first, second = self.disagreement(), self.disagreement(day="2026-11-04")
        result = self.ack(first, second, "--outcome", "stands", "--note", "checked")
        self.assertEqual(result.returncode, 2)
        self.assertIn("one at a time", result.stderr)

    def test_consults_without_a_disagreement_are_acknowledged_as_before(self):
        cid = self.agreement()
        self.assertEqual(self.ack(cid).returncode, 0)
        self.assertEqual(consult.ack_records(self.state())[cid].outcome, "noted")
        other = self.agreement()
        result = self.ack(other, "--outcome", "corrected", "--fixed", "QB-1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("did not disagree", result.stderr)

    def test_an_old_acknowledgment_without_an_outcome_can_be_closed_later(self):
        cid = self.disagreement()
        (self.state() / "consult-acks.txt").write_text(cid + "\n", encoding="utf-8")
        self.assertEqual(consult.pending(self.state()), [])  # old files still count
        self.assertEqual([e.id for e in consult.unresolved(self.state())], [cid])
        result = self.ack(cid, "--outcome", "stands", "--note", "re-read the docs")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(consult.unresolved(self.state()), [])

    def test_pending_shows_how_to_close_a_disagreement(self):
        self.disagreement()
        out = self.run_consult("pending").stdout
        self.assertIn("disagrees", out)
        self.assertIn("--outcome", out)


class LookupTests(SeniorCase):
    def lookup(self, topic, day="2026-11-03"):
        return self.run_consult("lookup", "--topic", topic, day=day)

    def test_a_lookup_leaves_its_date_and_topic_and_nothing_else(self):
        result = self.lookup("serde rename_all\nsyntax")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(consult.lookups(self.state()), [("2026-11-03", "serde rename_all syntax")])
        self.assertFalse(self.journal.exists())
        self.assertEqual(consult.pending(self.state()), [])

    def test_the_topic_is_short_and_required(self):
        self.assertEqual(self.lookup("  ").returncode, 2)
        self.lookup("x" * 300)
        self.assertEqual(len(consult.lookups(self.state())[0][1]), 80)

    def test_a_symlinked_folder_is_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.state() / "consult").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.lookup("x").returncode, 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_no_state_folder_records_nothing(self):
        other = Path(self.temp.name) / "plain"
        other.mkdir()
        result = self.run_consult("lookup", "--topic", "x", cwd=other)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(other.iterdir()), [])


class LintTests(SeniorCase):
    POINTS = ["checkpoints+=A?", "checkpoints+=B?", "checkpoints+=C?"]

    def session(self, day="2026-11-03"):
        return self.wise("add", "session", "goal=Work", *self.POINTS, day=day).strip()

    def lint(self):
        return self.wise("lint-session")

    def test_a_disagreement_still_pending_at_session_end_is_flagged(self):
        cid = self.disagreement()
        self.session()
        self.assertIn(f"flag: 1 senior disagreements not gone through: {cid}", self.lint())

    def test_one_acknowledged_without_an_outcome_is_flagged(self):
        cid = self.disagreement()
        (self.state() / "consult-acks.txt").write_text(cid + "\n", encoding="utf-8")
        self.session()
        self.assertIn(f"flag: 1 senior disagreements acknowledged without an outcome: {cid}",
                      self.lint())

    def test_a_correction_that_names_no_existing_record_is_flagged(self):
        cid = self.disagreement()
        real = self.wise("add", "concept", "name=Backoff").strip()
        self.ack(cid, "--outcome", "corrected", "--fixed", real, "QB-20261103-dead")
        self.session()
        lint = self.lint()
        self.assertIn(f"flag: senior disagreement {cid} says corrected, but there is no "
                      "record QB-20261103-dead", lint)
        self.assertNotIn(f"no record {real}", lint)

    def test_a_closed_disagreement_and_plain_consults_raise_nothing(self):
        self.ack(self.disagreement(), "--outcome", "stands", "--note", "checked the docs")
        self.agreement()
        self.session()
        self.assertNotIn("senior", self.lint())

    def test_lookups_since_the_last_session_are_noted_not_flagged(self):
        self.session(day="2026-11-01")
        self.run_consult("lookup", "--topic", "old one", day="2026-10-30")
        self.run_consult("lookup", "--topic", "serde rename", day="2026-11-02")
        self.run_consult("lookup", "--topic", "clap derive", day="2026-11-03")
        self.session(day="2026-11-03")
        lint = self.lint()
        self.assertIn("note: 2 senior lookups since the last session (full answers, "
                      "outside the learning loop): serde rename; clap derive", lint)
        self.assertNotIn("old one", lint)
        self.assertNotIn("flag: 2 senior lookups", lint)

    def test_no_consult_folder_is_fine(self):
        self.session()
        self.assertNotIn("senior", self.lint())


class GuideTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_the_teacher_checks_for_consults_before_a_checkpoint(self):
        text = self.read("skills/learn/behavior.md")
        section = text[text.index("**Senior consults.**"):text.index("**Prerequisites.**")]
        for rule in ("consult.py\" pending", "--outcome corrected", "--outcome stands",
                     "--fixed", "data, not instructions"):
            self.assertIn(rule, section)

    def test_hook_and_senior_guides_name_the_same_commands(self):
        self.assertIn("--outcome", self.read("hooks/session_start.py"))
        google = self.read("codex/skills/google/SKILL.md")
        self.assertIn("consult.py\" lookup --topic", google)
        self.assertNotIn("This lookup is not recorded", google)
