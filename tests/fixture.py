"""Build a mid-life WiseCode project in the legacy Markdown formats.

Used by the graph tests and by `python3 tests/measure_tokens.py`. Sizes match the
grill's proof target: 300 Q/A entries, 100 questions, 30 concepts, 5 sessions.
Deterministic: the same seed gives the same files.
"""

from pathlib import Path
import random

TOPICS = [f"Topic {n:02d} {word}" for n, word in enumerate(
    ["strings", "ownership", "lifetimes", "traits", "errors", "async", "tokio",
     "channels", "serde", "http", "caching", "sqlite", "migrations", "testing",
     "mocking", "tracing", "config", "cli", "wasm", "ffi", "unsafe", "macros",
     "iterators", "closures", "generics", "modules", "cargo", "clippy",
     "benchmarks", "profiling"])]
VERDICTS = ["correct", "correct", "partial", "wrong"]
SOURCES = ["checkpoint", "review", "quiz", "lesson", "explore", "asked"]


def sentence(rng, words):
    vocab = ("the parser keeps a byte offset while the browser sends utf16 code units so "
             "every span must be converted at the boundary before the core stores it and "
             "the queue retries with backoff because the broker throttles bursts").split()
    return " ".join(rng.choice(vocab) for _ in range(words)).capitalize()


def build(project, seed=7, qa=300, questions=100, sessions=5):
    rng = random.Random(seed)
    state = Path(project) / ".wise-code"
    teach = state / "teach"
    (teach / "learning-records").mkdir(parents=True)
    (teach / "lessons").mkdir()
    (Path(project) / "research").mkdir()

    lines = ["# Q/A History", ""]
    for n in range(qa):
        day = 1 + n * 27 // qa
        lines += [f"## 2026-10-{day:02d} · {TOPICS[n % 30]} · {SOURCES[n % 6]}",
                  f"Q: {sentence(rng, 14)}?", f"A: {sentence(rng, 22)}.",
                  f"Verdict: {VERDICTS[n % 4]}", "Follow-up: none", ""]
    (state / "qa-history.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Question Bank", ""]
    for n in range(questions):
        lines += [f"## QB-{n + 1:04d} · {TOPICS[n % 30]}", f"Q: {sentence(rng, 16)}?",
                  f"A: {sentence(rng, 24)}.", f"Source: qa-history 2026-10-{1 + n % 27:02d}",
                  f"Box: {1 + n % 5}", f"Due: 2026-{10 + n % 2}-{1 + n % 27:02d}", ""]
    (state / "questions.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Learning Progress", ""]
    for n, topic in enumerate(TOPICS):
        lines += [f"## {topic}", f"- Introduced: {sentence(rng, 10)}.",
                  f"- Demonstrated understanding: {sentence(rng, 12)}."]
        if n % 4 == 0:
            lines.append(f"- Needs reinforcement: {sentence(rng, 10)}.")
        lines.append("")
    lines += ["## Pending decision", "Storage choice: SQLite vs JSON. Stage: awaiting "
              "implementation approval. Waiting for Implement.", ""]
    (state / "progress.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Session Recap", ""]
    for n in range(sessions):
        lines += [f"## 2026-10-{20 + n:02d} · Session goal {n}", "Finished:",
                  f"- {sentence(rng, 8)}", "Learned:", f"- {sentence(rng, 8)}", "Decided:",
                  f"- {sentence(rng, 8)}", "Open:", f"- {sentence(rng, 6)}", "Check points:",
                  *(f"- {sentence(rng, 10)}" for _ in range(4)),
                  f"Start check: {'pending' if n == sessions - 1 else 'done 2026-10-2' + str(n + 1) + ' · 3/4'}",
                  ""]
    (state / "session-recap.md").write_text("\n".join(lines), encoding="utf-8")

    rows = ["#separator:Tab", "#html:false", "#notetype:Basic", "#deck:wise-code::fixture",
            "#tags column:3"]
    for n in range(50):
        rows.append(f"Card {n}: {sentence(rng, 6)}?\t{sentence(rng, 8)}.\twise-code "
                    f"topic-{n % 30:02d}-x")
    (state / "cards.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    (state / "guardrails.md").write_text(
        "# Guardrails\n\n| Mistake class | Evidence | Level | Enforced by | Proven |\n"
        "|---|---|---|---|---|\n"
        "| Slicing `&str` at a byte index | qa-history 2026-10-21, 2026-10-24 | types | "
        "`CharOffset` newtype | 2026-10-25: reverted mistake fails `cargo check` |\n",
        encoding="utf-8")
    (state / "reflections.md").write_text(
        "# Reflections\n\n## 2026-10-20\nLearner: I finally get why offsets differ.\n"
        "Evidence check: supported by QA on strings.\n", encoding="utf-8")
    (state / "plugin-feedback.md").write_text(
        "# WiseCode feedback\n\n## 2026-10-20 · Hint level · assist-levels.md \"Hint\"\n"
        "What happened: wrote a full signature after the second hint.\n"
        "Rule: \"Never write code...\"\nProposed edit: a → b\nStatus: proposed\n",
        encoding="utf-8")
    (teach / "GLOSSARY.md").write_text(
        "# Glossary\n\n- **Byte offset**: index into the UTF-8 bytes.\n"
        "- **Code unit**: one UTF-16 element.\n", encoding="utf-8")
    (teach / "MISSION.md").write_text("# Mission\n\nShip the grammar core in Rust.\n",
                                      encoding="utf-8")
    (teach / "RESOURCES.md").write_text(
        "# Resources\n\n- [The Rust Book](https://doc.rust-lang.org/book/)\n"
        "- [Rust forum](https://users.rust-lang.org/)\n", encoding="utf-8")
    (teach / "learning-records" / "0001-utf8.md").write_text(
        "# UTF-8 is variable width\n\nKnows a char can be 1-4 bytes.\n", encoding="utf-8")
    (teach / "learning-records" / "0002-offsets.md").write_text(
        "---\nStatus: superseded by LR-0003\n---\n# Offsets are bytes\n\nOld view.\n",
        encoding="utf-8")
    (teach / "learning-records" / "0003-offsets-v2.md").write_text(
        "# Offsets need a unit\n\nByte vs code unit vs char.\n\nEvidence: lesson 2 exercise.\n",
        encoding="utf-8")
    (teach / "lessons" / "0001-utf8.html").write_text(
        "<!doctype html><title>UTF-8 basics</title><p>…</p>", encoding="utf-8")
    (Path(project) / "research" / "2026-10-22-utf16.md").write_text(
        "# Does the browser send UTF-16 offsets?\n\nYes.\n", encoding="utf-8")
    return state
