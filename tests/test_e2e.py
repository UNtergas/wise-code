"""End to end: one learner, one project, two weeks, through the real entry
points (the session hook as Claude Code registers it, and wise.py as the
skills call it). Each stage checks what the learner or Claude would see next,
and the graph must pass `wise.py check` after every day.

Unit tests cover each rule's edges. This file covers the joins between them:
what one command writes is what the next one reads.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wise.py"
HOOK = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))[
    "hooks"]["SessionStart"][0]["hooks"][0]["command"]

# What the learner typed, by day. Every quote recorded below is cut from here,
# so `check-said` can find each one in the transcript.
TYPED = {
    "owner": "high: the owner frees the value when it goes out of scope",
    "alias": "high: two mutable borrows are fine as long as only one writes",
    "recall": "we split take_names so it borrows the slice, and I learned a borrow "
              "ends at its last use, not at the closing brace",
    "clone": "mid: because clone copies the whole Vec just to read it",
    "partial": "mid: the compiler tracks who can write to the data",
    "repair": "high: two mutable borrows could alias the same data, so a write "
              "through one would invalidate the other",
    "unsure": "low: only one mutable borrow can exist, since two could alias",
    "sure": "high: only one mutable borrow can exist, and none while a shared one is alive",
    "variant": "high: push needs a mutable borrow of the Vec while first still borrows it",
    "unprefixed": "the borrow ends when it is last used",
}


def said(key):
    """The learner's words without the confidence prefix they typed."""
    text = TYPED[key]
    return text.split(": ", 1)[1] if text.split(":")[0] in ("low", "mid", "high") else text


