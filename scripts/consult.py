"""The senior consult journal: one Markdown file Codex appends to, Claude reads.

Codex, as the on-demand senior developer, records each consult here with
`consult.py add`. The journal sits in the project's `.wise-code/consult/`, beside
the learning graph but not in it: Codex is its only writer, so it needs no lock,
and nothing here touches `graph/`. The session hook counts entries with
`entries()`; Claude reads the file itself.

Each entry has a stable id, a hash of its own text and of how many identical
entries come before it (Codex only appends, so earlier entries never change). Claude, the teacher, records that it went
through an entry with `consult.py ack <id>`, in `.wise-code/consult-acks.txt`:
outside `consult/`, so the senior's sandbox can't acknowledge for it, and the
journal stays Codex's alone. An entry is pending until acknowledged, however
many sessions pass; `consult.py pending` lists them.

An entry is a `doubt` (the learner doubts something the teacher said; it
carries a verdict) or a `question` (an independent question; no verdict).
Format, one entry per consult, one field per line:

    ## 2026-11-03 14:10 — <topic>
    Kind: doubt
    Level: Hint
    Asked: ...
    Tried / knew: ...
    Senior view: ...
    Disagrees with teacher: yes — <what> | no      (doubt only)
    Refs: src/foo.ts, D-12
"""

import argparse
import collections
import datetime as dt
import hashlib
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wise  # noqa: E402 - shares state lookup, errors and the pinned test date


LEVELS = ("Hint", "Pseudo", "Full code")
KINDS = ("doubt", "question")
HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) \d\d:\d\d — ")
DISAGREES = re.compile(r"^Disagrees with teacher: (yes|no)\b")

Entry = collections.namedtuple("Entry", "id date disagrees topic")
ACK_ID = re.compile(r"^c-[0-9a-f]{12}$")


def journal_path(state):
    return state / "consult" / "journal.md"


def acks_path(state):
    return state / "consult-acks.txt"


def one_line(text):
    """Collapse a value to one line, so it can't forge a heading or a field."""
    return " ".join(str(text).split())


def entry_text(block):
    return "\n".join(line.rstrip() for line in block).strip()


def entry_id(text, occurrence):
    """The id of one entry: a hash of its text and how many identical entries
    precede it. Two consults can match line for line (headings carry minutes
    only); appending never changes an earlier entry's occurrence, so ids stay
    stable."""
    key = text if occurrence == 0 else f"{text}\n#{occurrence}"
    return "c-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def parse(text):
    """Each entry in a journal's text, in order."""
    blocks = []
    for line in text.splitlines():
        if HEADING.match(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    found, seen = [], collections.Counter()
    for block in blocks:
        text = entry_text(block)
        occurrence, seen[text] = seen[text], seen[text] + 1
        heading = HEADING.match(block[0])
        verdicts = [DISAGREES.match(line) for line in block[1:]]
        verdict = next((v for v in verdicts if v), None)
        found.append(Entry(entry_id(text, occurrence), heading.group(1),
                           bool(verdict) and verdict.group(1) == "yes",
                           block[0][heading.end():].strip()))
    return found


def entries(path):
    """The journal's entries; [] if absent, linked or unreadable."""
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        return []
    try:
        return parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return []


def acknowledged(state):
    """Ids the teacher acknowledged; empty if absent or linked."""
    path = acks_path(state)
    if path.is_symlink() or not path.is_file():
        return set()
    try:
        return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if ACK_ID.match(line.strip())}
    except (OSError, UnicodeError):
        return set()


def pending(state):
    """Entries not yet acknowledged, oldest first."""
    done = acknowledged(state)
    return [e for e in entries(journal_path(state)) if e.id not in done]


