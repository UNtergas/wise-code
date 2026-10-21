"""Copy skills that also ship as standalone plugins into those plugins.

`skills/<name>/` is the source of truth. Each standalone plugin under `plugins/`
gets an identical copy, because an installed plugin can't read files outside its
own directory. Run after editing a shared skill; `--check` only reports drift.
"""

import argparse
import filecmp
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
# standalone plugin directory -> skills it ships
STANDALONE = {"wise-research": ["research"]}


def pairs():
    for plugin, names in STANDALONE.items():
        for name in names:
            yield ROOT / "skills" / name, ROOT / "plugins" / plugin / "skills" / name


def drift(source, copy):
    """Return the relative paths that differ between two skill folders."""
    if not copy.is_dir():
        return ["<missing copy>"]
    result = []
    comparison = filecmp.dircmp(source, copy)
    stack = [(comparison, Path())]
    while stack:
        node, prefix = stack.pop()
        result += [str(prefix / n) for n in node.left_only + node.right_only + node.diff_files]
        # dircmp compares shallowly; confirm byte equality for files it calls equal.
        result += [str(prefix / n) for n in node.same_files
                   if (Path(node.left) / n).read_bytes() != (Path(node.right) / n).read_bytes()]
        stack += [(sub, prefix / n) for n, sub in node.subdirs.items()]
    return sorted(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift, change nothing")
    args = parser.parse_args()
    status = 0
    for source, copy in pairs():
        differences = drift(source, copy)
        if not differences:
            continue
        if args.check:
            print(f"{copy.relative_to(ROOT)} differs from {source.relative_to(ROOT)}: {differences}")
            status = 1
            continue
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(source, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"synced {source.relative_to(ROOT)} -> {copy.relative_to(ROOT)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
