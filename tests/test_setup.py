"""scripts/setup.py: check and apply the sandbox setup Learn requires first."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SetupCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wise-setup-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home = base / "home"
        self.home.mkdir()
        self.codex_home = self.home / ".codex"
        self.codex_home.mkdir()
        # PATH holds only what a test puts there, so a real `codex` on the
        # developer's machine can't change what setup detects.
        self.bin = base / "bin"
        self.bin.mkdir()
        # Linux sandbox dependencies present unless a test removes them.
        for tool in ("bwrap", "socat"):
            self.tool(tool)
        self.project = base / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.settings = self.project / ".claude/settings.local.json"
        self.profile = self.codex_home / "senior.config.toml"
        self.codex_plugin = self.codex_home / "plugins/cache/wise-code"
        (self.codex_plugin / ".codex-plugin").mkdir(parents=True)
        (self.codex_plugin / ".codex-plugin/plugin.json").write_text(
            json.dumps({"name": "wise-code"}), encoding="utf-8")

    def tool(self, name):
        path = self.bin / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)

    def setup(self, *args, cwd=None, platform="linux"):
        env = {"PATH": str(self.bin), "HOME": str(self.home),
               "CODEX_HOME": str(self.codex_home), "WISE_SETUP_PLATFORM": platform}
        return subprocess.run([sys.executable, str(ROOT / "scripts/setup.py"), *args],
                              text=True, capture_output=True, env=env, timeout=30,
                              cwd=cwd or self.project)

    def fake_codex(self):
        codex = self.bin / "codex"
        codex.write_text("#!/bin/sh\necho codex-cli 0.0.0\n", encoding="utf-8")
        codex.chmod(0o755)

    def claude(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))


class FreshProjectTests(SetupCase):
    def test_check_reports_every_missing_item_and_fails(self):
        result = self.setup("check")
        self.assertEqual(result.returncode, 1, result.stderr)
        for item in ("consult folder", "Claude sandbox", "Codex senior profile"):
            self.assertRegex(result.stdout, rf"(?m)^missing +{item}")
        self.assertRegex(result.stdout, r'setup\.py"? apply')
        self.assertFalse(self.settings.exists())
        self.assertFalse(self.profile.exists())

    def test_apply_creates_everything_then_check_passes(self):
        result = self.setup("apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.project / ".wise-code/consult").is_dir())
        settings = self.claude()
        self.assertIs(settings["sandbox"]["enabled"], True)
        self.assertIs(settings["sandbox"]["failIfUnavailable"], True)
        self.assertIn("~/.ssh", settings["sandbox"]["filesystem"]["denyRead"])
        self.assertIn("*.github.com", settings["sandbox"]["network"]["allowedDomains"])
        self.assertIn("Read(~/.ssh/**)", settings["permissions"]["deny"])
        profile = self.profile.read_text(encoding="utf-8")
        for line in ('default_permissions = "senior"', 'web_search = "live"',
                     '":root" = "deny"', '".wise-code/consult" = "write"',
                     '"." = "read"', "network_proxy = true",
                     json.dumps(str(self.codex_plugin)) + ' = "read"'):
            self.assertIn(line, profile)
        self.assertEqual(self.setup("check").returncode, 0)

    def test_apply_twice_changes_nothing(self):
        self.setup("apply")
        before = (self.settings.read_bytes(), self.profile.read_bytes())
        result = self.setup("apply")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.settings.read_bytes(), self.profile.read_bytes()), before)
        self.assertNotRegex(result.stdout, r"(?m)^(created|updated)")

    def test_runs_from_a_subfolder_at_the_project_root(self):
        nested = self.project / "src"
        nested.mkdir()
        self.assertEqual(self.setup("apply", cwd=nested).returncode, 0)
        self.assertTrue(self.settings.is_file())
        self.assertTrue((self.project / ".wise-code/consult").is_dir())


class ExistingClaudeSettingsTests(SetupCase):
    def write(self, data):
        self.settings.parent.mkdir(exist_ok=True)
        text = data if isinstance(data, str) else json.dumps(data)
        self.settings.write_text(text, encoding="utf-8")

    def test_merge_keeps_other_keys_and_list_entries(self):
        self.write({"model": "opus", "permissions": {"allow": ["Bash(npm test)"],
                                                      "deny": ["Read(./secrets/**)"]},
                    "sandbox": {"network": {"allowedDomains": ["example.org"]}}})
        self.assertEqual(self.setup("apply").returncode, 0)
        settings = self.claude()
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["permissions"]["allow"], ["Bash(npm test)"])
        self.assertIn("Read(./secrets/**)", settings["permissions"]["deny"])
        self.assertIn("Read(~/.ssh/**)", settings["permissions"]["deny"])
        self.assertIn("example.org", settings["sandbox"]["network"]["allowedDomains"])
        self.assertIn("*.github.com", settings["sandbox"]["network"]["allowedDomains"])

    def test_sandbox_turned_off_on_purpose_is_a_conflict_not_overwritten(self):
        self.write({"sandbox": {"enabled": False}})
        before = self.settings.read_bytes()
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Claude sandbox")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_invalid_json_is_a_conflict_not_overwritten(self):
        self.write("{ not json")
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Claude sandbox")
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")

    def test_every_protected_path_is_denied_to_both_shell_and_read_tool(self):
        # The Read tool runs outside the shell sandbox (review on #26), and
        # .env was denied to the Read tool only (review #30).
        self.assertEqual(self.setup("apply").returncode, 0)
        settings = self.claude()
        shell = settings["sandbox"]["filesystem"]["denyRead"]
        read = settings["permissions"]["deny"]
        for path in ("~/.ssh", "~/.aws", "~/.config/gh"):
            self.assertIn(path, shell)
            self.assertIn(f"Read({path}/**)", read)
        # Sandbox paths: `./` is the project root; `**` doesn't cover the root file.
        self.assertIn("./.env", shell)
        self.assertIn("./**/.env", shell)
        self.assertIn("Read(**/.env)", read)

    def test_settings_from_an_older_setup_gain_the_env_rules(self):
        self.write({"sandbox": {"enabled": True, "failIfUnavailable": True,
                                "filesystem": {"denyRead": ["~/.ssh", "~/.aws", "~/.config/gh"]}},
                    "permissions": {"deny": ["Read(**/.env)"]}})
        check = self.setup("check")
        self.assertEqual(check.returncode, 1)
        self.assertRegex(check.stdout, r"(?m)^missing +Claude sandbox")
        self.assertEqual(self.setup("apply").returncode, 0)
        self.assertIn("./**/.env", self.claude()["sandbox"]["filesystem"]["denyRead"])

    def test_planted_temp_symlink_cannot_write_outside(self):
        # A fixed temp name was followed and truncated its target (review on #26).
        outside = Path(self.temp.name) / "victim.txt"
        outside.write_text("keep me", encoding="utf-8")
        self.settings.parent.mkdir()
        (self.settings.parent / ".settings.local.json.tmp").symlink_to(outside)
        (self.codex_home / ".senior.config.toml.tmp").symlink_to(outside)
        result = self.setup("apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep me")
        self.assertFalse(self.settings.is_symlink())
        self.assertFalse(self.profile.is_symlink())
        self.assertIn("sandbox", self.claude())

    def test_fail_open_left_on_purpose_is_a_conflict(self):
        # Without failIfUnavailable the sandbox silently runs commands
        # unsandboxed when it can't start (review on #26).
        self.write({"sandbox": {"failIfUnavailable": False}})
        before = self.settings.read_bytes()
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Claude sandbox")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_unavailable_sandbox_is_a_conflict_and_writes_nothing(self):
        # failIfUnavailable would make Claude Code refuse to start in this
        # project, so setup must not write it where the sandbox can't run.
        for case, platform, missing in (("native Windows", "win32", None),
                                        ("Linux without bubblewrap", "linux", "bwrap"),
                                        ("Linux without socat", "linux", "socat")):
            with self.subTest(case=case):
                if missing:
                    (self.bin / missing).unlink()
                result = self.setup("apply", platform=platform)
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stdout, r"(?m)^conflict +Claude sandbox")
                self.assertIn("WSL2" if platform == "win32" else missing, result.stdout)
                self.assertFalse(self.settings.exists())
                if missing:
                    self.tool(missing)

    def test_macos_needs_no_extra_tools(self):
        for tool in ("bwrap", "socat"):
            (self.bin / tool).unlink()
        self.assertEqual(self.setup("apply", platform="darwin").returncode, 0)

    def test_symlinked_settings_are_refused(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        self.settings.parent.mkdir()
        self.settings.symlink_to(outside)
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stdout)
        self.assertEqual(outside.read_text(encoding="utf-8"), "{}")


class CodexProfileTests(SetupCase):
    def test_a_different_existing_profile_is_a_conflict_not_overwritten(self):
        self.profile.write_text("# mine\n", encoding="utf-8")
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Codex senior profile")
        self.assertEqual(self.profile.read_text(encoding="utf-8"), "# mine\n")

    def test_installed_codex_without_a_config_folder_still_gets_the_profile(self):
        # Codex on PATH but never run: no CODEX_HOME yet (review on #26).
        import shutil
        shutil.rmtree(self.codex_home)
        self.fake_codex()
        result = self.setup("check")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^missing +Codex senior profile")
        given = Path(self.temp.name) / "plugin/wise-code"
        given.mkdir(parents=True)
        result = self.setup("apply", "--codex-plugin-root", str(given))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(json.dumps(str(given)) + ' = "read"',
                      self.profile.read_text(encoding="utf-8"))

    def test_legacy_sandbox_settings_block_the_profile(self):
        # Any loaded sandbox_mode or [sandbox_workspace_write] makes Codex ignore
        # default_permissions, so the senior profile would not apply (review on #26).
        self.setup("apply")
        cases = {self.codex_home / "config.toml": 'model = "x"\nsandbox_mode = "workspace-write"\n',
                 self.project / ".codex/config.toml": "[sandbox_workspace_write]\nnetwork_access = true\n"}
        for path, text in cases.items():
            with self.subTest(config=str(path)):
                path.parent.mkdir(exist_ok=True)
                path.write_text(text, encoding="utf-8")
                for command in ("check", "apply"):
                    result = self.setup(command)
                    self.assertEqual(result.returncode, 1, command)
                    self.assertRegex(result.stdout, r"(?m)^conflict +Codex senior profile")
                    self.assertIn(str(path), result.stdout)
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                path.unlink()

    def test_commented_legacy_key_is_not_a_conflict(self):
        (self.codex_home / "config.toml").write_text('# sandbox_mode = "read-only"\n',
                                                    encoding="utf-8")
        self.assertEqual(self.setup("apply").returncode, 0)

    def test_profile_with_non_bmp_plugin_path_is_valid_toml(self):
        # json.dumps escaped 🚀 as a surrogate pair, which TOML rejects (review on #26).
        given = Path(self.temp.name) / "plugin-🚀" / 'we"ird\\path'
        given.mkdir(parents=True)
        result = self.setup("apply", "--codex-plugin-root", str(given))
        self.assertEqual(result.returncode, 0, result.stdout)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("🚀", text)
        try:
            import tomllib
        except ImportError:  # Python < 3.11: no parser to check with
            self.skipTest("tomllib needs Python 3.11+")
        data = tomllib.loads(text)
        self.assertEqual(data["permissions"]["senior"]["filesystem"][str(given)], "read")

    def moved_plugin(self):
        new = Path(self.temp.name) / "plugins-v2/wise-code"
        (new / ".codex-plugin").mkdir(parents=True)
        return new

    def test_moved_plugin_regenerates_an_unedited_profile(self):
        # A marker-only check kept granting the old plugin folder (review on #26).
        self.setup("apply")
        new = self.moved_plugin()
        result = self.setup("check", "--codex-plugin-root", str(new))
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^missing +Codex senior profile")
        self.assertIn(str(self.codex_plugin), result.stdout)
        result = self.setup("apply", "--codex-plugin-root", str(new))
        self.assertEqual(result.returncode, 0, result.stdout)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn(json.dumps(str(new)) + ' = "read"', text)
        self.assertNotIn(json.dumps(str(self.codex_plugin)), text)
        self.assertEqual(self.setup("check", "--codex-plugin-root", str(new)).returncode, 0)

    def test_moved_plugin_with_an_edited_profile_is_a_conflict(self):
        self.setup("apply")
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write('"~/notes" = "read"\n')
        before = self.profile.read_bytes()
        result = self.setup("apply", "--codex-plugin-root", str(self.moved_plugin()))
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Codex senior profile")
        self.assertIn("show-codex", result.stdout)
        self.assertEqual(self.profile.read_bytes(), before)

    def test_an_untouched_profile_is_ok(self):
        self.setup("apply")
        result = self.setup("check")
        self.assertRegex(result.stdout, r"(?m)^ok +Codex senior profile")

    def weaken(self):
        text = self.profile.read_text(encoding="utf-8")
        self.profile.write_text(text.replace('":root" = "deny"', '":root" = "write"')
                                    .replace('"**/.env" = "deny"\n', ""), encoding="utf-8")

    def test_weakened_profile_blocks_until_accepted(self):
        # Only the plugin grant was checked, so ":root" = "write" read as ok
        # (review #33); then an edit passed with a one-off notice.
        self.setup("apply")
        self.weaken()
        before = self.profile.read_bytes()
        for command in ("check", "apply"):
            with self.subTest(command):
                result = self.setup(command)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertRegex(result.stdout, r"(?m)^edited +Codex senior profile")
                self.assertNotRegex(result.stdout, r"(?m)^ok +Codex senior profile")
                self.assertIn('removed [permissions.senior.filesystem] ":root" = "deny"',
                              result.stdout)
                self.assertIn('added [permissions.senior.filesystem] ":root" = "write"',
                              result.stdout)
                self.assertIn('removed [permissions.senior.filesystem.":workspace_roots"] '
                              '"**/.env" = "deny"', result.stdout)
                self.assertIn("accept-profile", result.stdout)
                # apply can't settle an edit, so check doesn't point to it.
                self.assertNotIn("run: python3", result.stdout)
                # The learner's edit is theirs: never rewritten.
                self.assertEqual(self.profile.read_bytes(), before)

    def test_accepted_edits_pass_but_are_never_ok(self):
        self.setup("apply")
        self.weaken()
        accept = self.setup("accept-profile")
        self.assertEqual(accept.returncode, 0, accept.stdout + accept.stderr)
        self.assertIn(':root" = "write"', accept.stdout)  # shows what was accepted
        result = self.setup("check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, r"(?m)^accepted +Codex senior profile")
        self.assertNotRegex(result.stdout, r"(?m)^ok +Codex senior profile")
        # A comment or blank line changes no setting: still accepted.
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write("\n# my note\n")
        self.assertEqual(self.setup("check").returncode, 0)

    def test_a_new_edit_after_acceptance_blocks_again(self):
        self.setup("apply")
        self.weaken()
        self.setup("accept-profile")
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write('"~/notes" = "read"\n')
        result = self.setup("check")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^edited +Codex senior profile")
        self.assertIn('"~/notes" = "read"', result.stdout)

    def test_restoring_the_generated_profile_is_ok_again(self):
        self.setup("apply")
        generated = self.profile.read_text(encoding="utf-8")
        self.weaken()
        self.setup("accept-profile")
        self.profile.write_text(generated, encoding="utf-8")
        self.assertRegex(self.setup("check").stdout, r"(?m)^ok +Codex senior profile")

    def test_nothing_to_accept_on_an_unedited_profile(self):
        self.setup("apply")
        result = self.setup("accept-profile")
        self.assertEqual(result.returncode, 0)
        self.assertIn("nothing to accept", result.stdout)
        self.assertEqual([p.name for p in self.codex_home.iterdir()
                          if p.name.endswith(".accepted")], [])

    def test_accept_refuses_a_profile_setup_did_not_write(self):
        self.setup("apply")
        self.profile.write_text('[permissions.senior]\n', encoding="utf-8")
        result = self.setup("accept-profile")
        self.assertEqual(result.returncode, 2)
        self.assertIn("wasn't written by setup", result.stderr)

    def test_symlinked_acceptance_is_refused_and_ignored(self):
        self.setup("apply")
        self.weaken()
        target = self.home / "elsewhere"
        (self.codex_home / "senior.config.toml.accepted").symlink_to(target)
        result = self.setup("accept-profile")
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(self.setup("check").returncode, 1)

    def test_edited_profile_without_a_detected_plugin_is_still_edited(self):
        self.setup("apply")
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write('"~/notes" = "read"\n')
        # The plugin isn't found under CODEX_HOME, but the granted folder exists.
        (self.codex_plugin / ".codex-plugin/plugin.json").unlink()
        result = self.setup("check")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^edited +Codex senior profile")
        self.assertIn('added [permissions.senior.network.domains] '
                      '"~/notes" = "read"', result.stdout)
        self.assertEqual(self.setup("accept-profile").returncode, 0)
        self.assertRegex(self.setup("check").stdout, r"(?m)^accepted +Codex senior profile")

    def test_granted_plugin_folder_gone_is_reported(self):
        import shutil
        self.setup("apply")
        shutil.rmtree(self.codex_home / "plugins")
        result = self.setup("check")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"(?m)^conflict +Codex senior profile")
        self.assertIn("--codex-plugin-root", result.stdout)

    def test_without_codex_installed_the_profile_is_not_applicable(self):
        import shutil
        shutil.rmtree(self.codex_home)
        result = self.setup("apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, r"(?m)^n/a +Codex senior profile")
        self.assertFalse(self.codex_home.exists())

    def test_undetected_plugin_needs_the_path_given(self):
        import shutil
        shutil.rmtree(self.codex_home / "plugins")
        result = self.setup("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--codex-plugin-root", result.stdout)
        self.assertFalse(self.profile.exists())
        given = Path(self.temp.name) / "elsewhere/wise-code"
        given.mkdir(parents=True)
        result = self.setup("apply", "--codex-plugin-root", str(given))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(json.dumps(str(given)) + ' = "read"',
                      self.profile.read_text(encoding="utf-8"))


class OnboardingGateTests(unittest.TestCase):
    def test_onboarding_runs_the_check_first_and_lets_the_learner_apply(self):
        text = (ROOT / "skills/learn/onboarding.md").read_text(encoding="utf-8")
        first_section = text.index("## Sandbox setup")
        self.assertLess(first_section, text.index("## Project"))
        for needed in ("scripts/setup.py\" check", "scripts/setup.py\" apply",
                       "Sandbox setup: skipped", "the learner runs"):
            self.assertIn(needed, text)


if __name__ == "__main__":
    unittest.main()
