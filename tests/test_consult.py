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
        args = ["add", "--topic", "Retry backoff", "--level", "Hint",
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
        for line in ("Level: Hint", "Asked: Is exponential backoff right here?",
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
        result = self.run_consult("add", "--topic", "A", "--level", "Pseudo",
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
        result = self.run_consult("add", "--topic", "T", "--level", "Full code",
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


if __name__ == "__main__":
    unittest.main()
