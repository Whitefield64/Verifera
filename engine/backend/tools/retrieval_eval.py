"""Retrieval-only evaluation against the benchmark's must_cite, no chat calls.

Usage (from engine/backend):
    python -m tools.retrieval_eval [--k 8] [--pool 30] [--per-doc-cap 0] [--verbose]

The questions' embeddings are cached on disk, so every iteration after the first
costs nothing. Coverage is computed over the doc_ids of the top-k chunks.
"""

import argparse
import hashlib
import json
from pathlib import Path

from app import db, llm, retrieval
from app.config import settings

# The evaluation set belongs to the example corpus it was written against; the
# cache sits with the other generated data, so it works in the container too.
SCENARIOS = Path(__file__).resolve().parents[3] / "example" / "benchmark.jsonl"
CACHE = settings.workspace_dir.parent / "eval-runs" / "query-embeddings-cache.json"


def load_scenarios() -> list[dict]:
    return [
        json.loads(line) for line in SCENARIOS.read_text().splitlines() if line.strip()
    ]


def cached_embeddings(questions: list[str]) -> dict[str, list[float]]:
    cache: dict[str, list[float]] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text())
    missing = []
    keys = {}
    for question in questions:
        key = hashlib.sha256(
            f"{settings.embed_model}\x1f{question}".encode()
        ).hexdigest()[:24]
        keys[question] = key
        if key not in cache:
            missing.append(question)
    if missing:
        vectors = llm.embed(missing)
        for question, vector in zip(missing, vectors):
            cache[keys[question]] = vector
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache))
    return {question: cache[keys[question]] for question in questions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=settings.top_k)
    parser.add_argument("--pool", type=int, default=settings.rrf_pool)
    parser.add_argument("--per-doc-cap", type=int, default=settings.per_doc_cap)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    items = [item for item in load_scenarios() if item["must_cite"]]
    vectors = cached_embeddings([item["question"] for item in items])

    full, partial = 0, 0
    per_path: dict[str, list[int]] = {
        "rag": [0, 0, 0],
        "agent": [0, 0, 0],
    }  # full, any, total
    misses = []
    with db.connect() as conn:
        for item in items:
            chunks = retrieval.hybrid_search(
                conn,
                item["question"],
                vectors[item["question"]],
                k=args.k,
                pool=args.pool,
                per_doc_cap=args.per_doc_cap,
            )
            docs = {chunk.doc_id for chunk in chunks}
            hit = sum(1 for d in item["must_cite"] if d in docs)
            n = len(item["must_cite"])
            stats = per_path[item["expected_path"]]
            stats[2] += 1
            if hit == n:
                full += 1
                stats[0] += 1
            if hit > 0:
                partial += 1
                stats[1] += 1
            else:
                misses.append(
                    (item["id"], item["expected_path"], item["must_cite"], sorted(docs))
                )
            if args.verbose and hit < n:
                print(
                    f"  {item['id']} [{item['expected_path']}] {hit}/{n} must={item['must_cite']}"
                )

    total = len(items)
    print(f"k={args.k} pool={args.pool} per_doc_cap={args.per_doc_cap}")
    print(f"  every must_cite in the top-k: {full}/{total}")
    print(f"  at least one in the top-k:    {partial}/{total}")
    for path, (path_full, path_any, path_total) in per_path.items():
        print(
            f"    [{path}] every: {path_full}/{path_total}, at least one: {path_any}/{path_total}"
        )
    if args.verbose:
        for item_id, path, must, got in misses:
            print(f"  TOTAL MISS {item_id} [{path}]: expected {must}, top-k from {got}")


if __name__ == "__main__":
    main()
