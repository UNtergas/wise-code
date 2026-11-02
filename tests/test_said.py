"""Learner's words: quotes are required, checked against transcripts, recalled as quotes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wise.py"
sys.path.insert(0, str(ROOT / "scripts"))

import wise  # noqa: E402


def user(content, **flags):
    return {"type": "user", "message": {"role": "user", "content": content}, **flags}


TRANSCRIPT = [
    user("I’d go with SQLite, one file per user — keeps backups trivial"),
    user([{"type": "text", "text": "<command-args>grill storage</command-args> use the "
           "outbox pattern for retries"}]),
    # Everything below holds "we need concurrency", and none of it is the learner.
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Postgres, since we need concurrency"}]}},
    user("Summary: the learner said we need concurrency", isCompactSummary=True),
    user([{"type": "tool_result", "content": "we need concurrency"}]),
    user("Agent prompt: assume we need concurrency", isSidechain=True),
    user("<system-reminder>we need concurrency here</system-reminder> ok then"),
    user("meta: we need concurrency", isMeta=True),
    user("Continue: we need concurrency", textNotTyped=True),
]


class SaidTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.project = base / "project"
        (self.project / ".git").mkdir(parents=True)
        self.config = base / "claude"
        self.transcripts = self.config / "projects" / wise.encode_project_dir(self.project)[0]
        self.transcripts.mkdir(parents=True)
        (self.transcripts / "s1.jsonl").write_text(
            "\n".join(json.dumps(e) for e in TRANSCRIPT) + "\nnot json\n", encoding="utf-8")

    def run_wise(self, *args, check=True, config=True):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": "2026-11-02",
               "HOME": str(self.project.parent)}
        if config:
            env["CLAUDE_CONFIG_DIR"] = str(self.config)
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.project), *args],
                                text=True, capture_output=True, env=env, timeout=30)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def out(self, *args, **kwargs):
        return self.run_wise(*args, **kwargs).stdout

    def decision(self, said, by="learner"):
        return self.out("add", "decision", "title=Storage", "status=settled", f"by={by}",
                        "outcome=SQLite", f"said={said}").strip()

    def node(self, node_id):
        path = self.project / ".wise-code" / "graph" / "nodes.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            node = json.loads(line)
            if node["id"] == node_id:
                return node
        raise KeyError(node_id)

    # ---- the write rule

    def test_learner_records_without_a_quote_are_refused(self):
        for args in (["add", "decision", "title=T", "status=settled", "by=learner"],
                     ["add", "decision", "title=T", "status=settled", "by=both"],
                     *[["add", "qa", f"source={s}", "q=Q", "a=A"]
                       for s in wise.LEARNER_QA_SOURCES]):
            with self.subTest(args=args):
                bad = self.run_wise(*args, check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("said=", bad.stderr)

    def test_ai_and_pending_records_need_no_quote(self):
        self.run_wise("add", "decision", "title=T", "status=settled", "by=ai", "outcome=x")
        self.run_wise("add", "decision", "title=T", "proposal=x", "by=learner")
        for source in ("asked", "review", "quiz", "critique"):
            self.run_wise("add", "qa", f"source={source}", "q=Q", "a=A")

    def test_settling_a_learner_decision_needs_a_quote_and_failure_changes_nothing(self):
        did = self.out("add", "decision", "title=T", "proposal=x", "by=learner").strip()
        bad = self.run_wise("set", did, "status=settled", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(self.node(did)["status"], "pending")

    def test_quotes_are_three_to_forty_words_per_part(self):
        for said in ("yes", "ok go", "one two three … no", " ".join(["w"] * 41)):
            with self.subTest(said=said[:20]):
                self.assertEqual(self.run_wise("add", "decision", "title=T", "status=settled",
                                               "by=learner", f"said={said}",
                                               check=False).returncode, 2)

    def test_blank_or_separator_only_quotes_are_refused(self):
        # Review: these passed the gate and check-said then marked them ok.
        for said in (" ", "…", " … ", " …  … "):
            with self.subTest(said=said):
                for by in ("learner", "ai"):
                    bad = self.run_wise("add", "decision", "title=T", "status=settled",
                                        f"by={by}", f"said={said}", check=False)
                    self.assertEqual(bad.returncode, 2)
        self.assertEqual(wise.said_status([], ["anything"]), "missing")

    def test_a_learners_own_ellipsis_stays_inside_the_quote(self):
        self.assertEqual(wise.said_parts("well… go with SQLite then"),
                         ["well… go with SQLite then"])
        self.assertEqual(wise.said_parts("go with SQLite … keeps backups trivial"),
                         ["go with SQLite", "keeps backups trivial"])
        self.decision("well… go with SQLite then")

    def test_a_failed_set_writes_nothing(self):
        session = self.out("add", "session", "goal=G").strip()
        bad = self.run_wise("set", session, "goal=", "finished+=leaked", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("finished", self.node(session))

    def test_said_check_is_set_only_by_the_checker(self):
        did = self.decision("go with SQLite, one file")
        self.assertEqual(self.node(did)["said_check"], "unchecked")
        for cmd in (["set", did, "said_check=ok"],
                    ["add", "qa", "source=asked", "q=Q", "a=A", "said_check=ok"]):
            self.assertIn("only by check-said", self.run_wise(*cmd, check=False).stderr)

    def test_changing_a_quote_resets_its_check(self):
        did = self.decision("go with SQLite, one file")
        self.run_wise("check-said")
        self.assertEqual(self.node(did)["said_check"], "ok")
        self.run_wise("set", did, "said=keeps backups trivial")
        self.assertEqual(self.node(did)["said_check"], "unchecked")

    def test_answer_takes_an_optional_quote(self):
        self.run_wise("add", "concept", "name=Ownership")
        qid = self.out("add", "question", "q=Who frees it?", "a=The owner",
                       "--tests", "ownership").strip()
        self.run_wise("answer", qid, "correct")
        self.assertIn("said", self.run_wise("answer", qid, "correct", "--said", "no",
                                            check=False).stderr)
        self.run_wise("answer", qid, "correct", "--said", "the owner frees it")

    # ---- the checker

    def test_the_learners_own_words_match_up_to_case_spacing_and_typography(self):
        ok = self.decision("I'd go with SQLITE,  one file per user - keeps backups trivial")
        parts = self.decision("go with SQLite … use the outbox pattern for retries")
        self.assertIn("ok 2", self.out("check-said"))
        self.assertEqual(self.node(ok)["said_check"], "ok")
        self.assertEqual(self.node(parts)["said_check"], "ok")

    def test_words_the_learner_never_typed_are_missing(self):
        # Present in Claude's reply, a compaction summary, a tool result, a
        # sub-agent prompt, a reminder and a meta line; never typed by the learner.
        invented = self.decision("we need concurrency")
        half = self.decision("go with SQLite … we need concurrency")
        out = self.out("check-said")
        self.assertIn("missing 2", out)
        self.assertIn(f"missing: {invented}", out)
        self.assertEqual(self.node(half)["said_check"], "missing")

    def test_reflections_are_checked_on_their_text(self):
        good = self.out("add", "reflection", "text=use the outbox pattern for retries").strip()
        edited = self.out("add", "reflection", "text=I learned the outbox pattern").strip()
        self.run_wise("check-said")
        self.assertEqual(self.node(good)["said_check"], "ok")
        self.assertEqual(self.node(edited)["said_check"], "missing")

    def test_no_transcript_means_unverified_never_ok(self):
        did = self.decision("go with SQLite, one file")
        out = self.out("check-said", config=False)
        self.assertIn("marked unverified", out)
        self.assertEqual(self.node(did)["said_check"], "unverified")

    def test_only_this_projects_transcripts_are_read(self):
        did = self.decision("words from another project")
        other = self.config / "projects" / "-somewhere-else"
        other.mkdir()
        (other / "s.jsonl").write_text(json.dumps(user("words from another project")),
                                       encoding="utf-8")
        self.run_wise("check-said")
        self.assertEqual(self.node(did)["said_check"], "missing")

    def test_ok_quotes_are_skipped_unless_asked(self):
        self.decision("go with SQLite, one file")
        self.run_wise("check-said")
        self.assertIn("nothing to check", self.out("check-said"))
        self.assertIn("ok 1", self.out("check-said", "--all"))

    def test_transcript_folder_can_be_given(self):
        did = self.decision("use the outbox pattern")
        self.out("check-said", "--transcripts", str(self.transcripts), config=False)
        self.assertEqual(self.node(did)["said_check"], "ok")
        bad = self.run_wise("check-said", "--transcripts", str(self.project / "nope"),
                            check=False)
        self.assertEqual(bad.returncode, 2)

    def test_both_folder_name_spellings_are_found(self):
        self.assertEqual(wise.encode_project_dir("/home/u/my.proj_x"),
                         ["-home-u-my-proj_x", "-home-u-my-proj-x"])

    # ---- recall

    def test_queries_label_notes_and_print_quotes_with_their_check(self):
        did = self.decision("go with SQLite, one file")
        out = self.out("decisions")
        self.assertIn("outcome (AI note, not the learner's words): SQLite", out)
        self.assertIn("learner said «go with SQLite, one file» · check unchecked", out)
        self.run_wise("add", "decision", "title=P", "proposal=Redis", "by=ai")
        self.assertIn("proposal (AI note, not the learner's words): Redis",
                      self.out("decisions", "--pending"))
        self.run_wise("add", "qa", "source=checkpoint", "q=Why?", "a=gist",
                      "said=one file per user")
        history = self.out("history", "--full")
        self.assertIn("A (gist): gist", history)
        self.assertIn("learner said «one file per user»", history)
        self.assertTrue(did)


class SaidGuideTests(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_behavior_states_the_recall_rule(self):
        text = self.read("skills/learn/behavior.md")
        for phrase in ("## Learner's words", "my note, not your words", "check-said",
                       "never fill the gap", "Read it back"):
            self.assertIn(phrase, text)

    def test_every_learner_record_example_carries_a_quote(self):
        for rel in ("skills/learn/materials.md", "skills/grill/SKILL.md",
                    "skills/grill-with-docs/SKILL.md", "skills/learn/state-templates.md",
                    "skills/explore/SKILL.md"):
            text = self.read(rel)
            for marker in ("status=settled", "source=checkpoint", "source=explore",
                           "source=repair"):
                start = 0
                while (i := text.find(marker, start)) != -1:
                    window = text[i: i + 260]
                    with self.subTest(file=rel, at=i):
                        self.assertIn("said=", window)
                    start = i + 1

    def test_session_end_and_reflect_run_the_checker(self):
        self.assertIn("wise.py check-said", self.read("skills/learn/SKILL.md"))
        self.assertIn("wise.py check-said", self.read("skills/reflect/SKILL.md"))

    def test_hook_carries_the_recall_rule(self):
        hook = self.read("hooks/session_start.py")
        self.assertIn("my note, not your words", hook)
        self.assertIn("compaction summary is your own paraphrase", hook)

    def test_codex_notes_say_quotes_are_unverified_there(self):
        for skill in ("learn", "reflect"):
            self.assertIn("unverified", self.read(f"skills/{skill}/codex.md"))


if __name__ == "__main__":
    unittest.main()
