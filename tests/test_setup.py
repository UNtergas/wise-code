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
        self.project = base / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.settings = self.project / ".claude/settings.local.json"
        self.profile = self.codex_home / "senior.config.toml"
        self.codex_plugin = self.codex_home / "plugins/cache/wise-code"
        (self.codex_plugin / ".codex-plugin").mkdir(parents=True)
        (self.codex_plugin / ".codex-plugin/plugin.json").write_text(
            json.dumps({"name": "wise-code"}), encoding="utf-8")

    def setup(self, *args, cwd=None):
        env = {"PATH": str(self.bin), "HOME": str(self.home),
               "CODEX_HOME": str(self.codex_home)}
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

    def test_every_shell_denied_path_is_also_denied_to_the_read_tool(self):
        # The Read tool runs outside the shell sandbox (review on #26).
        self.assertEqual(self.setup("apply").returncode, 0)
        settings = self.claude()
        deny = settings["permissions"]["deny"]
        for path in settings["sandbox"]["filesystem"]["denyRead"]:
            self.assertIn(f"Read({path}/**)", deny)

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
