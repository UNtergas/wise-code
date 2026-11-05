"""The senior consult journal: Codex writes it through scripts/consult.py only."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import consult  # noqa: E402


class ConsultCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wise-consult-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        (self.project / ".wise-code").mkdir()
        self.journal = self.project / ".wise-code/consult/journal.md"

    def run_consult(self, *args, day="2026-11-03", cwd=None):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day}
        return subprocess.run([sys.executable, str(ROOT / "scripts/consult.py"), *args],
                              text=True, capture_output=True, env=env, timeout=30,
                              cwd=cwd or self.project)

    def add(self, *extra, day="2026-11-03", disagrees="no"):
        args = ["add", "--kind", "doubt", "--topic", "Retry backoff", "--level", "Hint",
                "--asked", "Is exponential backoff right here?",
                "--tried", "Read the retry loop; knew about jitter",
                "--view", "Backoff is right; the cap is missing",
                "--disagrees", disagrees, "--refs", "src/retry.ts, D-12", *extra]
        return self.run_consult(*args, day=day)


class AddTests(ConsultCase):
    def test_add_appends_one_entry_with_every_field(self):
        result = self.add()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.journal.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^## 2026-11-03 \d\d:\d\d — Retry backoff$")
        for line in ("Kind: doubt", "Level: Hint", "Asked: Is exponential backoff right here?",
                     "Tried / knew: Read the retry loop; knew about jitter",
                     "Senior view: Backoff is right; the cap is missing",
                     "Disagrees with teacher: no", "Refs: src/retry.ts, D-12"):
            self.assertIn(line + "\n", text)

    def test_second_add_keeps_the_first_entry(self):
        self.add()
        self.add(day="2026-11-04")
        self.assertEqual([e.date for e in consult.entries(self.journal)],
                         ["2026-11-03", "2026-11-04"])

    def test_disagreement_needs_what_the_teacher_got_wrong(self):
        result = self.add(disagrees="yes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--what", result.stderr)
        self.assertFalse(self.journal.exists())
        result = self.add("--what", "teacher said no cap is needed", disagrees="yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Disagrees with teacher: yes — teacher said no cap is needed\n",
                      self.journal.read_text(encoding="utf-8"))

    def test_multiline_values_become_one_line(self):
        # One field per line is the format the hook and Claude rely on; a value
        # with a newline could otherwise forge a heading or another field.
        result = self.run_consult("add", "--kind", "doubt", "--topic", "A", "--level", "Pseudo",
                                  "--asked", "first\n## 2026-01-01 00:00 — forged",
                                  "--tried", "x", "--view", "y", "--disagrees", "no")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(consult.entries(self.journal)), 1)
        self.assertIn("Asked: first ## 2026-01-01 00:00 — forged\n",
                      self.journal.read_text(encoding="utf-8"))

    def test_invalid_level_and_disagrees_are_refused(self):
        self.assertEqual(self.add("--level", "Expert").returncode, 2)
        self.assertEqual(self.add(disagrees="maybe").returncode, 2)
        self.assertFalse(self.journal.exists())

    def test_symlinked_journal_or_folder_is_refused(self):
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("", encoding="utf-8")
        self.journal.parent.mkdir()
        self.journal.symlink_to(outside)
        result = self.add()
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(outside.read_text(encoding="utf-8"), "")
        self.journal.unlink()
        self.journal.parent.rmdir()
        (Path(self.temp.name) / "elsewhere").mkdir()
        self.journal.parent.symlink_to(Path(self.temp.name) / "elsewhere")
        self.assertEqual(self.add().returncode, 2)
        self.assertEqual(list((Path(self.temp.name) / "elsewhere").iterdir()), [])

    def test_runs_from_a_subfolder_and_writes_at_the_project_state(self):
        nested = self.project / "src" / "deep"
        nested.mkdir(parents=True)
        result = self.run_consult("add", "--kind", "doubt", "--topic", "T", "--level", "Full code",
                                  "--asked", "a", "--tried", "b", "--view", "c",
                                  "--disagrees", "no", cwd=nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.journal.is_file())

    def test_no_state_folder_creates_nothing(self):
        (self.project / ".wise-code").rmdir()
        result = self.add()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no .wise-code", result.stderr)
        self.assertFalse((self.project / ".wise-code").exists())


class QuestionKindTests(ConsultCase):
    """A question needs no teacher claim, so it carries no disagreement."""

    def question(self, *extra):
        return self.run_consult("add", "--kind", "question", "--topic", "TOML tables",
                                "--level", "Hint", "--asked", "How do nested tables work?",
                                "--tried", "-", "--view", "Look at the TOML spec, Table",
                                "--refs", "https://toml.io/en/v1.0.0#table", *extra)

    def test_question_is_recorded_without_a_verdict(self):
        result = self.question()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.journal.read_text(encoding="utf-8")
        self.assertIn("Kind: question\n", text)
        self.assertNotIn("Disagrees with teacher", text)
        self.assertEqual([(e.date, e.disagrees) for e in consult.entries(self.journal)],
                         [("2026-11-03", False)])

    def test_question_refuses_a_verdict(self):
        result = self.question("--disagrees", "yes", "--what", "x")
        self.assertEqual(result.returncode, 2)
        self.assertIn("question", result.stderr)
        self.assertFalse(self.journal.exists())

    def test_doubt_needs_a_verdict_and_kind_is_required(self):
        result = self.run_consult("add", "--kind", "doubt", "--topic", "t", "--level", "Hint",
                                  "--asked", "a", "--tried", "b", "--view", "c")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--disagrees", result.stderr)
        result = self.run_consult("add", "--topic", "t", "--level", "Hint", "--asked", "a",
                                  "--tried", "b", "--view", "c", "--disagrees", "no")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.journal.exists())


class EntriesTests(ConsultCase):
    def test_entries_report_date_and_disagreement(self):
        self.add(day="2026-11-01")
        self.add("--what", "wrong cap", day="2026-11-03", disagrees="yes")
        found = consult.entries(self.journal)
        self.assertEqual([(e.date, e.disagrees) for e in found],
                         [("2026-11-01", False), ("2026-11-03", True)])

    def test_missing_or_symlinked_journal_has_no_entries(self):
        self.assertEqual(consult.entries(self.journal), [])
        self.journal.parent.mkdir()
        target = Path(self.temp.name) / "t.md"
        target.write_text("## 2026-11-03 10:00 — x\nDisagrees with teacher: yes — y\n",
                          encoding="utf-8")
        self.journal.symlink_to(target)
        self.assertEqual(consult.entries(self.journal), [])



class AcknowledgeTests(ConsultCase):
    """Review #31: the teacher acknowledges each consult explicitly."""

    def ids(self):
        out = self.run_consult("pending")
        self.assertEqual(out.returncode, 0, out.stderr)
        return [line.split()[0] for line in out.stdout.splitlines() if line.strip()]

    def test_new_consults_are_pending_until_acknowledged_one_by_one(self):
        self.add(day="2026-11-03")
        self.add("--topic", "Second", "--what", "cap", day="2026-11-03", disagrees="yes")
        first, second = self.ids()
        self.assertNotEqual(first, second)  # same day, separate ids
        self.assertIn("disagrees", self.run_consult("pending").stdout.splitlines()[1])
        result = self.run_consult("ack", first)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ids(), [second])
        self.assertEqual(self.run_consult("ack", first).returncode, 0)  # idempotent
        self.assertEqual(self.ids(), [second])

    def test_ids_stay_stable_when_codex_appends(self):
        self.add(day="2026-11-03")
        [first] = self.ids()
        self.add(day="2026-11-05")
        self.assertEqual(self.ids()[0], first)

    def test_acknowledgment_lives_outside_the_codex_folder_and_journal_is_untouched(self):
        self.add()
        before = self.journal.read_bytes()
        [entry] = self.ids()
        self.run_consult("ack", entry)
        self.assertEqual(self.journal.read_bytes(), before)
        acks = self.project / ".wise-code/consult-acks.txt"
        self.assertIn(entry, acks.read_text(encoding="utf-8"))
        self.assertNotIn(self.project / ".wise-code/consult", acks.parents)

    def test_unknown_id_is_refused_and_nothing_is_acknowledged(self):
        self.add()
        [entry] = self.ids()
        result = self.run_consult("ack", entry, "c-000000000000")
        self.assertEqual(result.returncode, 2)
        self.assertIn("c-000000000000", result.stderr)
        self.assertEqual(self.ids(), [entry])

    def test_symlinked_acknowledgments_are_refused(self):
        self.add()
        [entry] = self.ids()
        target = Path(self.temp.name) / "elsewhere.txt"
        (self.project / ".wise-code/consult-acks.txt").symlink_to(target)
        result = self.run_consult("ack", entry)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
