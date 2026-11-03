"""Run the documented shelf git sync against two real clones."""

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
               GIT_CONFIG_NOSYSTEM="1", HOME=tempfile.gettempdir())


def sh_blocks(text):
    """The commands of each ```sh block, one list of lines per block."""
    return [[line.strip() for line in block.splitlines() if line.strip()]
            for block in re.findall(r"```sh\n(.*?)```", text, re.S)]


def run(line, **values):
    for name, value in values.items():
        line = line.replace(f"<{name}>", value)
    return subprocess.run(shlex.split(line), capture_output=True, text=True,
                          env=GIT_ENV, timeout=30)


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                          text=True, env=GIT_ENV, timeout=30, check=True).stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git not installed")
class QuizShelfSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        remote, self.a, self.b = base / "remote.git", base / "a", base / "b"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)],
                       check=True, env=GIT_ENV)
        for clone in (self.a, self.b):
            subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                           check=True, env=GIT_ENV, capture_output=True)
        state = self.a / ".wise-code"
        state.mkdir()
        (state / "shelf.md").write_text("# Shelf\n", encoding="utf-8")
        git(self.a, "add", ".wise-code")
        git(self.a, "commit", "-q", "-m", "base")
        git(self.a, "push", "-q", "origin", "HEAD:main")
        git(self.b, "pull", "-q", "origin", "main")
        git(self.a, "branch", "-q", "-u", "origin/main")

    def quiz_blocks(self):
        quiz = (ROOT / "skills/quiz/SKILL.md").read_text(encoding="utf-8")
        blocks = sh_blocks(quiz[quiz.index("**Shelf repo:**"):])
        self.assertGreaterEqual(len(blocks), 2, "sync block and failed-pull block")
        return blocks[0], blocks[1]

    def test_conflicting_pull_is_aborted_and_keeps_the_answer(self):
        sync, recover = self.quiz_blocks()
        # Another machine changed a file that has no union merge driver.
        (self.b / ".wise-code/shelf.md").write_text("# Shelf\nLFS prompt: off\n",
                                                   encoding="utf-8")
        git(self.b, "commit", "-q", "-am", "other machine")
        git(self.b, "push", "-q")
        (self.a / ".wise-code/shelf.md").write_text("# Shelf\nMode: shelf\n",
                                                   encoding="utf-8")
        values = {"root": str(self.a), "QB-id": "QB-1", "verdict": "correct"}
        results = [run(line, **values) for line in sync[:3]]
        self.assertNotEqual(results[-1].returncode, 0, "the pull must conflict")
        self.assertNotEqual(run('git -C "<root>" symbolic-ref -q HEAD', **values)
                            .returncode, 0, "a stopped rebase leaves HEAD detached")

        check, abort = recover
        self.assertTrue(run(check, **values).stdout.strip(), "REBASE_HEAD names a commit")
        self.assertEqual(run(abort, **values).returncode, 0)

        self.assertEqual(git(self.a, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(git(self.a, "log", "-1", "--format=%s"), "shelf: quiz QB-1 correct")
        self.assertEqual(git(self.a, "status", "--porcelain"), "")
        self.assertNotIn("<<<<<<<", (self.a / ".wise-code/shelf.md").read_text("utf-8"))
        # Nothing to abort after a clean pull: the check prints nothing.
        git(self.b, "pull", "-q")
        self.assertEqual(run(check, root=str(self.b)).stdout.strip(), "")

    def test_shelf_failed_pull_block_recovers_the_same_way(self):
        shelf = (ROOT / "skills/shelf/SKILL.md").read_text(encoding="utf-8")
        step1 = shelf.split("## Step 1: Sync")[1].split("\n## ")[0]
        recover = next(b for b in sh_blocks(step1) if any("rebase --abort" in l for l in b))
        (self.b / ".wise-code/shelf.md").write_text("B\n", encoding="utf-8")
        git(self.b, "commit", "-q", "-am", "other machine")
        git(self.b, "push", "-q")
        (self.a / ".wise-code/shelf.md").write_text("A\n", encoding="utf-8")
        git(self.a, "commit", "-q", "-am", "shelf(p): carry-over")
        self.assertNotEqual(run('git -C "<shelf>" pull --rebase --quiet',
                                shelf=str(self.a)).returncode, 0)
        check, abort = recover
        self.assertTrue(run(check, shelf=str(self.a)).stdout.strip())
        self.assertEqual(run(abort, shelf=str(self.a)).returncode, 0)
        self.assertEqual(git(self.a, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(git(self.a, "log", "-1", "--format=%s"), "shelf(p): carry-over")

        # Every Shelf pull failure path points to the block.
        self.assertEqual(shelf.count("**Failed pull**"), 3)


if __name__ == "__main__":
    unittest.main()
