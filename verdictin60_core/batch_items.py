"""Multi-URL input parsing for the Batch tab's "Add Videos" workflow (issue #77).

- parse_pasted_urls: one URL per line, from the Add Videos dialog's textarea.
- parse_url_list_file: a .txt (one URL per line) or .csv (URL in the first
  column) list imported from disk.
"""
import csv
import re
from pathlib import Path

_URL_RE = re.compile(r'^https?://\S+$', re.IGNORECASE)


def parse_pasted_urls(text: str) -> list:
    """Extract well-formed http(s) URLs, one per line, de-duplicated while
    preserving first-seen order. Blank lines and non-URL lines are ignored."""
    seen = set()
    urls = []
    for line in (text or "").splitlines():
        url = line.strip()
        if url and _URL_RE.match(url) and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_url_list_file(path: Path) -> list:
    """Read a .txt (one URL per line) or .csv (URL in the first column,
    header row optional) list of URLs."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        lines = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if row:
                    lines.append(row[0])
        return parse_pasted_urls("\n".join(lines))
    return parse_pasted_urls(path.read_text(encoding="utf-8-sig"))
