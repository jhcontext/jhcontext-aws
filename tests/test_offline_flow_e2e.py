"""End-to-end smoke test: OfflineContextMixin -> OfflineQueue -> SyncManager.

Does NOT require an ANTHROPIC_API_KEY — we don't run any CrewAI agents.
Instead we manually drive the mixin as an offline-healthcare flow would, producing a
3-envelope chain and then draining it against a scripted timeline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from agent.protocol.mock_upstream import MockUpstreamClient
from agent.protocol.offline_context_mixin import OfflineContextMixin
from agent.protocol.offline_queue import OfflineQueue
from agent.protocol.sync_manager import SyncManager, build_timeline

from jhcontext import ArtifactType, RiskLevel


class _DummyFlow(OfflineContextMixin):
    """Mimics what a Flow subclass would own: a ``state`` dict."""

    def __init__(self) -> None:
        self.state: dict = {}


def test_three_handoff_chain_drains_cleanly(tmp_path: Path) -> None:
    flow = _DummyFlow()
    queue_path = tmp_path / "triage.sqlite"

    ctx = flow._init_context(
        scope="rural_cardiac_triage",
        producer="did:hospital:physio-signal-agent",
        risk_level=RiskLevel.HIGH,
        queue_path=queue_path,
    )
    assert ctx, "context_id should be generated"

    # --- Simulate 3 handoffs: physio -> triage -> resource allocation ---
    flow._persist_step(
        step_name="physio-extraction",
        agent_id="did:hospital:physio-signal-agent",
        output='{"finding":"suspected_AF","confidence":0.87}',
        artifact_type=ArtifactType.SEMANTIC_EXTRACTION,
        started_at="2026-04-18T14:00:00+00:00",
        ended_at="2026-04-18T14:00:30+00:00",
    )
    flow._persist_step(
        step_name="triage-priority",
        agent_id="did:hospital:triage-agent",
        output='{"priority":"P1","rationale":"AF+elevated_BP"}',
        artifact_type=ArtifactType.SEMANTIC_EXTRACTION,
        started_at="2026-04-18T14:00:45+00:00",
        ended_at="2026-04-18T14:01:00+00:00",
        used_artifacts=["art-physio-extraction"],
    )
    flow._persist_step(
        step_name="allocation",
        agent_id="did:hospital:resource-agent",
        output='{"bed":"CCU-3","specialist":"teleconsult:cardiology"}',
        artifact_type=ArtifactType.SEMANTIC_EXTRACTION,
        started_at="2026-04-18T14:01:15+00:00",
        ended_at="2026-04-18T14:01:30+00:00",
        used_artifacts=["art-triage-priority"],
    )
    flow._cleanup()

    # --- Drain against scripted timeline: offline until 14:10 ---
    with OfflineQueue(queue_path) as queue:
        assert queue.pending_count() == 3
        timeline = build_timeline([
            ("2026-04-18T13:59:00+00:00", "offline"),
            ("2026-04-18T14:10:00+00:00", "online"),
        ])
        upstream = MockUpstreamClient()
        report = SyncManager(queue, timeline, upstream).run()

    assert report.drained == 3, f"expected all 3 drained, got {report}"
    assert report.tampered == 0
    assert report.chain_broken == 0
    assert report.late == 0
    assert len(upstream.envelopes) == 3


def test_tamper_is_detected_on_drain(tmp_path: Path) -> None:
    flow = _DummyFlow()
    queue_path = tmp_path / "tamper.sqlite"
    flow._init_context(
        scope="test",
        producer="did:test:agent",
        risk_level=RiskLevel.HIGH,
        queue_path=queue_path,
    )
    flow._persist_step(
        step_name="step-a",
        agent_id="did:test:a",
        output="a",
        artifact_type=ArtifactType.SEMANTIC_EXTRACTION,
        started_at="2026-04-18T14:00:00+00:00",
        ended_at="2026-04-18T14:00:01+00:00",
    )
    flow._persist_step(
        step_name="step-b",
        agent_id="did:test:b",
        output="b",
        artifact_type=ArtifactType.SEMANTIC_EXTRACTION,
        started_at="2026-04-18T14:00:02+00:00",
        ended_at="2026-04-18T14:00:03+00:00",
    )
    flow._cleanup()

    # Tamper with the stored envelope JSON of the second row
    import sqlite3
    conn = sqlite3.connect(queue_path)
    conn.execute(
        "UPDATE pending_envelopes SET envelope_json = envelope_json || ' TAMPERED' "
        "WHERE envelope_id = 2"
    )
    conn.commit()
    conn.close()

    with OfflineQueue(queue_path) as queue:
        timeline = build_timeline([
            ("2026-04-18T13:59:00+00:00", "offline"),
            ("2026-04-18T14:10:00+00:00", "online"),
        ])
        upstream = MockUpstreamClient()
        report = SyncManager(queue, timeline, upstream).run()

    assert report.drained == 1, f"clean envelope should drain: {report}"
    assert report.tampered == 1, f"tamper must be caught: {report}"
