"""Check or apply the sandbox setup WiseCode's Learn onboarding requires first.

Three items, each reported as ok, missing, conflict, n/a, or (Codex profile
only) edited or accepted:

- consult folder: `.wise-code/consult/` in this project, so the Codex senior can
  write its journal while every other path stays read-only to it.
- Claude sandbox: this project's `.claude/settings.local.json` (not committed)
  turns Claude Code's shell sandbox on, keeps credentials unreadable and allows
  only package and code hosts on the network.
- Codex senior profile: `$CODEX_HOME/senior.config.toml` (default `~/.codex`),
  used with `codex --profile senior`: deny-all filesystem, read the project and
  the plugin, write only the consult folder, live web search, docs hosts only for
  shell network. n/a when Codex isn't installed.

`check` changes nothing and exits 1 if anything is missing, conflicts or is
edited. A Codex profile the learner edited is reported as `edited` with every
setting line that differs from what setup writes, and blocks until the learner
approves exactly those settings with `accept-profile`, which stores their hash
next to the profile. From then on it reads `accepted` (passing, never `ok`);
any later change to a setting blocks again.
`apply` creates what is missing, merges the Claude settings, and never
overwrites anything that differs from what it would write: that is reported as a
conflict for the learner to resolve. Running it twice changes nothing.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wise  # noqa: E402 - shares project lookup and errors


# Secrets no Claude tool may read: (shell sandbox path, Read-tool rule) pairs.
# The shell sandbox (sandbox.filesystem.denyRead) and the Read tool
# (permissions.deny) are separate layers, and each list is written in its own
# syntax: in sandbox paths `./` is the project root and `~/` home; in Read rules
# a bare `**/` pattern matches anywhere under the project. Recent Claude Code
# also copies Read deny rules into denyRead, but setup doesn't rely on that.
# `./**/.env` may not match the root file, so the root gets its own entry.
PROTECTED = [
    (["~/.ssh"], ["Read(~/.ssh/**)"]),
    (["~/.aws"], ["Read(~/.aws/**)"]),
    (["~/.config/gh"], ["Read(~/.config/gh/**)"]),
    (["./.env", "./**/.env"], ["Read(**/.env)"]),
]

CLAUDE_REQUIRED = {
    ("sandbox", "filesystem", "denyRead"): [p for shell, _ in PROTECTED for p in shell],
    ("sandbox", "network", "allowedDomains"): [
        "*.github.com", "registry.npmjs.org", "pypi.org", "files.pythonhosted.org"],
    ("permissions", "deny"): [rule for _, read in PROTECTED for rule in read],
}

DOCS_HOSTS = ("developer.mozilla.org", "nodejs.org", "www.typescriptlang.org",
              "typeorm.io", "www.mongodb.com", "docs.python.org", "*.github.com",
              "raw.githubusercontent.com")

# A loaded `sandbox_mode` or `[sandbox_workspace_write]` makes Codex use those
# older settings instead of `default_permissions`, so the senior profile would
# silently not apply.
LEGACY_SANDBOX = re.compile(
    r"^[ \t]*(sandbox_mode[ \t]*=|sandbox_workspace_write[ \t]*\.|\[[ \t]*sandbox_workspace_write[ \t]*\])",
    re.MULTILINE)

PROFILE_MARKER = "# Managed by wise-code scripts/setup.py; edit freely, setup won't overwrite."


class Item:
    def __init__(self, name, status, detail, apply=None, warning=None):
        self.name, self.status, self.detail, self.apply = name, status, detail, apply
        # A line the learner must not miss, printed apart after the report.
        self.warning = warning


# ---------------------------------------------------------------- pure parts

def platform():
    # Tests set WISE_SETUP_PLATFORM; real runs use the interpreter's platform.
    return os.environ.get("WISE_SETUP_PLATFORM") or sys.platform


def sandbox_unavailable():
    """Why Claude Code's sandbox can't run here, or None.

    With failIfUnavailable set, Claude Code refuses to start where the sandbox
    can't run, so setup must not write that setting on such a machine.
    """
    if platform() == "win32":
        return ("the sandbox doesn't run on native Windows; run Claude Code inside "
                "WSL2, or skip setup")
    if platform().startswith("linux"):
        missing = [tool for tool in ("bwrap", "socat") if shutil.which(tool) is None]
        if missing:
            return (f"sandbox dependencies missing: {', '.join(missing)}; install "
                    "bubblewrap and socat (apt-get or dnf), then check again")
    return None


def toml_string(text):
    """A TOML basic string: escape only what TOML requires, keep all Unicode."""
    out = []
    for char in str(text):
        if char in ('"', "\\"):
            out.append("\\" + char)
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def toml_unstring(text):
    """Inverse of toml_string for the strings setup writes."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            if text[i + 1] == "u":
                out.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# A learner's valid TOML must not hide the grant: basic or literal strings,
