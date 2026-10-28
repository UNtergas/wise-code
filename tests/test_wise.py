"""The learning graph script: store, IDs, queries, cap, imports, shelf."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wise.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fixture  # noqa: E402
import measure_tokens  # noqa: E402
import wise  # noqa: E402


class WiseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wise-graph-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()

    def run_wise(self, *args, root=None, day="2026-10-28", check=True):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day}
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root or self.project), *args],
            text=True, capture_output=True, env=env, timeout=30)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def out(self, *args, **kwargs):
        return self.run_wise(*args, **kwargs).stdout

    def nodes(self, root=None):
        path = (root or self.project) / ".wise-code" / "graph" / "nodes.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class StoreTests(WiseTestCase):
    def test_reads_need_no_state_and_create_nothing(self):
        self.assertIn("nothing recorded yet", self.out("due"))
        self.assertFalse((self.project / ".wise-code").exists())

    def test_first_write_creates_state_at_git_root_from_subfolder(self):
        sub = self.project / "src" / "deep"
        sub.mkdir(parents=True)
        self.run_wise("add", "concept", "name=Ownership", root=sub)
        self.assertTrue((self.project / ".wise-code" / "graph" / "nodes.jsonl").is_file())
        self.assertFalse((sub / ".wise-code").exists())

    def test_files_are_sorted_jsonl_one_object_per_line(self):
        for name in ("Zeta", "Alpha", "Mid"):
            self.run_wise("add", "concept", f"name={name}")
        ids = [n["id"] for n in self.nodes()]
        self.assertEqual(ids, sorted(ids))
        edges = (self.project / ".wise-code/graph/edges.jsonl")
        self.assertTrue(edges.exists())

    def test_ids_are_dated_random_and_typed(self):
        qid = self.out("add", "question", "q=Why?", "a=Because.").strip()
        self.assertRegex(qid, r"^QB-20261028-[0-9a-f]{4}$")

    def test_two_machines_never_collide_and_merge_cleanly(self):
        self.run_wise("add", "concept", "name=Strings")
        clone = Path(self.temp.name) / "clone"
        shutil.copytree(self.project, clone)
        for root in (self.project, clone):
            for n in range(40):
                self.run_wise("add", "qa", f"q=Q{n}", "a=A", "source=asked",
                              "--about", "strings", root=root)
        # A git merge of two sorted JSONL files is the union of their lines.
        merged = {}
        for root in (self.project, clone):
            for node in self.nodes(root):
                merged.setdefault(node["id"], []).append(node)
        dupes = [i for i, v in merged.items() if len(v) > 1 and v[0] != v[1]]
        self.assertEqual(dupes, [])
        self.assertEqual(sum(1 for i in merged if i.startswith("QA-")), 80)

    def git(self, cwd, *args):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.temp.name,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}
        return subprocess.run(["git", "-C", str(cwd), *args], text=True,
                              capture_output=True, env=env, timeout=30)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_real_git_merge_of_two_clones_needs_no_conflict_resolution(self):
        shutil.rmtree(self.project / ".git")
        self.git(self.project, "init", "-q", "-b", "main")
        self.run_wise("add", "concept", "name=Strings")
        qid = self.out("add", "question", "q=Why?", "a=Because.", "--tests", "strings").strip()
        self.assertTrue((self.project / ".wise-code/graph/.gitattributes").is_file())
        self.git(self.project, "add", "-A")
        self.git(self.project, "commit", "-qm", "base")
        clone = Path(self.temp.name) / "clone"
        self.assertEqual(self.git(self.temp.name, "clone", "-q", str(self.project),
                                  str(clone)).returncode, 0)
        # Both sides add records and both answer the same question.
        for root, day, verdict in ((self.project, "2026-10-28", "wrong"),
                                   (clone, "2026-10-29", "correct")):
            for n in range(5):
                self.run_wise("add", "qa", f"q={root.name} {n}", "a=A", "source=asked",
                              "--about", "strings", root=root, day=day)
            self.run_wise("answer", qid, verdict, root=root, day=day)
            self.git(root, "add", "-A")
            self.git(root, "commit", "-qm", f"work on {root.name}")
        self.git(self.project, "fetch", "-q", str(clone), "main")
        merge = self.git(self.project, "merge", "-q", "--no-edit", "FETCH_HEAD")
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        text = (self.project / ".wise-code/graph/nodes.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("<<<<<<<", text)
        self.assertIn("ok", self.out("check"))
        qa = [n for n in self.nodes() if n["type"] == "qa"]
        self.assertEqual(len({n["id"] for n in qa}), 12)  # 10 added + 2 answers
        # The newer change to the shared question wins, and a write cleans the file.
        self.run_wise("add", "concept", "name=Lifetimes")
        question = [n for n in self.nodes() if n["id"] == qid]
        self.assertEqual(len(question), 1)
        self.assertEqual(question[0]["box"], 2)

    def test_unknown_field_and_bad_enum_are_rejected(self):
        bad = self.run_wise("add", "qa", "q=x", "a=y", "source=nope", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("source must be one of", bad.stderr)
        bad = self.run_wise("add", "card", "front=x", "back=y", "colour=red", check=False)
        self.assertIn("has no field 'colour'", bad.stderr)

    def test_edges_are_type_checked(self):
        self.run_wise("add", "concept", "name=Strings")
        card = self.out("add", "card", "front=f", "back=b").strip()
        bad = self.run_wise("link", card, "prereq", "strings", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("not allowed", bad.stderr)
        self.run_wise("link", card, "tests", "strings")

    def test_symlinked_graph_is_refused(self):
        state = self.project / ".wise-code" / "graph"
        state.mkdir(parents=True)
        target = Path(self.temp.name) / "elsewhere.jsonl"
        target.write_text("", encoding="utf-8")
        (state / "nodes.jsonl").symlink_to(target)
        bad = self.run_wise("stats", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("symlink", bad.stderr)


class ConceptTests(WiseTestCase):
    def test_near_duplicate_concept_is_refused_with_the_match(self):
        self.run_wise("add", "concept", "name=Rust strings", "aliases+=str")
        dup = self.run_wise("add", "concept", "name=rust string", check=False)
        self.assertEqual(dup.returncode, 1)
        self.assertIn("exists: rust-strings", dup.stdout)
        self.run_wise("add", "concept", "name=Rust traits")  # different idea passes

    def test_alias_resolves_everywhere(self):
        self.run_wise("add", "concept", "name=Rust strings", "aliases+=str")
        self.run_wise("add", "qa", "q=Q", "a=A", "source=asked", "--about", "str")
        self.assertIn("rust-strings", self.out("history", "--concept", "str"))

    def test_merge_moves_edges_and_keeps_alias(self):
        self.run_wise("add", "concept", "name=Strings")
        self.run_wise("add", "--force", "concept", "name=String slicing")
        self.run_wise("add", "qa", "q=Q", "a=A", "source=asked", "--about", "string-slicing")
        self.run_wise("merge", "strings", "string-slicing")
        self.assertIn("strings", self.out("history", "--concept", "string-slicing"))
        node = next(n for n in self.nodes() if n["id"] == "strings")
        self.assertIn("string-slicing", node["aliases"])


class QueryTests(WiseTestCase):
    def test_due_and_leitner_schedule(self):
        self.run_wise("add", "concept", "name=Strings")
        qid = self.out("add", "question", "q=Why panic?", "a=Boundary.", "--tests", "strings").strip()
        self.assertIn("nothing due; next due 2026-10-29", self.out("due"))
        self.assertIn(qid, self.out("due", day="2026-10-29"))
        self.assertIn("box 2 · due 2026-11-01", self.out("answer", qid, "correct", day="2026-10-29"))
        self.assertIn("box 1 · due 2026-11-02", self.out("answer", qid, "wrong", day="2026-11-01"))
        history = self.out("history", "--concept", "strings")
        self.assertEqual(history.count("quiz"), 2)

    def test_weak_mistakes_and_prereqs(self):
        for name in ("Strings", "Bytes"):
            self.run_wise("add", "concept", f"name={name}")
        self.run_wise("link", "strings", "prereq", "bytes")
        for _ in range(2):
            self.run_wise("add", "qa", "q=Q", "a=A", "source=review", "verdict=wrong",
                          "--about", "strings")
        self.assertIn("prereq: bytes", self.out("weak", "--with-prereqs"))
        self.assertIn("strings · 2 misses", self.out("mistakes", "--repeated"))

    def test_session_pending_and_auto_links_the_days_records(self):
        qa = self.out("add", "qa", "q=Q", "a=A", "source=asked", day="2026-10-27").strip()
        session = self.out("add", "session", "goal=Retry queue", "checkpoints+=Backoff doubles",
                           day="2026-10-27").strip()
        self.assertEqual(self.run_wise("session", "--pending", "--quiet").returncode, 0)
        self.assertIn("checkpoints: Backoff doubles", self.out("session", "--pending"))
        self.assertIn(f"→ in {session}", self.out("show", qa))
        self.run_wise("set", session, "start_check=done 2026-10-28 · 3/4")
        self.assertEqual(self.run_wise("session", "--pending", "--quiet", check=False).returncode, 1)

    def test_pending_decisions(self):
        did = self.out("add", "decision", "title=Storage", "proposal=SQLite",
                       "stage=implementation-approval").strip()
        self.assertIn("implementation-approval", self.out("decisions", "--pending"))
        self.run_wise("set", did, "status=settled", "outcome=JSON", "by=learner")
        self.assertIn("no pending decisions", self.out("decisions", "--pending"))

    def test_output_is_capped_and_says_how_to_narrow(self):
        self.run_wise("add", "concept", "name=Strings")
        long = "word " * 60
        for _ in range(60):
            self.run_wise("add", "qa", f"q={long}", "a=A", "source=asked", "--about", "strings")
        text = self.out("history", "--limit", "200", "--full")
        self.assertLessEqual(len(text), wise.CAP_CHARS + 200)
        self.assertRegex(text, r"… \d+ more; pass --concept")


class ViewTests(WiseTestCase):
    def test_render_and_anki_export(self):
        self.run_wise("add", "concept", "name=Strings", "definition=UTF-8 text",
                      "status=reinforce")
        self.run_wise("add", "card", "front=Rust: slice &str mid-char?", "back=Panics.",
                      "--tests", "strings")
        self.assertIn("## Strings · reinforce", self.out("render", "progress"))
        self.assertIn("**Strings**: UTF-8 text", self.out("render", "glossary"))
        self.run_wise("export", "anki")
        rows = (self.project / ".wise-code/cards.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[3], "#deck:wise-code::project")
        self.assertEqual(rows[5], "Rust: slice &str mid-char?\tPanics.\twise-code strings")

    def test_check_flags_dangling_edges_and_gone_files(self):
        self.run_wise("add", "concept", "name=Strings", "code+=src/missing.rs:parse")
        edges = self.project / ".wise-code/graph/edges.jsonl"
        edges.write_text('{"from": "ghost", "rel": "about", "to": "strings"}\n', encoding="utf-8")
        result = self.run_wise("check", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("dangling edge", result.stdout)
        self.assertIn("code file gone: src/missing.rs", result.stdout)

    def test_reset_progress_keeps_materials(self):
        self.run_wise("add", "concept", "name=Strings", "status=demonstrated")
        self.run_wise("add", "decision", "title=Storage")
        self.run_wise("add", "decision", "title=Old", "status=settled")
        self.run_wise("add", "qa", "q=Q", "a=A", "source=asked")
        self.run_wise("reset-progress")
        kinds = [n["type"] for n in self.nodes()]
        self.assertEqual(sorted(kinds), ["concept", "decision", "qa"])
        self.assertNotIn("status", next(n for n in self.nodes() if n["type"] == "concept"))
        self.assertTrue(list((self.project / ".wise-code/backups").glob("reset-*/graph/nodes.jsonl")))


class LessonImportTests(WiseTestCase):
    def results(self, folder, result_id="r-1"):
        path = folder / f"lesson-0001-results-{result_id}.json"
        path.write_text(json.dumps({
            "result_id": result_id, "lesson": "0001", "date": "2026-10-28",
            "answers": [
                {"q": "How wide is a UTF-8 char?", "answer": "1-4 bytes", "correct": True},
                {"q": "What does the browser send?", "answer": "bytes", "correct": False,
                 "expected": "UTF-16 code units"}]}), encoding="utf-8")
        return path

    def test_import_by_path_then_duplicate_is_refused(self):
        downloads = Path(self.temp.name) / "Downloads"
        downloads.mkdir()
        path = self.results(downloads)
        self.assertIn("2 answers · 1 wrong", self.out("import-lesson", str(path)))
        self.assertIn("already imported", self.out("import-lesson", str(path)))
        kinds = [n["type"] for n in self.nodes()]
        self.assertEqual(kinds.count("qa"), 2)
        self.assertEqual(kinds.count("question"), 1)

    def test_inbox_is_imported_and_moved_to_done(self):
        inbox = self.project / ".wise-code" / "inbox"
        inbox.mkdir(parents=True)
        self.results(inbox, "r-2")
        self.out("import-lesson", "--inbox")
        self.assertEqual(list(inbox.glob("*.json")), [])
        self.assertEqual(len(list((inbox / "done").glob("*.json"))), 1)


class ShelfTests(WiseTestCase):
    def setUp(self):
        super().setUp()
        self.shelf = Path(self.temp.name).resolve() / "shelf"
        self.shelf.mkdir()
        (self.shelf / ".git").mkdir()

    def test_stable_ids_upsert_and_projects_are_marked(self):
        s = {"root": self.shelf}
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf", **s)
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf",
                      "pages=611", **s)
        self.run_wise("add", "section", "book=ddia", "number=1.2", "title=Scalability", **s)
        self.run_wise("add", "citation", "project=job-tracking", "question=Why p99?",
                      "--on", "SEC-ddia-1.2", **s)
        self.run_wise("add", "read", "project=grammar", "verdict=understood",
                      "--on", "SEC-ddia-1.2", **s)
        book = next(n for n in self.nodes(self.shelf) if n["id"] == "BK-ddia")
        self.assertEqual(book["pages"], 611)
        self.assertEqual(book["projects"], ["grammar", "job-tracking"])
        impact = self.out("impact", "ddia", **s)
        # Reads and explain-backs are evidence for a citation, not extra outcomes.
        self.assertIn("grammar: 0 citations · 1 sections · understood 0 · not yet 0", impact)
        self.assertIn("job-tracking: 1 citations · 1 sections · understood 0 · not yet 1", impact)

    def test_index_fields_with_digits_outline_order_and_outcomes(self):
        s = {"root": self.shelf}
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf",
                      "l1=2026-10-28", **s)
        for number in ("10", "2", "1.2", "1"):
            self.run_wise("add", "section", "book=ddia", f"number={number}",
                          f"title=S{number}", **s)
        self.run_wise("set", "SEC-ddia-1.2", "l2=2026-10-28", "concepts+=tail latency", **s)
        outline = self.out("list", "section", "--where", "book=ddia", **s)
        order = [line.split(" · ")[0] for line in outline.splitlines()]
        self.assertEqual(order, ["SEC-ddia-1", "SEC-ddia-1.2", "SEC-ddia-2", "SEC-ddia-10"])
        cid = self.out("add", "citation", "project=p", "question=Q", "--on", "SEC-ddia-1.2",
                       **s).strip()
        self.run_wise("add", "explainback", "project=p", "text=gist", "verdict=understood",
                      "--on", "SEC-ddia-1.2", "--for", cid, **s)
        self.run_wise("set", cid, "status=understood", **s)
        self.assertIn("p: 1 citations · 1 sections · understood 1 · not yet 0",
                      self.out("impact", "ddia", **s))

    def test_project_check_warns_on_dead_shelf_ids(self):
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf",
                      root=self.shelf)
        self.run_wise("add", "concept", "name=Latency", "shelf+=SEC-ddia-9.9")
        result = self.out("check", "--shelf", str(self.shelf))
        self.assertIn("shelf id not found: SEC-ddia-9.9", result)


class MarkdownImportTests(WiseTestCase):
    def test_fixture_imports_completely_and_moves_originals(self):
        state = fixture.build(self.project)
        report = self.out("import-md")
        for part in ("qa 300", "question 100", "session 5", "record 3", "card 50",
                     "guardrail 1", "reflection 1", "feedback 1", "decision 1",
                     "lesson 1", "mission 1", "research 1", "resource 2"):
            self.assertIn(part, report)
        for gone in ("qa-history.md", "questions.md", "progress.md", "session-recap.md",
                     "cards.tsv", "guardrails.md", "reflections.md", "plugin-feedback.md"):
            self.assertFalse((state / gone).exists(), gone)
        # Tier-2 files stay where they are; only the graph indexes them.
        self.assertTrue((state / "teach" / "MISSION.md").exists())
        self.assertTrue((state / "teach" / "lessons" / "0001-utf8.html").exists())
        self.assertTrue(list((state / "backups").glob("import-*/qa-history.md")))
        self.assertIn("ok ·", self.out("check"))
        # Legacy question ids still resolve.
        self.assertIn("topic-06-tokio", self.out("show", "QB-0007"))
        self.assertIn("pending", self.out("session", "--pending"))
        self.assertIn("implementation-approval", self.out("decisions", "--pending"))
        self.assertIn("**Byte offset**", self.out("render", "glossary"))
        self.assertIn("superseded", self.out("list", "record"))

    def test_rerun_is_a_no_op(self):
        fixture.build(self.project)
        self.out("import-md")
        before = len(self.nodes())
        self.out("import-md")
        self.assertEqual(len(self.nodes()), before)

    def test_dry_run_writes_nothing(self):
        state = fixture.build(self.project)
        self.out("import-md", "--dry-run")
        self.assertTrue((state / "qa-history.md").exists())
        self.assertFalse((state / "graph").exists())


class TokenBudgetTests(unittest.TestCase):
    """Proof for the grill's metric: every replacing query fits the cap."""

    def test_every_query_is_under_the_cap_and_far_below_the_old_read(self):
        for label, old, new, longest in measure_tokens.measure():
            with self.subTest(command=label):
                self.assertLessEqual(longest, wise.CAP_CHARS + 200)
                self.assertLess(new, old)


if __name__ == "__main__":
    unittest.main()
