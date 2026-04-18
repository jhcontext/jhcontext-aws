"""Simulation driver for the three offline healthcare scenarios.

Runs each flow in local-first mode (envelopes enqueued offline into
per-scenario SQLite queues) and then drains each queue against a
scripted connectivity timeline matching the scenario's constraint
profile.

The driver emits a combined JSON summary plus per-scenario sync logs
so reviewers can see:

* how many envelopes were queued during offline intervals
* which ones synced successfully once the uplink returned
* any chain-broken / tampered / late arrivals detected at drain time

Usage:

    source .venv/bin/activate
    ANTHROPIC_API_KEY=... python -m agent.offline_simulate [scenario]

Where ``scenario`` ∈ {triage, chronic, chw, all} — defaults to ``all``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import agent.output_dir as _out
from agent.flows.chronic_monitoring_flow import ChronicMonitoringFlow
from agent.flows.chw_mental_health_flow import CHWMentalHealthFlow
from agent.flows.triage_rural_flow import TriageRuralFlow
from agent.protocol.mock_upstream import MockUpstreamClient
from agent.protocol.offline_queue import OfflineQueue
from agent.protocol.sync_manager import SyncManager, build_timeline


# ---------------------------------------------------------------------------
# Scripted connectivity timelines
#
# Each timeline reflects the paper's constraint profile for the scenario.
# Envelopes queued during offline intervals wait for the next online window;
# drain-time checks verify the predecessor-hash chain, detect tampering,
# and flag late arrivals.
# ---------------------------------------------------------------------------
SCENARIO_TIMELINES = {
    "triage_rural": [
        ("2026-04-18T14:00:00+00:00", "offline"),  # pipeline running offline
        ("2026-04-18T14:10:00+00:00", "online"),   # uplink returns 10 min later
    ],
    "chronic_monitoring": [
        ("2026-04-13T07:00:00+00:00", "offline"),  # daily aggregation offline
        ("2026-04-13T07:15:00+00:00", "offline"),
        ("2026-04-13T09:00:00+00:00", "online"),   # handset syncs at 09:00
        ("2026-04-13T09:30:00+00:00", "offline"),
        ("2026-04-14T09:00:00+00:00", "online"),   # next-day nurse review window
    ],
    "chw_mental_health": [
        ("2026-04-18T09:15:00+00:00", "offline"),  # CHW visit offline
        ("2026-04-18T13:00:00+00:00", "online"),   # CHW returns to clinic
    ],
}


def _drain(scenario: str, queue_path: Path) -> dict:
    """Replay the scripted timeline against a scenario queue."""
    timeline = build_timeline(SCENARIO_TIMELINES[scenario])
    upstream_record_path = queue_path.with_name(f"{scenario}_upstream_received.json")
    upstream = MockUpstreamClient(record_path=upstream_record_path)

    with OfflineQueue(queue_path) as queue:
        pending_before = queue.pending_count()
        manager = SyncManager(queue, timeline, upstream)
        report = manager.run()
        summary = queue.summary()
        log = queue.log_dict()
        # Persist sync log alongside queue
        sync_log_path = queue_path.with_name(f"{scenario}_sync_log.json")
        sync_log_path.write_text(
            json.dumps({
                "scenario": scenario,
                "timeline": SCENARIO_TIMELINES[scenario],
                "pending_before_drain": pending_before,
                "summary": summary,
                "report": report.as_dict(),
                "log": log,
            }, indent=2),
            encoding="utf-8",
        )
    upstream.close()
    return {
        "scenario": scenario,
        "pending_before_drain": pending_before,
        "summary": summary,
        "drained": report.drained,
        "tampered": report.tampered,
        "chain_broken": report.chain_broken,
        "late": report.late,
        "upstream_received": len(upstream.envelopes),
        "sync_log_path": str(sync_log_path),
    }


def run_triage() -> dict:
    flow = TriageRuralFlow()
    flow.kickoff()
    return _drain("triage_rural", _out.current / "triage_rural_queue.sqlite")


def run_chronic() -> dict:
    flow = ChronicMonitoringFlow()
    flow.kickoff()
    return _drain("chronic_monitoring", _out.current / "chronic_monitoring_queue.sqlite")


def run_chw() -> dict:
    flow = CHWMentalHealthFlow()
    flow.kickoff()
    return _drain("chw_mental_health", _out.current / "chw_mental_health_queue.sqlite")


def main(argv: list[str] | None = None) -> None:
    scenarios = (argv or sys.argv[1:]) or ["all"]
    choice = scenarios[0]

    # Versioned output dir so the three scenario runs share one snapshot
    run_dir = _out.next_run_dir()
    _out.set_current(run_dir)
    print(f"[offline-sim] run dir: {run_dir}")

    results: dict[str, dict] = {}
    if choice in ("triage", "all"):
        print("\n>>> Scenario 1 — Rural Cardiac Triage")
        results["triage_rural"] = run_triage()
    if choice in ("chronic", "all"):
        print("\n>>> Scenario 2 — Chronic-Disease Remote Monitoring")
        results["chronic_monitoring"] = run_chronic()
    if choice in ("chw", "all"):
        print("\n>>> Scenario 3 — CHW Mental-Health Screening")
        results["chw_mental_health"] = run_chw()

    summary_path = run_dir / "healthcare_offline_summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 68)
    print("Healthcare offline simulation summary")
    print("=" * 68)
    for name, res in results.items():
        print(f"{name}:")
        print(f"  queued : {res['pending_before_drain']}   "
              f"drained: {res['drained']}   "
              f"tampered: {res['tampered']}   "
              f"chain_broken: {res['chain_broken']}   "
              f"late: {res['late']}")
    print(f"\nSummary written to: {summary_path}")


if __name__ == "__main__":
    main()