class LearnerJourney(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="wise-e2e-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / "project"
        (self.project / ".git").mkdir(parents=True)
        self.transcripts = self.base / "transcripts"
        self.transcripts.mkdir()
        (self.transcripts / "s1.jsonl").write_text("\n".join(
            json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            for text in TYPED.values()) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ entry points

    def wise(self, day, *args, ok=True):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day,
               "HOME": str(self.base / "home")}
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.project),
                                 *args], text=True, capture_output=True, env=env, timeout=60)
        if ok:
            self.assertEqual(result.returncode, 0, f"{args}\n{result.stderr}{result.stdout}")
            return result.stdout
        self.assertEqual(result.returncode, 2, f"{args}\n{result.stderr}{result.stdout}")
        return result.stderr

    def hook(self, day, source="startup"):
        """Run the SessionStart hook the way hooks.json registers it."""
        payload = json.dumps({"hook_event_name": "SessionStart", "source": source,
                              "cwd": str(self.project)})
        result = subprocess.run(
            HOOK, shell=True, input=payload, text=True, capture_output=True, timeout=60,
            cwd=self.base, env={
                "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath)),
                "CLAUDE_PLUGIN_ROOT": str(ROOT), "HOME": str(self.base / "home"),
                "WISE_TODAY": day})
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        if not result.stdout:
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def onboard(self, mode="active"):
        """What Learn's onboarding leaves behind: the profile that turns the hook on."""
        state = self.project / ".wise-code"
        state.mkdir(exist_ok=True)
        (state / "profile.md").write_text(
            f"# Learner Profile\nLearning mode: {mode}\nOnboarding: complete\n"
            "Assist level: Hint\nLevel overrides: Rust: Example\n", encoding="utf-8")

    def first_id(self, output):
        return output.split()[0]

    def end_of_day(self, day):
        self.wise(day, "check-said", "--transcripts", str(self.transcripts))
        self.assertIn("ok · ", self.wise(day, "check"))

    # ------------------------------------------------------------ the journey

    def test_two_weeks_of_one_learner(self):
        d1, d2, d3, d4, d11 = ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
                               "2026-11-12")

        # ---- Day 1: a fresh project. The hook stays silent and writes nothing.
        self.assertIsNone(self.hook(d1))
        self.assertEqual([p.name for p in self.project.iterdir()], [".git"])

        # Onboarding, then concepts and what rests on what. Borrowing can't be
        # built on yet.
        self.onboard()
        self.wise(d1, "add", "concept", "name=Ownership")
        self.wise(d1, "add", "concept", "name=Borrowing")
        self.wise(d1, "link", "borrowing", "prereq", "ownership")
        ready = self.wise(d1, "ready", "borrowing")
        self.assertIn("borrowing · not ready: 1 prerequisites to cover first", ready)
        self.assertIn("first: ownership · introduced", ready)

        # The prerequisite is asked, answered and marked; now the step can go on.
        self.wise(d1, "add", "qa", "source=checkpoint", "q=Who frees a value?",
                  "a=its owner, at end of scope", "verdict=correct", "confidence=high",
                  f"said={said('owner')}", "--about", "ownership")
        self.wise(d1, "set", "ownership", "status=demonstrated")
        self.assertEqual(self.wise(d1, "ready", "borrowing"), "borrowing · ready\n")

        # Full code step, then the explain-back: sure, and wrong. That is a confusion.
        missed = self.wise(d1, "add", "qa", "source=explain-back",
                           "q=Why does the compiler reject the second &mut here?",
                           "a=thinks two &mut are fine", "verdict=wrong", "confidence=high",
                           f"said={said('alias')}", "--about", "borrowing")
        self.assertIn("confusion:", missed)
        missed_id = self.first_id(missed)
        self.assertIn(missed_id, self.wise(d1, "confusions"))
        self.assertIn("sure but missed", self.wise(d1, "calibration"))

        # The miss becomes a question with its rubric, and a task to do in code.
        self.assertIn("points", self.wise(d1, "add", "question", "q=Why only one &mut?",
                                          "a=aliasing", ok=False))
        question = self.wise(
            d1, "add", "question", "q=Why can only one &mut borrow exist at a time?",
            "a=Two could alias; a write through one invalidates the other.",
            "points+=two mutable borrows could alias the same data",
            "points+=a write through one would invalidate the other",
            "--tests", "borrowing").strip()
        task = self.wise(
            d1, "add", "question", "q=Make take_names compile without clone",
            "a=Borrow the slice", "check=cargo test --manifest-path .wise-code/scratch/t/Cargo.toml",
            "--tests", "ownership").strip()

        # Session end: the recap, then the process check. One Full code step, one
        # explain-back, every answer quoted and prefixed: nothing to flag.
        first = self.wise(
            d1, "add", "session", "goal=Borrow names instead of cloning",
            "finished+=take_names borrows the slice", "learned+=A borrow ends at its last use",
            "checkpoints+=Why does take_names borrow the slice?",
            "checkpoints+=When does a borrow end?",
            "checkpoints+=Why was clone the wrong fix?", "full_steps=1").strip()
        self.end_of_day(d1)
        self.assertEqual(self.wise(d1, "lint-session").splitlines(),
                         [f"{first} · {d1} · 2 answers", "no flags"])

        # That evening, after the recap, one more question to Claude. It belongs
        # to no session yet; tomorrow's session must take it.
        self.wise(d1, "add", "qa", "source=asked", "q=Is Rc a borrow?", "a=No, shared ownership",
                  "verdict=n/a", "--about", "ownership")

        # ---- Day 2: the hook announces the start check and the backlog, as counts.
        context = self.hook(d2)
        self.assertIn("free recall of the last session from memory", context)
        self.assertIn("2 questions are due for review", context)
        self.assertNotIn("take_names", context)

        pending = self.wise(d2, "session", "--pending")
        self.assertIn("checkpoints: 3. Why was clone the wrong fix?", pending)

        # Free recall covers two of three check points; the script says what to ask.
        recall = self.wise(d2, "start-check", "recall", first, "--covers", "1,2",
                           "--said", said("recall"))
        self.assertIn("· partial · recalled 2 of 3 check points", recall)
        self.assertIn("ask next: 3. Why was clone the wrong fix?", recall)
        self.wise(d2, "start-check", "point", first, "3", "correct", "--said", said("clone"),
                  "--confidence", "mid", "--about", "ownership")
        self.assertIn(f"{first} · start check done {d2} · 3/3",
                      self.wise(d2, "start-check", "done", first))
        self.assertEqual(self.wise(d2, "session", "--pending"), "no pending start check\n")

        # Quiz. One point of two: `correct` is refused, `partial` is recorded
        # with the missed point, and the question stays in box 1.
        due = self.wise(d2, "due")
        self.assertIn(f"{question} ·", due)
        self.assertIn(f"{task} ·", due)
        self.assertIn("· task: cargo test", due)
        self.assertIn("1 of 2 key points hit: the verdict can be at most partial",
                      self.wise(d2, "answer", question, "correct", "--hit", "1",
                                "--said", said("partial"), ok=False))
        self.assertIn("--said", self.wise(d2, "answer", question, "partial", "--hit", "1",
                                          ok=False))
        self.assertIn(f"{question} now box 1 · due {d3}",
                      self.wise(d2, "answer", question, "partial", "--hit", "1",
                                "--said", said("partial"), "--confidence", "mid"))
        self.assertIn("  missed: a write through one would invalidate the other",
                      self.wise(d2, "history", "--full", "--source", "quiz"))

        # The task: the check fails, so only `wrong` is accepted.
        self.assertIn("the check exited 101: the verdict can only be wrong",
                      self.wise(d2, "answer", task, "correct", "--exit", "101", ok=False))
        self.wise(d2, "answer", task, "wrong", "--exit", "101")

        # Yesterday's confusion gates the next borrowing step until it is
        # repaired with a different question.
        self.assertIn(missed_id, self.wise(d2, "confusions", "--concept", "borrowing"))
        self.wise(d2, "add", "qa", "source=repair",
                  "q=What could go wrong if two &mut to one Vec existed?",
                  "a=aliasing, invalidated writes", "verdict=correct", "confidence=high",
                  f"said={said('repair')}", "--about", "borrowing", "--repairs", missed_id)
        self.assertNotIn(missed_id, self.wise(d2, "confusions", "--concept", "borrowing"))

        # One checkpoint answer came without a prefix: the session's lint says so.
        self.wise(d2, "add", "qa", "source=checkpoint", "q=When does this borrow end?",
                  "a=at last use", "verdict=correct", f"said={said('unprefixed')}",
                  "--about", "borrowing")
        second = self.wise(d2, "add", "session", "goal=Fix the aliasing confusion",
                           "checkpoints+=Why can't two &mut alias?",
                           "checkpoints+=What does the task's test check?",
                           "checkpoints+=When is clone the right call?").strip()
        self.end_of_day(d2)
        lint = self.wise(d2, "lint-session")
        self.assertIn(f"{second} · {d2} · 7 answers", lint)  # six today, one from last evening
        self.assertEqual([line for line in lint.splitlines() if line.startswith("flag:")],
                         ["flag: 1 of 3 answers without a confidence prefix"])
        self.assertIn("no confidence: 1 of 5 ", self.wise(d2, "calibration"))

        # Borrowing was missed twice (explain-back, quiz) and answered right
        # twice since (repair, checkpoint): it has recovered. Ownership has one
        # open miss from the failed task.
        weak = self.wise(d2, "weak")
        self.assertNotIn("borrowing ·", weak)
        self.assertIn("ownership · concept", weak)
        self.assertIn("open misses 1", weak)

        # ---- Day 3: right but unsure does not move the question up.
        self.wise(d3, "start-check", "skip", second)
        kept = self.wise(d3, "answer", question, "correct", "--hit", "all",
                         "--said", said("unsure"), "--confidence", "low")
        self.assertIn(f"now box 1 · due {d4} · kept in its box: low confidence", kept)

        # ---- Day 4 and day 11: sure and right, twice. Box 3.
        self.assertIn("now box 2", self.wise(d4, "answer", question, "correct", "--hit", "all",
                                             "--said", said("sure"), "--confidence", "high"))
        self.assertIn("now box 3", self.wise("2026-11-08", "answer", question, "correct",
                                             "--hit", "all", "--said", said("sure"),
                                             "--confidence", "high"))
        self.assertIn("now box 2", self.wise(d4, "answer", task, "correct", "--exit", "0"))

        # From box 3 the same words are not asked again: a variant, recorded as asked.
        # Box 3 means seven days: on day 11 only the task is back.
        waiting = self.wise(d11, "due")
        self.assertIn(f"{task} ·", waiting)
        self.assertNotIn(question, waiting)
        later = "2026-11-16"
        self.assertIn("2 questions are due for review", self.hook(later, source="clear"))
        self.assertNotIn("due for review", self.hook(later, source="compact"))
        line = [l for l in self.wise(later, "due").splitlines() if l.startswith(question)][0]
        self.assertTrue(line.endswith("· ask a variant"), line)
        asked = "Why can't you push to a Vec while holding a reference to its first item?"
        self.wise(later, "answer", question, "correct", "--hit", "all", "--asked", asked,
                  "--said", said("variant"), "--confidence", "high")
        history = self.wise(later, "history", "--full", "--source", "quiz", "--since", later)
        self.assertIn(f"Q: {asked}", history)
        self.assertIn("Why can only one &mut borrow exist at a time?",
                      self.wise(later, "show", question))

        # Less help? Over the default month borrowing still holds a miss, a
        # partial and an unsure answer, so no. Over the last nine days its two
        # answers were clean; ownership has none there and an open confusion.
        self.assertEqual(self.wise(later, "level-advice"),
                         "no concept is ready for less help yet\n")
        self.assertEqual(self.wise(later, "level-advice", "--days", "9", "--min", "2"),
                         "less help: borrowing · 2 answers · 2 correct · no hints\n")

        # A card whose front Anki would read as a comment leaves quoted.
        self.wise(later, "add", "card", "front=#[derive(Clone)] gives a type what?",
                  "back=A clone() method", "--tests", "ownership")
        self.wise(later, "export", "anki")
        cards = (self.project / ".wise-code" / "cards.tsv").read_text(encoding="utf-8")
        self.assertIn('\n"#[derive(Clone)] gives a type what?"\tA clone() method\t', cards)

        # The whole graph is still valid, every quote was found in the
        # transcript, and reading it back changes nothing.
        self.end_of_day(later)
        self.assertNotIn("unchecked", self.wise(later, "history", "--full"))
        self.assertNotIn("missing", self.wise(later, "history", "--full"))
        graph = self.project / ".wise-code" / "graph"
        before = {p.name: p.read_bytes() for p in graph.glob("*.jsonl")}
        for command in (("stats",), ("due",), ("weak",), ("confusions",), ("calibration",),
                        ("lint-session",), ("level-advice",), ("render", "progress")):
            self.wise(later, *command)
        self.assertEqual({p.name: p.read_bytes() for p in graph.glob("*.jsonl")}, before)

        # Pausing learning silences the hook; the graph stays where it is.
        self.onboard(mode="paused")
        self.assertIsNone(self.hook(later))
        self.assertEqual({p.name: p.read_bytes() for p in graph.glob("*.jsonl")}, before)
        self.assertTrue(set(p.name for p in self.project.iterdir()) <= {".git", ".wise-code"})


if __name__ == "__main__":
    unittest.main()
