"""Exercise the shelf quote checker without real PDFs."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/shelf/check_quote.py"
spec = importlib.util.spec_from_file_location("check_quote", SCRIPT)
cq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cq)

PAGES = {
    6: "Chapter 1\nReliability means the system con-\ntinues to work correctly",
    7: "even when things go wrong. A fault is not the same as a ﬁailure.",
    8: "The “tail latency” of requests — the slowest ones — matters most.",
}


def reader(path, page):
    return PAGES.get(page, "")


class CheckQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pdf = Path(self.temp.name) / "book.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake")

    def check(self, page, quote):
        return cq.check(self.pdf, page, quote, read_page=reader)

    def test_found_on_cited_page_with_hyphenation_and_case(self):
        self.assertEqual(self.check(6, "the system continues to work"), ("FOUND", 6))

    def test_found_on_neighbour_page_reports_real_page(self):
        self.assertEqual(self.check(7, "Reliability means the system"), ("FOUND", 6))

    def test_quote_across_page_break(self):
        self.assertEqual(self.check(7, "continues to work correctly even when things"),
                         ("FOUND", 7))

    def test_typographic_quotes_dashes_and_ligatures_normalize(self):
        self.assertEqual(self.check(8, 'The "tail latency" of requests - the slowest'),
                         ("FOUND", 8))
        self.assertEqual(self.check(7, "not the same as a fiailure"), ("FOUND", 7))

    def test_altered_quote_is_missing(self):
        self.assertEqual(self.check(7, "a fault is the same as a failure"), ("MISSING", None))

    def test_page_without_text_nearby_is_unreadable(self):
        self.assertEqual(self.check(20, "tail latency"), ("UNREADABLE", None))

    def test_text_layer_missing_is_unreadable(self):
        status = cq.check(self.pdf, 6, "anything", read_page=lambda p, n: "  \n")
        self.assertEqual(status, ("UNREADABLE", None))

    def test_markdown_book_is_searched_whole(self):
        book = Path(self.temp.name) / "notes.md"
        book.write_text("# Notes\n\nBackoff spreads   retries\nover time.\n", encoding="utf-8")
        self.assertEqual(cq.check(book, "-", "backoff spreads retries over time"),
                         ("FOUND", None))
        self.assertEqual(cq.check(book, "-", "backoff stops retries"), ("MISSING", None))

    def test_cli_exit_codes(self):
        book = Path(self.temp.name) / "notes.txt"
        book.write_text("Idempotent requests can be retried safely.", encoding="utf-8")
        run = lambda *args: subprocess.run([sys.executable, "-I", str(SCRIPT), *args],
                                           capture_output=True, text=True, timeout=10)
        self.assertEqual(run(str(book), "-", "retried safely").returncode, 0)
        self.assertEqual(run(str(book), "-", "never retried").returncode, 1)
        self.assertEqual(run(str(self.pdf), "-", "x").returncode, 2)
        self.assertEqual(run(str(book)).returncode, 2)

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_real_pdf_when_poppler_available(self):
        try:
            from reportlab.pdfgen import canvas  # noqa: optional dependency
        except ImportError:
            self.skipTest("reportlab not installed")
        pdf = Path(self.temp.name) / "real.pdf"
        page = canvas.Canvas(str(pdf))
        page.drawString(72, 720, "First page text.")
        page.showPage()
        page.drawString(72, 720, "Backpressure slows the producer down.")
        page.showPage()
        page.save()
        self.assertEqual(cq.check(pdf, 2, "backpressure slows the producer"), ("FOUND", 2))


if __name__ == "__main__":
    unittest.main()
