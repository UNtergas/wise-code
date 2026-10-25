"""Check that a quote really appears in a shelf book, near the cited page.

Usage: check_quote.py <book file> <page|-> "<quote>"

PDF pages are read with pdftotext (page, then the page before and after, since a
quote can cross a page break). Markdown and text files are searched whole; pass
"-" as the page. Matching ignores case, whitespace, line-break hyphenation,
typographic quotes and dashes, and common ligatures.

Exit 0: found (prints the page). 1: not found. 2: the book can't be read
(LFS_POINTER when the file is a Git LFS pointer that was never downloaded).
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


LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer(path):
    """A checkout without Git LFS leaves a small text pointer in place of the book."""
    try:
        with path.open("rb") as stream:
            return stream.read(len(LFS_POINTER)) == LFS_POINTER
    except OSError:
        return False


def check(path, page, quote, read_page=pdf_page):
    """Return (status, page). status is FOUND, MISSING, LFS_POINTER or UNREADABLE."""
    path = Path(path)
    needle = normalize(quote)
    if not needle or not path.is_file():
        return "UNREADABLE", None
    if is_lfs_pointer(path):
        return "LFS_POINTER", None
    if path.suffix.lower() != ".pdf":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "UNREADABLE", None
        return ("FOUND" if needle in normalize(text) else "MISSING"), None
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
    print(status if found is None else f"{status} p. {found}")
    return {"FOUND": 0, "MISSING": 1}.get(status, 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
