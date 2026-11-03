"""Check or apply the sandbox setup WiseCode's Learn onboarding requires first.

Three items, each reported as ok, missing, conflict or n/a:

- consult folder: `.wise-code/consult/` in this project, so the Codex senior can
  write its journal while every other path stays read-only to it.
- Claude sandbox: this project's `.claude/settings.local.json` (not committed)
  turns Claude Code's shell sandbox on, keeps credentials unreadable and allows
  only package and code hosts on the network.
- Codex senior profile: `$CODEX_HOME/senior.config.toml` (default `~/.codex`),
  used with `codex --profile senior`: deny-all filesystem, read the project and
  the plugin, write only the consult folder, live web search, docs hosts only for
  shell network. n/a when Codex isn't installed.

`check` changes nothing and exits 1 if anything is missing or conflicts.
`apply` creates what is missing, merges the Claude settings, and never
overwrites anything that differs from what it would write: that is reported as a
conflict for the learner to resolve. Running it twice changes nothing.
"""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wise  # noqa: E402 - shares project lookup and errors


CLAUDE_REQUIRED = {
    ("sandbox", "filesystem", "denyRead"): ["~/.ssh", "~/.aws", "~/.config/gh"],
    ("sandbox", "network", "allowedDomains"): [
        "*.github.com", "registry.npmjs.org", "pypi.org", "files.pythonhosted.org"],
    ("permissions", "deny"): ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(**/.env)"],
}

DOCS_HOSTS = ("developer.mozilla.org", "nodejs.org", "www.typescriptlang.org",
              "typeorm.io", "www.mongodb.com", "docs.python.org", "*.github.com",
              "raw.githubusercontent.com")

PROFILE_MARKER = "# Managed by wise-code scripts/setup.py; edit freely, setup won't overwrite."


class Item:
    def __init__(self, name, status, detail, apply=None):
        self.name, self.status, self.detail, self.apply = name, status, detail, apply


# ---------------------------------------------------------------- pure parts

