#!/usr/bin/env python3
"""Download the example corpus into data/raw/.

This is not part of Verifera. The system ingests whatever it finds in data/raw/
and has no idea where it came from; this script exists only because the
documents behind the published benchmark are large public files that do not
belong in a git repository. Your own corpus needs nothing like it — copy your
files into data/raw/ and run `make ingest`.

Standard library only, so it runs on a bare `python3` with nothing installed:

    python3 example/fetch.py              fetch what is missing
    python3 example/fetch.py --force      re-download everything
"""

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(__file__).resolve().parent / "sources.txt"
RAW_DIR = ROOT / "data" / "raw"
OBJECTS_DIR = ROOT / "data" / "objects"

USER_AGENT = "verifera-example-fetch/1.0"
TIMEOUT_S = 90
# Courtesy delay between requests; these are public institutional servers.
DELAY_S = 0.5

# Cellar picks the format from Accept. xhtml has to come first: it carries the
# same text as the web page without the portal's chrome, and asking for
# text/html alone gets a 404. Servers that just hand back a file ignore all this.
ACCEPT = {
    ".html": "application/xhtml+xml, text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# A response can be successful and still be worthless: a bot challenge answers
# 202 with an empty body, and a content-negotiation miss answers 200 with a
# one-line explanation. Writing either produces a file that only fails later,
# during ingestion, far from the cause.
MIN_BYTES = 4096
MAGIC = {".pdf": b"%PDF"}


def sources() -> list[tuple[str, str, str]]:
    """(filename, url, language) for every non-comment line of sources.txt."""
    entries = []
    for number, line in enumerate(SOURCES.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) not in (2, 3):
            raise SystemExit(
                f"{SOURCES}:{number}: expected '<filename> <url> [language]', got {line!r}"
            )
        entries.append((parts[0], parts[1], parts[2] if len(parts) == 3 else "eng"))
    return entries


def rejected(data: bytes, suffix: str) -> str | None:
    """Why this response is not the document, or None if it looks like one."""
    if len(data) < MIN_BYTES:
        return f"{len(data)} bytes — probably a challenge or an error page"
    magic = MAGIC.get(suffix)
    if magic and not data.startswith(magic):
        return f"does not start with {magic.decode()}"
    if suffix == ".html" and b"<" not in data[:2048]:
        return "does not look like markup"
    return None


def download(url: str, suffix: str, language: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT.get(suffix, "*/*"),
            "Accept-Language": language,
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read()


def main() -> int:
    force = "--force" in sys.argv[1:]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fetched, skipped, failed = 0, 0, 0
    for index, (filename, url, language) in enumerate(sources()):
        target = RAW_DIR / filename
        # An ingested document has moved on to the object store and its name is
        # no longer in the inbox. Downloading it again would only queue an
        # identical re-ingest, so both places count as "already here".
        if not force and (target.exists() or (OBJECTS_DIR / filename).exists()):
            skipped += 1
            continue
        if index:
            time.sleep(DELAY_S)
        try:
            data = download(url, target.suffix.lower(), language)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"FAIL {filename}: {error}")
            failed += 1
            continue
        if problem := rejected(data, target.suffix.lower()):
            print(f"FAIL {filename}: {problem}")
            failed += 1
            continue
        target.write_bytes(data)
        print(f"ok   {filename}  ({len(data) // 1024} KB)")
        fetched += 1

    print(f"\n{fetched} fetched, {skipped} already present, {failed} failed")
    if failed:
        print("Download the failed ones by hand and drop them in data/raw/.")
    if fetched:
        print("Run `make ingest` to publish them.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
