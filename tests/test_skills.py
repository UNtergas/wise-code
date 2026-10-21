"""Check that every skill is wired consistently and that guide links resolve."""

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir())
# Skills Claude may start on its own from their description; every other skill
# runs only when the learner invokes it.
MODEL_INVOKED = {"grill", "research"}
FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields


class SkillLayoutTests(unittest.TestCase):
    def test_expected_skills_exist(self):
        names = {path.name for path in SKILLS}
        expected = {"learn", "level", "reset", "teach", "quiz",
                    "explore", "correct", "reflect", "sharpen", "critique",
                    "grill", "grill-with-docs", "research"}
        self.assertTrue(expected <= names, expected - names)

    def test_each_skill_has_frontmatter_codex_notes_and_agent_policy(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                fields = frontmatter(skill / "SKILL.md")
                self.assertEqual(fields.get("name"), skill.name)
                self.assertTrue(fields.get("description"))
                self.assertTrue((skill / "codex.md").is_file())
                agent = (skill / "agents/openai.yaml").read_text(encoding="utf-8")
                if skill.name in MODEL_INVOKED:
                    self.assertNotIn("disable-model-invocation", fields)
                    self.assertIn("allow_implicit_invocation: true", agent)
                else:
                    # Learning commands run only when the learner asks for them.
                    self.assertEqual(fields.get("disable-model-invocation"), "true")
                    self.assertIn("allow_implicit_invocation: false", agent)

    def test_relative_links_in_guides_resolve(self):
        for guide in sorted((ROOT / "skills").rglob("*.md")):
            # Links inside code fences are format examples, not real references.
            text = FENCE.sub("", guide.read_text(encoding="utf-8"))
            for target in LINK.findall(text):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                with self.subTest(guide=str(guide.relative_to(ROOT)), link=target):
                    self.assertTrue((guide.parent / target.split("#")[0]).exists())

    def test_readme_lists_every_command(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                self.assertIn(f"/wise-code:{skill.name}", readme)

    def test_plugin_manifests_share_one_version(self):
        claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(claude["version"], codex["version"])


class SharedPluginTests(unittest.TestCase):
    """The plugin is shared by every project, so it must not ship learner data."""

    def test_plugin_contains_no_learning_state(self):
        state_names = {"profile.md", "progress.md", "project-map.md", "qa-history.md",
                       "questions.md", "cards.tsv", "guardrails.md", "reflections.md",
                       "plugin-feedback.md", "MISSION.md"}
        found = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*")
                 if ".git" not in path.parts and path.name in state_names]
        self.assertEqual(found, [])
        self.assertFalse((ROOT / ".wise-code").exists())

    def test_teach_and_quiz_use_the_project_state_directory(self):
        for name in ("teach", "quiz"):
            with self.subTest(skill=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(".wise-code/", text)
                self.assertIn("Git root", text)

    def test_materials_guide_defines_every_material(self):
        text = (ROOT / "skills/learn/materials.md").read_text(encoding="utf-8")
        for heading in ("## qa-history.md", "## questions.md", "## cards.tsv",
                        "## guardrails.md", "## reflections.md", "## plugin-feedback.md"):
            self.assertIn(heading, text)
        self.assertIn("#separator:Tab", text)
        self.assertIn("#tags column:3", text)

    def test_reset_keeps_every_material(self):
        materials = (ROOT / "skills/learn/materials.md").read_text(encoding="utf-8")
        reset = (ROOT / "skills/reset/SKILL.md").read_text(encoding="utf-8")
        for name in re.findall(r"^## ([\w-]+\.(?:md|tsv))$", materials, re.MULTILINE):
            with self.subTest(material=name):
                self.assertIn(f"`{name}`", reset)


class LearnerFirstTests(unittest.TestCase):
    """Borrowed skills must keep the learner doing the work."""

    def test_principles_are_named_not_applied(self):
        text = (ROOT / "skills/learn/principles.md").read_text(encoding="utf-8")
        self.assertIn("Name, don't apply", text)
        self.assertIn("## Checking a number", text)
        # Autonomy principles conflict with learner-owned decisions.
        self.assertIn("*Never block on the human*", text.split("## Not included")[1])

    def test_learner_acts_before_claude_answers(self):
        cues = {
            "explore": "Prediction first",
            "reflect": "The learner writes first",
            "correct": "Ask the learner first",
            "sharpen": "Ask the learner to rewrite the task",
            "critique": "never rewrites the",
        }
        for name, cue in cues.items():
            with self.subTest(skill=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(cue, text)

    def test_grills_hold_back_recommendations_in_learning_mode(self):
        for name in ("grill", "grill-with-docs"):
            with self.subTest(skill=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                section = text.split("## Learning mode")[1]
                self.assertIn("Learner answers first", section)
                self.assertIn("Learning mode: active", section)
        adr_rule = (ROOT / "skills/grill-with-docs/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("The learner writes the ADR", adr_rule)

    def test_reflect_never_edits_the_installed_plugin(self):
        text = (ROOT / "skills/reflect/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never edit the installed", text)
        self.assertIn("plugin-feedback.md", text)

    def test_borrowed_material_is_attributed(self):
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 Lauren Tan", notices)
        for path in ("skills/learn/principles.md", "skills/explore/",
                     "skills/correct/", "skills/reflect/", "skills/sharpen/",
                     "skills/critique/writing-rubric.md"):
            with self.subTest(path=path):
                self.assertIn(path, notices)
                self.assertTrue((ROOT / path).exists())


class MarketplaceTests(unittest.TestCase):
    """One marketplace ships wise-code and standalone plugins people install alone."""

    def test_claude_marketplace_entries_point_at_matching_plugins(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        names = [entry["name"] for entry in market["plugins"]]
        self.assertEqual(sorted(names), ["wise-code", "wise-research"])
        for entry in market["plugins"]:
            with self.subTest(plugin=entry["name"]):
                self.assertNotIn("..", entry["source"])
                manifest = ROOT / entry["source"] / ".claude-plugin/plugin.json"
                # The install id uses the entry name, skills use the manifest name.
                self.assertEqual(json.loads(manifest.read_text())["name"], entry["name"])

    def test_codex_marketplace_paths_exist(self):
        market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        for entry in market["plugins"]:
            with self.subTest(plugin=entry["name"]):
                path = ROOT / entry["source"]["path"]
                self.assertTrue((path / ".codex-plugin/plugin.json").is_file())

    def test_standalone_copies_match_their_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_standalone.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_standalone_research_ships_nothing_else(self):
        skills = ROOT / "plugins/wise-research/skills"
        self.assertEqual(sorted(p.name for p in skills.iterdir()), ["research"])
        text = (skills / "research/SKILL.md").read_text(encoding="utf-8")
        # A friend installs this without wise-code: it must not depend on its guides.
        self.assertNotIn("../learn/", text)
        self.assertNotIn(".wise-code", text)


if __name__ == "__main__":
    unittest.main()