# any spacing around `=`, a trailing comment.
GRANT = re.compile(r'^(?:"((?:[^"\\]|\\.)*)"|\'([^\']*)\')[ \t]*=[ \t]*'
                   r'(?:"read"|\'read\')[ \t]*(?:#.*)?$')


def granted_plugin(profile):
    """The plugin folder a setup-written profile grants read on, or None."""
    section = None
    for line in profile.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
            continue
        match = GRANT.match(line)
        if section == "[permissions.senior.filesystem]" and match:
            basic, literal = match.groups()
            path = toml_unstring(basic) if basic is not None else literal
            if not path.startswith(":"):
                return path
    return None


def legacy_sandbox_files(paths):
    """The loaded Codex configs that carry legacy sandbox settings."""
    found = []
    for path in paths:
        try:
            if path.is_file() and LEGACY_SANDBOX.search(path.read_text(encoding="utf-8")):
                found.append(path)
        except (OSError, UnicodeError):
            continue
    return found


def merge_claude(settings):
    """(merged, problem): add every required entry; problem is a conflict or None."""
    if not isinstance(settings, dict):
        return None, "settings file is not a JSON object"
    sandbox = settings.get("sandbox", {})
    if not isinstance(sandbox, dict):
        return None, "`sandbox` is not an object"
    for key in ("enabled", "failIfUnavailable"):
        if sandbox.get(key) is False:
            return None, f"`sandbox.{key}` is false; set it to true yourself or remove the key"
    merged = json.loads(json.dumps(settings))
    merged.setdefault("sandbox", {})["enabled"] = True
    # Fail closed: without this, a sandbox that can't start runs commands
    # unsandboxed and the deny rules above protect nothing.
    merged["sandbox"]["failIfUnavailable"] = True
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
    hosts = "\n".join(f'{toml_string(h)} = "allow"' for h in DOCS_HOSTS)
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
{toml_string(plugin_root)} = "read"

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
    """Write through a fresh, exclusively created temp file, then replace.

    A fixed temp name could be a planted symlink that write_text would follow;
    mkstemp creates a new file with O_EXCL and never follows one.
    """
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, path)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise


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
    unavailable = sandbox_unavailable()
    if unavailable:
        return Item(name, "conflict", unavailable)
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
    """The folder holding every installed version of wise-code in Codex, or None.

    Codex installs a plugin at plugins/cache/<marketplace>/<plugin>/<version>
    and loads it from there. Granting the folder above the versions keeps the
    profile valid across updates. Marketplace clones under .tmp are only
    sources, and their .staging checkouts vanish after a refresh.
    """
    for manifest in sorted((codex_home / "plugins/cache").glob("*/*/*/.codex-plugin/plugin.json")):
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") == "wise-code":
                return manifest.parent.parent.parent
        except (OSError, ValueError, UnicodeError, AttributeError):
            continue
    return None


