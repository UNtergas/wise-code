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
              "reflect", "asked", "start-check", "shelf")
READ_VERDICTS = ("understood", "partial", "misread", "skipped-read")

# Field kinds: "str", "list", "int", "date", or a tuple of allowed values.
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
        "result": "str", "project": "str"}},
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
        "proposal": "str", "outcome": "str", "by": ("learner", "ai", "both")}},
    "guardrail": {"prefix": "G", "required": ["mistake"], "fields": {
        "mistake": "str", "evidence": "list",
        "level": ("design", "types", "lint", "test", "note"),
        "enforced_by": "str", "proven": "str", "retired": "str"}},
    "reflection": {"prefix": "R", "required": ["text"], "fields": {
        "date": "date", "text": "str", "evidence_check": "str"}},
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
                           "pages": "str", "printed": "str", "concepts": "list",
                           "l2": "date"}},
    "citation": {"prefix": "CIT", "required": ["project", "question"], "fields": {
        "date": "date", "project": "str", "question": "str", "quote": "str",
        "page": "int", "status": ("sent",) + READ_VERDICTS, "updated": "date"}},
    "read": {"prefix": "RD", "required": ["project"], "fields": {
        "date": "date", "project": "str", "verdict": READ_VERDICTS,
        "evidence": "str"}},
    "explainback": {"prefix": "EB", "required": ["project", "text"], "fields": {
        "date": "date", "project": "str", "text": "str",
        "verdict": READ_VERDICTS}},
}

META = ("id", "type", "created", "updated", "rev")
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
    "from": (("question", "card"), ("qa", "record", "lesson", "citation",
                                    "section")),
}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# Leftover markers from a merge done without the union driver.
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)")
# Git keeps both sides' lines when two clones add records, instead of a conflict.
GITATTRIBUTES = "*.jsonl merge=union\n"


