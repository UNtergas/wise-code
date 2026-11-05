#!/usr/bin/env python3
"""WiseCode learning graph: the only reader and writer of a project's learning data.

The graph lives in <repo>/.wise-code/graph/ as two sorted JSONL files:
nodes.jsonl (one object per line, keyed by "id") and edges.jsonl
({"from", "rel", "to"}). Claude never edits them directly; every write goes
through this script, which assigns collision-free IDs, validates fields and
edges, and rewrites the files atomically. Queries print compact one-line
results with a size cap, so a lookup costs a slice of the history, not all of it.

Standard library only, Python 3.9+. Spec: docs/graph.md. Usage: wise.py --help.
"""

import argparse
import datetime as dt
import difflib
import errno
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata

try:  # Graph lock: flock on Unix, byte-range locking on Windows.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
    import msvcrt

if sys.version_info < (3, 9):  # pragma: no cover - checked by the caller's interpreter
    sys.stderr.write("wise.py needs Python 3.9 or newer\n")
    sys.exit(3)

# Query output budget: about 1.5k tokens at ~4 characters per token.
CAP_CHARS = 6000
DEFAULT_LIMIT = 10
# Leitner boxes: box -> days until the next review.
BOXES = {1: 1, 2: 3, 3: 7, 4: 21, 5: 60}

VERDICTS = ("correct", "partial", "wrong", "n/a")
QA_SOURCES = ("checkpoint", "review", "quiz", "lesson", "explore", "critique",
              "reflect", "asked", "start-check", "shelf", "repair")
CONFIDENCE = ("low", "mid", "high")
# Confusions skipped with "skip repair" that may stay open at once. One more
# skip is refused: the learner repairs one first.
SKIP_CAPACITY = 2
READ_VERDICTS = ("understood", "partial", "misread", "skipped-read")
# Attribution: a record that says what the learner thought carries `said`, a
# verbatim span of their own message. `check-said` matches it against this
# project's session transcripts. Parts of one span are joined with " … ".
SAID_CHECKS = ("unchecked", "ok", "missing", "unverified")
SAID_SEP = " … "
SAID_MIN_WORDS, SAID_MAX_WORDS = 3, 40
# QA sources where `a` is the learner's reasoning, so `said` is required.
LEARNER_QA_SOURCES = ("checkpoint", "explore", "reflect", "repair")

# Field kinds: "str", "list", "int", "date", "range" (a line range, "12-40" or
# "7"), or a tuple of allowed values.
# "prefix" is the ID prefix; None means the ID is a slug the caller provides.
TYPES = {
    "concept": {"prefix": None, "required": ["name"], "fields": {
        "name": "str", "aliases": "list", "definition": "str",
        "status": ("introduced", "demonstrated", "reinforce"),
        "notes": "list", "code": "list", "shelf": "list", "glossary": "str",
        "avoid": "list"}},
    "qa": {"prefix": "QA", "required": ["q", "a", "source"], "fields": {
        "date": "date", "source": QA_SOURCES, "q": "str", "a": "str",
        "verdict": VERDICTS, "hints": "int", "followup": "str",
        "result": "str", "project": "str", "confidence": CONFIDENCE,
        "skipped": "date", "said": "str", "said_check": SAID_CHECKS,
        "said_hash": "str"}},
    "question": {"prefix": "QB", "required": ["q", "a"], "fields": {
        "q": "str", "a": "str", "source": "str", "box": "int", "due": "date",
        "legacy": "str"}},
    "card": {"prefix": "CARD", "required": ["front", "back"], "fields": {
        "front": "str", "back": "str", "tags": "list"}},
    "session": {"prefix": "S", "required": ["goal"], "fields": {
        "date": "date", "goal": "str", "finished": "list", "learned": "list",
        "decided": "list", "open": "list", "checkpoints": "list",
        "start_check": "str"}},
    "decision": {"prefix": "D", "required": ["title"], "fields": {
        "date": "date", "title": "str", "status": ("pending", "settled"),
        "stage": ("awaiting-reasoning", "choice-confirmation",
                  "implementation-approval"),
        "proposal": "str", "outcome": "str", "by": ("learner", "ai", "both"),
        "said": "str", "said_check": SAID_CHECKS, "said_hash": "str"}},
    "guardrail": {"prefix": "G", "required": ["mistake"], "fields": {
        "mistake": "str", "evidence": "list",
        "level": ("design", "types", "lint", "test", "note"),
        "enforced_by": "str", "proven": "str", "retired": "str"}},
    "reflection": {"prefix": "R", "required": ["text"], "fields": {
        "date": "date", "text": "str", "evidence_check": "str",
        "said_check": SAID_CHECKS, "said_hash": "str"}},
    "feedback": {"prefix": "FB", "required": ["what"], "fields": {
        "date": "date", "what": "str", "guide": "str", "rule": "str",
        "proposed_edit": "str",
        "status": ("proposed", "accepted", "rejected", "applied")}},
    "record": {"prefix": "LR", "required": ["title", "body"], "fields": {
        "date": "date", "title": "str", "body": "str",
        "status": ("active", "superseded"), "evidence": "str",
        "implications": "str", "legacy": "str"}},
    # Tier 2: a file is the store; the node indexes it.
    "lesson": {"prefix": "LES", "required": ["path", "title"],
               "fields": {"path": "str", "title": "str"}},
    "reference": {"prefix": "REF", "required": ["path", "title"],
                  "fields": {"path": "str", "title": "str"}},
    "research": {"prefix": "RES", "required": ["path", "title"],
                 "fields": {"path": "str", "title": "str", "question": "str"}},
    "adr": {"prefix": "ADR", "required": ["path", "title"],
            "fields": {"path": "str", "title": "str"}},
    "mission": {"prefix": "MIS", "required": ["path", "title"],
                "fields": {"path": "str", "title": "str"}},
    "resource": {"prefix": "SRC", "required": ["title"], "fields": {
        "title": "str", "url": "str", "kind": ("knowledge", "community"),
        "note": "str", "path": "str"}},
    # Shelf: books and sections have stable slug IDs shared by every project.
    "book": {"prefix": "BK", "required": ["slug", "title", "file"], "fields": {
        "slug": "str", "title": "str", "file": "str", "folder": "str",
        "pages": "int", "l1": "date", "projects": "list"}},
    "section": {"prefix": "SEC", "required": ["book", "number", "title"],
                "fields": {"book": "str", "number": "str", "title": "str",
                           "pages": "str", "printed": "str", "lines": "range",
                           "concepts": "list",
                           "l2": "date"}},
    "citation": {"prefix": "CIT", "required": ["project", "question"], "fields": {
        "date": "date", "project": "str", "question": "str", "quote": "str",
        "page": "int", "lines": "range", "status": ("sent",) + READ_VERDICTS,
        "updated": "date"}},
    "read": {"prefix": "RD", "required": ["project"], "fields": {
        "date": "date", "project": "str", "verdict": READ_VERDICTS,
        "evidence": "str"}},
    "explainback": {"prefix": "EB", "required": ["project", "text"], "fields": {
        "date": "date", "project": "str", "text": "str",
        "verdict": READ_VERDICTS}},
}

META = ("id", "type", "created", "updated", "rev", "at", "seen")
# Stored kinds of the metadata every record may carry (id and type checked apart).
META_FIELDS = {"created": "date", "updated": "date", "rev": "int", "at": "str",
               "seen": "list"}
# How many earlier versions a node remembers (`seen`). A version this many
# edits back on one side, merged with the other, reads as divergent: resolve asks.
MERGE_HISTORY = 16
# Allowed ranges for int fields; others must be 0 or more.
RANGES = {("question", "box"): (min(BOXES), max(BOXES))}
TIER2 = ("lesson", "reference", "research", "adr", "mission", "resource")
SHELF_RECORDS = ("citation", "read", "explainback")
ANY = tuple(TYPES)

# rel -> (allowed source types, allowed target types)
RELS = {
    "about": (("qa", "decision", "record", "citation", "explainback", "feedback",
               "reflection"), ("concept",)),
    "in": (("qa", "decision", "reflection", "feedback", "question", "card",
            "record"), ("session",)),
    "answers": (("qa",), ("question",)),
    "tests": (("question", "card"), ("concept",)),
    "prereq": (("concept",), ("concept",)),
    "covers": (TIER2 + ("record", "section"), ("concept",)),
    "supersedes": (("record",), ("record",)),
    "of": (("section",), ("book",)),
    "on": (SHELF_RECORDS, ("section",)),
    "for": (("explainback", "read"), ("citation",)),
    "evidence": (("guardrail",), ("qa",)),
    "repairs": (("qa",), ("qa",)),
    "from": (("question", "card"), ("qa", "record", "lesson", "citation",
                                    "section")),
}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RANGE_RE = re.compile(r"^([1-9][0-9]*)(?:-([1-9][0-9]*))?$")


def range_problem(kind, field, value):
    """Why a value is not a line range ("12-40", or "7" for one line), or None."""
    match = RANGE_RE.match(value) if isinstance(value, str) else None
    if match and int(match.group(1)) <= int(match.group(2) or match.group(1)):
        return None
    return f"{kind}.{field} must be a line range like 12-40; got {value!r}"
# Leftover markers from a merge done without the union driver.
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)")
# Git keeps both sides' lines when two clones add records, instead of a conflict.
GITATTRIBUTES = "*.jsonl merge=union\n"
# Process-local files in graph/: the lock, the commit journal, and temp files
# (named .<file>.<random>.tmp). Git ignores them; they never merge.
LOCK_NAME = ".lock"
JOURNAL_NAME = ".commit"
GRAPH_IGNORE = f"{LOCK_NAME}\n{JOURNAL_NAME}\n.*.tmp\n"
DATA_FILES = ("nodes.jsonl", "edges.jsonl")
# Every file wise.py keeps inside graph/; none of them may be a symlink.
GRAPH_FILES = (*DATA_FILES, ".gitattributes", ".gitignore", LOCK_NAME, JOURNAL_NAME)
# Errors meaning graph/ can't be written (a read-only mount, no permission):
# reads go on without the lock, writes are refused.
READ_ONLY_ERRORS = (errno.EROFS, errno.EACCES, errno.EPERM)
# How long a command waits for another wise.py using the same graph.
LOCK_TIMEOUT = 20.0


def canonical(node):
    """One node as its stored line."""
    return json.dumps(node, ensure_ascii=False, sort_keys=True)


def stamp(node):
    return (node.get("updated") or node.get("created") or "", node.get("rev", 0))


def version_id(node):
    """A short content hash naming one version of a node."""
    return hashlib.sha256(canonical(node).encode("utf-8")).hexdigest()[:12]


def remember(node, *versions):
    """Record that `node` includes `versions` (ids), keeping the newest MERGE_HISTORY."""
    seen = [v for v in node.get("seen", []) if v not in versions] + list(versions)
    node["seen"] = seen[-MERGE_HISTORY:]


def surviving_versions(versions):
    """The versions of one node a union merge left that no other version includes.

    A version is dropped when it is identical to an earlier one or when another
    version lists it in `seen` (that one was edited from it). What remains are
    independent edits: one means the merge is settled; more than one must be
    resolved by the learner, whatever their stamps say, since a higher rev or a
    later date doesn't show that side saw the other's change.
    """
    unique = []
    for node in versions:
        if canonical(node) not in (canonical(u) for u in unique):
            unique.append(node)
    included = {v for node in unique for v in node.get("seen", [])}
    return [node for node in unique if version_id(node) not in included]


class WiseError(Exception):
    """A user-facing failure: printed as one line, exit status 2."""


# ---------------------------------------------------------------- utilities

def today():
    # Tests pin the date; normal runs use the local calendar day.
    override = os.environ.get("WISE_TODAY")
    return dt.date.fromisoformat(override) if override else dt.date.today()


def iso(day):
    return day.isoformat()


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "untitled"


def short(text, width=90):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def stamp_now():
    """Date (pinned in tests) plus wall-clock time: orders records within a day."""
    return f"{iso(today())}T{dt.datetime.now().time().isoformat()}"


def new_id(prefix, existing):
    stamp = today().strftime("%Y%m%d")
    for _ in range(1000):
        candidate = f"{prefix}-{stamp}-{secrets.token_hex(2)}"
        if candidate not in existing:
            return candidate
    raise WiseError(f"could not find a free {prefix} id for {stamp}")


# ---------------------------------------------------------------- location

def git_root(start):
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def find_state(start, create=False):
    """Locate .wise-code the way the Learn guide does (nearest, inside Git)."""
    start = start.resolve()
    root = git_root(start)
    if root is None:
        candidates = [start]
    else:
        candidates = [start, *start.parents][: len(start.relative_to(root).parts) + 1]
    for directory in candidates:
        state = directory / ".wise-code"
        if state.exists() or state.is_symlink():
            if state.is_symlink() or not state.is_dir():
                raise WiseError(f"{state} is a symlink or not a directory; refusing")
            return state
    if not create:
        return None
    state = (root or start) / ".wise-code"
    state.mkdir()
    return state