def codex_item(codex_home, plugin_root, project):
    name = "Codex senior profile"
    # Installed means the CLI is on PATH or Codex has created its home; a CLI
    # that was never run has no home yet and still needs the profile.
    if not codex_home.is_dir() and shutil.which("codex") is None:
        return Item(name, "n/a", f"Codex not installed (no `codex` on PATH, no {codex_home})")
    legacy = legacy_sandbox_files([codex_home / "config.toml", project / ".codex" / "config.toml"])
    if legacy:
        files = ", ".join(str(f) for f in legacy)
        return Item(name, "conflict", f"{files} sets sandbox_mode or [sandbox_workspace_write]; "
                    "while loaded, Codex ignores the senior permission profile. Remove "
                    "those keys (permission profiles replace them), then check again")
    path = codex_home / "senior.config.toml"
    if path.is_symlink():
        return Item(name, "conflict", f"{path} is a symlink; refusing")
    root = plugin_root or find_codex_plugin(codex_home)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if not text.startswith(PROFILE_MARKER):
            return Item(name, "conflict", f"{path} exists and wasn't written by setup; "
                        "compare it with `setup.py show-codex` and merge by hand")
        return existing_profile_item(name, path, text, root, codex_home,
                                     read_accepted(path))
    if root is None:
        return Item(name, "missing", "wise-code not found under "
                    f"{codex_home}; install it in Codex, or pass --codex-plugin-root PATH")

    def apply():
        codex_home.mkdir(parents=True, exist_ok=True)
        write_atomic(path, codex_profile(root))
        return f"created {path}"
    return Item(name, "missing", str(path), apply)


def profile_lines(text):
    """Each setting line of a profile with its [section], comments and blanks left out."""
    section, found = "", []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line
            continue
        found.append(f"{section} {line}".strip())
    return found


def profile_changes(text, generated):
    """How a profile differs from what setup writes: removed and added lines."""
    ours, theirs = profile_lines(generated), profile_lines(text)
    return ([f"removed {line}" for line in ours if line not in theirs]
            + [f"added {line}" for line in theirs if line not in ours])


def profile_digest(text):
    """Hash of a profile's settings: comments, blanks and spacing don't count."""
    return hashlib.sha256("\n".join(profile_lines(text)).encode("utf-8")).hexdigest()


def accepted_path(profile):
    return profile.with_name(profile.name + ".accepted")


def read_accepted(profile):
    """The digest the learner accepted; None if absent, linked or unreadable."""
    path = accepted_path(profile)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeError):
        return None


def verified_item(name, path, text, granted, accepted):
    """ok when the profile is exactly what setup writes for its plugin folder.

    Otherwise the learner edited it. The edit is theirs and is never
    rewritten, but it loosens or tightens the senior's sandbox, so it blocks
    (`edited`, every differing line listed) until the learner approves these
    exact settings with `accept-profile`; then it passes as `accepted`.
    """
    changes = profile_changes(text, codex_profile(granted))
    if not changes:
        return Item(name, "ok", str(path))
    if accepted == profile_digest(text):
        return Item(name, "accepted", f"{path}: your edits, accepted: " + "; ".join(changes))
    script = Path(__file__).resolve()
    if accepted is None:
        why = ("it has edits you never approved. Edited profiles now need your "
               "approval, so this also happens to a profile you edited before")
    else:
        why = "it changed since you accepted it"
    warning = (f"WARNING: onboarding stops at your Codex senior profile ({path}): {why}. "
               f'Approve it as it is with `python3 "{script}" accept-profile`, or restore '
               "the generated one from `setup.py show-codex`, then check again.")
    return Item(name, "edited", f"{path} differs from what setup writes: "
                + "; ".join(changes) + ". If you meant these, approve them with "
                f'`python3 "{script}" accept-profile`; otherwise compare with '
                "`setup.py show-codex` and fix the file", warning=warning)


