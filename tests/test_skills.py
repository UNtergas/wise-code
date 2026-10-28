"""Check that every skill is wired consistently and that guide links resolve."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir())
# Skills Claude may start on its own from their description; every other skill
# runs only when the learner invokes it.
MODEL_INVOKED = {"grill", "research", "shelf"}
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
                    "grill", "grill-with-docs", "research", "shelf"}
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
            "shelf": "Read first: the learner reads the section before you explain it.",
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

    def test_grill_only_suggests_itself_when_not_asked(self):
        path = ROOT / "skills/grill/SKILL.md"
        description = frontmatter(path)["description"]
        self.assertIn("only suggest running /wise-code:grill, never grill unasked", description)
        text = path.read_text(encoding="utf-8")
        # The decision comes before any grilling rule, so it is read first.
        self.assertLess(text.index("## First: did the user ask for a grill?"),
                        text.index("## Grilling"))
        section = text.split("## First: did the user ask for a grill?")[1].split("\n## ")[0]
        self.assertIn("Don't grill.", section)
        self.assertIn("at most once per plan", section)

    def test_delegated_steps_name_a_cheaper_model(self):
        # Self-contained sub-steps run on a cheaper model; the main session keeps
        # its model and prompt cache. Hints live in the body, not frontmatter,
        # because claude.ai skill uploads reject Claude Code-only keys.
        expected = {"research": "model: sonnet", "explore": "model: sonnet",
                    "grill": "model: haiku", "teach": "model: sonnet",
                    "shelf": "model: sonnet"}
        for skill, hint in expected.items():
            with self.subTest(skill=skill):
                path = ROOT / f"skills/{skill}/SKILL.md"
                self.assertIn(hint, path.read_text(encoding="utf-8"))
                self.assertIn("Ignore `model:` hints",
                              (ROOT / f"skills/{skill}/codex.md").read_text(encoding="utf-8"))
        for skill in SKILLS:
            with self.subTest(frontmatter=skill.name):
                fields = frontmatter(skill / "SKILL.md")
                self.assertFalse({"model", "context", "agent", "effort"} & fields.keys())
        self.assertIn("Do not switch to a subagent",
                      (ROOT / "skills/learn/SKILL.md").read_text(encoding="utf-8"))

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


class CanaryTests(unittest.TestCase):
    """Every skill and the restore hook state the same exact reply markers."""

    START = "=====> ah0y_sir <name>"
    END = "<===== f1n"

    def test_every_skill_states_both_markers_on_their_own_lines(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                lines = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
                self.assertIn("## Canary", lines)
                self.assertIn(self.START, lines)
                self.assertIn(self.END, lines)
                self.assertIn("What's your name?", "\n".join(lines))
                self.assertIn("never store it", "\n".join(lines))

    def test_hook_uses_the_same_markers(self):
        hook = (ROOT / "hooks/session_start.py").read_text(encoding="utf-8")
        self.assertIn('CANARY_START = "=====> ah0y_sir"', hook)
        self.assertIn(f'CANARY_END = "{self.END}"', hook)


class SessionRecapTests(unittest.TestCase):
    """Sessions end with an evidence-backed recap; the next one opens with a check."""

    def test_learn_defines_start_check_and_session_end(self):
        text = (ROOT / "skills/learn/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Start check", text)
        self.assertIn("## Session end", text)
        self.assertIn("AskUserQuestion", text)
        self.assertIn("Don't show the recap yet", text)
        self.assertIn("Start check: pending", text)

    def test_recap_format_and_source_are_documented(self):
        text = (ROOT / "skills/learn/materials.md").read_text(encoding="utf-8")
        self.assertIn("## session-recap.md", text)
        self.assertIn("Check points:", text)
        self.assertIn("`start-check`", text)

    def test_reflect_recaps_only_after_the_learner_writes(self):
        text = (ROOT / "skills/reflect/SKILL.md").read_text(encoding="utf-8")
        self.assertLess(text.index("## 2. The learner writes first"),
                        text.index("## 5. Session recap"))


class ResearchSpanTests(unittest.TestCase):
    def test_research_format_requires_a_span_and_runs_the_checker(self):
        text = (ROOT / "skills/research/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("«{exact span copied from the page}» [", text)
        self.assertIn("skills/research/verify_quotes.py", text)
        self.assertIn("Copy, never recall", text)
        self.assertTrue((ROOT / "skills/research/verify_quotes.py").is_file())


class ShelfTests(unittest.TestCase):
    """The shelf is opt-in, bounded to mapped folders, and pushes every record."""

    def text(self):
        return (ROOT / "skills/shelf/SKILL.md").read_text(encoding="utf-8")

    def test_gate_comes_first_and_is_silent(self):
        text = self.text()
        self.assertLess(text.index("## Step 0: Gate"), text.index("## Step 1: Sync"))
        gate = text.split("## Step 0: Gate")[1].split("\n## ")[0]
        self.assertIn("**never create**", gate)
        self.assertIn("Say nothing about the shelf", gate)
        description = frontmatter(ROOT / "skills/shelf/SKILL.md")["description"]
        self.assertIn("stop silently if it is missing", description)

    def test_unreachable_shelf_links_the_setup_guide(self):
        guide = ROOT / "docs/shelf-setup.md"
        self.assertTrue(guide.is_file())
        self.assertIn("https://github.com/UNtergas/wise-code/blob/main/docs/shelf-setup.md",
                      self.text())
        self.assertIn("not reachable", self.text())
        self.assertIn("not reachable", guide.read_text(encoding="utf-8"))
        self.assertIn("docs/shelf-setup.md", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_scope_is_shared_plus_mapped_folders_via_sparse_clone(self):
        text = self.text()
        self.assertIn("`shared` is always in scope", text)
        self.assertIn("sparse-checkout set .wise-code shared <Folders...>", text)
        self.assertIn("lists `shelf-repo/`", text)

    def test_every_cite_and_explanation_is_pushed(self):
        text = self.text()
        self.assertIn("## Step 5: Record and push (after every cite and every explanation)", text)
        self.assertIn("git -C <shelf> pull --rebase --quiet\ngit -C <shelf> push --quiet", text)
        self.assertIn("No `cd`, no `&&` chains", text)
        self.assertIn("citations/<Project>.md", text)

    def test_quotes_are_checked_and_capped(self):
        text = self.text()
        self.assertIn("skills/shelf/check_quote.py", text)
        self.assertIn("at most 2", text)
        self.assertTrue((ROOT / "skills/shelf/check_quote.py").is_file())

    def test_lfs_books_are_pulled_for_mapped_folders_only(self):
        text = self.text()
        self.assertIn("lfs install --local", text)
        self.assertIn('--include="shared/**,<folder>/**"', text)
        self.assertIn('git -C "<shelf>" lfs pull', text)
        self.assertIn("LFS_POINTER", text)
        guide = (ROOT / "docs/shelf-setup.md").read_text(encoding="utf-8")
        self.assertIn("git lfs track", guide)

    def test_shelf_mode_syncs_and_pulls_every_folder(self):
        text = self.text()
        section = text[text.index("### Shelf mode"):text.index("### Git LFS step")]
        self.assertIn('git -C "<shelf>" pull --rebase --quiet', section)
        self.assertIn("without `--include`", section)
        self.assertIn("never force or reset", section)

    def test_lfs_install_prompt_covers_both_cases_and_never_installs(self):
        text = self.text()
        section = text[text.index("### Prompt to install LFS"):text.index("## Step 2")]
        self.assertIn("**LFS needed, not installed:**", section)
        self.assertIn("**Big PDFs without LFS:**", section)
        self.assertIn('-size +50M', section)
        self.assertIn("header `Git LFS`", section)
        self.assertIn("LFS prompt: off", section)
        self.assertIn("Don't run the install yourself", section)
        self.assertIn("the learner runs that themselves, never you", section)

    def test_reset_keeps_shelf(self):
        reset = (ROOT / "skills/reset/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`shelf.md`", reset)
        self.assertIn("`shelf-repo/`", reset)


class SinglePluginTests(unittest.TestCase):
    """The repository is exactly one plugin; claude.ai syncs it as a whole."""

    def test_marketplaces_list_only_this_plugin_at_the_root(self):
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual([(e["name"], e["source"]) for e in claude["plugins"]],
                         [("wise-code", "./")])
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual([(e["name"], e["source"]["path"]) for e in codex["plugins"]],
                         [("wise-code", "./")])

    def test_no_nested_plugin_manifest(self):
        # claude.ai sync fails with "plugin.json must be at .claude-plugin/plugin.json
        # at the plugin root" when another plugin.json sits below the root.
        found = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("plugin.json")
                       if ".git" not in p.parts)
        self.assertEqual(found, [".claude-plugin/plugin.json", ".codex-plugin/plugin.json"])


if __name__ == "__main__":
    unittest.main()
