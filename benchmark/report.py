#!/usr/bin/env python3
"""Objective metrics from a transcript file.

Everything here can be computed without judgement: routing against
`expected_path`, `must_cite` coverage, the share of quotes the backend could
verify, latency and tokens. Whether an answer is *correct* is not in this
script, and should not be — that is a reading of the transcript against the
reference and the source documents.

Unlike run.py this is a developer tool and may use dependencies.

    python3 benchmark/report.py benchmark/results/<file>.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = Path(os.getenv("PACK_DIR") or ROOT / "packs" / "eu-ai-act")


def variant_groups() -> dict[str, set[str]]:
    """doc_id -> every doc_id that counts as the same document."""
    pack = yaml.safe_load((PACK_DIR / "pack.yaml").read_text(encoding="utf-8")) or {}
    groups: dict[str, set[str]] = {}
    for canonical, variants in (pack.get("document_variants") or {}).items():
        family = {canonical, *variants}
        for member in family:
            groups[member] = family
    return groups


def turns(transcripts: list[dict]) -> list[dict]:
    return [turn for t in transcripts for turn in t["turns"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcripts", type=Path)
    args = parser.parse_args()

    data = json.loads(args.transcripts.read_text(encoding="utf-8"))
    rows = turns(data["transcripts"])
    scenarios = {
        json.loads(line)["id"]: json.loads(line)
        for line in (PACK_DIR / "benchmark.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    groups = variant_groups()

    routing_hits: list[str] = []
    cite_hits: list[str] = []
    cite_misses: list[tuple[str, list[str]]] = []
    verified = total_citations = 0
    empty_citations: list[str] = []
    latencies: list[int] = []
    tokens_in = tokens_out = 0
    by_path: Counter[str] = Counter()

    for turn in rows:
        item = scenarios[turn["item_id"]]
        body = turn["response"]
        meta = body.get("meta", {})

        by_path[body.get("path", "?")] += 1
        latencies.append(meta.get("elapsed_ms", 0))
        usage = meta.get("usage") or {}
        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)

        if body.get("path") == item["expected_path"]:
            routing_hits.append(turn["item_id"])

        cited = {c["doc_id"] for c in body.get("citations", [])}
        expanded = {member for doc in cited for member in groups.get(doc, {doc})}
        required = item["must_cite"]
        if required:
            missing = [doc for doc in required if doc not in expanded]
            (cite_hits if not missing else cite_misses).append(
                turn["item_id"] if not missing else (turn["item_id"], missing)
            )
        elif cited:
            empty_citations.append(turn["item_id"])

        for citation in body.get("citations", []):
            total_citations += 1
            verified += bool(citation.get("verified"))

    graded = [t for t in rows if scenarios[t["item_id"]]["must_cite"]]
    print(f"Transcripts: {args.transcripts}   items: {len(rows)}\n")

    print(f"Routing vs expected_path : {len(routing_hits)}/{len(rows)}")
    for turn in rows:
        item = scenarios[turn["item_id"]]
        got = turn["response"].get("path")
        if got != item["expected_path"]:
            method = (turn["response"].get("meta", {}).get("router") or {}).get("method", "?")
            print(f"    {turn['item_id']}: expected {item['expected_path']}, got {got} ({method})")

    print(f"\nmust_cite satisfied      : {len(cite_hits)}/{len(graded)}")
    for item_id, missing in cite_misses:
        print(f"    {item_id}: missing {', '.join(missing)}")

    rate = 100 * verified / total_citations if total_citations else 0.0
    print(f"\nQuotes verified          : {verified}/{total_citations} ({rate:.0f}%)")

    abstentions = [i for i, s in scenarios.items() if not s["must_cite"]]
    print(f"\nAbstention items         : {len(abstentions)} ({', '.join(sorted(abstentions))})")
    if empty_citations:
        print(f"    cited something anyway: {', '.join(empty_citations)}")

    print(f"\nPath taken               : {dict(by_path)}")
    print(
        f"Latency ms               : median {int(statistics.median(latencies))}, "
        f"max {max(latencies)}"
    )
    print(f"Tokens                   : input {tokens_in:,}  output {tokens_out:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
