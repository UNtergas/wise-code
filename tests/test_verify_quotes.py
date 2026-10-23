"""Exercise the research span checker offline with fake pages."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/research/verify_quotes.py"
spec = importlib.util.spec_from_file_location("verify_quotes", SCRIPT)
vq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vq)

PAGE = """<html><head><title>Docs</title><script>var hidden = "secret span";</script>
<style>.x{}</style></head><body><h1>Auth</h1>
<p>Tokens expire after&nbsp;<b>15 minutes</b> by default.</p>
<p>Use the “refresh” endpoint — never store secrets.</p></body></html>"""


def research(*bullets, extra=""):
    return ("# Q\n\n## Answer\nTokens expire. «not checked here» [x](https://a.test)\n\n"
            "## Evidence\n" + "\n".join(bullets) + "\n\n## Conflicts & gaps\n- none\n"
            + extra)


def fake_fetch(pages):
    def fetch(url):
        if url not in pages:
            raise OSError("connection refused")
        return vq.html_to_text(pages[url])
    return fetch


class VerifyQuotesTests(unittest.TestCase):
    def check(self, markdown, pages=None):
        return vq.verify(markdown, fetch=fake_fetch(pages or {"https://docs.test/auth": PAGE}))

    def test_span_found_across_tags_entities_and_case(self):
        results = self.check(research(
            "- **Expiry** — default lifetime. «tokens expire after 15 minutes» "
            "[Auth docs](https://docs.test/auth)"))
        self.assertEqual([r["status"] for r in results], ["FOUND"])
        self.assertEqual(vq.exit_code(results), 0)

    def test_typographic_quotes_and_dashes_normalize(self):
        results = self.check(research(
            '- **Refresh** — use it. «Use the "refresh" endpoint - never store secrets» '
            "[Auth docs](https://docs.test/auth)"))
        self.assertEqual(results[0]["status"], "FOUND")

    def test_invented_or_altered_span_is_missing(self):
        results = self.check(research(
            "- **Expiry** — x. «tokens expire after 30 minutes» [Auth](https://docs.test/auth)"))
        self.assertEqual(results[0]["status"], "MISSING")
        self.assertEqual(vq.exit_code(results), 1)

    def test_script_and_style_text_does_not_count(self):
        results = self.check(research(
            "- **Hidden** — x. «secret span» [Auth](https://docs.test/auth)"))
        self.assertEqual(results[0]["status"], "MISSING")

    def test_span_from_another_page_fails(self):
        pages = {"https://docs.test/auth": PAGE,
                 "https://docs.test/other": "<p>Nothing about tokens.</p>"}
        results = self.check(research(
            "- **Expiry** — x. «tokens expire after 15 minutes» [Other](https://docs.test/other)"),
            pages)
        self.assertEqual(results[0]["status"], "MISSING")

    def test_long_span_is_rejected_before_fetching(self):
        long_span = " ".join(["word"] * 16)
        results = vq.verify(research(f"- **C** — x. «{long_span}» [A](https://docs.test/auth)"),
                            fetch=lambda url: self.fail("should not fetch"))
        self.assertEqual(results[0]["status"], "TOO_LONG")

    def test_evidence_bullet_without_span_fails(self):
        results = self.check(research("- **Expiry** — paraphrase only. [Auth](https://docs.test/auth)"))
        self.assertEqual(results[0]["status"], "NO_SPAN")
        self.assertEqual(vq.exit_code(results), 1)

    def test_unreachable_page_is_exit_two_not_pass(self):
        results = self.check(research(
            "- **C** — x. «anything» [Down](https://down.test/page)"))
        self.assertEqual(results[0]["status"], "UNREACHABLE")
        self.assertEqual(vq.exit_code(results), 2)

    def test_only_evidence_section_is_parsed_and_pages_fetched_once(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return vq.html_to_text(PAGE)
        markdown = research(
            "- **A** — x. «tokens expire after» [Auth](https://docs.test/auth)",
            "- **B** — y. «by default» [Auth](https://docs.test/auth)")
        results = vq.verify(markdown, fetch=fetch)
        self.assertEqual([r["status"] for r in results], ["FOUND", "FOUND"])
        self.assertEqual(calls, ["https://docs.test/auth"])  # Answer span ignored, one fetch

    def test_cli_with_no_evidence_exits_one(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as stream:
            stream.write("# Q\n\n## Answer\nNothing.\n")
        self.addCleanup(Path(stream.name).unlink)
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), stream.name],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("No Evidence lines found", result.stdout)


if __name__ == "__main__":
    unittest.main()
