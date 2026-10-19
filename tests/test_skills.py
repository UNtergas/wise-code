"""Check that every skill is wired consistently and that guide links resolve."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir())
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
        self.assertTrue({"learn", "level", "reset", "teach", "quiz"} <= names, names)

    def test_each_skill_has_frontmatter_codex_notes_and_agent_policy(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                fields = frontmatter(skill / "SKILL.md")
                self.assertEqual(fields.get("name"), skill.name)
                self.assertTrue(fields.get("description"))
                # Learning commands run only when the learner asks for them.
                self.assertEqual(fields.get("disable-model-invocation"), "true")
                self.assertTrue((skill / "codex.md").is_file())
                agent = (skill / "agents/openai.yaml").read_text(encoding="utf-8")
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
                       "questions.md", "cards.tsv", "MISSION.md"}
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
        for heading in ("## qa-history.md", "## questions.md", "## cards.tsv"):
            self.assertIn(heading, text)
        self.assertIn("#separator:Tab", text)
        self.assertIn("#tags column:3", text)


if __name__ == "__main__":
    unittest.main()
