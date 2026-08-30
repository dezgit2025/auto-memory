"""Tier-1 budget tests for CodexProvider.list_sessions (spec.yaml budgets).

Byte budget mirrors the main CLI convention (test_budgets.py: ~200-300
bytes/row, 7000-byte envelope for list+files); provider-level list rows
alone get a 5000-byte cap. Latency is the spec.yaml hard gate: list p95
< 150 ms on the 500-thread scaled store.
"""

import json
import time

import pytest

from .. import state_queries
from ..paths import CodexPaths
from ..provider import CodexProvider
from ._fixture_state import REF_NOW_MS

RUNS = 11
LIST_P95_BUDGET_MS = 150
LIST_BYTE_BUDGET = 5000


@pytest.fixture()
def scaled_provider(scaled_store_factory, monkeypatch):
    store = scaled_store_factory(500)
    monkeypatch.setattr(state_queries.time, "time", lambda: REF_NOW_MS / 1000)
    paths = CodexPaths(
        state_db=store.state_db,
        history_db=store.history_db,
        sessions_root=store.root / "sessions",
    )
    return CodexProvider(paths)


def test_list_output_under_byte_budget(scaled_provider):
    rows = scaled_provider.list_sessions(limit=10)
    assert len(rows) == 10
    size = len(json.dumps(rows))
    assert size < LIST_BYTE_BUDGET, (
        f"list --limit 10 payload is {size} bytes, exceeds "
        f"{LIST_BYTE_BUDGET} byte Tier-1 budget"
    )


def test_list_p95_latency_under_150ms(scaled_provider):
    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        rows = scaled_provider.list_sessions(limit=10)
        times.append((time.perf_counter() - t0) * 1000)
        assert len(rows) == 10
    p95 = sorted(times)[int(0.95 * (RUNS - 1))]
    assert p95 < LIST_P95_BUDGET_MS, (
        f"list p95 latency {p95:.1f}ms exceeds {LIST_P95_BUDGET_MS}ms "
        f"budget on 500-thread store (all runs: "
        f"{[f'{t:.0f}' for t in sorted(times)]})"
    )
