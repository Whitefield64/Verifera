"""Valutazione retrieval-only contro i must_cite del benchmark, senza chiamate chat.

Uso (da root repo, PYTHONPATH=backend):
    python -m tools.retrieval_eval [--k 8] [--pool 30] [--per-doc-cap 0] [--verbose]

Le embedding delle 40 domande sono cachate su file: le iterazioni successive
costano zero. La coverage è calcolata sui doc_id dei chunk nei top-k.
"""

import argparse
import hashlib
import json
from pathlib import Path

from app import db, llm, retrieval
from app.config import settings

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "benchmark" / "benchmark.jsonl"
CACHE = ROOT / "benchmark" / "results" / "query-embeddings-cache.json"


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
    }  # full, any, tot
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
    print(f"  tutti i must_cite nei top-k: {full}/{total}")
    print(f"  almeno uno nei top-k:        {partial}/{total}")
    for path, (path_full, path_any, path_total) in per_path.items():
        print(
            f"    [{path}] tutti: {path_full}/{path_total}, almeno uno: {path_any}/{path_total}"
        )
    if args.verbose:
        for item_id, path, must, got in misses:
            print(f"  MISS totale {item_id} [{path}]: attesi {must}, top-k da {got}")


if __name__ == "__main__":
    main()