def existing_profile_item(name, path, text, root, codex_home, accepted):
    """Check a setup-written profile: its plugin grant, then every other line.

    The profile denies the filesystem root, so a stale grant (the plugin moved,
    e.g. on update) leaves the senior unable to read its own scripts. A current
    grant alone proves nothing about the other restrictions.
    """
    granted = granted_plugin(text)
    if root is None:
        if granted and Path(granted).is_dir():
            return verified_item(name, path, text, granted, accepted)
        what = f"grants {granted}, which is gone" if granted else "grants no plugin folder"
        return Item(name, "conflict", f"{path} {what}, and wise-code wasn't found under "
                    f"{codex_home}; pass --codex-plugin-root PATH")
    if granted == str(root):
        return verified_item(name, path, text, granted, accepted)
    if granted and text == codex_profile(granted):
        # Unedited since setup wrote it: safe to regenerate for the new folder.
        def apply():
            write_atomic(path, codex_profile(root))
            return f"updated {path}"
        return Item(name, "missing", f"{path} grants the old plugin folder {granted}; "
                    f"apply regenerates it for {root}", apply)
    if granted is None:
        return Item(name, "conflict", f"{path} was edited and grants no plugin folder, so the "
                    "senior can't read wise-code. Your edits are kept: in that file, add the "
                    f'line {toml_string(root)} = "read" under [permissions.senior.filesystem] '
                    "(if a line there already grants a wise-code folder, change its path "
                    "instead: a second one is invalid TOML), then check again")
    return Item(name, "conflict", f"{path} was edited and grants {granted}, but the plugin "
                f"is now at {root}. Your edits are kept: in that file, under "
                f"[permissions.senior.filesystem], change the path {toml_string(granted)} to "
                f"{toml_string(root)}, then check again")


def items(args):
    start = Path.cwd().resolve()
    project = wise.git_root(start) or start
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    plugin = Path(args.codex_plugin_root).resolve() if args.codex_plugin_root else None
    return [consult_item(project), claude_item(project), codex_item(codex_home, plugin, project)]


# ---------------------------------------------------------------- commands

def report(found):
    for item in found:
        print(f"{item.status:<9}{item.name}: {item.detail}")


def warn(found):
    """Warnings come last, apart, so nothing scrolls them out of sight."""
    for item in found:
        if item.warning:
            print(f"\n{item.warning}")


# Statuses that let onboarding continue.
PASSING = ("ok", "accepted", "n/a")


def cmd_check(args):
    found = items(args)
    report(found)
    if all(i.status in PASSING for i in found):
        return 0
    if any(i.status in ("missing", "conflict") for i in found):
        script = Path(__file__).resolve()
        print(f'run: python3 "{script}" apply   (then check again)')
    warn(found)
    return 1


def cmd_apply(args):
    for item in items(args):
        if item.status == "missing" and item.apply:
            print(item.apply())
    # Report the state after applying, the same way check does.
    found = items(args)
    report(found)
    warn(found)
    return 0 if all(i.status in PASSING for i in found) else 1


def cmd_accept_profile(args):
    """The learner approves their edited Codex profile, exactly as it is now."""
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    item = items(args)[2]
    if item.status in ("ok", "n/a"):
        print(f"nothing to accept: {item.detail}")
        return 0
    if item.status == "accepted":
        print(f"already accepted: {item.detail}")
        return 0
    if item.status != "edited":
        raise wise.WiseError(f"can't accept the Codex profile: {item.detail}")
    profile = codex_home / "senior.config.toml"
    target = accepted_path(profile)
    if target.is_symlink():
        raise wise.WiseError(f"{target} is a symlink; refusing")
    text = profile.read_text(encoding="utf-8")
    write_atomic(target, profile_digest(text) + "\n")
    print(f"accepted {profile} as it is now; any later change to a setting needs accepting "
          "again. Accepted: "
          + "; ".join(profile_changes(text, codex_profile(granted_plugin(text)))))
    return 0


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
                             ("accept-profile", cmd_accept_profile,
                              "approve your edited Codex profile as it is now"),
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
