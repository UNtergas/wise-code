"""The senior consult journal: one Markdown file Codex appends to, Claude reads.

Codex, as the on-demand senior developer, records each consult here with
`consult.py add`. The journal sits in the project's `.wise-code/consult/`, beside
the learning graph but not in it: Codex is its only writer, so it needs no lock,
and nothing here touches `graph/`. The session hook counts entries with
`entries()`; Claude reads the file itself.

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
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wise  # noqa: E402 - shares state lookup, errors and the pinned test date


LEVELS = ("Hint", "Pseudo", "Full code")
KINDS = ("doubt", "question")
HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) \d\d:\d\d — ")
DISAGREES = re.compile(r"^Disagrees with teacher: (yes|no)\b")

Entry = collections.namedtuple("Entry", "date disagrees")


def journal_path(state):
    return state / "consult" / "journal.md"


def one_line(text):
    """Collapse a value to one line, so it can't forge a heading or a field."""
    return " ".join(str(text).split())


def entries(path):
    """Each entry's date and whether the senior disagreed; [] if absent or linked."""
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        return []
    found = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                heading = HEADING.match(line)
                if heading:
                    found.append(Entry(heading.group(1), False))
                    continue
                verdict = DISAGREES.match(line)
                if verdict and found:
                    found[-1] = found[-1]._replace(disagrees=verdict.group(1) == "yes")
    except (OSError, UnicodeError):
        return []
    return found


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
    state = wise.find_state(Path.cwd())
    if state is None:
        raise wise.WiseError("no .wise-code here; run Learn with Claude first")
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
