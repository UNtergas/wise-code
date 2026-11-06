"""The learning graph script: store, IDs, queries, cap, imports, shelf."""

import errno
import json
import re
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
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

    def run_wise(self, *args, root=None, day="2026-10-28", check=True, extra_env=None):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": day, **(extra_env or {})}
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
    def test_real_git_merge_of_two_clones_keeps_every_record(self):
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
        qa = [n for n in self.nodes() if n["type"] == "qa"]
        self.assertEqual(len({n["id"] for n in qa}), 12)  # 10 added + 2 answers
        # Both sides rescheduled the shared question. The schedule merges by
        # itself to the safer side: lower box, earlier due (wrong on 10-28 put
        # it in box 1 due 10-29; correct on 10-29 in box 2 due 11-01).
        check = self.run_wise("check", check=False)
        self.assertNotIn("conflicting", check.stdout + check.stderr)
        self.run_wise("add", "concept", "name=Lifetimes")
        question = [n for n in self.nodes() if n["id"] == qid]
        self.assertEqual(len(question), 1)
        self.assertEqual((question[0]["box"], question[0]["due"]), (1, "2026-10-29"))
        self.assertIn("ok", self.out("check"))

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

    def test_symlinked_graph_folder_is_refused_for_reads_and_writes(self):
        # Review #19 finding 4: the folder, not just its files, is the boundary.
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "nodes.jsonl").write_text(
            '{"id": "ext", "name": "External", "type": "concept"}\n', encoding="utf-8")
        before = sorted((p.name, p.read_bytes()) for p in outside.iterdir())
        state = self.project / ".wise-code"
        state.mkdir()
        (state / "graph").symlink_to(outside, target_is_directory=True)
        for args in (("list", "concept"), ("add", "concept", "name=Inside")):
            with self.subTest(args=args):
                bad = self.run_wise(*args, check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("symlink", bad.stderr)
                self.assertNotIn("External", bad.stdout)
        self.assertEqual(sorted((p.name, p.read_bytes()) for p in outside.iterdir()), before)

    def test_symlinked_gitattributes_is_refused(self):
        self.run_wise("add", "concept", "name=Alpha")
        graph = self.project / ".wise-code" / "graph"
        target = Path(self.temp.name) / "attrs"
        target.write_text("", encoding="utf-8")
        (graph / ".gitattributes").unlink()
        (graph / ".gitattributes").symlink_to(target)
        bad = self.run_wise("add", "concept", "name=Beta", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "")


class ConceptTests(WiseTestCase):
    def test_near_duplicate_concept_is_refused_with_the_match(self):
        self.run_wise("add", "concept", "name=Rust strings", "aliases+=str")
        dup = self.run_wise("add", "concept", "name=rust string", check=False)
        self.assertEqual(dup.returncode, 1)
        self.assertIn("exists: rust-strings", dup.stdout)
        self.run_wise("add", "concept", "name=Rust traits")  # different idea passes

    def test_forced_add_never_replaces_an_existing_concept_id(self):
        # Review #19 finding 3: --force skips the similarity check, not identity.
        self.run_wise("add", "concept", "name=Alpha", "notes+=keep me")
        graph = self.project / ".wise-code" / "graph"
        before = {name: (graph / name).read_bytes() for name in ("nodes.jsonl", "edges.jsonl")
                  if (graph / name).exists()}
        for args in (("name=Alpha",), ("id=alpha", "name=Other idea")):
            with self.subTest(args=args):
                bad = self.run_wise("add", "--force", "concept", *args, check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("'alpha' is taken", bad.stderr)
                after = {name: (graph / name).read_bytes() for name in before}
                self.assertEqual(after, before)
        # A distinct id with a similar name still goes through with --force.
        self.run_wise("add", "--force", "concept", "id=alpha-prime", "name=Alpha prime")
        ids = {n["id"]: n for n in self.nodes()}
        self.assertEqual(ids["alpha"]["notes"], ["keep me"])
        self.assertIn("alpha-prime", ids)

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
        self.run_wise("set", did, "status=settled", "outcome=JSON", "by=learner",
                      "said=just use a JSON file")
        self.assertIn("no pending decisions", self.out("decisions", "--pending"))

    def test_output_is_capped_and_says_how_to_narrow(self):
        self.run_wise("add", "concept", "name=Strings")
        long = "word " * 60
        for _ in range(60):
            self.run_wise("add", "qa", f"q={long}", "a=A", "source=asked", "--about", "strings")
        text = self.out("history", "--limit", "200", "--full")
        self.assertLessEqual(len(text), wise.CAP_CHARS + 200)
        self.assertRegex(text, r"… \d+ more; pass --concept")


class ValidationTests(WiseTestCase):
    """Review #19 finding 5: stored types and ranges are checked, not just converted."""

    def graph_bytes(self):
        graph = self.project / ".wise-code" / "graph"
        return {p.name: p.read_bytes() for p in graph.iterdir() if p.suffix == ".jsonl"}

    def editor(self, change):
        # A stand-in editor: applies `change` (JSON fields) to the file it opens.
        script = Path(self.temp.name) / "editor.py"
        script.write_text(
            "import json, sys\n"
            "path = sys.argv[1]\n"
            "node = json.load(open(path, encoding='utf-8'))\n"
            f"node.update(json.loads({json.dumps(json.dumps(change))}))\n"
            "json.dump(node, open(path, 'w', encoding='utf-8'))\n", encoding="utf-8")
        return {"EDITOR": f"{sys.executable} {script}"}

    def test_box_outside_leitner_range_is_refused(self):
        for box in ("0", "6", "-1"):
            with self.subTest(box=box):
                bad = self.run_wise("add", "question", "q=Q", "a=A", f"box={box}", check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("question.box must be 1 to 5", bad.stderr)
        self.assertFalse((self.project / ".wise-code" / "graph" / "nodes.jsonl").exists())

    def test_answer_on_a_stored_bad_box_fails_cleanly_without_writing(self):
        qid = self.out("add", "question", "q=Q", "a=A").strip()
        nodes = self.project / ".wise-code" / "graph" / "nodes.jsonl"
        nodes.write_text(nodes.read_text(encoding="utf-8").replace('"box": 1', '"box": 0'),
                         encoding="utf-8")
        before = self.graph_bytes()
        bad = self.run_wise("answer", qid, "partial", "--source", "quiz", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("Traceback", bad.stderr)
        self.assertIn(f"set {qid} box=1", bad.stderr)
        self.assertEqual(self.graph_bytes(), before)

    def test_editor_cannot_store_wrong_json_types(self):
        self.run_wise("add", "concept", "name=Alpha", "notes+=one")
        qid = self.out("add", "question", "q=Q", "a=A").strip()
        cases = [("alpha", {"notes": "a string, not a list"}, "concept.notes must be a list"),
                 ("alpha", {"aliases": ["ok", 3]}, "concept.aliases must be a list of text"),
                 ("alpha", {"rev": "2"}, "concept.rev must be a whole number"),
                 ("alpha", {"created": "yesterday"}, "concept.created must be YYYY-MM-DD"),
                 (qid, {"box": "2"}, "question.box must be a whole number"),
                 (qid, {"box": True}, "question.box must be a whole number")]
        before = self.graph_bytes()
        for node_id, change, message in cases:
            with self.subTest(change=change):
                bad = self.run_wise("edit", node_id, check=False, extra_env=self.editor(change))
                self.assertEqual(bad.returncode, 2, bad.stdout)
                self.assertIn(message, bad.stderr)
                self.assertEqual(self.graph_bytes(), before)
        # A well-typed edit still works.
        self.run_wise("edit", "alpha", extra_env=self.editor({"notes": ["one", "two"]}))
        self.assertEqual({n["id"]: n for n in self.nodes()}["alpha"]["notes"], ["one", "two"])

    def test_imported_legacy_records_pass_strict_validation(self):
        fixture.build(self.project, qa=40, questions=20, sessions=2)
        self.run_wise("import-md")
        self.assertIn("ok · ", self.out("check"))


class ConcurrencyTests(WiseTestCase):
    """Review #19 finding 1: overlapping writers never silently lose records."""

    def state(self):
        return wise.find_state(self.project, create=True)

    def spawn(self, *args):
        env = {"PATH": os.environ.get("PATH", ""), "WISE_TODAY": "2026-10-28"}
        return subprocess.Popen(
            [sys.executable, str(SCRIPT), "--root", str(self.project), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    def add_concept(self, graph, name):
        node_id = wise.slugify(name)
        graph.nodes[node_id] = {"id": node_id, "type": "concept", "name": name,
                                "created": "2026-10-28"}
        graph.dirty = True
        graph.save()

    def test_second_process_waits_and_both_additions_survive(self):
        self.run_wise("add", "concept", "name=Seed")
        with wise.Graph(self.state(), write=True) as graph:
            other = self.spawn("add", "concept", "name=Beta")
            time.sleep(1.0)
            self.assertIsNone(other.poll(), "the second writer must wait for the lock")
            self.add_concept(graph, "Alpha")
        _, err = other.communicate(timeout=30)
        self.assertEqual(other.returncode, 0, err)
        self.assertEqual({n["id"] for n in self.nodes()}, {"seed", "alpha", "beta"})

    def test_parallel_independent_processes_keep_every_record(self):
        self.run_wise("add", "concept", "name=Seed")
        names = [f"Topic {chr(65 + i)} unique{i}" for i in range(8)]
        procs = [self.spawn("add", "--force", "concept", f"name={n}") for n in names]
        for proc in procs:
            _, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err)
        self.assertEqual({n["id"] for n in self.nodes()},
                         {"seed", *(wise.slugify(n) for n in names)})

    def test_stale_writer_on_a_new_graph_fails_explicitly(self):
        # No graph yet: A loads an empty graph, B creates it, A's save must refuse.
        with wise.Graph(self.state(), write=True) as graph:
            self.run_wise("add", "concept", "name=Beta")
            with self.assertRaisesRegex(wise.WiseError, "created by another wise.py"):
                self.add_concept(graph, "Alpha")
        self.assertEqual({n["id"] for n in self.nodes()}, {"beta"})

    def test_new_graph_save_finishes_a_crashed_writers_journal_first(self):
        # PR #20 review: A and B both load before graph/ exists; A dies right
        # after publishing its journal. B must not overwrite A's commit.
        state = self.state()
        first, second = wise.Graph(state), wise.Graph(state)
        self.addCleanup(second.close)

        class Stop(Exception):
            pass

        def stop_at(_, reached):
            if reached == "journal published":
                raise Stop
        original = wise.Graph._checkpoint
        wise.Graph._checkpoint = stop_at
        try:
            with self.assertRaises(Stop):
                self.add_concept(first, "Alpha")
        finally:
            wise.Graph._checkpoint = original
        first.close()  # the crashed process releases its lock
        with self.assertRaisesRegex(wise.WiseError, "created by another wise.py"):
            self.add_concept(second, "Beta")
        second.close()
        self.assertEqual({n["id"] for n in self.nodes()}, {"alpha"})

    def test_two_instances_in_one_process_do_not_overwrite(self):
        self.run_wise("add", "concept", "name=Seed")
        with wise.Graph(self.state(), write=True) as first:
            with self.assertRaisesRegex(wise.WiseError, "busy"):
                wise.Graph(self.state(), write=True, timeout=0.2)
            self.add_concept(first, "Alpha")
        self.assertEqual({n["id"] for n in self.nodes()}, {"seed", "alpha"})

    def test_read_only_file_system_reads_without_the_lock(self):
        # PR #20 review: a read-only mount raises EROFS, not PermissionError.
        self.run_wise("add", "concept", "name=Alpha")
        state = self.state()
        real_open = os.open
        for code in (errno.EROFS, errno.EACCES, errno.EPERM):
            with self.subTest(errno=errno.errorcode[code]):
                def refuse(path, *args, code=code, **kwargs):
                    if str(path).endswith(".lock"):
                        raise OSError(code, os.strerror(code))
                    return real_open(path, *args, **kwargs)
                os.open = refuse
                try:
                    with wise.Graph(state) as graph:
                        self.assertEqual(set(graph.nodes), {"alpha"})
                    with self.assertRaisesRegex(wise.WiseError, "not writable"):
                        wise.Graph(state, write=True)
                    # An unfinished save is never read past without the lock.
                    journal = state / "graph" / ".commit"
                    journal.write_text("[]", encoding="utf-8")
                    try:
                        with self.assertRaisesRegex(wise.WiseError, "unfinished save"):
                            wise.Graph(state)
                    finally:
                        journal.unlink()
                finally:
                    os.open = real_open

    def test_process_files_are_git_ignored(self):
        self.run_wise("add", "concept", "name=Seed")
        ignore = (self.project / ".wise-code" / "graph" / ".gitignore").read_text()
        for name in (".lock", ".commit", ".*.tmp"):
            self.assertIn(name, ignore.splitlines())


class CommitTests(WiseTestCase):
    """Review #19 finding 6: an interrupted save leaves one whole graph."""

    class Stop(Exception):
        pass

    STEPS = ("temps written", "journal published", "nodes.jsonl replaced",
             "edges.jsonl replaced")

    def graph_state(self):
        graph = self.project / ".wise-code" / "graph"
        nodes = {n["id"] for n in self.nodes()}
        edges = [json.loads(line) for line in
                 (graph / "edges.jsonl").read_text(encoding="utf-8").splitlines()]
        return nodes, {(e["from"], e["rel"], e["to"]) for e in edges}

    def test_interrupted_delete_recovers_old_or_new_graph_in_a_new_process(self):
        old = ({"alpha", "beta"}, {("alpha", "prereq", "beta")})
        new = ({"alpha"}, set())
        for step in self.STEPS:
            with self.subTest(step=step):
                shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
                self.run_wise("add", "concept", "name=Alpha")
                self.run_wise("add", "concept", "name=Beta")
                self.run_wise("link", "alpha", "prereq", "beta")
                self.assertEqual(self.graph_state(), old)

                def stop_at(_, reached, step=step):
                    if reached == step:
                        raise self.Stop(step)
                state = wise.find_state(self.project)
                original = wise.Graph._checkpoint
                wise.Graph._checkpoint = stop_at
                try:
                    with wise.Graph(state, write=True) as graph:
                        graph.remove("beta")
                        with self.assertRaises(self.Stop):
                            graph.save()
                finally:
                    wise.Graph._checkpoint = original
                # A new process loads (and, if needed, finishes) the graph.
                self.assertIn("ok · ", self.out("check"))
                expected = old if step == "temps written" else new
                self.assertEqual(self.graph_state(), expected)
                leftovers = [p.name for p in (state / "graph").iterdir()
                             if p.name.endswith(".tmp") or p.name == ".commit"]
                self.assertEqual(leftovers, [])

    def test_journal_naming_a_symlinked_temp_is_refused_before_any_move(self):
        # PR #20 review: recovery must keep the no-symlink boundary.
        self.run_wise("add", "concept", "name=Alpha")
        graph = self.project / ".wise-code" / "graph"
        outside = Path(self.temp.name) / "external.jsonl"
        outside.write_text('{"id": "evil", "name": "Evil", "type": "concept"}\n',
                           encoding="utf-8")
        # A real temp first, then the link: no move may happen at all.
        (graph / ".edges.jsonl.real.tmp").write_text("", encoding="utf-8")
        (graph / ".nodes.jsonl.example.tmp").symlink_to(outside)
        (graph / ".commit").write_text(json.dumps(
            [[".edges.jsonl.real.tmp", "edges.jsonl"],
             [".nodes.jsonl.example.tmp", "nodes.jsonl"]]), encoding="utf-8")
        before = {name: (graph / name).read_bytes() for name in ("nodes.jsonl", "edges.jsonl")
                  if (graph / name).exists()}
        bad = self.run_wise("list", "concept", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("symlink", bad.stderr)
        self.assertNotIn("evil", bad.stdout)
        self.assertFalse((graph / "nodes.jsonl").is_symlink())
        self.assertEqual({name: (graph / name).read_bytes() for name in before}, before)

    def test_unreadable_journal_stops_instead_of_guessing(self):
        self.run_wise("add", "concept", "name=Alpha")
        (self.project / ".wise-code" / "graph" / ".commit").write_text(
            '[["../../escape.tmp", "nodes.jsonl"]]', encoding="utf-8")
        bad = self.run_wise("list", "concept", check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unreadable", bad.stderr)


class MergeConflictTests(WiseTestCase):
    """Review #19 finding 2: equal merge stamps never pick a winner silently."""

    def nodes_file(self):
        return self.project / ".wise-code" / "graph" / "nodes.jsonl"

    def with_lines(self, *extra):
        # Simulate a union merge: append other clones' versions of a node.
        path = self.nodes_file()
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([*lines, *extra]) + "\n", encoding="utf-8")

    def versions(self, node_id):
        return [json.loads(line) for line in self.nodes_file().read_text(
            encoding="utf-8").splitlines() if json.loads(line)["id"] == node_id]

    def two_divergent(self):
        self.run_wise("add", "concept", "name=Alpha", "notes+=base")
        self.run_wise("add", "concept", "name=Other")
        base = self.versions("alpha")[0]
        ours = {**base, "notes": ["base", "ours"], "updated": "2026-10-29", "rev": 1}
        theirs = {**base, "notes": ["base", "theirs"], "updated": "2026-10-29", "rev": 1}
        return base, ours, theirs

    def line(self, node):
        return json.dumps(node, ensure_ascii=False, sort_keys=True)

    def test_divergent_equal_stamps_are_kept_in_either_line_order(self):
        for order in ("ours-first", "theirs-first"):
            with self.subTest(order=order):
                shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
                base, ours, theirs = self.two_divergent()
                pair = [ours, theirs] if order == "ours-first" else [theirs, ours]
                # Drop the base line: both sides edited it.
                keep = [l for l in self.nodes_file().read_text(encoding="utf-8").splitlines()
                        if json.loads(l)["id"] != "alpha"]
                self.nodes_file().write_text("\n".join(keep) + "\n", encoding="utf-8")
                self.with_lines(*(self.line(n) for n in pair))
                # An unrelated write keeps both versions on disk and warns.
                res = self.run_wise("set", "other", "definition=x")
                self.assertIn("conflicting versions from a merge: alpha", res.stderr)
                self.assertCountEqual([v["notes"] for v in self.versions("alpha")],
                                      [["base", "ours"], ["base", "theirs"]])
                # Changing the conflicted node is refused until resolved.
                bad = self.run_wise("set", "alpha", "definition=y", check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("wise.py resolve alpha", bad.stderr)
                self.assertEqual(self.run_wise("delete", "alpha", check=False).returncode, 2)
                self.assertIn("alpha: 2 conflicting versions",
                              self.run_wise("check", check=False).stdout)
                shown = self.out("resolve", "alpha")
                self.assertIn("differ in notes", shown)
                self.assertIn('2: {"notes": ["base", "', shown)
                theirs_at = 1 + [n["notes"][1] for n in pair].index("theirs")
                self.out("resolve", "alpha", "--keep", str(theirs_at))
                [kept] = self.versions("alpha")
                self.assertEqual(kept["notes"], ["base", "theirs"])
                self.assertEqual(kept["rev"], 2)  # beats both sides in later merges
                self.assertIn("ok · ", self.out("check"))

    def test_resolved_choice_beats_future_dated_versions(self):
        # PR #20 review: versions dated ahead of today (another time zone,
        # a clock ahead) must not outrank the learner's later choice.
        base, ours, theirs = self.two_divergent()
        ours, theirs = ({**n, "updated": "2026-10-30"} for n in (ours, theirs))
        keep = [l for l in self.nodes_file().read_text(encoding="utf-8").splitlines()
                if json.loads(l)["id"] != "alpha"]
        self.nodes_file().write_text("\n".join(keep) + "\n", encoding="utf-8")
        self.with_lines(self.line(ours), self.line(theirs))
        self.out("resolve", "alpha", "--keep", "1", day="2026-10-28")
        [kept] = self.versions("alpha")
        for rejected in (ours, theirs):
            self.assertGreater(wise.stamp(kept), wise.stamp(rejected))
        # A later merge that brings the rejected version back loses to it.
        self.with_lines(self.line(theirs))
        self.run_wise("set", "other", "definition=x")
        [after] = self.versions("alpha")
        self.assertEqual(after["notes"], kept["notes"])

    def test_identical_duplicates_collapse_silently(self):
        self.run_wise("add", "concept", "name=Alpha")
        self.with_lines(self.line(self.versions("alpha")[0]))
        res = self.run_wise("add", "concept", "name=Other")
        self.assertNotIn("conflicting", res.stderr)
        self.assertEqual(len(self.versions("alpha")), 1)

    def test_divergent_unequal_stamps_wait_for_resolve(self):
        # Review #34: a higher stamp doesn't mean that side saw the other's
        # edit; picking it silently dropped the other clone's change.
        for newer_first in (True, False):
            with self.subTest(newer_first=newer_first):
                shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
                base, ours, theirs = self.two_divergent()
                # Both sides edited the base, as wise.py records it.
                seen = {"seen": [wise.version_id(base)]}
                ours, theirs = {**ours, **seen}, {**theirs, **seen, "rev": 2}
                self.with_lines(*(self.line(n) for n in
                                  ([theirs, ours] if newer_first else [ours, theirs])))
                res = self.run_wise("set", "other", "definition=x")
                self.assertIn("conflicting versions from a merge: alpha", res.stderr)
                # The base is an ancestor of both and goes; both edits stay.
                self.assertCountEqual([v["notes"] for v in self.versions("alpha")],
                                      [["base", "ours"], ["base", "theirs"]])

    def test_a_version_and_its_own_ancestor_collapse_to_the_descendant(self):
        # A union merge of neighbouring edits leaves the unchanged base line
        # beside the edited one; the edit includes the base, so it wins.
        self.run_wise("add", "concept", "name=Alpha", "notes+=base")
        self.run_wise("add", "concept", "name=Other")
        base = self.versions("alpha")[0]
        self.run_wise("set", "alpha", "notes+=one", day="2026-10-29")
        self.run_wise("set", "alpha", "notes+=two", day="2026-10-30")
        for order in ("base-last", "base-first"):
            with self.subTest(order=order):
                lines = self.nodes_file().read_text(encoding="utf-8").splitlines()
                lines = [l for l in lines if json.loads(l) != base]
                lines = lines + [self.line(base)] if order == "base-last" else [self.line(base)] + lines
                self.nodes_file().write_text("\n".join(lines) + "\n", encoding="utf-8")
                res = self.run_wise("set", "other", "definition=x")
                self.assertNotIn("conflicting", res.stderr)
                [kept] = self.versions("alpha")
                self.assertEqual(kept["notes"], ["base", "one", "two"])

    def test_resolved_choice_includes_the_rejected_branch_history(self):
        # Review on #34: keeping A over B1 forgot B0, B1's own ancestor, so a
        # merge bringing B0 back asked again.
        base, ours, _ = self.two_divergent()
        b0 = {**base, "notes": ["base", "b0"], "updated": "2026-10-29", "rev": 1,
              "seen": [wise.version_id(base)]}
        b1 = {**b0, "notes": ["base", "b0", "b1"], "rev": 2,
              "seen": [wise.version_id(base), wise.version_id(b0)]}
        a = {**ours, "seen": [wise.version_id(base)]}
        self.with_lines(self.line(a), self.line(b1))
        shown = self.out("resolve", "alpha")
        keep_a = 1 + ["ours" in line for line in shown.splitlines()
                      if re.match(r"^[12]: ", line)].index(True)
        self.out("resolve", "alpha", "--keep", str(keep_a))
        self.with_lines(self.line(b0))
        res = self.run_wise("set", "other", "definition=x")
        self.assertNotIn("conflicting", res.stderr)
        [kept] = self.versions("alpha")
        self.assertEqual(kept["notes"], ["base", "ours"])

    def test_malformed_seen_is_a_line_error_not_a_crash(self):
        self.run_wise("add", "concept", "name=Alpha")
        good = self.versions("alpha")[0]
        for label, value in (("null", None), ("object entry", [{"x": 1}])):
            with self.subTest(label):
                text = self.line(good) + "\n" + self.line({**good, "rev": 3, "seen": value}) + "\n"
                self.nodes_file().write_text(text, encoding="utf-8")
                for command in (("check",), ("list", "concept")):
                    res = self.run_wise(*command, check=False)
                    self.assertEqual(res.returncode, 2, res.stderr)
                    self.assertIn("nodes.jsonl line 2: seen must be a list of text", res.stderr)
                    self.assertNotIn("Traceback", res.stderr)
                self.assertEqual(self.nodes_file().read_text(encoding="utf-8"), text)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_two_projects_citing_one_book_merge_without_resolve(self):
        # Review on #34: each project adds itself to the book's projects, so
        # every shared book became a conflict that blocked further citations.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.temp.name,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}

        def git(cwd, *args):
            return subprocess.run(["git", "-C", str(cwd), *args], text=True,
                                  capture_output=True, env=env, timeout=30)
        shutil.rmtree(self.project / ".git")
        git(self.project, "init", "-q", "-b", "main")
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf")
        self.run_wise("add", "section", "book=ddia", "number=1.2", "title=Scalability")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "base")
        clone = Path(self.temp.name) / "clone"
        git(self.temp.name, "clone", "-q", str(self.project), str(clone))
        for root, project, day in ((self.project, "grammar", "2026-10-29"),
                                   (clone, "job-tracking", "2026-10-30")):
            self.run_wise("add", "citation", f"project={project}", "question=Q",
                          "--on", "SEC-ddia-1.2", root=root, day=day)
            git(root, "add", "-A")
            git(root, "commit", "-qm", project)
        git(self.project, "fetch", "-q", str(clone), "main")
        merge = git(self.project, "merge", "-q", "--no-edit", "FETCH_HEAD")
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        res = self.run_wise("add", "citation", "project=third", "question=Q",
                            "--on", "SEC-ddia-1.2", day="2026-10-31")
        self.assertNotIn("conflicting", res.stderr)
        [book] = self.versions("BK-ddia")
        self.assertEqual(book["projects"], ["grammar", "job-tracking", "third"])

    def test_versions_differing_in_more_than_book_projects_still_wait(self):
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf")
        self.run_wise("add", "concept", "name=Other")
        base = self.versions("BK-ddia")[0]
        seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29", "rev": 1}
        ours = {**base, **seen, "projects": ["a"]}
        theirs = {**base, **seen, "projects": ["b"], "title": "Designing DIA"}
        self.with_lines(self.line(ours), self.line(theirs))
        res = self.run_wise("set", "other", "definition=x")
        self.assertIn("conflicting versions from a merge: BK-ddia", res.stderr)

    def test_book_projects_cannot_shrink_so_union_loses_nothing(self):
        # Review on #34: `projects-=old` on one clone was undone by the union.
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf")
        self.run_wise("set", "BK-ddia", "projects+=old")
        before = self.nodes_file().read_text(encoding="utf-8")
        for change in ("projects-=old", "projects=new"):
            with self.subTest(change):
                bad = self.run_wise("set", "BK-ddia", change, check=False)
                self.assertEqual(bad.returncode, 2)
                self.assertIn("book.projects only grows", bad.stderr)
                self.assertIn("old", bad.stderr)
                self.assertEqual(self.nodes_file().read_text(encoding="utf-8"), before)
        self.run_wise("set", "BK-ddia", "projects=new,old")
        self.assertEqual(self.versions("BK-ddia")[0]["projects"], ["new", "old"])

    def test_malformed_project_entries_are_not_combined(self):
        # Review on #34: a non-text list item crashed the union during load.
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf")
        base = self.versions("BK-ddia")[0]
        seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29", "rev": 1}
        self.with_lines(self.line({**base, **seen, "projects": [{"bad": 1}]}),
                        self.line({**base, **seen, "projects": ["other"]}))
        text = self.nodes_file().read_text(encoding="utf-8")
        res = self.run_wise("check", check=False)
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("book.projects must be a list of text", res.stdout + res.stderr)
        self.assertEqual(self.nodes_file().read_text(encoding="utf-8"), text)

    def test_resolving_a_book_keeps_every_project_whichever_title_is_kept(self):
        # Review on #34: --keep 2 was refused for "removing" version 1's project.
        for order in ("ours-first", "theirs-first"):
            for keep_title in ("DDIA", "Designing DIA"):
                with self.subTest(order=order, keep=keep_title):
                    shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
                    self.run_wise("add", "book", "slug=ddia", "title=DDIA",
                                  "file=shared/ddia.pdf")
                    base = self.versions("BK-ddia")[0]
                    seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29",
                            "rev": 1}
                    ours = {**base, **seen, "projects": ["a"]}
                    theirs = {**base, **seen, "projects": ["b"], "title": "Designing DIA"}
                    pair = [ours, theirs] if order == "ours-first" else [theirs, ours]
                    lines = [l for l in self.nodes_file().read_text(encoding="utf-8")
                             .splitlines() if json.loads(l)["id"] != "BK-ddia"]
                    self.nodes_file().write_text("\n".join(lines + [self.line(n) for n in pair])
                                                 + "\n", encoding="utf-8")
                    number = 1 + [n["title"] for n in pair].index(keep_title)
                    res = self.run_wise("resolve", "BK-ddia", "--keep", str(number),
                                        check=False)
                    self.assertEqual(res.returncode, 0, res.stderr)
                    [kept] = self.versions("BK-ddia")
                    self.assertEqual(kept["title"], keep_title)
                    self.assertEqual(kept["projects"], ["a", "b"])

    def test_resolved_book_still_includes_the_original_kept_version(self):
        # Review on #34: uniting projects into the kept version before hashing
        # recorded the edited copy, so the original came back as a conflict.
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf")
        base = self.versions("BK-ddia")[0]
        seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29", "rev": 1}
        a = {**base, **seen, "projects": ["a"], "title": "A"}
        b = {**base, **seen, "projects": ["b"], "title": "B"}
        c = {**base, **seen, "projects": ["c"], "title": "C"}
        lines = [l for l in self.nodes_file().read_text(encoding="utf-8").splitlines()
                 if json.loads(l)["id"] != "BK-ddia"]
        self.nodes_file().write_text("\n".join(lines + [self.line(a), self.line(b)]) + "\n",
                                     encoding="utf-8")
        self.out("resolve", "BK-ddia", "--keep", "1")
        self.with_lines(self.line(a), self.line(c))
        self.assertIn("2 versions", self.out("resolve", "BK-ddia"))

    def test_malformed_metadata_is_not_combined(self):
        # Review on #34: "at": null beside a text `at` crashed the combine.
        self.run_wise("add", "concept", "name=Alpha")
        base = self.versions("alpha")[0]
        seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29", "rev": 1}
        self.with_lines(self.line({**base, **seen, "at": None}),
                        self.line({**base, **seen, "at": "2026-10-29T10:00:00"}))
        text = self.nodes_file().read_text(encoding="utf-8")
        res = self.run_wise("check", check=False)
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("alpha", res.stdout + res.stderr)
        self.assertEqual(self.nodes_file().read_text(encoding="utf-8"), text)

    def question_versions(self, ours_fields, theirs_fields):
        self.run_wise("add", "question", "q=Why?", "a=Because.")
        self.run_wise("add", "concept", "name=Other")
        [base] = [n for n in self.nodes() if n["type"] == "question"]
        seen = {"seen": [wise.version_id(base)], "updated": "2026-10-29", "rev": 1}
        ours = {**base, **seen, **ours_fields}
        theirs = {**base, **seen, "rev": 2, **theirs_fields}
        for field in ("box", "due"):
            for node in (ours, theirs):
                if node.get(field) is None:
                    node.pop(field, None)
        lines = [l for l in self.nodes_file().read_text(encoding="utf-8").splitlines()
                 if json.loads(l)["id"] != base["id"]]
        return base["id"], lines, ours, theirs

    def test_a_schedule_changed_on_both_sides_merges_to_the_sooner_review(self):
        # Box and due are computed from answers, and both answers are kept:
        # take the lower box and the earlier due, each, in either line order.
        for order in ("ours-first", "theirs-first"):
            with self.subTest(order=order):
                shutil.rmtree(self.project / ".wise-code", ignore_errors=True)
                qid, lines, ours, theirs = self.question_versions(
                    {"box": 3, "due": "2026-11-01"}, {"box": 2, "due": "2026-11-09"})
                pair = [ours, theirs] if order == "ours-first" else [theirs, ours]
                self.nodes_file().write_text("\n".join(lines + [self.line(n) for n in pair])
                                             + "\n", encoding="utf-8")
                res = self.run_wise("set", "other", "definition=x")
                self.assertNotIn("conflicting", res.stderr)
                [kept] = self.versions(qid)
                self.assertEqual((kept["box"], kept["due"]), (2, "2026-11-01"))
                self.assertEqual(kept["rev"], 2)
                # Bringing either side back later changes nothing.
                for old in (ours, theirs):
                    self.with_lines(self.line(old))
                    self.assertNotIn("conflicting",
                                     self.run_wise("set", "other", "definition=y").stderr)
                    [again] = self.versions(qid)
                    self.assertEqual((again["box"], again["due"]), (2, "2026-11-01"))

    def test_a_missing_due_means_due_now_and_wins(self):
        qid, lines, ours, theirs = self.question_versions(
            {"box": 3, "due": None}, {"box": 4, "due": "2026-11-09"})
        self.nodes_file().write_text("\n".join(lines + [self.line(ours), self.line(theirs)])
                                     + "\n", encoding="utf-8")
        self.assertNotIn("conflicting", self.run_wise("set", "other", "definition=x").stderr)
        [kept] = self.versions(qid)
        self.assertEqual(kept["box"], 3)
        self.assertNotIn("due", kept)

    def test_schedule_lines_from_before_seen_also_merge(self):
        # Graphs written before `seen` existed: the rule is by field, not ancestry.
        qid, lines, ours, theirs = self.question_versions({"box": 3}, {"box": 5})
        for node in (ours, theirs):
            node.pop("seen")
        self.nodes_file().write_text("\n".join(lines + [self.line(ours), self.line(theirs)])
                                     + "\n", encoding="utf-8")
        self.assertNotIn("conflicting", self.run_wise("set", "other", "definition=x").stderr)
        self.assertEqual(self.versions(qid)[0]["box"], 3)

    def test_a_question_changed_beyond_its_schedule_still_waits(self):
        qid, lines, ours, theirs = self.question_versions(
            {"box": 3}, {"box": 2, "a": "Because, really."})
        self.nodes_file().write_text("\n".join(lines + [self.line(ours), self.line(theirs)])
                                     + "\n", encoding="utf-8")
        res = self.run_wise("set", "other", "definition=x")
        self.assertIn(f"conflicting versions from a merge: {qid}", res.stderr)

    def test_show_hides_merge_history(self):
        self.run_wise("add", "concept", "name=Alpha")
        self.run_wise("set", "alpha", "notes+=one")
        self.assertNotIn("seen", self.out("show", "alpha").splitlines()[0])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_real_git_merge_of_unequal_stamps_keeps_both_edits(self):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.temp.name,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}

        def git(cwd, *args):
            return subprocess.run(["git", "-C", str(cwd), *args], text=True,
                                  capture_output=True, env=env, timeout=30)
        shutil.rmtree(self.project / ".git")
        git(self.project, "init", "-q", "-b", "main")
        self.run_wise("add", "concept", "name=Alpha")
        self.run_wise("add", "concept", "name=Other")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "base")
        clone = Path(self.temp.name) / "clone"
        git(self.temp.name, "clone", "-q", str(self.project), str(clone))
        # Different fields, different stamps: ours edits once, theirs twice a day later.
        self.run_wise("set", "alpha", "definition=ours", day="2026-10-29")
        git(self.project, "commit", "-qam", "ours")
        self.run_wise("set", "alpha", "notes+=theirs", root=clone, day="2026-10-30")
        self.run_wise("set", "alpha", "notes+=again", root=clone, day="2026-10-30")
        git(clone, "commit", "-qam", "theirs")
        git(self.project, "fetch", "-q", str(clone), "main")
        merge = git(self.project, "merge", "-q", "--no-edit", "FETCH_HEAD")
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        res = self.run_wise("set", "other", "definition=x", check=False)
        self.assertIn("conflicting versions from a merge: alpha", res.stderr)
        shown = self.out("resolve", "alpha")
        self.assertIn("2 versions", shown)
        self.assertIn("ours", shown)
        self.assertIn("again", shown)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_real_git_merge_of_same_day_edits_waits_for_resolve(self):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.temp.name,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}

        def git(cwd, *args):
            return subprocess.run(["git", "-C", str(cwd), *args], text=True,
                                  capture_output=True, env=env, timeout=30)
        shutil.rmtree(self.project / ".git")
        git(self.project, "init", "-q", "-b", "main")
        self.run_wise("add", "concept", "name=Alpha")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "base")
        tracked = git(self.project, "ls-files").stdout.split()
        self.assertFalse([f for f in tracked if f.endswith((".lock", ".commit", ".tmp"))])
        clone = Path(self.temp.name) / "clone"
        git(self.temp.name, "clone", "-q", str(self.project), str(clone))
        for root, note in ((self.project, "ours"), (clone, "theirs")):
            self.run_wise("set", "alpha", f"notes+={note}", root=root, day="2026-10-29")
            git(root, "commit", "-qam", note)
        git(self.project, "fetch", "-q", str(clone), "main")
        merge = git(self.project, "merge", "-q", "--no-edit", "FETCH_HEAD")
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        self.assertEqual(len(self.versions("alpha")), 2)
        self.assertIn("2 versions", self.out("resolve", "alpha"))


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

    def test_malformed_answers_are_rejected_and_nothing_is_recorded(self):
        # bool("false") is True: a string verdict was stored as correct (review #32).
        good = {"q": "Q1", "answer": "a", "correct": True}
        bad_answers = {
            "string false": {"q": "Q", "answer": "wrong", "correct": "false", "expected": "right"},
            "number": {"q": "Q", "answer": "a", "correct": 0},
            "null": {"q": "Q", "answer": "a", "correct": None},
            "missing": {"q": "Q", "answer": "a"},
            "not an object": "Q: a",
            "non-string text": {"q": ["Q"], "answer": "a", "correct": True},
        }
        self.run_wise("add", "qa", "q=Q0", "a=A0", "source=asked")  # graph exists
        before = self.nodes()
        folder = Path(self.temp.name)
        for label, bad in bad_answers.items():
            with self.subTest(label):
                path = folder / "results.json"
                path.write_text(json.dumps({"result_id": f"r-{len(label)}", "lesson": "0001",
                                            "answers": [good, bad]}), encoding="utf-8")
                result = self.run_wise("import-lesson", str(path), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("answer 2", result.stderr)
                self.assertEqual(self.nodes(), before)

    def test_malformed_payload_is_rejected(self):
        folder = Path(self.temp.name)
        for label, data in {"result_id not a string": {"result_id": 7, "answers": []},
                            "answers not a list": {"result_id": "r", "answers": {}},
                            "not an object": [], "lesson not a string": {
                                "result_id": "r", "lesson": 1, "answers": []}}.items():
            with self.subTest(label):
                path = folder / "results.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                result = self.run_wise("import-lesson", str(path), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("results.json", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

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

    def test_text_book_sections_and_citations_carry_line_ranges(self):
        s = {"root": self.shelf}
        self.run_wise("add", "book", "slug=notes", "title=Notes", "file=shared/notes.md", **s)
        self.run_wise("add", "section", "book=notes", "number=2", "title=Backoff",
                      "lines=12-40", **s)
        cid = self.out("add", "citation", "project=p", "question=Q", "lines=14-15",
                       "--on", "SEC-notes-2", **s).strip()
        nodes = {n["id"]: n for n in self.nodes(self.shelf)}
        self.assertEqual(nodes["SEC-notes-2"]["lines"], "12-40")
        self.assertEqual(nodes[cid]["lines"], "14-15")
        self.assertNotIn("page", nodes[cid])
        self.run_wise("set", "SEC-notes-2", "lines=7", **s)  # one line is a range too
        for bad in ("40-12", "0-3", "12 - 40", "abc"):
            result = self.run_wise("set", "SEC-notes-2", f"lines={bad}", check=False, **s)
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn("section.lines must be a line range", result.stderr + result.stdout)
        # The location is the index's line range; the heading field is gone.
        result = self.run_wise("add", "citation", "project=p", "question=Q",
                               "heading=Backoff", check=False, **s)
        self.assertIn("citation has no field 'heading'", result.stderr + result.stdout)

    def test_check_flags_text_books_indexed_before_line_ranges(self):
        s = {"root": self.shelf}
        # An index built before line ranges: a Markdown section with pages only.
        self.run_wise("add", "book", "slug=notes", "title=Notes", "file=shared/notes.md", **s)
        self.run_wise("add", "section", "book=notes", "number=1", "title=Intro",
                      "pages=1-1", **s)
        self.run_wise("add", "book", "slug=ddia", "title=DDIA", "file=shared/ddia.pdf", **s)
        self.run_wise("add", "section", "book=ddia", "number=1", "title=Reliable",
                      "pages=3-9", **s)
        report = self.out("check", **s)
        self.assertIn("warning: BK-notes: Markdown or text book indexed without line ranges "
                      "(SEC-notes-1); rebuild its L1", report)
        self.assertNotIn("BK-ddia", report)  # a PDF is located by pages
        self.run_wise("set", "SEC-notes-1", "lines=1-12", **s)
        self.assertNotIn("BK-notes", self.out("check", **s))

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


class ConfusionTests(WiseTestCase):
    """Confidence, confusions, repair by transfer, and the capped skip gate."""

    def setUp(self):
        super().setUp()
        self.run_wise("add", "concept", "name=Ownership")
        self.run_wise("add", "concept", "name=Borrowing")
        self.run_wise("link", "borrowing", "prereq", "ownership")

    def qa(self, concept, verdict, q="Q?", confidence=None, day="2026-10-28",
           repairs=(), source="checkpoint"):
        args = ["add", "qa", f"source={source}", f"q={q}", "a=A", f"verdict={verdict}",
                "said=because the owner drops it", "--about", concept]
        if confidence:
            args.append(f"confidence={confidence}")
        for miss in repairs:
            args += ["--repairs", miss]
        return self.out(*args, day=day).strip()

    def repair(self, concept, *misses, q="Fresh transfer question?", verdict="correct"):
        return self.qa(concept, verdict, q=q, repairs=misses, source="repair")

    def test_what_counts_as_a_confusion(self):
        # A correct answer from the day before can't repair today's misses.
        self.qa("ownership", "correct", q="d", confidence="high", day="2026-10-27")
        wrong_low = self.qa("ownership", "wrong", q="a", confidence="low")
        partial_high = self.qa("ownership", "partial", q="b", confidence="high")
        self.qa("ownership", "partial", q="c", confidence="mid")
        out = self.out("confusions")
        self.assertIn(wrong_low, out)
        self.assertIn(partial_high, out)
        self.assertEqual(out.count("QA-"), 2)
        self.assertIn("gate: repair first", out)

    def test_bad_confidence_is_rejected(self):
        bad = self.run_wise("add", "qa", "source=quiz", "q=x", "a=y", "confidence=sure",
                            check=False)
        self.assertEqual(bad.returncode, 2)

    def test_only_a_different_later_question_repairs(self):
        miss = self.qa("ownership", "wrong", q="Why does the move invalidate x?")
        self.repair("ownership", miss, q="Why does the move invalidate x?")
        self.assertIn(miss, self.out("confusions"))  # same question: recall, not transfer
        self.repair("ownership", miss, q="Where would the poller lose ownership here?")
        self.assertIn("no open confusions", self.out("confusions"))
        self.assertIn("gate: clear", self.out("confusions"))

    def test_an_unlinked_correct_answer_on_the_concept_does_not_repair(self):
        # The demo that found the bug: a miss about char indexing was cleared by an
        # unrelated correct answer about len(), only because both share a concept.
        miss = self.qa("ownership", "wrong", q="Why can't you index a String by char?",
                       confidence="high")
        self.qa("ownership", "correct", q="What does s.len() return?", source="quiz")
        self.assertIn(miss, self.out("confusions"))
        self.assertIn("gate: repair first", self.out("confusions"))

    def test_a_wrong_repair_attempt_does_not_repair(self):
        miss = self.qa("ownership", "wrong", q="move")
        self.repair("ownership", miss, verdict="wrong")
        out = self.out("confusions")
        self.assertIn(miss, out)
        self.assertEqual(out.count("QA-"), 2)  # the failed attempt is a confusion too

    def test_repair_clears_only_the_misses_it_links(self):
        first = self.qa("ownership", "wrong", q="first miss")
        second = self.qa("ownership", "wrong", q="second miss")
        self.repair("ownership", first)
        out = self.out("confusions")
        self.assertNotIn(first, out)
        self.assertIn(second, out)

    def test_repairs_must_point_at_a_confusion(self):
        fine = self.qa("ownership", "correct", q="fine")
        bad = self.run_wise("add", "qa", "source=repair", "q=x", "a=y", "verdict=correct",
                            "said=the owner frees it", "--about", "ownership", "--repairs", fine, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("is not a confusion", bad.stderr)

    def test_render_qa_shows_confidence(self):
        self.qa("ownership", "wrong", q="move", confidence="high")
        self.assertIn("Verdict: wrong · Confidence: high", self.out("render", "qa"))

    def test_correct_answer_before_the_miss_does_not_repair(self):
        self.qa("ownership", "correct", q="Earlier question", day="2026-10-27")
        miss = self.qa("ownership", "wrong", q="Later miss", day="2026-10-28")
        self.assertIn(miss, self.out("confusions"))

    def test_gate_covers_prerequisites(self):
        miss = self.qa("ownership", "wrong", q="move")
        self.assertIn("no open confusions", self.out("confusions", "--concept", "borrowing"))
        out = self.out("confusions", "--concept", "borrowing", "--with-prereqs")
        self.assertIn(miss, out)

    def test_skips_are_capped_until_one_is_repaired(self):
        misses = [self.qa("ownership", "wrong", q=f"miss {n}") for n in range(3)]
        for miss in misses[:2]:
            self.assertIn("skipped", self.out("skip-repair", miss))
        third = self.run_wise("skip-repair", misses[2], check=False)
        self.assertEqual(third.returncode, 1)
        self.assertIn("Repair one of them first", third.stdout)
        self.assertIn("blocked", self.out("confusions"))
        # Repairing frees capacity. One fresh question may target several misses
        # when it tests the idea they share; each one it repairs is linked.
        self.repair("ownership", *misses)
        self.assertIn("no open confusions", self.out("confusions"))
        self.assertIn("skips open 0/2", self.out("confusions"))

    def test_answer_records_confidence_and_flags_a_confusion(self):
        qid = self.out("add", "question", "q=Why move?", "a=Ownership.", "--tests",
                       "ownership").strip()
        out = self.out("answer", qid, "wrong", "--confidence", "high", "--answer", "copy")
        self.assertIn("confusion:", out)
        self.assertIn("(high)", self.out("history"))

    def test_calibration_counts_and_lists_sure_misses(self):
        self.qa("ownership", "correct", q="a", confidence="high")
        sure_miss = self.qa("ownership", "wrong", q="b", confidence="high")
        self.qa("ownership", "wrong", q="c", confidence="low")
        out = self.out("calibration")
        self.assertIn("high: 2 answers · 50% correct", out)
        self.assertIn("low: 1 answers · 0% correct", out)
        self.assertIn(f"sure but missed: {sure_miss}", out)


if __name__ == "__main__":
    unittest.main()
