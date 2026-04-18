"""Smoke test for the offline protocol layer.

Validates OfflineQueue + SyncManager end-to-end without any CrewAI or
LLM dependency. Run with:

    pytest tests/test_offline_layer.py -v
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent.protocol.mock_upstream import MockUpstreamClient
from agent.protocol.offline_queue import OfflineQueue
from agent.protocol.sync_manager import SyncManager, build_timeline


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _envelope(context_id: str, step: str, predecessor: str | None,
              tamper_mode: bool = False) -> tuple[str, str, str]:
    """Return (envelope_json, content_hash, predecessor_hash)."""
    payload = {
        "context_id": context_id,
        "step": step,
        "predecessor_hash": predecessor,
        "content": f"{step} payload",
    }
    env_json = json.dumps(payload, sort_keys=True)
    h = _sha(env_json)
    return env_json, h, predecessor


def test_clean_drain_chain_verified(tmp_path: Path) -> None:
    queue = OfflineQueue(tmp_path / "queue.sqlite", reset=True)
    ctx = "ctx-triage-001"

    # Three envelopes in a chain: E1 (no predecessor) -> E2 -> E3
    j1, h1, _ = _envelope(ctx, "physio", None)
    queue.enqueue(
        context_id=ctx, step_name="physio",
        envelope_json=j1, prov_ttl="# prov step=physio",
        content_hash=h1, predecessor_hash=None,
        queued_at="2026-04-18T14:00:00+00:00",  # offline
    )
    j2, h2, _ = _envelope(ctx, "triage", h1)
    queue.enqueue(
        context_id=ctx, step_name="triage",
        envelope_json=j2, prov_ttl="# prov step=triage",
        content_hash=h2, predecessor_hash=h1,
        queued_at="2026-04-18T14:01:00+00:00",  # offline
    )
    j3, h3, _ = _envelope(ctx, "allocation", h2)
    queue.enqueue(
        context_id=ctx, step_name="allocation",
        envelope_json=j3, prov_ttl="# prov step=allocation",
        content_hash=h3, predecessor_hash=h2,
        queued_at="2026-04-18T14:02:00+00:00",  # offline
    )

    # Uplink comes back at 14:10 and stays online
    timeline = build_timeline([
        ("2026-04-18T14:00:00+00:00", "offline"),
        ("2026-04-18T14:10:00+00:00", "online"),
    ])

    upstream = MockUpstreamClient()
    report = SyncManager(queue, timeline, upstream).run()

    assert report.drained == 3
    assert report.tampered == 0
    assert report.chain_broken == 0
    assert report.late == 0
    assert len(upstream.envelopes) == 3
    assert queue.pending_count() == 0


def test_tamper_detected(tmp_path: Path) -> None:
    queue = OfflineQueue(tmp_path / "q.sqlite", reset=True)
    ctx = "ctx-tamper"

    j1, h1, _ = _envelope(ctx, "physio", None)
    queue.enqueue(
        context_id=ctx, step_name="physio",
        envelope_json=j1, prov_ttl="# prov",
        content_hash=h1, predecessor_hash=None,
        queued_at="2026-04-18T14:00:00+00:00",
    )
    # Inject a tampered envelope (wrong content hash on record)
    j2, _h2, _ = _envelope(ctx, "triage", h1)
    queue.enqueue(
        context_id=ctx, step_name="triage",
        envelope_json=j2,
        prov_ttl="# prov",
        content_hash="deadbeef",  # tampered hash
        predecessor_hash=h1,
        queued_at="2026-04-18T14:01:00+00:00",
    )

    timeline = build_timeline([
        ("2026-04-18T14:00:00+00:00", "offline"),
        ("2026-04-18T14:10:00+00:00", "online"),
    ])
    upstream = MockUpstreamClient()
    report = SyncManager(queue, timeline, upstream).run()

    assert report.drained == 1  # only the clean envelope drained
    assert report.tampered == 1
    assert report.chain_broken == 0


def test_chain_broken_detected(tmp_path: Path) -> None:
    queue = OfflineQueue(tmp_path / "q.sqlite", reset=True)
    ctx = "ctx-chain"

    j1, h1, _ = _envelope(ctx, "physio", None)
    queue.enqueue(
        context_id=ctx, step_name="physio",
        envelope_json=j1, prov_ttl="# prov",
        content_hash=h1, predecessor_hash=None,
        queued_at="2026-04-18T14:00:00+00:00",
    )
    # Envelope 2 references a wrong predecessor hash
    j2, h2, _ = _envelope(ctx, "triage", "wrong_prev")
    queue.enqueue(
        context_id=ctx, step_name="triage",
        envelope_json=j2, prov_ttl="# prov",
        content_hash=h2,
        predecessor_hash="wrong_prev",
        queued_at="2026-04-18T14:01:00+00:00",
    )

    timeline = build_timeline([
        ("2026-04-18T14:00:00+00:00", "offline"),
        ("2026-04-18T14:10:00+00:00", "online"),
    ])
    upstream = MockUpstreamClient()
    report = SyncManager(queue, timeline, upstream).run()

    assert report.drained == 1
    assert report.chain_broken == 1


def test_late_flag_when_drain_window_is_days_later(tmp_path: Path) -> None:
    queue = OfflineQueue(tmp_path / "q.sqlite", reset=True)
    ctx = "ctx-late"

    j1, h1, _ = _envelope(ctx, "physio", None)
    queue.enqueue(
        context_id=ctx, step_name="physio",
        envelope_json=j1, prov_ttl="# prov",
        content_hash=h1, predecessor_hash=None,
        queued_at="2026-04-18T09:00:00+00:00",  # queued morning
    )

    timeline = build_timeline([
        ("2026-04-18T09:00:00+00:00", "offline"),
        ("2026-04-19T10:00:00+00:00", "online"),  # drain 25 hours later
    ])
    upstream = MockUpstreamClient()
    report = SyncManager(queue, timeline, upstream,
                         late_after_seconds=6 * 3600).run()

    assert report.drained == 1
    assert report.late == 1