def stamp(node):
    return (node.get("updated") or node.get("created") or "", node.get("rev", 0))


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
    def __init__(self, state):
        self.state = state
        self.dir = state / "graph"
        self.nodes = {}
        self.edges = set()
        self.dirty = False
        for name in ("nodes.jsonl", "edges.jsonl"):
            path = self.dir / name
            if path.is_symlink():
                raise WiseError(f"{path} is a symlink; refusing")
        self._load()

    def _load(self):
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
                old = self.nodes.get(node["id"])
                if old is not None:
                    # A union merge kept both sides' version of one node: the
                    # newer change wins, and the next write drops the other line.
                    self.dirty = True
                    if stamp(old) > stamp(node):
                        continue
                self.nodes[node["id"]] = node
        if edges_path.is_file():
            for number, line in enumerate(edges_path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip() or CONFLICT_RE.match(line):
                    continue
                try:
                    edge = json.loads(line)
                    self.edges.add((edge["from"], edge["rel"], edge["to"]))
                except (ValueError, KeyError, TypeError) as error:
                    raise WiseError(f"edges.jsonl line {number}: {error}") from None

    def save(self):
        if not self.dirty:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        attributes = self.dir / ".gitattributes"
        if not attributes.exists():
            attributes.write_text(GITATTRIBUTES, encoding="utf-8")
        node_lines = [json.dumps(self.nodes[key], ensure_ascii=False, sort_keys=True)
                      for key in sorted(self.nodes)]
        edge_lines = [json.dumps({"from": a, "rel": r, "to": b}, ensure_ascii=False,
                                 sort_keys=True)
                      for a, r, b in sorted(self.edges)]
        for name, lines in (("nodes.jsonl", node_lines), ("edges.jsonl", edge_lines)):
            target = self.dir / name
            # Write beside the target and rename: a crash never leaves half a file.
            handle, temp = tempfile.mkstemp(dir=self.dir, prefix=f".{name}.")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write("\n".join(lines) + ("\n" if lines else ""))
            os.replace(temp, target)
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
        """Mark a changed node so a later union merge can tell which side is newer."""
        node["updated"] = iso(today())
        node["rev"] = int(node.get("rev", 0)) + 1
        self.dirty = True

    def remove(self, node_id):
        node_id = self.resolve(node_id)
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
            return int(value)
        except (TypeError, ValueError):
            raise WiseError(f"{kind}.{field} must be a number; got {value!r}") from None
    if spec == "date":
        try:
            return iso(dt.date.fromisoformat(str(value)))
        except ValueError:
            raise WiseError(f"{kind}.{field} must be YYYY-MM-DD; got {value!r}") from None
    if spec == "list":
        return value if isinstance(value, list) else [value]
    return str(value)


def validate_node(node):
    kind = node.get("type")
    if kind not in TYPES:
        return [f"{node.get('id')}: unknown type {kind!r}"]
    problems = []
    for field in TYPES[kind]["required"]:
        if node.get(field) in (None, "", []):
            problems.append(f"{node['id']}: missing {field}")
    for field, value in node.items():
        if field in META:
            continue
        try:
            coerce(kind, field, value)
        except WiseError as error:
            problems.append(f"{node['id']}: {error}")
    return problems


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
        return (f"{i} · {node.get('date', '')} · {node.get('source')} · "
                f"{node.get('verdict', '-')} · {concept_of(i, 'about') or '-'} · "
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


# ---------------------------------------------------------------- commands: writes

def cmd_add(graph, args):
    kind = args.type
    if kind not in TYPES:
        raise WiseError(f"unknown type {kind!r}; one of: {', '.join(TYPES)}")
    fields = [f for f in args.fields if f != "--force"]
    args.force = args.force or len(fields) != len(args.fields)
    sets, appends, removes, links = parse_assignments(fields)
    spec = TYPES[kind]
    node = {"type": kind}

    if kind == "concept":
        slug = sets.pop("id", None) or slugify(sets.get("name", ""))
        if not SLUG_RE.match(slug):
            raise WiseError(f"concept id must be a lowercase slug; got {slug!r}")
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
    apply_fields(node, sets, appends, removes)
    problems = validate_node(node)
    if problems:
        raise WiseError("; ".join(problems))
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
    apply_fields(node, sets, appends, removes)
    problems = validate_node(node)
    if problems:
        raise WiseError("; ".join(problems))
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


def cmd_answer(graph, args):
    """Record a quiz or start-check answer: QA entry plus Leitner rescheduling."""
    qid = graph.resolve(args.id)
    question = graph.nodes[qid]
    if question["type"] != "question":
        raise WiseError(f"{qid} is not a question")
    if args.verdict not in ("correct", "partial", "wrong"):
        raise WiseError("verdict: correct, partial or wrong")
    if args.source in ("quiz", "start-check") or args.schedule:
        box = int(question.get("box", 1))
        if args.verdict == "correct":
            box = min(box + 1, 5)
        elif args.verdict == "wrong":
            box = 1
        question["box"] = box
        question["due"] = iso(today() + dt.timedelta(days=BOXES[box]))
        graph.touch(question)
    qa = {"id": new_id("QA", graph.nodes), "type": "qa", "date": iso(today()),
          "created": iso(today()), "source": args.source, "q": question["q"],
          "a": args.answer or "(answered in chat)", "verdict": args.verdict}
    if args.hints:
        qa["hints"] = args.hints
    graph.nodes[qa["id"]] = qa
    graph.dirty = True
    graph.link(qa["id"], "answers", qid)
    for concept in graph.out(qid, "tests"):
        graph.link(qa["id"], "about", concept)
    graph.save()
    print(f"{qa['id']} · {qid} now box {question['box']} · due {question['due']}")
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
    problems = validate_node(node)
    if problems:
        raise WiseError("; ".join(problems))
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
    print(json.dumps(node, ensure_ascii=False, sort_keys=True))
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
            printer.line(f"  A: {short(node.get('a', ''), 200)}")
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
            printer.line(f"  proposal: {short(node['proposal'], 300)}")
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
                      f"Verdict: {node.get('verdict', 'n/a')}"]
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

def cmd_check(graph, args):
    problems, warnings = [], []
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
        shelf = Graph(Path(args.shelf).resolve() / ".wise-code")
        for node in graph.of_type("concept"):
            for ref in node.get("shelf", []):
                if ref not in shelf.nodes:
                    warnings.append(f"{node['id']}: shelf id not found: {ref}")
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

def import_lesson_file(graph, path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    result_id = data.get("result_id")
    answers = data.get("answers")
    if not result_id or not isinstance(answers, list):
        raise WiseError(f"{path}: needs result_id and answers")
    if any(n.get("result") == result_id for n in graph.of_type("qa")):
        print(f"skip {Path(path).name}: result {result_id} already imported")
        return 0
    date = data.get("date") or iso(today())
    lesson = data.get("lesson", "")
    lesson_node = next((n["id"] for n in graph.of_type("lesson")
                        if lesson and (lesson in n.get("path", "") or lesson == n["id"])), None)
    concepts = graph.out(lesson_node, "covers") if lesson_node else []
    created = 0
    for answer in answers:
        correct = bool(answer.get("correct"))
        qa = {"id": new_id("QA", graph.nodes), "type": "qa", "date": coerce("qa", "date", date),
              "created": iso(today()), "source": "lesson",
              "q": str(answer.get("q", "")).strip() or "(lesson question)",
              "a": str(answer.get("answer", "")).strip() or "(no answer)",
              "verdict": "correct" if correct else "wrong", "result": result_id}
        graph.nodes[qa["id"]] = qa
        for concept in concepts:
            graph.edges.add((qa["id"], "about", concept))
        if not correct:
            question = {"id": new_id("QB", graph.nodes), "type": "question",
                        "created": iso(today()), "q": qa["q"],
                        "a": str(answer.get("expected", "")).strip() or "(see the lesson)",
                        "source": f"lesson {lesson}".strip(), "box": 1,
                        "due": iso(today() + dt.timedelta(days=1))}
            graph.nodes[question["id"]] = question
            graph.edges.add((question["id"], "from", qa["id"]))
            for concept in concepts:
                graph.edges.add((question["id"], "tests", concept))
        created += 1
    graph.dirty = True
    wrong = sum(1 for a in answers if not a.get("correct"))
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

    p = sub.add_parser("answer", help="record an answer to a question and reschedule it")
    p.add_argument("id")
    p.add_argument("verdict")
    p.add_argument("--answer", help="gist of the learner's answer")
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

    p = sub.add_parser("import-md", help="convert legacy Markdown notes, then back them up")
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
        graph = Graph(state)
        return args.func(graph, args) or 0
    except WiseError as error:
        print(f"wise.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
