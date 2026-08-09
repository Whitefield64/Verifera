"""Fetch the corpus declared by the domain pack and keep it up to date.

The pack lists its sources in sources.yaml; this downloads them into the
ingestion inbox and records provenance in data/manifest.json. Documents are
never redistributed with the repository — they are re-fetched from the
publisher, which is also what makes the corpus refreshable when the underlying
regulation changes.

Change detection deliberately does not hash the raw bytes. EUR-Lex injects a
per-request analytics id into every HTML response, so the bytes differ on every
fetch while the legal text is identical; hashing the visible text instead means
"changed" means the document changed.
"""

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any

import yaml

from app.config import settings
from ingestion.html_clean import visible_text

USER_AGENT = "corpus-sync/1.0 (+https://github.com/)"
REQUEST_TIMEOUT = 90
# Courtesy delay between requests; these are public institutional servers.
DELAY_S = 0.5

EXTENSIONS = {"pdf": ".pdf", "html": ".html", "docx": ".docx"}


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    category: str
    format: str
    lang: str
    license: str
    notes: str = ""

    @property
    def filename(self) -> str:
        return f"{self.id}{EXTENSIONS[self.format]}"


def load_sources() -> list[Source]:
    path = settings.pack_dir / "sources.yaml"
    if not path.is_file():
        raise SourceError(f"pack has no source list at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = []
    for raw in data.get("sources", []):
        try:
            source = Source(**raw)
        except TypeError as error:
            raise SourceError(f"invalid source entry {raw.get('id', '?')}: {error}") from error
        if source.format not in EXTENSIONS:
            raise SourceError(f"{source.id}: unsupported format {source.format!r}")
        sources.append(source)
    ids = [s.id for s in sources]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise SourceError(f"duplicate source ids: {sorted(duplicates)}")
    return sources


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def content_digest(data: bytes, fmt: str) -> str:
    """Hash of what the document says, not of how it was served."""
    if fmt == "html":
        text = visible_text(data.decode("utf-8", errors="replace"))
        return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
    return hashlib.sha256(data).hexdigest()


def load_manifest() -> dict[str, dict[str, Any]]:
    if not settings.manifest_path.is_file():
        return {}
    entries = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in entries}


def write_manifest(entries: dict[str, dict[str, Any]]) -> None:
    ordered = [entries[key] for key in sorted(entries)]
    settings.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    settings.manifest_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _entry(source: Source, data: bytes, digest: str) -> dict[str, Any]:
    return {
        "id": source.id,
        "title": source.title,
        "category": source.category,
        "source_url": source.url,
        "format": source.format,
        "lang": source.lang,
        "license": source.license,
        # Name only: RAW_DIR differs between a host checkout and the container,
        # and an absolute path would make the manifest machine-specific.
        "filename": source.filename,
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_sha256": digest,
        "downloaded_at": date.today().isoformat(),
        "notes": source.notes,
    }


def sync(check_only: bool = False, only_id: str | None = None) -> int:
    sources = load_sources()
    if only_id:
        sources = [s for s in sources if s.id == only_id]
        if not sources:
            print(f"no source with id {only_id!r}")
            return 1

    manifest = load_manifest()
    new, changed, unchanged, failed = [], [], [], []

    for index, source in enumerate(sources):
        if index:
            time.sleep(DELAY_S)
        try:
            data = fetch(source.url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            failed.append((source.id, str(error)))
            print(f"FAIL {source.id}: {error}")
            continue

        digest = content_digest(data, source.format)
        known = manifest.get(source.id)
        if known and known.get("content_sha256") == digest:
            unchanged.append(source.id)
            continue

        bucket = changed if known else new
        bucket.append(source.id)
        print(f"{'CHANGED' if known else 'NEW    '} {source.id}  {source.title}")
        if check_only:
            continue

        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        (settings.raw_dir / source.filename).write_bytes(data)
        manifest[source.id] = _entry(source, data, digest)

    if not check_only and (new or changed):
        write_manifest(manifest)

    verb = "would fetch" if check_only else "fetched"
    print(
        f"\n{len(sources)} sources: {len(new)} new, {len(changed)} changed "
        f"({verb}), {len(unchanged)} unchanged, {len(failed)} failed"
    )
    if new or changed:
        print("Run `python -m ingestion ingest` to publish them.")
    return 1 if failed else 0


def status() -> int:
    sources = {s.id: s for s in load_sources()}
    manifest = load_manifest()

    missing = sorted(set(sources) - set(manifest))
    orphans = sorted(set(manifest) - set(sources))

    print(f"Sources declared: {len(sources)}")
    print(f"Documents in manifest: {len(manifest)}")

    by_category: dict[str, int] = {}
    by_format: dict[str, int] = {}
    for source in sources.values():
        by_category[source.category] = by_category.get(source.category, 0) + 1
        by_format[source.format] = by_format.get(source.format, 0) + 1
    print("\nBy category:")
    for key, count in sorted(by_category.items()):
        print(f"  {key}: {count}")
    print("By format:")
    for key, count in sorted(by_format.items()):
        print(f"  {key}: {count}")

    if missing:
        print(f"\nDeclared but never fetched ({len(missing)}): {', '.join(missing)}")
    if orphans:
        print(f"\nIn manifest but no longer declared ({len(orphans)}): {', '.join(orphans)}")
    return 0