# ---------------------------------------------------------------- store

class Graph:
    """The learning graph, locked from load to close.

    Every command that opens a graph holds an exclusive lock on graph/.lock
    until close(), so a save always writes the snapshot it loaded: two
    processes take turns instead of overwriting each other (review #19, 1).
    Use it as a context manager. A save publishes both files through a commit
    journal, so a crash leaves the old graph or the new one, never a mix (6).
    """

    def __init__(self, state, write=False, timeout=LOCK_TIMEOUT):
        self.state = state
        self.dir = state / "graph"
        self.nodes = {}
        self.edges = set()
        # id -> canonical JSON of each independent version a union merge left;
        # nodes[id] holds the first until `resolve` picks one.
        self.conflicts = {}
        # id -> version_id of the version loaded, so touch() can record that
        # the edited node includes it; ids already touched in this process.
        self._loaded = {}
        self._touched = set()
        self.dirty = False
        self._lock = None
        # The state boundary holds for every path wise.py reads or writes: a
        # symlinked folder would move the files outside it as surely as a
        # symlinked file.
        for path in (state, self.dir, *(self.dir / name for name in GRAPH_FILES)):
            if path.is_symlink():
                raise WiseError(f"{path} is a symlink; refusing")
        # No graph/ yet: nothing to read or lock. save() creates it and
        # refuses if another process got there first.
        if self.dir.is_dir():
            try:
                self._acquire(timeout)
            except OSError as error:
                if error.errno not in READ_ONLY_ERRORS:
                    raise
                if write:
                    raise WiseError(f"can't lock {self.dir}: not writable") from None
                # A read-only checkout: read without the lock, but never a
                # half-committed save.
            try:
                self._recover()
                self._load()
            except BaseException:
                self.close()
                raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        lock, self._lock = getattr(self, "_lock", None), None
        if lock is not None:
            os.close(lock)  # closing the descriptor releases the lock

    # -- lock and commit

    def _acquire(self, timeout):
        path = self.dir / LOCK_NAME
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if fcntl:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:  # pragma: no cover - Windows
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise WiseError(f"{self.dir} is busy: another wise.py is using it; "
                                    "retry when it finishes") from None
                time.sleep(0.05)
        self._lock = fd
        ignore = self.dir / ".gitignore"
        if not ignore.exists():
            self._publish(".gitignore", GRAPH_IGNORE)

    def _fsync_dir(self):
        if hasattr(os, "O_DIRECTORY"):  # POSIX: make renames survive power loss
            fd = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _temp(self, name, text):
        """Write text to a durable temp file beside name; return its file name."""
        handle, temp = tempfile.mkstemp(dir=self.dir, prefix=f".{name}.", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        return Path(temp).name

    def _publish(self, name, text):
        os.replace(self.dir / self._temp(name, text), self.dir / name)
        self._fsync_dir()

    def _checkpoint(self, step):
        """No-op; tests replace it to interrupt a save after each step."""

    def _recover(self):
        """Finish a save that stopped after its journal was published."""
        journal = self.dir / JOURNAL_NAME
        if journal.exists():
            if self._lock is None:
                raise WiseError(f"{self.dir} has an unfinished save; run any write "
                                "command where the graph is writable to finish it")
            try:
                moves = json.loads(journal.read_text(encoding="utf-8"))
                valid = isinstance(moves, list) and all(
                    isinstance(m, list) and len(m) == 2 and m[1] in DATA_FILES
                    and isinstance(m[0], str) and re.fullmatch(r"\.[\w.-]+\.tmp", m[0])
                    for m in moves)
            except ValueError:
                valid = False
            if not valid:
                raise WiseError(f"{journal} is unreadable; restore graph/ from Git")
            # Check every source before moving any: a symlinked temp would
            # put a link to outside data where nodes.jsonl or edges.jsonl is.
            for temp, _ in moves:
                if (self.dir / temp).is_symlink():
                    raise WiseError(f"{self.dir / temp} is a symlink; refusing to "
                                    "finish the save; restore graph/ from Git")
            # Roll forward: a temp already moved is already in place.
            for temp, name in moves:
                if (self.dir / temp).exists():
                    os.replace(self.dir / temp, self.dir / name)
            self._fsync_dir()
            journal.unlink()
            self._fsync_dir()
        if self._lock is not None:
            # Temps no journal names come from a save that stopped before
            # publishing; the old graph is intact, so they are garbage.
            for leftover in self.dir.glob(".*.tmp"):
                leftover.unlink()

    def _load(self):
        lines = {}  # id -> every version on disk, in file order
        nodes_path = self.dir / "nodes.jsonl"
        edges_path = self.dir / "edges.jsonl"
        if nodes_path.is_file():
            for number, line in enumerate(nodes_path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip() or CONFLICT_RE.match(line):
                    continue
                try:
                    node = json.loads(line)
                except ValueError as error:
                    raise WiseError(f"nodes.jsonl line {number}: {error}") from None
                if not isinstance(node, dict) or "id" not in node or "type" not in node:
                    raise WiseError(f"nodes.jsonl line {number}: needs id and type")
                lines.setdefault(node["id"], []).append(node)
        for node_id, versions in lines.items():
            survivors = surviving_versions(versions)
            if len(survivors) < len(versions):
                self.dirty = True  # included or duplicate lines go on the next write
            self.nodes[node_id] = survivors[0]
            if len(survivors) > 1:
                self.conflicts[node_id] = [canonical(n) for n in survivors]
            else:
                self._loaded[node_id] = version_id(survivors[0])
        if edges_path.is_file():
            for number, line in enumerate(edges_path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip() or CONFLICT_RE.match(line):
                    continue
                try:
                    edge = json.loads(line)
                    self.edges.add((edge["from"], edge["rel"], edge["to"]))
                except (ValueError, KeyError, TypeError) as error:
                    raise WiseError(f"edges.jsonl line {number}: {error}") from None

    def _check_unresolved(self, node_id):
        if node_id in self.conflicts:
            raise WiseError(f"{node_id} has {len(self.conflicts[node_id])} conflicting "
                            f"versions from a merge; pick one first: wise.py resolve {node_id}")

    def save(self):
        if not self.dirty:
            return
        for node_id, versions in self.conflicts.items():
            # Every change path is guarded; this catches any that isn't.
            if canonical(self.nodes.get(node_id)) != versions[0]:
                self._check_unresolved(node_id)
        if self._lock is None:
            # graph/ didn't exist at load: lock now, finish any save another
            # process committed but didn't complete, and refuse if the graph
            # exists now (this snapshot is stale).
            self.dir.mkdir(parents=True, exist_ok=True)
            self._acquire(LOCK_TIMEOUT)
            self._recover()
            if any((self.dir / name).exists() for name in DATA_FILES):
                raise WiseError("the graph was created by another wise.py meanwhile; "
                                "nothing saved, retry the command")
        if not (self.dir / ".gitattributes").exists():
            self._publish(".gitattributes", GITATTRIBUTES)
        node_lines = [line for key in sorted(self.nodes)
                      for line in self.conflicts.get(key, [canonical(self.nodes[key])])]
        edge_lines = [json.dumps({"from": a, "rel": r, "to": b}, ensure_ascii=False,
                                 sort_keys=True)
                      for a, r, b in sorted(self.edges)]
        # 1. Both new files, durable, beside their targets.
        moves = [[self._temp(name, "\n".join(lines) + ("\n" if lines else "")), name]
                 for name, lines in (("nodes.jsonl", node_lines), ("edges.jsonl", edge_lines))]
        self._checkpoint("temps written")
        # 2. The journal is the single commit point: once it exists, the new
        #    graph is the graph, and _recover finishes the moves if we stop.
        self._publish(JOURNAL_NAME, json.dumps(moves))
        self._checkpoint("journal published")
        for temp, name in moves:
            os.replace(self.dir / temp, self.dir / name)
            self._checkpoint(f"{name} replaced")
        self._fsync_dir()
        (self.dir / JOURNAL_NAME).unlink()
        self._fsync_dir()
        self.dirty = False

    # -- lookup

    def resolve(self, ref, required=True):
        """Find a node by id, concept alias, or legacy id (QB-0007)."""
        if ref in self.nodes:
            return ref
        lowered = ref.lower()
        if lowered in self.nodes and self.nodes[lowered]["type"] == "concept":
            return lowered
        for node in self.nodes.values():
            if node["type"] == "concept" and lowered in [a.lower() for a in node.get("aliases", [])]:
                return node["id"]
            if node.get("legacy") == ref:
                return node["id"]
        if required:
            raise WiseError(f"no node {ref!r}")
        return None

    def out(self, node_id, rel=None):
        return [b for a, r, b in self.edges if a == node_id and (rel is None or r == rel)]

    def into(self, node_id, rel=None):
        return [a for a, r, b in self.edges if b == node_id and (rel is None or r == rel)]

    def of_type(self, kind):
        return [n for n in self.nodes.values() if n["type"] == kind]

    # -- writes

    def link(self, source, rel, target):
        if rel not in RELS:
            raise WiseError(f"unknown relation {rel!r}; one of: {', '.join(sorted(RELS))}")
        source = self.resolve(source)
        target = self.resolve(target)
        allowed_from, allowed_to = RELS[rel]
        kind_from, kind_to = self.nodes[source]["type"], self.nodes[target]["type"]
        if kind_from not in allowed_from or kind_to not in allowed_to:
            raise WiseError(f"{rel}: {kind_from} → {kind_to} is not allowed "
                            f"({'/'.join(allowed_from)} → {'/'.join(allowed_to)})")
        if source == target:
            raise WiseError("a node can't link to itself")
        if rel == "repairs" and not is_confusion(self.nodes[target]):
            raise WiseError(f"repairs: {target} is not a confusion "
                            "(wrong, or partial at high confidence)")
        if (source, rel, target) not in self.edges:
            self.edges.add((source, rel, target))
            self.dirty = True
        if kind_to == "section" and kind_from in SHELF_RECORDS:
            self._mark_book_project(target, self.nodes[source].get("project"))

    def _mark_book_project(self, section_id, project):
        # A book records every project that cites it, so overlap needs no scan.
        if not project:
            return
        for book_id in self.out(section_id, "of"):
            book = self.nodes[book_id]
            projects = book.setdefault("projects", [])
            if project not in projects:
                projects.append(project)
                projects.sort()
                self.touch(book)

    def touch(self, node):
        """Mark a changed node so a later union merge can tell what it includes."""
        self._check_unresolved(node["id"])
        # Never move the date back: a node dated ahead of today (another
        # time zone, a clock ahead) would otherwise outrank this change.
        node["updated"] = max(iso(today()), node.get("updated") or "",
                              node.get("created") or "")
        node["rev"] = int(node.get("rev", 0)) + 1
        # Name the version this edit started from, so a merge that brings it
        # back knows this one includes it (surviving_versions).
        if node["id"] in self._loaded and node["id"] not in self._touched:
            remember(node, self._loaded[node["id"]])
        self._touched.add(node["id"])
        self.dirty = True

    def remove(self, node_id):
        node_id = self.resolve(node_id)
        self._check_unresolved(node_id)
        del self.nodes[node_id]
        self.edges = {e for e in self.edges if node_id not in (e[0], e[2])}
        self.dirty = True
        return node_id


# ---------------------------------------------------------------- validation

def coerce(kind, field, value):
    spec = TYPES[kind]["fields"].get(field)
    if spec is None:
        raise WiseError(f"{kind} has no field {field!r}; fields: "
                        f"{', '.join(TYPES[kind]['fields'])}")
    if isinstance(spec, tuple):
        if value not in spec:
            raise WiseError(f"{kind}.{field} must be one of {', '.join(spec)}; got {value!r}")
        return value
    if spec == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise WiseError(f"{kind}.{field} must be a number; got {value!r}") from None
        low, high = RANGES.get((kind, field), (None, None))
        if low is not None and not low <= number <= high:
            raise WiseError(f"{kind}.{field} must be {low} to {high}; got {number}")
        return number
    if spec == "date":
        try:
            return iso(dt.date.fromisoformat(str(value)))
        except ValueError:
            raise WiseError(f"{kind}.{field} must be YYYY-MM-DD; got {value!r}") from None
    if spec == "list":
        return value if isinstance(value, list) else [value]
    if spec == "range":
        problem = range_problem(kind, field, str(value))
        if problem:
            raise WiseError(problem)
    return str(value)


def stored_problem(kind, field, value):
    """Why a stored value has the wrong JSON type or range, or None.

    coerce converts CLI text; this checks a record as stored, so a value that
    coerce would convert (the string "3" for an int, "a" for a list) is wrong
    here: later commands read it without converting.
    """
    spec = META_FIELDS.get(field) or TYPES[kind]["fields"].get(field)
    if spec is None:
        return f"{kind} has no field {field!r}"
    if isinstance(spec, tuple):
        ok = isinstance(value, str) and value in spec
        return None if ok else f"{kind}.{field} must be one of {', '.join(spec)}; got {value!r}"
    if spec == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{kind}.{field} must be a whole number; got {value!r}"
        low, high = RANGES.get((kind, field), (0, None))
        if value < low or (high is not None and value > high):
            limit = f"{low} to {high}" if high is not None else f"{low} or more"
            return f"{kind}.{field} must be {limit}; got {value}"
        return None
    if spec == "date":
        try:
            ok = isinstance(value, str) and iso(dt.date.fromisoformat(value)) == value
        except ValueError:
            ok = False
        return None if ok else f"{kind}.{field} must be YYYY-MM-DD; got {value!r}"
    if spec == "list":
        ok = isinstance(value, list) and all(isinstance(item, str) for item in value)
        return None if ok else f"{kind}.{field} must be a list of text; got {value!r}"
    if spec == "range":
        return range_problem(kind, field, value)
    return None if isinstance(value, str) else f"{kind}.{field} must be text; got {value!r}"


def validate_node(node):
    kind = node.get("type")
    if kind not in TYPES:
        return [f"{node.get('id')}: unknown type {kind!r}"]
    if not isinstance(node.get("id"), str) or not node["id"]:
        return [f"{node.get('id')!r}: id must be text"]
    problems = []
    for field in TYPES[kind]["required"]:
        if node.get(field) in (None, "", []):
            problems.append(f"{node['id']}: missing {field}")
    for field, value in node.items():
        if field in ("id", "type"):
            continue
        problem = stored_problem(kind, field, value)
        if problem:
            problems.append(f"{node['id']}: {problem}")
    return problems


def said_parts(text):
    # The spaced separator only: a learner's own "well… so" stays one part.
    return [part.strip() for part in str(text).split(SAID_SEP) if part.strip()]


def attribution_problems(node):
    """Write-time rule: what the learner said is quoted, not paraphrased.

    Checked on add, set and answer, not on load, so graphs written before the
    rule still validate. The fix is always to quote the learner's message.
    """
    kind, said = node["type"], node.get("said", "")
    parts = said_parts(said)
    if said and not parts:
        return [f"{node['id']}: said is empty; quote the learner's words or leave it out"]
    needs = ((kind == "decision" and node.get("status") == "settled"
              and node.get("by") in ("learner", "both"))
             or (kind == "qa" and node.get("source") in LEARNER_QA_SOURCES))
    if needs and not parts:
        what = "a settled learner decision" if kind == "decision" else f"a {node.get('source')} QA"
        return [f"{node['id']}: {what} needs said=\"<the learner's exact words>\"; "
                f"copy a span from their message, parts joined with '{SAID_SEP}'"]
    problems = []
    for part in parts:
        words = len(part.split())
        if words < SAID_MIN_WORDS:
            problems.append(f"{node['id']}: said part {part!r} has {words} word(s); "
                            f"quote at least {SAID_MIN_WORDS} so it identifies one message")
        elif words > SAID_MAX_WORDS:
            problems.append(f"{node['id']}: said part has {words} words; quote at most "
                            f"{SAID_MAX_WORDS}, the words that carry the decision")
    return problems


def quote_of(node):
    """The learner's words a record claims, or '' (reflections: their whole text)."""
    if node.get("type") not in ("qa", "decision", "reflection"):
        return ""
    return node.get("text" if node["type"] == "reflection" else "said") or ""


def quote_hash(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


def said_check_of(node):
    """The stored check, but only if it was made on the quote stored now.

    `set` resets the check on a changed quote, but `edit`, a hand edit, or a
    union merge resolved to another version can change the words and leave an
    old `ok` behind. Binding the check to a hash of the checked words makes
    any such change read as `unchecked`, whatever path changed it.
    """
    check = node.get("said_check", "unchecked")
    if check in ("ok", "missing") and node.get("said_hash") != quote_hash(quote_of(node)):
        return "unchecked"
    return check


def mark_said(node, before):
    """A new or changed quote has not been checked yet."""
    field = "text" if node["type"] == "reflection" else "said"
    if node["type"] in ("qa", "decision", "reflection") and node.get(field) \
            and node.get(field) != before:
        node["said_check"] = "unchecked"
        node.pop("said_hash", None)


def similar_concept(graph, slug, names):
    """Return an existing concept that looks like the same idea, or None."""
    wanted = {slug, *(slugify(n) for n in names)}
    for node in graph.of_type("concept"):
        theirs = {node["id"], slugify(node.get("name", "")),
                  *(slugify(a) for a in node.get("aliases", []))}
        if wanted & theirs:
            return node["id"]
        for a in wanted:
            for b in theirs:
                if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
                    return node["id"]
    return None


# ---------------------------------------------------------------- argument parsing

def parse_assignments(tokens):
    """Split `key=value`, `key+=value`, `key-=value` and `--rel TARGET` tokens."""
    sets, appends, removes, links = {}, {}, {}, []
    tokens = list(tokens)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--") and token[2:] in RELS:
            if index + 1 >= len(tokens):
                raise WiseError(f"{token} needs a target id")
            links.append((token[2:], tokens[index + 1]))
            index += 2
            continue
        match = re.match(r"^([a-z_][a-z0-9_]*)(\+=|-=|=)(.*)$", token, re.DOTALL)
        if not match:
            raise WiseError(f"expected key=value or --relation id, got {token!r}")
        key, op, value = match.groups()
        if op == "=":
            sets[key] = value
        elif op == "+=":
            appends.setdefault(key, []).append(value)
        else:
            removes.setdefault(key, []).append(value)
        index += 1
    return sets, appends, removes, links


def apply_fields(node, sets, appends, removes):
    kind = node["type"]
    for key, value in sets.items():
        spec = TYPES[kind]["fields"].get(key)
        if spec == "list":
            # A plain `tags=a,b` sets the whole list.
            node[key] = [v.strip() for v in value.split(",") if v.strip()] if value else []
        elif value == "":
            node.pop(key, None)
        else:
            node[key] = coerce(kind, key, value)
    for key, values in appends.items():
        if TYPES[kind]["fields"].get(key) != "list":
            raise WiseError(f"{kind}.{key} is not a list; use {key}=value")
        current = node.setdefault(key, [])
        current.extend(v for v in values if v not in current)
    for key, values in removes.items():
        if TYPES[kind]["fields"].get(key) != "list":
            raise WiseError(f"{kind}.{key} is not a list")
        node[key] = [v for v in node.get(key, []) if v not in values]


# ---------------------------------------------------------------- output

class Printer:
    """Print lines until the character budget runs out, then say how many remain."""

    def __init__(self, hint="narrow the query"):
        self.used = 0
        self.hidden = 0
        self.hint = hint

    def line(self, text):
        if self.hidden or self.used + len(text) + 1 > CAP_CHARS:
            self.hidden += 1
            return
        print(text)
        self.used += len(text) + 1

    def done(self, total_more=0):
        more = self.hidden + total_more
        if more:
            print(f"… {more} more; {self.hint}")


def summary(graph, node):
    kind, i = node["type"], node["id"]
    concept_of = lambda nid, rel: ",".join(graph.out(nid, rel)[:3])  # noqa: E731
    if kind == "concept":
        status = node.get("status", "-")
        return f"{i} · concept · {status} · {short(node.get('name', ''), 60)}"
    if kind == "qa":
        confidence = f" ({node['confidence']})" if node.get("confidence") else ""
        return (f"{i} · {node.get('date', '')} · {node.get('source')} · "
                f"{node.get('verdict', '-')}{confidence} · {concept_of(i, 'about') or '-'} · "
                f"Q: {short(node.get('q', ''), 80)}")
    if kind == "question":
        return (f"{i} · {concept_of(i, 'tests') or '-'} · due {node.get('due', '-')} · "
                f"box {node.get('box', 1)} · {short(node.get('q', ''), 90)}")
    if kind == "card":
        return f"{i} · card · {short(node.get('front', ''), 60)} → {short(node.get('back', ''), 50)}"
    if kind == "session":
        return (f"{i} · {node.get('date', '')} · {short(node.get('goal', ''), 60)} · "
                f"start check: {node.get('start_check', '-')}")
    if kind == "decision":
        stage = node.get("stage", "")
        return (f"{i} · decision · {node.get('status', 'pending')}"
                f"{' · ' + stage if stage else ''} · {short(node.get('title', ''), 70)}")
    if kind == "guardrail":
        return (f"{i} · guardrail · {node.get('level', '-')} · proven {node.get('proven', 'no')} · "
                f"{short(node.get('mistake', ''), 70)}")
    if kind == "reflection":
        return f"{i} · {node.get('date', '')} · reflection · {short(node.get('text', ''), 80)}"
    if kind == "feedback":
        return f"{i} · {node.get('status', 'proposed')} · {short(node.get('what', ''), 80)}"
    if kind == "record":
        return f"{i} · record · {node.get('status', 'active')} · {short(node.get('title', ''), 80)}"
    if kind in TIER2:
        where = node.get("path") or node.get("url", "")
        return f"{i} · {kind} · {short(node.get('title', ''), 60)} · {where}"
    if kind == "book":
        projects = ",".join(node.get("projects", [])) or "-"
        return f"{i} · book · {short(node.get('title', ''), 60)} · {node.get('file', '')} · projects {projects}"
    if kind == "section":
        return (f"{i} · {short(node.get('title', ''), 60)} · pp. {node.get('pages', '?')}"
                f"{' · L2' if node.get('l2') else ''}")
    if kind in SHELF_RECORDS:
        target = ",".join(graph.out(i, "on")) or "-"
        state = node.get("status") or node.get("verdict") or "-"
        text = node.get("question") or node.get("text") or node.get("evidence", "")
        return f"{i} · {kind} · {node.get('project')} · {state} · {target} · {short(text, 60)}"
    return f"{i} · {kind}"


def said_lines(node, with_note=True):
    """How a record may be recalled: a quote with its check, or a labeled note."""
    lines = []
    if with_note and node.get("outcome"):
        lines.append(f"  outcome (AI note, not the learner's words): {short(node['outcome'], 200)}")
    if node.get("said"):
        check = said_check_of(node)
        lines.append(f"  learner said «{short(node['said'], 240)}» · check {check}")
    return lines


# ---------------------------------------------------------------- commands: writes

def cmd_add(graph, args):
    kind = args.type
    if kind not in TYPES:
        raise WiseError(f"unknown type {kind!r}; one of: {', '.join(TYPES)}")
    fields = [f for f in args.fields if f != "--force"]
    args.force = args.force or len(fields) != len(args.fields)
    sets, appends, removes, links = parse_assignments(fields)
    if "said_check" in sets or "said_hash" in sets:
        raise WiseError("said_check is set only by check-said")
    spec = TYPES[kind]
    node = {"type": kind}

    if kind == "concept":
        slug = sets.pop("id", None) or slugify(sets.get("name", ""))
        if not SLUG_RE.match(slug):
            raise WiseError(f"concept id must be a lowercase slug; got {slug!r}")
        # Same identity and similar meaning are separate checks: --force
        # overrides only the second, never replacing an existing concept.
        if args.force and slug in graph.nodes:
            raise WiseError(f"concept id {slug!r} is taken; change it with "
                            f"wise.py set {slug} …, or add with a different id=")
        names = [sets.get("name", "")] + appends.get("aliases", [])
        match = similar_concept(graph, slug, names)
        if match and not args.force:
            print(f"exists: {summary(graph, graph.nodes[match])}")
            print(f"use {match}, or add an alias: wise.py set {match} aliases+=<name>; "
                  "--force only for a truly different idea")
            return 1
        node["id"] = slug
    elif kind == "book":
        slug = slugify(sets.get("slug", ""))
        sets["slug"] = slug
        node["id"] = f"BK-{slug}"
    elif kind == "section":
        book = slugify(sets.get("book", ""))
        sets["book"] = book
        number = sets.get("number", "")
        node["id"] = f"SEC-{book}-{slugify(number) if not re.match(r'^[0-9.]+$', number) else number}"
        if f"BK-{book}" not in graph.nodes:
            raise WiseError(f"no book BK-{book}; add the book first")
        links.append(("of", f"BK-{book}"))
    else:
        node["id"] = new_id(spec["prefix"], graph.nodes)

    # Stable shelf IDs upsert: two projects describing the same book converge.
    existing = graph.nodes.get(node["id"]) if kind in ("book", "section") else None
    if existing:
        node = existing
    if "date" in spec["fields"] and "date" not in sets and not existing:
        node["date"] = iso(today())
    if kind == "question" and not existing:
        node.setdefault("box", 1)
        node.setdefault("due", iso(today() + dt.timedelta(days=BOXES[1])))
    if kind == "session":
        node.setdefault("start_check", "pending")
    if kind == "decision":
        node.setdefault("status", "pending")
    if kind == "feedback":
        node.setdefault("status", "proposed")
    if kind == "record":
        node.setdefault("status", "active")
    if kind == "guardrail":
        node.setdefault("proven", "no")
    if kind in SHELF_RECORDS and kind == "citation":
        node.setdefault("status", "sent")
    node["created"] = node.get("created", iso(today()))
    if kind == "qa":
        node["at"] = stamp_now()
    apply_fields(node, sets, appends, removes)
    problems = validate_node(node) + attribution_problems(node)
    if problems:
        raise WiseError("; ".join(problems))
    mark_said(node, None)
    if kind in TIER2 and node.get("path"):
        for other in graph.of_type(kind):
            if other.get("path") == node["path"] and other["id"] != node["id"]:
                print(f"exists: {summary(graph, other)}")
                return 1
    graph.nodes[node["id"]] = node
    if existing:
        graph.touch(node)
    graph.dirty = True
    for rel, target in links:
        graph.link(node["id"], rel, target)
    if kind == "session":
        link_session(graph, node["id"])
    graph.save()
    print(node["id"])
    return 0


def link_session(graph, session_id):
    """Attach this session's unlinked records: everything dated after the last session."""
    session = graph.nodes[session_id]
    earlier = [s["date"] for s in graph.of_type("session")
               if s["id"] != session_id and s.get("date", "") < session["date"]]
    since = max(earlier) if earlier else ""
    for node in list(graph.nodes.values()):
        if node["type"] not in RELS["in"][0] or graph.out(node["id"], "in"):
            continue
        if since < node.get("date", node.get("created", "")) <= session["date"]:
            graph.link(node["id"], "in", session_id)


def cmd_set(graph, args):
    node_id = graph.resolve(args.id)
    node = graph.nodes[node_id]
    sets, appends, removes, links = parse_assignments(args.fields)
    if "id" in sets or "type" in sets:
        raise WiseError("id and type can't change; use merge or delete + add")
    if "said_check" in sets or "said_hash" in sets:
        raise WiseError("said_check is set only by check-said")
    previous_said = node.get("text" if node["type"] == "reflection" else "said")
    apply_fields(node, sets, appends, removes)
    problems = validate_node(node) + attribution_problems(node)
    if problems:
        # Nothing is saved: the error exits before graph.save(). The node is
        # already changed in memory, so a caller that catches WiseError and
        # keeps using this graph must reload it.
        raise WiseError("; ".join(problems))
    mark_said(node, previous_said)
    graph.touch(node)
    for rel, target in links:
        graph.link(node_id, rel, target)
    graph.save()
    print(summary(graph, node))
    return 0


def cmd_link(graph, args):
    graph.link(args.source, args.rel, args.target)
    graph.save()
    return 0


def cmd_unlink(graph, args):
    edge = (graph.resolve(args.source), args.rel, graph.resolve(args.target))
    if edge in graph.edges:
        graph.edges.discard(edge)
        graph.dirty = True
        graph.save()
    return 0


def cmd_delete(graph, args):
    print(f"deleted {graph.remove(args.id)}")
    graph.save()
    return 0


def cmd_merge(graph, args):
    keep, drop = graph.resolve(args.keep), graph.resolve(args.drop)
    if keep == drop:
        raise WiseError("same node")
    graph._check_unresolved(drop)
    a, b = graph.nodes[keep], graph.nodes[drop]
    if a["type"] != b["type"]:
        raise WiseError("can only merge nodes of the same type")
    for field, value in b.items():
        if field in META:
            continue
        if isinstance(value, list):
            target = a.setdefault(field, [])
            target.extend(v for v in value if v not in target)
        elif field not in a:
            a[field] = value
    if a["type"] == "concept":
        aliases = a.setdefault("aliases", [])
        for alias in [drop, b.get("name", "")]:
            if alias and alias not in aliases and alias != a.get("name"):
                aliases.append(alias)
    edges = set()
    for s, r, t in graph.edges:
        s, t = (keep if s == drop else s), (keep if t == drop else t)
        if s != t:
            edges.add((s, r, t))
    graph.edges = edges
    del graph.nodes[drop]
    graph.touch(a)
    graph.save()
    print(f"merged {drop} into {keep}")
    return 0


def cmd_resolve(graph, args):
    """Show a merge conflict's versions, or keep one of them."""
    node_id = graph.resolve(args.id)
    versions = graph.conflicts.get(node_id)
    if not versions:
        raise WiseError(f"{node_id} has no conflicting versions")
    nodes = [json.loads(text) for text in versions]
    if args.keep is None:
        fields = sorted({f for n in nodes for f in n})
        differ = [f for f in fields if f not in META
                  and len({canonical(n.get(f)) for n in nodes}) > 1]
        print(f"{node_id}: {len(nodes)} versions edited apart in different clones; "
              f"they differ in {', '.join(differ)}")
        for number, node in enumerate(nodes, 1):
            print(f"{number}: " + canonical({f: node.get(f) for f in differ}))
        print(f"keep one: wise.py resolve {node_id} --keep <number>")
        return 0
    if not 1 <= args.keep <= len(nodes):
        raise WiseError(f"--keep must be 1 to {len(nodes)}")
    node = nodes[args.keep - 1]
    del graph.conflicts[node_id]
    graph.nodes[node_id] = node
    # The choice includes every version, so it wins every later merge that
    # brings one back.
    remember(node, *(version_id(n) for n in nodes))
    graph.touch(node)
    graph.save()
    print(f"kept version {args.keep} of {node_id}")
    return 0


def cmd_answer(graph, args):
    """Record a quiz or start-check answer: QA entry plus Leitner rescheduling."""
    qid = graph.resolve(args.id)
    question = graph.nodes[qid]
    if question["type"] != "question":
        raise WiseError(f"{qid} is not a question")
    if args.verdict not in ("correct", "partial", "wrong"):
        raise WiseError("verdict: correct, partial or wrong")
    problems = attribution_problems({"id": qid, "type": "qa", "source": args.source,
                                     "said": args.said or ""})
    if problems:
        raise WiseError("; ".join(problems))
    problem = stored_problem("question", "box", question.get("box", 1))
    if problem:
        # Checked before any change, so a bad stored box never half-applies.
        raise WiseError(f"{qid}: {problem}; fix it with wise.py set {qid} box=1")
    if args.source in ("quiz", "start-check") or args.schedule:
        box = question.get("box", 1)
        if args.verdict == "correct":
            box = min(box + 1, 5)
        elif args.verdict == "wrong":
            box = 1
        question["box"] = box
        question["due"] = iso(today() + dt.timedelta(days=BOXES[box]))
        graph.touch(question)
    qa = {"id": new_id("QA", graph.nodes), "type": "qa", "date": iso(today()),
          "created": iso(today()), "source": args.source, "q": question["q"],
          "a": args.answer or "(answered in chat)", "verdict": args.verdict,
          "at": stamp_now()}
    if args.hints:
        qa["hints"] = args.hints
    if args.confidence:
        qa["confidence"] = args.confidence
    if args.said:
        qa["said"] = args.said
        mark_said(qa, None)
    graph.nodes[qa["id"]] = qa
    graph.dirty = True
    graph.link(qa["id"], "answers", qid)
    for concept in graph.out(qid, "tests"):
        graph.link(qa["id"], "about", concept)
    graph.save()
    print(f"{qa['id']} · {qid} now box {question.get('box', 1)} · due {question.get('due', '-')}")
    if is_confusion(qa):
        print(f"confusion: {qa['id']} · repair before building on "
              f"{', '.join(graph.out(qid, 'tests')) or 'this concept'}")
    return 0


# ---------------------------------------------------------------- confusions and repair

def is_confusion(qa):
    """A wrong answer, or a partial one given with high confidence."""
    verdict = qa.get("verdict")
    return verdict == "wrong" or (verdict == "partial" and qa.get("confidence") == "high")


def order(qa):
    return (qa.get("date", ""), qa.get("at", ""), qa["id"])


def same_question(graph, a, b):
    asked_a, asked_b = set(graph.out(a["id"], "answers")), set(graph.out(b["id"], "answers"))
    if asked_a & asked_b:
        return True
    norm = lambda text: " ".join(str(text).lower().split())  # noqa: E731
    return norm(a.get("q", "")) == norm(b.get("q", ""))


def repaired_by(graph, miss, concept):
    """The later correct answer, to a different question, that repairs a confusion.

    Only an answer linked to this miss with `repairs` counts. A correct answer that
    merely shares the concept may test a different idea, so it says nothing about
    whether this misconception is gone.
    """
    for node_id in graph.into(miss["id"], "repairs"):
        node = graph.nodes[node_id]
        if node.get("verdict") != "correct" or concept not in graph.out(node_id, "about"):
            continue
        later = order(node) > order(miss) if (node.get("at") and miss.get("at")) \
            else node.get("date", "") > miss.get("date", "")
        if later and not same_question(graph, node, miss):
            return node["id"]
    return None


def with_prereqs(graph, concepts):
    seen, stack = [], list(concepts)
    while stack:
        concept = stack.pop()
        if concept in seen:
            continue
        seen.append(concept)
        stack.extend(graph.out(concept, "prereq"))
    return seen


def open_confusions(graph, concepts=None):
    """Unrepaired confusions as (qa node, concept), oldest first."""
    found = []
    for node in graph.of_type("qa"):
        if not is_confusion(node):
            continue
        for concept in graph.out(node["id"], "about"):
            if concepts is not None and concept not in concepts:
                continue
            if not repaired_by(graph, node, concept):
                found.append((node, concept))
    found.sort(key=lambda item: order(item[0]))
    return found


def skips_open(graph):
    return sorted({qa["id"] for qa, _ in open_confusions(graph) if qa.get("skipped")})


def gate_line(graph, pending):
    skips = skips_open(graph)
    unskipped = [qa for qa, _ in pending if not qa.get("skipped")]
    if not unskipped:
        state = "clear"
    elif len(skips) >= SKIP_CAPACITY:
        state = "blocked: repair before building (skip capacity used)"
    else:
        state = "repair first (learner may skip)"
    return f"gate: {state} · skips open {len(skips)}/{SKIP_CAPACITY}"


def cmd_confusions(graph, args):
    concepts = None
    if args.concept:
        concepts = [graph.resolve(c) for c in args.concept]
        if args.with_prereqs:
            concepts = with_prereqs(graph, concepts)
    pending = open_confusions(graph, concepts)
    printer = Printer("pass --concept")
    for qa, concept in pending[: args.limit]:
        flags = []
        if qa.get("confidence"):
            flags.append(f"confidence {qa['confidence']}")
        if qa.get("skipped"):
            flags.append(f"skipped {qa['skipped']}")
        printer.line(f"{qa['id']} · {concept} · {qa.get('date', '')} · {qa.get('verdict')}"
                     f"{' · ' + ' · '.join(flags) if flags else ''} · Q: {short(qa.get('q', ''), 80)}")
        printer.line(f"  their answer: {short(qa.get('a', ''), 120)}")
    printer.done(max(0, len(pending) - args.limit))
    if not pending:
        print("no open confusions")
    print(gate_line(graph, pending))
    return 0


def cmd_skip_repair(graph, args):
    qa_id = graph.resolve(args.id)
    qa = graph.nodes[qa_id]
    if qa["type"] != "qa" or not is_confusion(qa):
        raise WiseError(f"{qa_id} is not a confusion")
    open_ids = {node["id"] for node, _ in open_confusions(graph)}
    if qa_id not in open_ids:
        raise WiseError(f"{qa_id} is already repaired")
    if qa.get("skipped"):
        print(f"{qa_id} already skipped on {qa['skipped']}")
        return 0
    skips = skips_open(graph)
    if len(skips) >= SKIP_CAPACITY:
        print(f"refused: {len(skips)}/{SKIP_CAPACITY} skipped confusions still open "
              f"({', '.join(skips)}). Repair one of them first.")
        return 1
    qa["skipped"] = iso(today())
    graph.touch(qa)
    graph.save()
    print(f"skipped {qa_id} · skips open {len(skips) + 1}/{SKIP_CAPACITY}")
    return 0


def cmd_calibration(graph, args):
    """How well confidence predicts correctness; high-confidence misses first."""
    table = {c: {"correct": 0, "partial": 0, "wrong": 0} for c in CONFIDENCE}
    misses = []
    for node in graph.of_type("qa"):
        confidence, verdict = node.get("confidence"), node.get("verdict")
        if args.since and node.get("date", "") < args.since:
            continue
        if confidence in table and verdict in table[confidence]:
            table[confidence][verdict] += 1
            if confidence == "high" and verdict in ("wrong", "partial"):
                misses.append(node)
    for confidence in reversed(CONFIDENCE):
        row = table[confidence]
        total = sum(row.values())
        rate = f"{100 * row['correct'] // total}% correct" if total else "no answers"
        print(f"{confidence}: {total} answers · {rate} · partial {row['partial']} · "
              f"wrong {row['wrong']}")
    misses.sort(key=order, reverse=True)
    printer = Printer("pass --since")
    for node in misses[: args.limit]:
        printer.line(f"  sure but missed: {summary(graph, node)}")
    printer.done(max(0, len(misses) - args.limit))
    return 0


def cmd_edit(graph, args):
    node_id = graph.resolve(args.id)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as stream:
        json.dump(graph.nodes[node_id], stream, ensure_ascii=False, indent=2)
        path = stream.name
    try:
        subprocess.run([*editor.split(), path], check=True)
        node = json.loads(Path(path).read_text(encoding="utf-8"))
    finally:
        os.unlink(path)
    if node.get("id") != node_id or node.get("type") != graph.nodes[node_id]["type"]:
        raise WiseError("id and type can't change in edit")
    old = graph.nodes[node_id]
    for field in ("said_check", "said_hash"):
        if node.get(field) != old.get(field):
            raise WiseError(f"{field} is set only by check-said; leave it as it is")
    problems = validate_node(node) + attribution_problems(node)
    if problems:
        raise WiseError("; ".join(problems))
    mark_said(node, quote_of(old))
    graph.nodes[node_id] = node
    graph.touch(node)
    graph.save()
    print(summary(graph, node))
    return 0


# ---------------------------------------------------------------- commands: queries

def concept_filter(graph, topic):
    if not topic:
        return None
    return graph.resolve(topic)


def cmd_due(graph, args):
    now = iso(today())
    wanted = concept_filter(graph, args.topic)
    due = []
    for node in graph.of_type("question"):
        if node.get("due", now) > now and not args.early:
            continue
        concepts = graph.out(node["id"], "tests")
        if wanted and wanted not in concepts:
            continue
        due.append((node.get("due", ""), concepts[0] if concepts else "", node))
    due.sort(key=lambda item: (item[0], item[2]["id"]))
    # Interleave topics so one topic doesn't fill the round.
    by_topic = {}
    for item in due:
        by_topic.setdefault(item[1], []).append(item[2])
    order = []
    while any(by_topic.values()):
        for topic in list(by_topic):
            if by_topic[topic]:
                order.append(by_topic[topic].pop(0))
    printer = Printer("pass --limit or --topic")
    for node in order[: args.limit]:
        printer.line(summary(graph, node))
    printer.done(max(0, len(order) - args.limit))
    if not order:
        upcoming = sorted(n.get("due", "") for n in graph.of_type("question"))
        print(f"nothing due; next due {upcoming[0]}" if upcoming else "no questions yet")
    return 0


def cmd_session(graph, args):
    sessions = sorted(graph.of_type("session"), key=lambda n: (n.get("date", ""), n["id"]))
    if args.pending:
        sessions = [s for s in sessions if s.get("start_check") == "pending"]
        if args.quiet:
            return 0 if sessions else 1
        sessions = list(reversed(sessions))
    elif args.last:
        sessions = sessions[-1:]
    printer = Printer("pass --limit")
    for node in sessions[: args.limit]:
        printer.line(summary(graph, node))
        if args.pending or args.last:
            for field in ("finished", "learned", "decided", "open", "checkpoints"):
                for item in node.get(field, []):
                    printer.line(f"  {field}: {short(item, 140)}")
    printer.done(max(0, len(sessions) - args.limit))
    if not sessions:
        print("no pending start check" if args.pending else "no sessions yet")
    return 0


def recent_misses(graph, limit_days=None):
    counts = {}
    since = iso(today() - dt.timedelta(days=limit_days)) if limit_days else ""
    for node in graph.of_type("qa"):
        if node.get("verdict") not in ("wrong", "partial") or node.get("date", "") < since:
            continue
        for concept in graph.out(node["id"], "about"):
            counts.setdefault(concept, []).append(node["id"])
    return counts


def cmd_weak(graph, args):
    misses = recent_misses(graph, args.days)
    scored = []
    for node in graph.of_type("concept"):
        score = len(misses.get(node["id"], [])) + (3 if node.get("status") == "reinforce" else 0)
        if score:
            scored.append((-score, node["id"]))
    scored.sort()
    printer = Printer("pass --limit or --days")
    shown = 0
    for score, concept in scored[: args.limit]:
        printer.line(f"{summary(graph, graph.nodes[concept])} · misses {len(misses.get(concept, []))}")
        shown += 1
        if args.with_prereqs:
            for pre in graph.out(concept, "prereq"):
                printer.line(f"  prereq: {summary(graph, graph.nodes[pre])}")
    printer.done(max(0, len(scored) - args.limit))
    if not scored:
        print("no weak concepts")
    return 0


def cmd_show(graph, args):
    node_id = graph.resolve(args.id)
    node = graph.nodes[node_id]
    shown = {k: v for k, v in node.items() if k != "seen"}  # merge bookkeeping
    print(json.dumps(shown, ensure_ascii=False, sort_keys=True))
    printer = Printer(f"pass --rel to filter {node_id}'s links")
    links = [("→", r, b) for a, r, b in sorted(graph.edges) if a == node_id] + \
            [("←", r, a) for a, r, b in sorted(graph.edges) if b == node_id]
    if args.rel:
        links = [link for link in links if link[1] == args.rel]
    # Newest related records first: dates are inside the IDs.
    links.sort(key=lambda link: graph.nodes[link[2]].get("date", ""), reverse=True)
    for arrow, rel, other in links[: args.limit]:
        printer.line(f"{arrow} {rel} {summary(graph, graph.nodes[other])}")
    printer.done(max(0, len(links) - args.limit))
    return 0


def cmd_mistakes(graph, args):
    misses = recent_misses(graph, args.days)
    rows = sorted(((len(v), k, v) for k, v in misses.items() if len(v) >= args.min),
                  reverse=True)
    printer = Printer("pass --min or --days")
    for count, concept, qa_ids in rows[: args.limit]:
        guarded = [g["id"] for g in graph.of_type("guardrail")
                   if set(graph.out(g["id"], "evidence")) & set(qa_ids)]
        printer.line(f"{concept} · {count} misses · {', '.join(sorted(qa_ids)[-4:])}"
                     f"{' · guarded by ' + ','.join(guarded) if guarded else ''}")
        for qa_id in sorted(qa_ids)[-2:]:
            printer.line(f"  {summary(graph, graph.nodes[qa_id])}")
    printer.done(max(0, len(rows) - args.limit))
    if not rows:
        print("no repeated mistakes")
    return 0


def cmd_history(graph, args):
    wanted = concept_filter(graph, args.concept)
    items = []
    for node in graph.of_type("qa"):
        if args.since and node.get("date", "") < args.since:
            continue
        if args.source and node.get("source") != args.source:
            continue
        if wanted and wanted not in graph.out(node["id"], "about"):
            continue
        items.append(node)
    items.sort(key=lambda n: (n.get("date", ""), n["id"]), reverse=True)
    printer = Printer("pass --concept, --since or --source")
    for node in items[: args.limit]:
        printer.line(summary(graph, node))
        if args.full:
            printer.line(f"  A (gist): {short(node.get('a', ''), 200)}")
            for line in said_lines(node, with_note=False):
                printer.line(line)
    printer.done(max(0, len(items) - args.limit))
    if not items:
        print("no matching history")
    return 0


def cmd_decisions(graph, args):
    items = graph.of_type("decision")
    if args.pending:
        items = [d for d in items if d.get("status") == "pending"]
    items.sort(key=lambda n: (n.get("date", ""), n["id"]), reverse=True)
    printer = Printer("pass --limit")
    for node in items[: args.limit]:
        printer.line(summary(graph, node))
        if args.pending and node.get("proposal"):
            printer.line(f"  proposal (AI note, not the learner's words): {short(node['proposal'], 300)}")
        for line in said_lines(node):
            printer.line(line)
    printer.done(max(0, len(items) - args.limit))
    if not items:
        print("no pending decisions" if args.pending else "no decisions")
    return 0


def cmd_list(graph, args):
    kind = args.type
    if kind not in TYPES:
        raise WiseError(f"unknown type {kind!r}")
    items = graph.of_type(kind)
    if args.where:
        key, _, value = args.where.partition("=")
        items = [n for n in items if str(n.get(key, "")) == value
                 or value in (n.get(key) if isinstance(n.get(key), list) else [])]
    wanted = concept_filter(graph, args.concept)
    if wanted:
        items = [n for n in items if wanted in graph.out(n["id"])]
    if kind == "section":
        # A book's outline reads in order: 1, 1.1, 1.2, 2, 10.
        items.sort(key=lambda n: (n.get("book", ""), section_order(n.get("number", ""))))
    else:
        items.sort(key=lambda n: (n.get("date", n.get("created", "")), n["id"]), reverse=True)
    printer = Printer("pass --where, --concept or --limit")
    for node in items[: args.limit]:
        printer.line(summary(graph, node))
    printer.done(max(0, len(items) - args.limit))
    if not items:
        print(f"no {kind} nodes")
    return 0


def section_order(number):
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in str(number).split(".")]


def cmd_find(graph, args):
    terms = [t.lower() for t in args.text]
    hits = []
    for node in graph.nodes.values():
        if args.type and node["type"] != args.type:
            continue
        blob = json.dumps(node, ensure_ascii=False).lower()
        if all(t in blob for t in terms):
            hits.append(node)
    hits.sort(key=lambda n: (n.get("date", n.get("created", "")), n["id"]), reverse=True)
    printer = Printer("add words or --type")
    for node in hits[: args.limit]:
        printer.line(summary(graph, node))
    printer.done(max(0, len(hits) - args.limit))
    if not hits:
        print("no match")
    return 0


def cmd_impact(graph, args):
    books = graph.of_type("book")
    if args.book:
        books = [graph.nodes[graph.resolve(args.book if args.book.startswith("BK-")
                                            else f"BK-{slugify(args.book)}")]]
    rows = []
    for book in books:
        per_project = {}
        for section in graph.into(book["id"], "of"):
            for record in graph.into(section, "on"):
                node = graph.nodes[record]
                stats = per_project.setdefault(node.get("project", "?"),
                                               {"sections": set(), "understood": 0,
                                                "other": 0, "citations": 0})
                stats["sections"].add(section)
                # A citation's status is its outcome; reads and explain-backs are
                # the evidence behind it, so they don't count twice.
                if node["type"] != "citation":
                    continue
                stats["citations"] += 1
                if node.get("status") == "understood":
                    stats["understood"] += 1
                else:
                    stats["other"] += 1
        uses = sum(s["citations"] for s in per_project.values())
        rows.append((uses, book, per_project))
    rows.sort(key=lambda row: (-row[0], row[1]["id"]))
    printer = Printer("pass a book")
    for uses, book, per_project in rows[: args.limit]:
        printer.line(f"{summary(graph, book)} · {uses} citations")
        for project, stats in sorted(per_project.items()):
            printer.line(f"  {project}: {stats['citations']} citations · "
                         f"{len(stats['sections'])} sections · understood {stats['understood']}"
                         f" · not yet {stats['other']}")
        if args.book:
            concepts = {c for s in graph.into(book["id"], "of") for c in graph.out(s, "covers")}
            if concepts:
                printer.line(f"  concepts: {', '.join(sorted(concepts))}")
    printer.done(max(0, len(rows) - args.limit))
    if not rows:
        print("no books yet")
    return 0


def cmd_stats(graph, args):
    counts = {}
    for node in graph.nodes.values():
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    print(" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "empty graph")
    print(f"edges {len(graph.edges)}")
    return 0


# ---------------------------------------------------------------- render and export

def render_markdown(graph, kind):
    """Readable Markdown view of one part of the graph. Never written back."""
    lines = []
    if kind == "progress":
        lines.append("# Learning Progress (rendered)")
        for node in sorted(graph.of_type("concept"), key=lambda n: n["id"]):
            lines.append(f"\n## {node.get('name', node['id'])} · {node.get('status', '-')}")
            for note in node.get("notes", []):
                lines.append(f"- {note}")
            for pre in graph.out(node["id"], "prereq"):
                lines.append(f"- prereq: {pre}")
        pending = [d for d in graph.of_type("decision") if d.get("status") == "pending"]
        for node in pending:
            lines.append(f"\n## Pending decision · {node['id']} · {node.get('stage', '')}")
            lines.append(f"{node.get('title', '')}: {node.get('proposal', '')}")
    elif kind == "questions":
        lines.append("# Question Bank (rendered)")
        for node in sorted(graph.of_type("question"), key=lambda n: n.get("due", "")):
            topic = ",".join(graph.out(node["id"], "tests"))
            lines += [f"\n## {node['id']} · {topic}", f"Q: {node['q']}", f"A: {node['a']}",
                      f"Box: {node.get('box', 1)} · Due: {node.get('due', '')}"]
    elif kind == "qa":
        lines.append("# Q/A History (rendered)")
        for node in sorted(graph.of_type("qa"), key=lambda n: (n.get("date", ""), n["id"])):
            topic = ",".join(graph.out(node["id"], "about"))
            lines += [f"\n## {node.get('date', '')} · {topic} · {node.get('source')}",
                      f"Q: {node['q']}", f"A: {node['a']}",
                      f"Verdict: {node.get('verdict', 'n/a')}"
                      + (f" · Confidence: {node['confidence']}" if node.get("confidence") else "")]
    elif kind == "recap":
        lines.append("# Session Recap (rendered)")
        for node in sorted(graph.of_type("session"), key=lambda n: n.get("date", "")):
            lines.append(f"\n## {node.get('date', '')} · {node.get('goal', '')}")
            for field, label in (("finished", "Finished"), ("learned", "Learned"),
                                 ("decided", "Decided"), ("open", "Open"),
                                 ("checkpoints", "Check points")):
                if node.get(field):
                    lines.append(f"{label}:")
                    lines += [f"- {item}" for item in node[field]]
            lines.append(f"Start check: {node.get('start_check', '')}")
    elif kind == "guardrails":
        lines += ["# Guardrails (rendered)", "",
                  "| Mistake class | Evidence | Level | Enforced by | Proven |", "|---|---|---|---|---|"]
        for node in graph.of_type("guardrail"):
            evidence = ", ".join(node.get("evidence", []) + graph.out(node["id"], "evidence"))
            lines.append(f"| {node['mistake']} | {evidence} | {node.get('level', '')} | "
                         f"{node.get('enforced_by', '')} | {node.get('proven', 'no')}"
                         f"{' · retired ' + node['retired'] if node.get('retired') else ''} |")
    elif kind == "reflections":
        lines.append("# Reflections (rendered)")
        for node in sorted(graph.of_type("reflection"), key=lambda n: n.get("date", "")):
            lines += [f"\n## {node.get('date', '')}", f"Learner: {node['text']}",
                      f"Evidence check: {node.get('evidence_check', '')}"]
    elif kind == "feedback":
        lines.append("# WiseCode feedback (rendered)")
        for node in graph.of_type("feedback"):
            lines += [f"\n## {node.get('date', '')} · {node.get('guide', '')}",
                      f"What happened: {node['what']}", f"Rule: {node.get('rule', '')}",
                      f"Proposed edit: {node.get('proposed_edit', '')}",
                      f"Status: {node.get('status', 'proposed')}"]
    elif kind == "glossary":
        lines.append("# Glossary (rendered)")
        for node in sorted(graph.of_type("concept"), key=lambda n: n.get("name", "").lower()):
            if node.get("definition"):
                aliases = f" (also: {', '.join(node['aliases'])})" if node.get("aliases") else ""
                avoid = f" _Avoid_: {', '.join(node['avoid'])}" if node.get("avoid") else ""
                lines.append(f"- **{node.get('name')}**{aliases}: {node['definition']}{avoid}")
    elif kind == "records":
        lines.append("# Learning records (rendered)")
        for node in sorted(graph.of_type("record"), key=lambda n: n["id"]):
            lines += [f"\n## {node['id']} · {node['title']} · {node.get('status', 'active')}",
                      node["body"]]
            for field in ("evidence", "implications"):
                if node.get(field):
                    lines.append(f"{field.title()}: {node[field]}")
    else:
        raise WiseError(f"unknown view {kind!r}")
    return "\n".join(lines) + "\n"


VIEWS = ("progress", "questions", "qa", "recap", "guardrails", "reflections",
         "feedback", "glossary", "records")


def cmd_render(graph, args):
    views = VIEWS if args.view == "all" else (args.view,)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for view in views:
            (out / f"{view}.md").write_text(render_markdown(graph, view), encoding="utf-8")
            print(out / f"{view}.md")
    else:
        for view in views:
            sys.stdout.write(render_markdown(graph, view))
    return 0


def cmd_export(graph, args):
    if args.format != "anki":
        raise WiseError("export formats: anki")
    deck = args.deck or graph.state.parent.name
    clean = lambda text: " ".join(str(text).replace("\t", " ").split())  # noqa: E731
    rows = ["#separator:Tab", "#html:false", "#notetype:Basic",
            f"#deck:wise-code::{deck}", "#tags column:3"]
    for node in sorted(graph.of_type("card"), key=lambda n: n["id"]):
        tags = ["wise-code", *node.get("tags", []), *graph.out(node["id"], "tests")]
        rows.append(f"{clean(node['front'])}\t{clean(node['back'])}\t"
                    f"{' '.join(dict.fromkeys(tags))}")
    target = Path(args.out) if args.out else graph.state / "cards.tsv"
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{target} · {len(rows) - 5} cards")
    return 0


# ---------------------------------------------------------------- check

# ---------------------------------------------------------------- learner quotes

# Text inside these tags in a user entry was injected, not typed by the learner.
INJECTED_RE = re.compile(
    r"<(system-reminder|command-message|command-name|local-command-stdout|"
    r"local-command-stderr|user-memory-input)>.*?</\1>", re.DOTALL)
QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " ", "…": "..."})


def fold(text):
    """Exact match up to case, whitespace, and curly quotes or dashes. No fuzz."""
    text = unicodedata.normalize("NFKC", str(text)).translate(QUOTE_FOLD)
    return " ".join(text.lower().split())


def encode_project_dir(path):
    """Claude Code's transcript folder names; two spellings are in use."""
    text = str(path)
    return [text.replace("/", "-").replace(".", "-"), re.sub(r"[^A-Za-z0-9]", "-", text)]


def transcript_dirs(graph, override):
    if override:
        folder = Path(override).expanduser().resolve()
        if not folder.is_dir():
            raise WiseError(f"--transcripts {override} is not a folder")
        return [folder]
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    root = graph.state.parent.resolve()
    seen, found = set(), []
    for name in encode_project_dir(root):
        folder = base / name
        if name not in seen and folder.is_dir():
            seen.add(name)
            found.append(folder)
    return found


def entry_text(entry):
    """The learner's typed words in one transcript line, or '' for anything else.

    Skips assistant turns, tool results, sub-agent threads (their prompts are
    written by Claude), meta lines, text the client sent but nobody typed, and
    compaction summaries (Claude's own
    paraphrase: exactly what this check must not trust).
    """
    if not isinstance(entry, dict) or entry.get("type") != "user":
        return ""
    if entry.get("isSidechain") or entry.get("isMeta") or entry.get("isCompactSummary") \
            or entry.get("textNotTyped") or entry.get("toolUseResult") is not None:
        return ""
    message = entry.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return ""
    content = message.get("content")
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return ""
    return INJECTED_RE.sub(" ", "\n".join(parts))


def learner_messages(folders):
    texts = []
    for folder in folders:
        for path in sorted(folder.glob("*.jsonl")):
            if path.is_symlink():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    text = entry_text(json.loads(line))
                except ValueError:
                    continue
                if text.strip():
                    texts.append(fold(text))
    return texts


def quote_pattern(part):
    """Match a folded quote as whole words: 'safe to use' must not match 'unsafe to use'.

    A boundary is required only at an edge that is a word character, so a quote
    that starts or ends with punctuation still matches where it was typed.
    """
    wanted = fold(part)
    head = r"(?<!\w)" if re.match(r"\w", wanted) else ""
    tail = r"(?!\w)" if re.search(r"\w$", wanted) else ""
    return re.compile(head + re.escape(wanted) + tail)


def said_status(spans, messages):
    if not spans:
        return "missing"
    for part in spans:
        pattern = quote_pattern(part)
        if not any(pattern.search(message) for message in messages):
            return "missing"
    return "ok"


def cmd_check_said(graph, args):
    folders = transcript_dirs(graph, args.transcripts)
    targets = []
    for node in graph.nodes.values():
        field = "text" if node["type"] == "reflection" else "said"
        if node["type"] not in ("qa", "decision", "reflection") or not node.get(field):
            continue
        if args.id and node["id"] not in {graph.resolve(i) for i in args.id}:
            continue
        if said_check_of(node) == "ok" and not (args.all or args.id):
            continue
        spans = [node["text"]] if field == "text" else said_parts(node["said"])
        targets.append((node, spans))
    if not targets:
        print("nothing to check")
        return 0
    messages = learner_messages(folders) if folders else []
    counts = {}
    printer = Printer("pass --id")
    for node, spans in targets:
        status = said_status(spans, messages) if messages else "unverified"
        digest = quote_hash(quote_of(node))
        if node.get("said_check") != status or node.get("said_hash") != digest:
            node["said_check"] = status
            node["said_hash"] = digest
            graph.touch(node)
        counts[status] = counts.get(status, 0) + 1
        if status == "missing":
            printer.line(f"missing: {summary(graph, node)}")
            printer.line(f"  not in the learner's messages: «{short(' … '.join(spans), 200)}»")
    graph.save()
    printer.done(0)
    if not messages:
        where = ", ".join(str(f) for f in folders) or "no transcript folder for this project"
        print(f"no learner messages found ({where}); marked unverified. "
              "Pass --transcripts <folder> if the session ran from a subfolder.")
    print(" · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


def unranged_text_sections(nodes):
    """{book id: [section ids]} for Markdown or text books with sections that have
    no line range: indexed before ranges existed, so quotes can't be located."""
    text_books = {node["slug"]: node["id"] for node in nodes
                  if node["type"] == "book"
                  and not str(node.get("file", "")).lower().endswith(".pdf")}
    found = {}
    for node in nodes:
        if node["type"] == "section" and node.get("book") in text_books \
                and not node.get("lines"):
            found.setdefault(text_books[node["book"]], []).append(node["id"])
    return found


def cmd_check(graph, args):
    problems, warnings = [], []
    for node_id, versions in sorted(graph.conflicts.items()):
        problems.append(f"{node_id}: {len(versions)} conflicting versions; "
                        f"wise.py resolve {node_id}")
    for node in graph.nodes.values():
        problems += validate_node(node)
    for a, r, b in graph.edges:
        if a not in graph.nodes or b not in graph.nodes:
            problems.append(f"dangling edge {a} -{r}-> {b}")
            continue
        allowed_from, allowed_to = RELS.get(r, ((), ()))
        if graph.nodes[a]["type"] not in allowed_from or graph.nodes[b]["type"] not in allowed_to:
            problems.append(f"edge {a} -{r}-> {b} has wrong types")
    repo = graph.state.parent
    for node in graph.nodes.values():
        for ref in node.get("code", []):
            path = ref.split(":", 1)[0]
            if path and not (repo / path).exists():
                warnings.append(f"{node['id']}: code file gone: {path}")
        if node["type"] in TIER2 and node.get("path"):
            if not (repo / node["path"]).exists():
                warnings.append(f"{node['id']}: file gone: {node['path']}")
    if args.shelf:
        shelf_state = Path(args.shelf).resolve() / ".wise-code"
        # Same graph: reuse it; a second lock in this process would wait forever.
        same = shelf_state.resolve() == graph.state.resolve()
        shelf = graph if same else Graph(shelf_state)
        try:
            for node in graph.of_type("concept"):
                for ref in node.get("shelf", []):
                    if ref not in shelf.nodes:
                        warnings.append(f"{node['id']}: shelf id not found: {ref}")
        finally:
            if not same:
                shelf.close()
    for book, sections in sorted(unranged_text_sections(list(graph.nodes.values())).items()):
        warnings.append(f"{book}: Markdown or text book indexed without line ranges "
                        f"({', '.join(sorted(sections))}); rebuild its L1")
    seen = {}
    for node in graph.of_type("concept"):
        for name in [node["id"], *node.get("aliases", [])]:
            key = slugify(name)
            if key in seen and seen[key] != node["id"]:
                warnings.append(f"{node['id']} and {seen[key]} share the name {name!r}; merge them")
            seen[key] = node["id"]
    for line in problems:
        print(f"error: {line}")
    for line in warnings:
        print(f"warning: {line}")
    if not problems and not warnings:
        print(f"ok · {len(graph.nodes)} nodes · {len(graph.edges)} edges")
    return 1 if problems else 0


# ---------------------------------------------------------------- import: lesson results

def parse_lesson_result(data):
    """Validate a lesson results payload; return (result_id, date, lesson, answers).

    Raises WiseError naming the first bad field, before anything is recorded.
    Each returned answer is {q, answer, correct, expected} with str texts and a
    bool `correct`: truthiness would turn the string "false" into a right answer.
    """
    if not isinstance(data, dict):
        raise WiseError("not a JSON object")
    result_id = data.get("result_id")
    if not isinstance(result_id, str) or not result_id.strip():
        raise WiseError("result_id must be a non-empty string")
    answers = data.get("answers")
    if not isinstance(answers, list):
        raise WiseError("answers must be a list")
    lesson = data.get("lesson", "")
    if not isinstance(lesson, str):
        raise WiseError("lesson must be a string")
    date = coerce("qa", "date", data.get("date") or iso(today()))
    parsed = []
    for number, answer in enumerate(answers, 1):
        if not isinstance(answer, dict):
            raise WiseError(f"answer {number} must be an object")
        if not isinstance(answer.get("correct"), bool):
            raise WiseError(f"answer {number}: correct must be true or false; "
                            f"got {answer.get('correct')!r}")
        texts = {}
        for key in ("q", "answer", "expected"):
            value = answer.get(key, "")
            if not isinstance(value, str):
                raise WiseError(f"answer {number}: {key} must be a string; got {value!r}")
            texts[key] = value.strip()
        parsed.append(dict(texts, correct=answer["correct"]))
    return result_id, date, lesson, parsed


def import_lesson_file(graph, path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        result_id, date, lesson, answers = parse_lesson_result(data)
    except (ValueError, UnicodeError) as error:
        raise WiseError(f"{path}: not valid JSON ({error})") from None
    except WiseError as error:
        raise WiseError(f"{path}: {error}") from None
    if any(n.get("result") == result_id for n in graph.of_type("qa")):
        print(f"skip {Path(path).name}: result {result_id} already imported")
        return 0
    lesson_node = next((n["id"] for n in graph.of_type("lesson")
                        if lesson and (lesson in n.get("path", "") or lesson == n["id"])), None)
    concepts = graph.out(lesson_node, "covers") if lesson_node else []
    created = 0
    for answer in answers:
        correct = answer["correct"]
        qa = {"id": new_id("QA", graph.nodes), "type": "qa", "date": date,
              "created": iso(today()), "source": "lesson",
              "q": answer["q"] or "(lesson question)",
              "a": answer["answer"] or "(no answer)",
              "verdict": "correct" if correct else "wrong", "result": result_id,
              "at": stamp_now()}
        graph.nodes[qa["id"]] = qa
        for concept in concepts:
            graph.edges.add((qa["id"], "about", concept))
        if not correct:
            question = {"id": new_id("QB", graph.nodes), "type": "question",
                        "created": iso(today()), "q": qa["q"],
                        "a": answer["expected"] or "(see the lesson)",
                        "source": f"lesson {lesson}".strip(), "box": 1,
                        "due": iso(today() + dt.timedelta(days=1))}
            graph.nodes[question["id"]] = question
            graph.edges.add((question["id"], "from", qa["id"]))
            for concept in concepts:
                graph.edges.add((question["id"], "tests", concept))
        created += 1
    graph.dirty = True
    wrong = sum(1 for a in answers if not a["correct"])
    print(f"imported {Path(path).name}: {created} answers · {wrong} wrong → question bank")
    return created


def cmd_import_lesson(graph, args):
    paths = [Path(p) for p in args.paths]
    inbox = graph.state / "inbox"
    if args.inbox and inbox.is_dir():
        paths += sorted(p for p in inbox.glob("*.json") if p.is_file() and not p.is_symlink())
    if not paths:
        print("nothing to import")
        return 0
    for path in paths:
        import_lesson_file(graph, path)
        graph.save()
        if path.parent == inbox:
            done = inbox / "done"
            done.mkdir(exist_ok=True)
            shutil.move(str(path), str(done / path.name))
    return 0


# ---------------------------------------------------------------- import: legacy Markdown

def blocks(text, header=r"^## "):
    """Split Markdown into (heading, body lines) blocks at level-2 headings."""
    result, current = [], None
    for line in text.splitlines():
        if re.match(header, line):
            current = [line[3:].strip(), []]
            result.append(current)
        elif current is not None:
            current[1].append(line)
    return result


def field_lines(lines):
    """Read `Key: value` lines; continuation lines join the previous key."""
    fields, key = {}, None
    for line in lines:
        match = re.match(r"^([A-Za-z][A-Za-z -]*):\s*(.*)$", line)
        if match and not line.startswith("- "):
            key = match.group(1).strip().lower()
            fields[key] = match.group(2).strip()
        elif key and line.strip():
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def bullet_sections(lines):
    """Read `Label:` followed by `- item` bullets (session recap format)."""
    sections, key = {}, None
    for line in lines:
        label = re.match(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$", line)
        if label and not line.startswith("-"):
            key = label.group(1).strip().lower()
            sections[key] = [label.group(2).strip()] if label.group(2).strip() else []
        elif key and line.strip().startswith("- "):
            sections[key].append(line.strip()[2:].strip())
    return sections


class Importer:
    def __init__(self, graph, dry_run):
        self.graph = graph
        self.dry_run = dry_run
        self.moved = []
        self.report = []

    def concept(self, name):
        name = name.strip() or "general"
        found = self.graph.resolve(slugify(name), required=False) or \
            similar_concept(self.graph, slugify(name), [name])
        if found:
            return found
        slug = slugify(name)
        self.graph.nodes[slug] = {"id": slug, "type": "concept", "name": name,
                                  "created": iso(today())}
        return slug

    def add(self, kind, fields, links=()):
        node = {"id": new_id(TYPES[kind]["prefix"], self.graph.nodes), "type": kind,
                "created": iso(today())}
        for key, value in fields.items():
            if value in (None, "", []):
                continue
            try:
                node[key] = coerce(kind, key, value)
            except WiseError as error:
                self.report.append(f"{kind}: dropped {key}: {error}")
        problems = validate_node(node)
        if problems:
            self.report.append("skipped: " + "; ".join(problems))
            return None
        self.graph.nodes[node["id"]] = node
        for rel, target in links:
            self.graph.edges.add((node["id"], rel, target))
        return node["id"]

    def done(self, path):
        self.moved.append(path)

    # -- formats

    def qa_history(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            parts = [p.strip() for p in heading.split("·")]
            date, topic = parts[0], parts[1] if len(parts) > 1 else "general"
            source = parts[2] if len(parts) > 2 else "asked"
            fields = field_lines(body)
            verdict = fields.get("verdict", "n/a")
            hints = re.search(r"after (\d+) hint", verdict)
            verdict = verdict.split()[0] if verdict else "n/a"
            self.add("qa", {"date": date, "source": source if source in QA_SOURCES else "asked",
                            "q": fields.get("q"), "a": fields.get("a"),
                            "verdict": verdict if verdict in VERDICTS else "n/a",
                            "hints": hints.group(1) if hints else None,
                            "followup": fields.get("follow-up")},
                     [("about", self.concept(topic))])
        self.done(path)

    def questions(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            parts = [p.strip() for p in heading.split("·")]
            fields = field_lines(body)
            self.add("question", {"legacy": parts[0], "q": fields.get("q"), "a": fields.get("a"),
                                  "source": fields.get("source"), "box": fields.get("box"),
                                  "due": fields.get("due")},
                     [("tests", self.concept(parts[1] if len(parts) > 1 else "general"))])
        self.done(path)

    def cards(self, path):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) < 2:
                self.report.append(f"cards.tsv: skipped {short(line, 40)!r}")
                continue
            tags = [t for t in (columns[2].split() if len(columns) > 2 else [])
                    if t != "wise-code"]
            # A tag that names a known concept becomes an edge; others stay tags.
            known = [(t, self.graph.resolve(t, required=False)) for t in tags]
            links = [("tests", c) for _, c in known if c]
            self.add("card", {"front": columns[0], "back": columns[1],
                              "tags": [t for t, c in known if not c]}, links)
        self.done(path)

    def recap(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            date, _, goal = heading.partition("·")
            sections = bullet_sections(body)
            check = (sections.get("start check") or ["pending"])[0]
            self.add("session", {"date": date.strip(), "goal": goal.strip() or "session",
                                 "finished": sections.get("finished"),
                                 "learned": sections.get("learned"),
                                 "decided": sections.get("decided"),
                                 "open": sections.get("open"),
                                 "checkpoints": sections.get("check points"),
                                 "start_check": check})
        self.done(path)

    def progress(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            text = [line.strip() for line in body if line.strip()]
            if heading.lower().startswith("pending decision"):
                joined = " ".join(text)
                stage = next((s for s in TYPES["decision"]["fields"]["stage"]
                              if s.replace("-", " ") in joined.lower()), None)
                self.add("decision", {"title": short(joined, 80) or "pending decision",
                                      "proposal": joined, "status": "pending", "stage": stage})
                continue
            concept = self.concept(heading)
            node = self.graph.nodes[concept]
            lowered = " ".join(text).lower()
            if "needs reinforcement" in lowered:
                status = "reinforce"
            elif "demonstrated" in lowered:
                status = "demonstrated"
            else:
                status = "introduced"
            node["status"] = status
            node.setdefault("notes", []).extend(t.lstrip("- ").strip() for t in text)
        self.done(path)

    def guardrails(self, path):
        for line in path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5 or cells[0] in ("Mistake class", "") or set(cells[0]) <= set("-"):
                continue
            proven, _, retired = cells[4].partition("retired")
            self.add("guardrail", {"mistake": cells[0], "evidence": [cells[1]],
                                   "level": cells[2] if cells[2] in TYPES["guardrail"]["fields"]["level"] else None,
                                   "enforced_by": cells[3], "proven": proven.strip(" ·") or "no",
                                   "retired": retired.strip(" ·")})
        self.done(path)

    def reflections(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            fields = field_lines(body)
            self.add("reflection", {"date": heading.split("·")[0].strip(),
                                    "text": fields.get("learner"),
                                    "evidence_check": fields.get("evidence check")})
        self.done(path)

    def feedback(self, path):
        for heading, body in blocks(path.read_text(encoding="utf-8")):
            parts = [p.strip() for p in heading.split("·")]
            fields = field_lines(body)
            status = fields.get("status", "proposed")
            self.add("feedback", {"date": parts[0], "guide": " · ".join(parts[1:]),
                                  "what": fields.get("what happened"), "rule": fields.get("rule"),
                                  "proposed_edit": fields.get("proposed edit"),
                                  "status": status if status in TYPES["feedback"]["fields"]["status"] else "proposed"})
        self.done(path)

    def learning_records(self, folder):
        legacy = {}
        for path in sorted(folder.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            status = "superseded" if re.search(r"(?im)^status:\s*superseded", text) else "active"
            body = re.sub(r"(?s)^---.*?---\s*", "", text)
            title_match = re.search(r"(?m)^# (.+)$", body)
            title = title_match.group(1).strip() if title_match else path.stem
            body = body.replace(title_match.group(0), "", 1).strip() if title_match else body.strip()
            evidence = re.search(r"(?ims)^\*{0,2}evidence\*{0,2}:?\s*(.+?)(?:\n\n|\Z)", body)
            number = path.stem.split("-")[0]
            node = self.add("record", {"title": title, "body": body or title, "status": status,
                                       "evidence": evidence.group(1).strip() if evidence else None,
                                       "legacy": f"LR-{number}"})
            if node:
                legacy[number] = node
            self.done(path)
        for path in sorted(folder.glob("*.md")):
            match = re.search(r"superseded by LR-(\d+)", path.read_text(encoding="utf-8"))
            number = path.stem.split("-")[0]
            if match and number in legacy and match.group(1) in legacy:
                self.graph.edges.add((legacy[match.group(1)], "supersedes", legacy[number]))

    def glossary(self, path):
        lines = path.read_text(encoding="utf-8").splitlines()
        # Teach format: **Term**: on its own line, definition below, then _Avoid_: a, b.
        index = 0
        while index < len(lines):
            term = re.match(r"^\*\*(.+?)\*\*:?\s*$", lines[index].strip())
            if not term:
                index += 1
                continue
            body, index = [], index + 1
            while index < len(lines) and lines[index].strip() and \
                    not re.match(r"^\*\*.+\*\*:?\s*$", lines[index].strip()):
                body.append(lines[index].strip())
                index += 1
            avoid = [b for b in body if b.lower().startswith("_avoid_")]
            definition = " ".join(b for b in body if b not in avoid).strip()
            concept = self.concept(term.group(1).strip())
            node = self.graph.nodes[concept]
            if definition:
                node.setdefault("definition", definition)
            for line in avoid:
                words = [w.strip(" .") for w in line.split(":", 1)[-1].split(",") if w.strip(" .")]
                node.setdefault("avoid", []).extend(w for w in words if w not in node["avoid"])
        for line in lines:
            match = (re.match(r"^\s*[-*]\s*\*\*(.+?)\*\*\s*[:—–-]\s*(.+)$", line)
                     or re.match(r"^\s*[-*]\s*([^:]{1,60}):\s*(.+)$", line)
                     or re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line))
            if not match or set(match.group(1)) <= set("-: ") or match.group(1).lower() == "term":
                continue
            concept = self.concept(match.group(1).strip("* "))
            self.graph.nodes[concept].setdefault("definition", match.group(2).strip())
        self.done(path)

    def resources(self, path, rel):
        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", path.read_text(encoding="utf-8")):
            if not any(n.get("url") == match.group(2) for n in self.graph.of_type("resource")):
                self.add("resource", {"title": match.group(1), "url": match.group(2), "path": rel})

    def index_file(self, kind, path, rel):
        if any(n.get("path") == rel for n in self.graph.of_type(kind)):
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"(?is)<title>(.*?)</title>", text) or re.search(r"(?m)^# (.+)$", text)
        title = html.unescape(title.group(1).strip()) if title else path.stem
        self.add(kind, {"path": rel, "title": title})


def index_files(importer, repo, state):
    """Register tier-2 files (they stay files) as nodes. Idempotent by path."""
    teach = state / "teach"
    found = [("lesson", p) for p in sorted((teach / "lessons").glob("*.html"))]
    found += [("reference", p) for p in sorted((teach / "reference").glob("*.html"))]
    found += [("mission", p) for p in [teach / "MISSION.md"] if p.is_file()]
    for folder in ("research", "notes/research", "docs/research"):
        found += [("research", p) for p in sorted((repo / folder).glob("*.md"))]
    found += [("adr", p) for p in sorted((repo / "docs" / "adr").glob("*.md"))
              if not p.name.startswith("0000-template")]
    for kind, path in found:
        if path.is_symlink():
            continue
        importer.index_file(kind, path, str(path.relative_to(repo)))
    resources = teach / "RESOURCES.md"
    if resources.is_file():
        importer.resources(resources, str(resources.relative_to(repo)))


def cmd_import_md(graph, args):
    state = graph.state
    importer = Importer(graph, args.dry_run)
    teach = state / "teach"
    # Progress first: its topics are the canonical concept names others link to.
    plan = [
        (state / "progress.md", importer.progress),
        (teach / "GLOSSARY.md", importer.glossary),
        (state / "qa-history-archive.md", importer.qa_history),
        (state / "qa-history.md", importer.qa_history),
        (state / "questions.md", importer.questions),
        (state / "cards.tsv", importer.cards),
        (state / "session-recap.md", importer.recap),
        (state / "guardrails.md", importer.guardrails),
        (state / "reflections.md", importer.reflections),
        (state / "plugin-feedback.md", importer.feedback),
    ]
    for path, reader in plan:
        if path.is_file() and not path.is_symlink():
            reader(path)
    if (teach / "learning-records").is_dir():
        importer.learning_records(teach / "learning-records")
    index_files(importer, state.parent, state)
    for line in importer.report:
        print(f"note: {line}")
    counts = {}
    for node in graph.nodes.values():
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    print("graph: " + (" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "empty"))
    if args.dry_run:
        print("dry run: nothing written, nothing moved")
        return 0
    graph.dirty = True
    graph.save()
    # Imported Markdown moves to a backup so it can't drift from the graph.
    if importer.moved:
        backup = state / "backups" / f"import-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        for path in importer.moved:
            target = backup / path.relative_to(state)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
        print(f"moved {len(importer.moved)} files to {backup}")
    return 0


def cmd_index(graph, args):
    importer = Importer(graph, False)
    index_files(importer, graph.state.parent, graph.state)
    graph.dirty = True
    graph.save()
    for line in importer.report:
        print(f"note: {line}")
    print(f"indexed · {sum(1 for n in graph.nodes.values() if n['type'] in TIER2)} files")
    return 0


def reset_progress(graph):
    """Reset's meaning on the graph: clear concept status and pending decisions.

    Everything else (Q/A, questions, cards, sessions, settled decisions,
    guardrails, reflections, feedback, records, indexed files) stays.
    """
    cleared = 0
    for node in graph.of_type("concept"):
        if node.pop("status", None):
            cleared += 1
            graph.touch(node)
    for node in [d for d in graph.of_type("decision") if d.get("status") == "pending"]:
        graph.remove(node["id"])
        cleared += 1
    graph.save()
    return cleared


def cmd_reset_progress(graph, args):
    backup = graph.state / "backups" / f"reset-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}" / "graph"
    if graph.dir.is_dir():
        shutil.copytree(graph.dir, backup)
    print(f"backup {backup} · cleared {reset_progress(graph)}")
    return 0


# ---------------------------------------------------------------- main

def build_parser():
    parser = argparse.ArgumentParser(
        prog="wise.py", description="WiseCode learning graph. Spec: docs/graph.md")
    parser.add_argument("--root", help="project or shelf folder (default: nearest .wise-code)")
    sub = parser.add_subparsers(dest="command", required=True)

    def limited(p, default=DEFAULT_LIMIT):
        p.add_argument("--limit", type=int, default=default)
        return p

    p = sub.add_parser("add", help="add a node: add TYPE key=value ... --rel ID")
    p.add_argument("type")
    p.add_argument("fields", nargs=argparse.REMAINDER)
    p.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_add, write=True)

    p = sub.add_parser("set", help="change fields: set ID key=value key+=item --rel ID")
    p.add_argument("id")
    p.add_argument("fields", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_set, write=True)

    for name, func in (("link", cmd_link), ("unlink", cmd_unlink)):
        p = sub.add_parser(name, help=f"{name} SOURCE REL TARGET")
        p.add_argument("source")
        p.add_argument("rel")
        p.add_argument("target")
        p.set_defaults(func=func, write=True)

    p = sub.add_parser("delete", help="delete a node and its edges")
    p.add_argument("id")
    p.set_defaults(func=cmd_delete, write=True)

    p = sub.add_parser("merge", help="merge DROP into KEEP")
    p.add_argument("keep")
    p.add_argument("drop")
    p.set_defaults(func=cmd_merge, write=True)

    p = sub.add_parser("resolve", help="show or pick between a node's conflicting versions")
    p.add_argument("id")
    p.add_argument("--keep", type=int, help="the version number to keep")
    p.set_defaults(func=cmd_resolve, write=True)

    p = sub.add_parser("answer", help="record an answer to a question and reschedule it")
    p.add_argument("id")
    p.add_argument("verdict")
    p.add_argument("--answer", help="gist of the learner's answer")
    p.add_argument("--said", help="verbatim span of the learner's answer")
    p.add_argument("--confidence", choices=CONFIDENCE, help="what the learner prefixed")
    p.add_argument("--source", default="quiz", choices=QA_SOURCES)
    p.add_argument("--hints", type=int, default=0)
    p.add_argument("--schedule", action="store_true", help="reschedule for any source")
    p.set_defaults(func=cmd_answer, write=True)

    p = sub.add_parser("edit", help="edit one node in $EDITOR")
    p.add_argument("id")
    p.set_defaults(func=cmd_edit, write=True)

    p = limited(sub.add_parser("due", help="questions due today or earlier"))
    p.add_argument("--topic")
    p.add_argument("--early", action="store_true", help="include questions not yet due")
    p.set_defaults(func=cmd_due, write=False)

    p = limited(sub.add_parser("session", help="sessions and start checks"), 3)
    p.add_argument("--pending", action="store_true")
    p.add_argument("--last", action="store_true")
    p.add_argument("--quiet", action="store_true", help="exit 0 if a check is pending, else 1")
    p.set_defaults(func=cmd_session, write=False)

    p = limited(sub.add_parser("weak", help="concepts needing reinforcement"))
    p.add_argument("--with-prereqs", action="store_true")
    p.add_argument("--days", type=int, default=None)
    p.set_defaults(func=cmd_weak, write=False)

    for name in ("show", "concept"):
        p = limited(sub.add_parser(name, help="one node and its links"), 15)
        p.add_argument("id")
        p.add_argument("--rel")
        p.set_defaults(func=cmd_show, write=False)

    p = limited(sub.add_parser("mistakes", help="concepts missed repeatedly"))
    p.add_argument("--repeated", action="store_true", help="(default) at least --min misses")
    p.add_argument("--min", type=int, default=2)
    p.add_argument("--days", type=int, default=None)
    p.set_defaults(func=cmd_mistakes, write=False)

    p = limited(sub.add_parser("confusions", help="unrepaired confusions and the repair gate"))
    p.add_argument("--concept", action="append", help="repeatable; default: all concepts")
    p.add_argument("--with-prereqs", action="store_true")
    p.set_defaults(func=cmd_confusions, write=False)

    p = sub.add_parser("skip-repair", help="skip repairing one confusion (capped)")
    p.add_argument("id")
    p.set_defaults(func=cmd_skip_repair, write=True)

    p = limited(sub.add_parser("calibration", help="confidence vs correctness"))
    p.add_argument("--since")
    p.set_defaults(func=cmd_calibration, write=False)

    p = limited(sub.add_parser("history", help="Q/A history, newest first"))
    p.add_argument("--concept")
    p.add_argument("--since")
    p.add_argument("--source", choices=QA_SOURCES)
    p.add_argument("--full", action="store_true", help="include answer gists")
    p.set_defaults(func=cmd_history, write=False)

    p = limited(sub.add_parser("decisions", help="decisions, newest first"))
    p.add_argument("--pending", action="store_true")
    p.set_defaults(func=cmd_decisions, write=False)

    p = limited(sub.add_parser("list", help="nodes of one type"))
    p.add_argument("type")
    p.add_argument("--where", help="field=value")
    p.add_argument("--concept")
    p.set_defaults(func=cmd_list, write=False)

    p = limited(sub.add_parser("find", help="full-text search over all nodes"))
    p.add_argument("text", nargs="+")
    p.add_argument("--type")
    p.set_defaults(func=cmd_find, write=False)

    p = limited(sub.add_parser("impact", help="shelf: book use across projects"))
    p.add_argument("book", nargs="?")
    p.set_defaults(func=cmd_impact, write=False)

    p = sub.add_parser("stats", help="node counts")
    p.set_defaults(func=cmd_stats, write=False)

    p = sub.add_parser("render", help="readable Markdown view")
    p.add_argument("view", choices=VIEWS + ("all",))
    p.add_argument("--out", help="write files into this folder instead of stdout")
    p.set_defaults(func=cmd_render, write=False)

    p = sub.add_parser("export", help="export cards for Anki")
    p.add_argument("format", choices=("anki",))
    p.add_argument("--out")
    p.add_argument("--deck")
    p.set_defaults(func=cmd_export, write=False)

    p = sub.add_parser("check", help="validate the graph")
    p.add_argument("--shelf", help="shelf repo folder, to check shelf ids")
    p.set_defaults(func=cmd_check, write=False)

    p = sub.add_parser("check-said", help="match learner quotes against this project's transcripts")
    p.add_argument("--id", action="append", help="check one record (repeatable)")
    p.add_argument("--all", action="store_true", help="recheck quotes already ok")
    p.add_argument("--transcripts", help="transcript folder, if not found automatically")
    p.set_defaults(func=cmd_check_said, write=False)  # never creates state

    p = sub.add_parser("import-md",help="convert legacy Markdown notes, then back them up")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_import_md, write=True)

    p = sub.add_parser("import-lesson", help="import lesson quiz results (.json)")
    p.add_argument("paths", nargs="*")
    p.add_argument("--inbox", action="store_true", help="also import .wise-code/inbox/*.json")
    p.set_defaults(func=cmd_import_lesson, write=True)

    p = sub.add_parser("index", help="register lessons, references, research, ADRs, mission, resources")
    p.set_defaults(func=cmd_index, write=True)

    p = sub.add_parser("reset-progress", help="used by /wise-code:reset")
    p.set_defaults(func=cmd_reset_progress, write=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        start = Path(args.root).resolve() if args.root else Path.cwd()
        if args.root and not start.is_dir():
            raise WiseError(f"--root {args.root} is not a folder")
        state = find_state(start, create=args.write)
        if state is None:
            print("no .wise-code here; nothing recorded yet")
            return 0
        with Graph(state, write=args.write) as graph:
            if graph.conflicts and args.func not in (cmd_resolve, cmd_check):
                ids = ", ".join(sorted(graph.conflicts))
                print(f"wise.py: conflicting versions from a merge: {ids}; "
                      "wise.py resolve <id>", file=sys.stderr)
            return args.func(graph, args) or 0
    except WiseError as error:
        print(f"wise.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
