#!/usr/bin/env python3
"""Replay benchmark conversations through the same HTTP contract as the web app."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
# The evaluation set is part of the domain pack: swapping the pack swaps the
# questions along with the prompts and the corpus.
PACK_DIR = Path(os.getenv("PACK_DIR") or ROOT / "packs" / "eu-ai-act")
SCENARIOS_PATH = PACK_DIR / "benchmark.jsonl"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
RESULTS_DIR = ROOT / "benchmark" / "results"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on {path}:{line_number}: {error}") from error
    return items


def validate_scenarios(items: list[dict[str, Any]], manifest_ids: set[str]) -> None:
    required = {
        "id", "domain", "complexity", "thread", "turn", "question",
        "reference_answer", "must_cite", "expected_path", "notes",
    }
    if not items:
        raise ValueError("scenario file must contain at least one item")
    expected_ids = [f"q{number:02d}" for number in range(1, len(items) + 1)]
    if [item["id"] for item in items] != expected_ids:
        raise ValueError(f"scenario IDs must be consecutive q01..q{len(items):02d}")

    for item in items:
        missing = required - item.keys()
        if missing:
            raise ValueError(f"{item.get('id', '?')} missing fields: {sorted(missing)}")
        # The domain vocabulary belongs to the pack, and this harness stays
        # dependency-free (no YAML parser). backend/tests/test_scenarios.py
        # checks each domain against pack.yaml, where the pack is already loaded.
        if not isinstance(item["domain"], str) or not item["domain"]:
            raise ValueError(f"{item['id']} has an empty domain")
        if item["complexity"] not in {"simple", "complex"}:
            raise ValueError(f"{item['id']} has invalid complexity")
        if item["expected_path"] not in {"rag", "agent"}:
            raise ValueError(f"{item['id']} has invalid expected_path")
        unknown = set(item["must_cite"]) - manifest_ids
        if unknown:
            raise ValueError(f"{item['id']} cites unknown documents: {sorted(unknown)}")

    for thread in {item["thread"] for item in items if item["thread"] is not None}:
        turns = sorted(item["turn"] for item in items if item["thread"] == thread)
        if turns != list(range(1, len(turns) + 1)):
            raise ValueError(f"thread {thread} has non-consecutive turns: {turns}")


def select_items(items: list[dict[str, Any]], requested_ids: list[str], limit: int | None) -> list[dict[str, Any]]:
    if requested_ids:
        known = {item["id"] for item in items}
        unknown = set(requested_ids) - known
        if unknown:
            raise ValueError(f"unknown scenario IDs: {sorted(unknown)}")
        selected_ids = set(requested_ids)
        for item in items:
            if item["id"] not in selected_ids or item["thread"] is None:
                continue
            selected_ids.update(
                candidate["id"]
                for candidate in items
                if candidate["thread"] == item["thread"] and candidate["turn"] < item["turn"]
            )
        items = [item for item in items if item["id"] in selected_ids]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be positive")
        items = items[:limit]
    return items


class ChatClient:
    """Calls the JSON endpoint shared by the simulator and the web application."""

    def __init__(self, url: str, timeout: float) -> None:
        self.url = url
        self.timeout = timeout

    def send(self, message: str, history: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
        request_body = {"message": message, "history": history}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = monotonic()
        with urllib.request.urlopen(request, timeout=self.timeout) as http_response:
            response_body = json.loads(http_response.read().decode("utf-8"))
            status = http_response.status
        elapsed_ms = round((monotonic() - started) * 1_000)
        if not isinstance(response_body, dict):
            raise ValueError("chat endpoint must return a JSON object")
        if not isinstance(response_body.get("answer"), str):
            raise ValueError("chat response must contain a string field named 'answer'")
        if not isinstance(response_body.get("citations"), list):
            raise ValueError("chat response must contain a list field named 'citations'")
        return request_body, {
            "body": response_body,
            "transport": {"http_status": status, "elapsed_ms": elapsed_ms},
        }


def expected_rubric(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "reference_answer": item["reference_answer"],
        "must_cite": item["must_cite"],
        "expected_path": item["expected_path"],
        "notes": item["notes"],
    }


def run_conversations(items: list[dict[str, Any]], client: ChatClient) -> list[dict[str, Any]]:
    transcripts: dict[str, dict[str, Any]] = {}
    histories: dict[str, list[dict[str, str]]] = {}

    for item in items:
        conversation_id = item["thread"] or item["id"]
        history = histories.setdefault(conversation_id, [])
        request_body, response = client.send(item["question"], list(history))
        response_body = response["body"]
        transcript = transcripts.setdefault(
            conversation_id,
            {"conversation_id": conversation_id, "threaded": item["thread"] is not None, "turns": []},
        )
        transcript["turns"].append({
            "item_id": item["id"],
            "domain": item["domain"],
            "complexity": item["complexity"],
            "request": request_body,
            "response": response_body,
            "transport": response["transport"],
            "expected": expected_rubric(item),
        })
        history.extend((
            {"role": "user", "content": item["question"]},
            {"role": "assistant", "content": response_body["answer"]},
        ))
        print(f"{item['id']}: {response['transport']['elapsed_ms']} ms")

    return list(transcripts.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument("--backend-url", default=os.getenv("EVAL_BACKEND_URL"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--item", action="append", default=[], help="Run one item; repeat for multiple items")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    items = load_jsonl(args.scenarios)
    validate_scenarios(items, {item["id"] for item in manifest})

    if args.validate_only:
        standalone = sum(item["thread"] is None for item in items)
        print(f"Scenarios valid: {len(items)} items, {standalone} standalone, {len(items) - standalone} threaded.")
        return 0

    items = select_items(items, args.item, args.limit)
    if not args.backend_url:
        raise ValueError("--backend-url or EVAL_BACKEND_URL is required")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcripts = run_conversations(items, ChatClient(args.backend_url, args.timeout))
    output = {
        "run": {
            "timestamp_utc": timestamp,
            "endpoint": args.backend_url,
            "scenario_file": str(args.scenarios.relative_to(ROOT)),
            "item_count": len(items),
        },
        "transcripts": transcripts,
    }
    output_path = args.output or RESULTS_DIR / f"{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Transcripts: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
