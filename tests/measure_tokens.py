"""Measure what each command reads before (whole Markdown files) and after (one query).

Run: python3 tests/measure_tokens.py
Tokens are estimated as characters / 4. The test suite asserts the "after"
column stays under the query cap; this script prints the table for the PR.
"""

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fixture  # noqa: E402
import wise  # noqa: E402

# command → (legacy files it read whole, graph queries that replace them)
COMMANDS = [
    ("quiz: find due questions", ["questions.md"], [["due"]]),
    ("start check", ["session-recap.md"], [["session", "--pending"]]),
    ("restore: pending decisions + weak topics", ["progress.md"],
     [["decisions", "--pending"], ["weak"]]),
    ("correct: repeated mistakes", ["qa-history.md", "progress.md", "guardrails.md"],
     [["mistakes", "--repeated"]]),
    ("history of one concept", ["qa-history.md"], [["history", "--concept", "topic-03-traits"]]),
    ("teach: what is known", ["progress.md", "teach/learning-records"],
     [["list", "record"], ["weak"]]),
]


def size(path):
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return path.stat().st_size if path.exists() else 0


def run(root, argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        wise.main(["--root", str(root), *argv])
    return buffer.getvalue()


def measure():
    os.environ["WISE_TODAY"] = "2026-10-28"
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "fixture"
        project.mkdir()
        (project / ".git").mkdir()
        state = fixture.build(project)
        before = {name: size(state / name) for _, files, _ in COMMANDS for name in files}
        run(project, ["import-md"])
        rows = []
        for label, files, queries in COMMANDS:
            old = sum(before[name] for name in files) // 4
            outputs = [run(project, q) for q in queries]
            new = sum(len(o) for o in outputs) // 4
            rows.append((label, old, new, max(len(o) for o in outputs)))
        return rows


if __name__ == "__main__":
    print("| Command | Before (tokens) | After (tokens) | Saved |")
    print("|---|---:|---:|---:|")
    for label, old, new, _ in measure():
        print(f"| {label} | {old:,} | {new:,} | {100 - 100 * new // max(old, 1)}% |")