def merge_claude(settings):
    """(merged, problem): add every required entry; problem is a conflict or None."""
    if not isinstance(settings, dict):
        return None, "settings file is not a JSON object"
    sandbox = settings.get("sandbox", {})
    if not isinstance(sandbox, dict):
        return None, "`sandbox` is not an object"
    if sandbox.get("enabled") is False:
        return None, "`sandbox.enabled` is false; turn it on yourself or remove the key"
    merged = json.loads(json.dumps(settings))
    merged.setdefault("sandbox", {})["enabled"] = True
    for path, entries in CLAUDE_REQUIRED.items():
        node = merged
        for key in path[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                return None, f"`{'.'.join(path[:-1])}` is not an object"
        current = node.setdefault(path[-1], [])
        if not isinstance(current, list):
            return None, f"`{'.'.join(path)}` is not a list"
        current.extend(e for e in entries if e not in current)
    return merged, None


def codex_profile(plugin_root):
    hosts = "\n".join(f'{json.dumps(h)} = "allow"' for h in DOCS_HOSTS)
    return f"""{PROFILE_MARKER}
# WiseCode senior: run `codex --profile senior` in the project folder.
default_permissions = "senior"
approval_policy = "on-request"
web_search = "live"

[features]
network_proxy = true

[permissions.senior]
description = "WiseCode senior: read the project and the plugin, write only the consult journal."
extends = ":read-only"

[permissions.senior.filesystem]
":root" = "deny"
":minimal" = "read"
{json.dumps(str(plugin_root))} = "read"

[permissions.senior.filesystem.":workspace_roots"]
"." = "read"
".wise-code/consult" = "write"
"**/.env" = "deny"
"**/*.pem" = "deny"

[permissions.senior.network]
enabled = true

[permissions.senior.network.domains]
{hosts}
"""


# ---------------------------------------------------------------- the items

def write_atomic(path, text):
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def consult_item(project):
    state = project / ".wise-code"
    folder = state / "consult"
    for path in (state, folder):
        if path.is_symlink():
            return Item("consult folder", "conflict", f"{path} is a symlink; refusing")
    if folder.is_dir():
        return Item("consult folder", "ok", str(folder))

    def apply():
        folder.mkdir(parents=True, exist_ok=True)
        return f"created {folder}"
    return Item("consult folder", "missing", str(folder), apply)


def claude_item(project):
    path = project / ".claude" / "settings.local.json"
    name = "Claude sandbox"
    for target in (path.parent, path):
        if target.is_symlink():
            return Item(name, "conflict", f"{target} is a symlink; refusing")
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as error:
            return Item(name, "conflict", f"{path} is not valid JSON ({error}); fix it first")
    merged, problem = merge_claude(existing)
    if problem:
        return Item(name, "conflict", f"{path}: {problem}")
    if merged == existing:
        return Item(name, "ok", str(path))

    def apply():
        path.parent.mkdir(exist_ok=True)
        write_atomic(path, json.dumps(merged, indent=2) + "\n")
        return f"{'updated' if existing else 'created'} {path}"
    return Item(name, "missing", f"{path} lacks the sandbox rules", apply)


def find_codex_plugin(codex_home):
    """The installed wise-code plugin under CODEX_HOME, or None."""
    for manifest in sorted(codex_home.rglob(".codex-plugin/plugin.json")):
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") == "wise-code":
                return manifest.parent.parent
        except (OSError, ValueError, UnicodeError, AttributeError):
            continue
    return None


def codex_item(codex_home, plugin_root):
    name = "Codex senior profile"
    if not codex_home.is_dir():
        return Item(name, "n/a", f"Codex not installed ({codex_home} missing)")
    path = codex_home / "senior.config.toml"
    if path.is_symlink():
        return Item(name, "conflict", f"{path} is a symlink; refusing")
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text.startswith(PROFILE_MARKER):
            return Item(name, "ok", str(path))
        return Item(name, "conflict", f"{path} exists and wasn't written by setup; "
                    "compare it with `setup.py show-codex` and merge by hand")
    root = plugin_root or find_codex_plugin(codex_home)
    if root is None:
        return Item(name, "missing", "wise-code not found under "
                    f"{codex_home}; install it in Codex, or pass --codex-plugin-root PATH")

    def apply():
        write_atomic(path, codex_profile(root))
        return f"created {path}"
    return Item(name, "missing", str(path), apply)


def items(args):
    start = Path.cwd().resolve()
    project = wise.git_root(start) or start
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    plugin = Path(args.codex_plugin_root).resolve() if args.codex_plugin_root else None
    return [consult_item(project), claude_item(project), codex_item(codex_home, plugin)]


# ---------------------------------------------------------------- commands

def report(found):
    for item in found:
        print(f"{item.status:<9}{item.name}: {item.detail}")


def cmd_check(args):
    found = items(args)
    report(found)
    if all(i.status in ("ok", "n/a") for i in found):
        return 0
    script = Path(__file__).resolve()
    print(f'run: python3 "{script}" apply   (then check again)')
    return 1


def cmd_apply(args):
    for item in items(args):
        if item.status == "missing" and item.apply:
            print(item.apply())
    # Report the state after applying, the same way check does.
    found = items(args)
    report(found)
    return 0 if all(i.status in ("ok", "n/a") for i in found) else 1


def cmd_show_codex(args):
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    root = (Path(args.codex_plugin_root).resolve() if args.codex_plugin_root
            else find_codex_plugin(codex_home) or Path("<wise-code plugin folder>"))
    print(codex_profile(root), end="")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="setup.py", description=__doc__.split("\n")[0])
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--codex-plugin-root",
                        help="the wise-code folder Codex installed, if not detected")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, func, text in (("check", cmd_check, "report; change nothing"),
                             ("apply", cmd_apply, "create what is missing"),
                             ("show-codex", cmd_show_codex,
                              "print the Codex profile setup would write")):
        commands.add_parser(name, parents=[shared], help=text).set_defaults(func=func)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, wise.WiseError) as error:
        print(f"setup.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