def render(args, when):
    lines = [
        f"## {when} — {one_line(args.topic)}",
        f"Kind: {args.kind}",
        f"Level: {args.level}",
        f"Asked: {one_line(args.asked)}",
        f"Tried / knew: {one_line(args.tried)}",
        f"Senior view: {one_line(args.view)}",
    ]
    if args.kind == "doubt":
        verdict = f"yes — {one_line(args.what)}" if args.disagrees == "yes" else "no"
        lines.append(f"Disagrees with teacher: {verdict}")
    lines.append(f"Refs: {one_line(args.refs) or '-'}")
    return "\n".join(lines) + "\n"


def check_verdict(args):
    """A doubt needs a verdict (and --what when yes); a question takes none."""
    if args.kind == "question":
        if args.disagrees or args.what:
            raise wise.WiseError("a question has no teacher claim: drop --disagrees/--what")
        return
    if args.disagrees is None:
        raise wise.WiseError("a doubt needs --disagrees yes|no")
    if args.disagrees == "yes" and not one_line(args.what or ""):
        raise wise.WiseError("--disagrees yes needs --what: what the teacher got wrong")


def cmd_add(args):
    check_verdict(args)
    state = find_state()
    folder = state / "consult"
    path = journal_path(state)
    for target in (folder, path):
        if target.is_symlink():
            raise wise.WiseError(f"{target} is a symlink; refusing")
    folder.mkdir(exist_ok=True)
    when = f"{wise.iso(wise.today())} {dt.datetime.now().strftime('%H:%M')}"
    entry = render(args, when)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    separator = "" if not existing or existing.endswith("\n\n") else (
        "\n" if existing.endswith("\n") else "\n\n")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(separator + entry)
    print(f"recorded in {path}")
    return 0


def find_state():
    state = wise.find_state(Path.cwd())
    if state is None:
        raise wise.WiseError("no .wise-code here; run Learn with Claude first")
    return state


def cmd_pending(args):
    for entry in pending(find_state()):
        if entry.disagrees:
            verdict = "disagrees"
        else:
            verdict = "-"
        print(f"{entry.id} {entry.date} {verdict} {entry.topic}")
    return 0


def cmd_ack(args):
    """Acknowledge only the ids given: an interrupted review leaves the rest pending."""
    state = find_state()
    path = acks_path(state)
    if path.is_symlink():
        raise wise.WiseError(f"{path} is a symlink; refusing")
    known = {e.id for e in entries(journal_path(state))}
    unknown = [i for i in args.ids if i not in known]
    if unknown:
        raise wise.WiseError(f"no consult {', '.join(unknown)} in the journal; "
                             "nothing acknowledged (see consult.py pending)")
    done = acknowledged(state)
    new = [i for i in dict.fromkeys(args.ids) if i not in done]
    if new:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        with path.open("a", encoding="utf-8") as stream:
            if existing and not existing.endswith("\n"):
                stream.write("\n")
            stream.write("".join(f"{i}\n" for i in new))
    print(f"acknowledged {len(args.ids)}; {len(pending(state))} pending")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="consult.py", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="append one consult to the journal")
    add.add_argument("--kind", required=True, choices=KINDS)
    add.add_argument("--topic", required=True)
    add.add_argument("--level", required=True, choices=LEVELS)
    add.add_argument("--asked", required=True, help="the learner's question")
    add.add_argument("--tried", required=True, help="what they tried and already knew")
    add.add_argument("--view", required=True, help="the senior's answer, as given")
    add.add_argument("--disagrees", choices=("yes", "no"), help="doubt only")
    add.add_argument("--what", help="doubt with --disagrees yes: what the teacher got wrong")
    add.add_argument("--refs", default="", help="files, lines, decision ids, links")
    add.set_defaults(func=cmd_add)
    show = commands.add_parser("pending", help="list consults the teacher hasn't acknowledged")
    show.set_defaults(func=cmd_pending)
    ack = commands.add_parser("ack", help="teacher: mark consults as gone through")
    ack.add_argument("ids", nargs="+", help="ids from consult.py pending")
    ack.set_defaults(func=cmd_ack)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except wise.WiseError as error:
        print(f"consult.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
