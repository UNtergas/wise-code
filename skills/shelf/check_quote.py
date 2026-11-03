"""Check that a quote really appears in a shelf book, near the cited page.

Usage: check_quote.py <book file> <page|heading|-> "<quote>"

PDF pages are read with pdftotext (page, then the page before and after, since a
quote can cross a page break). A Markdown book takes the cited heading instead of
a page ("Summary", or "Two > Summary" when the title repeats) and is searched only
under it, subsections included; every occurrence of a repeated title is checked,
and FOUND prints the full heading path. NO_HEADING when the book has no such
heading. Plain text has no structure: pass "-" and it
is searched whole. Matching ignores case, whitespace, line-break hyphenation,
typographic quotes and dashes, and common ligatures.

A quote over MAX_WORDS words is refused as TOO_LONG before any search: the shelf
shows short hooks, never passages.

Exit 0: found (prints the page or heading). 1: MISSING, NO_HEADING or TOO_LONG. 2: the book can't be
read (LFS_POINTER when the file is a Git LFS pointer that was never downloaded).
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata


TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "−": "-", " ": " ", "­": "",
})


def normalize(text):
    # NFKC folds ligatures such as "ﬁ" into "fi".
    text = unicodedata.normalize("NFKC", text).translate(TRANSLATE)
    # Rejoin words hyphenated across a line break: "distri-\nbuted" -> "distributed".
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def pdf_page(path, page):
    """Return the text of one PDF page, or None when it doesn't exist."""
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-enc", "UTF-8", str(path), "-"],
        capture_output=True, timeout=60,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


MAX_WORDS = 25

LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer(path):
    """A checkout without Git LFS leaves a small text pointer in place of the book."""
    try:
        with path.open("rb") as stream:
            return stream.read(len(LFS_POINTER)) == LFS_POINTER
    except OSError:
        return False


HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
SETEXT_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")


def headings(lines):
    """Yield (title line, body start, level, title) for each ATX or Setext heading
    outside fenced code."""
    fence = None
    paragraph = None  # index of the last plain text line, if the paragraph is open
    for index, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            paragraph = None
            continue
        if fence is not None:
            continue
        atx = HEADING_RE.match(line)
        setext = SETEXT_RE.match(line)
        if atx:
            yield index, index + 1, len(atx.group(1)), atx.group(2)
            paragraph = None
        elif setext and paragraph is not None:
            # "Title\n===" is level 1, "Title\n---" level 2. Without a text line
            # just above, "---" is a thematic break.
            level = 1 if setext.group(1)[0] == "=" else 2
            yield paragraph, index + 1, level, lines[paragraph].strip()
            paragraph = None
        else:
            paragraph = index if line.strip() else None


def heading_blocks(text, location):
    """Yield (heading path, its text up to the next same-or-higher heading) for each
    heading whose path ends with `location` ("Title" or "Parent > Title")."""
    wanted = [normalize(part) for part in location.split(">")]
    lines = text.splitlines()
    found = list(headings(lines))
    parents = []  # (level, title) of the headings above the current one
    for position, (_, body, level, title) in enumerate(found):
        while parents and parents[-1][0] >= level:
            parents.pop()
        parents.append((level, title))
        path = [name for _, name in parents]
        if [normalize(name) for name in path[-len(wanted):]] != wanted:
            continue
        end = next((start for start, _, other, _ in found[position + 1:] if other <= level),
                   len(lines))
        yield " > ".join(path), "\n".join(lines[body:end])


def check_text(path, heading, needle):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "UNREADABLE", None
    if heading in ("", "-") or path.suffix.lower() != ".md":
        return ("FOUND" if needle in normalize(text) else "MISSING"), None
    status = "NO_HEADING"
    # A title can repeat ("Summary" in every chapter): check each occurrence.
    for where, block in heading_blocks(text, heading):
        if needle in normalize(block):
            return "FOUND", where
        status = "MISSING"
    return status, None


def check(path, page, quote, read_page=pdf_page):
    """Return (status, where): FOUND, MISSING, NO_HEADING, TOO_LONG, LFS_POINTER or
    UNREADABLE. `where` is the page for a PDF, the heading path ("Two > Summary") for
    Markdown, else None."""
    path = Path(path)
    needle = normalize(quote)
    if len(needle.split()) > MAX_WORDS:
        return "TOO_LONG", None
    if not needle or not path.is_file():
        return "UNREADABLE", None
    if is_lfs_pointer(path):
        return "LFS_POINTER", None
    if path.suffix.lower() != ".pdf":
        return check_text(path, str(page), needle)
    if read_page is pdf_page and shutil.which("pdftotext") is None:
        return "UNREADABLE", None
    page = int(page)
    pages = {}
    for number in (page, page - 1, page + 1):
        if number >= 1:
            pages[number] = read_page(path, number)
    if all(not (text or "").strip() for text in pages.values()):
        return "UNREADABLE", None  # no text layer (scanned) or bad page number
    for number in (page, page - 1, page + 1):
        if needle in normalize(pages.get(number) or ""):
            return "FOUND", number
    # A quote that crosses the page break.
    joined = normalize("\n".join(pages.get(n) or "" for n in sorted(pages)))
    if needle in joined:
        return "FOUND", page
    return "MISSING", None


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2])
        return 2
    _, path, page, quote = argv
    if Path(path).suffix.lower() == ".pdf" and not page.isdigit():
        print("UNREADABLE: a PDF needs a page number")
        return 2
    status, found = check(path, page, quote)
    where = "" if found is None else (f" § {found}" if isinstance(found, str) else f" p. {found}")
    print(status + where)
    return {"FOUND": 0, "MISSING": 1, "NO_HEADING": 1, "TOO_LONG": 1}.get(status, 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
