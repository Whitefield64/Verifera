"""The evaluation set must agree with the pack it belongs to.

benchmark/run.py is deliberately dependency-free and cannot read pack.yaml, so
the vocabulary checks live here, where the pack loader is available.
"""

import json

import pytest

from app import pack
from app.config import settings

SCENARIOS = settings.pack_dir / "benchmark.jsonl"


@pytest.fixture(scope="module")
def scenarios():
    if not SCENARIOS.is_file():
        pytest.skip(f"pack has no evaluation set at {SCENARIOS}")
    return [json.loads(line) for line in SCENARIOS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_domains_are_declared_by_the_pack(scenarios):
    declared = set(pack.manifest()["domains"])
    used = {item["domain"] for item in scenarios}
    assert used <= declared, f"scenarios use domains absent from pack.yaml: {sorted(used - declared)}"


def test_every_declared_domain_is_exercised(scenarios):
    declared = set(pack.manifest()["domains"])
    used = {item["domain"] for item in scenarios}
    assert declared <= used, f"pack declares unused domains: {sorted(declared - used)}"


def test_paths_and_complexity_are_balanced(scenarios):
    """A set skewed to one path measures the router less than it looks like it does."""
    paths = [item["expected_path"] for item in scenarios]
    assert set(paths) == {"rag", "agent"}
    assert min(paths.count("rag"), paths.count("agent")) >= len(scenarios) // 3


def test_abstention_cases_exist(scenarios):
    """At least one question whose honest answer is "not in the corpus"."""
    assert any(not item["must_cite"] for item in scenarios)
