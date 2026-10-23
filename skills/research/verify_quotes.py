"""Check that every quoted span in a research file appears verbatim at its source.

Usage:
    python3 verify_quotes.py research/2026-10-23-some-question.md [--json]

The research file's Evidence lines carry one short verbatim span in «guillemets»
followed by the Markdown link it was copied from:

    - **Claim** — paraphrase. «exact words from the page» [Title, v2](https://...)

For each span we fetch the linked page, strip it to visible text, normalize
whitespace, case and typographic punctuation, then look for the span. A citation
proves nothing if the cited page doesn't contain the words, so a missing span is
a failure, not a warning.

Exit codes:
    0  every span found
    1  at least one span MISSING, TOO_LONG, or an Evidence line without a span
    2  no failures, but some pages UNREACHABLE (check those by hand)
"""

import argparse
from html.parser import HTMLParser
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request


MAX_WORDS = 15  # Short spans keep quoting within fair, minimal reproduction.
TIMEOUT = 20
USER_AGENT = "wise-code-verify-quotes/1.0 (+https://github.com/UNtergas/wise-code)"

EVIDENCE_HEADING = re.compile(r"^##\s+Evidence\s*$", re.IGNORECASE)
NEXT_HEADING = re.compile(r"^##\s+")
SPAN = re.compile(r"«([^»]+)»\s*\[[^\]]*\]\((https?://[^)\s]+)\)")
BULLET = re.compile(r"^\s*[-*]\s+")


class _TextExtractor(HTMLParser):
    """Collect visible text; skip script, style and other non-content tags."""

    SKIP = {"script", "style", "noscript", "template", "svg", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def html_to_text(html):
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return " ".join(parser.parts)


_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "−": "-", " ": " ", " ": " ",
    " ": " ", "​": None, "‌": None, "‍": None,
    "﻿": None, "­": None,
})


def normalize(text):
    """Make matching robust to rendering noise, never to different words."""
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT)
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_evidence(markdown):
    """Return (line_number, span, url) for spans, and line numbers lacking one."""
    spans, missing = [], []
    in_evidence = False
    for number, line in enumerate(markdown.splitlines(), start=1):
        if EVIDENCE_HEADING.match(line):
            in_evidence = True
            continue
        if in_evidence and NEXT_HEADING.match(line):
            in_evidence = False
        if not in_evidence or not BULLET.match(line):
            continue
        found = SPAN.findall(line)
        if not found:
            missing.append(number)
        for span, url in found:
            spans.append((number, span.strip(), url))
    return spans, missing


def fetch_text(url):
    """Fetch a page as visible text. Raises on network or non-text responses."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        kind = response.headers.get_content_type()
        if not (kind.startswith("text/") or kind in ("application/xhtml+xml",
                                                     "application/json")):
            raise ValueError(f"unsupported content type {kind}")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(10_000_000).decode(charset, errors="replace")
    return html_to_text(body) if "html" in kind else body


def verify(markdown, fetch=fetch_text):
    """Check every span. `fetch` is injectable so tests run offline."""
    spans, missing = parse_evidence(markdown)
    results = [{"line": n, "status": "NO_SPAN", "span": "", "url": "",
                "detail": "Evidence line has no «verbatim span» [link](url)"}
               for n in missing]
    pages = {}
    for line, span, url in spans:
        result = {"line": line, "span": span, "url": url, "detail": ""}
        words = len(span.split())
        if words > MAX_WORDS:
            result.update(status="TOO_LONG",
                          detail=f"{words} words; keep spans at {MAX_WORDS} or fewer")
            results.append(result)
            continue
        if url not in pages:
            try:
                pages[url] = normalize(fetch(url))
            except (urllib.error.URLError, OSError, ValueError, UnicodeError) as error:
                pages[url] = error
        page = pages[url]
        if isinstance(page, Exception):
            result.update(status="UNREACHABLE", detail=str(page))
        elif normalize(span) in page:
            result["status"] = "FOUND"
        else:
            result.update(status="MISSING", detail="span not on the fetched page")
        results.append(result)
    return sorted(results, key=lambda r: r["line"])


def exit_code(results):
    statuses = {r["status"] for r in results}
    if statuses & {"MISSING", "TOO_LONG", "NO_SPAN"}:
        return 1
    if "UNREACHABLE" in statuses:
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", help="research Markdown file to check")
    parser.add_argument("--json", action="store_true", help="print JSON results")
    args = parser.parse_args(argv)
    with open(args.file, encoding="utf-8") as stream:
        results = verify(stream.read())
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        if not results:
            print("No Evidence lines found.")
        for r in results:
            print(f"{r['status']:<11} line {r['line']:<4} {r['url']}")
            if r["span"]:
                print(f"            «{r['span']}»")
            if r["detail"]:
                print(f"            {r['detail']}")
    code = exit_code(results) if results else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
