# Offline Healthcare Scenarios — CrewAI + offline persistence

Three CrewAI flows that reproduce resource-constrained clinical scenarios
under offline/deferred-sync semantics.

| # | Flow | Crews | Connectivity timeline |
|---|------|-------|-----------------------|
| 1 | [`triage_rural_flow.py`](../../agent/flows/triage_rural_flow.py) | `TriageRuralClinicalCrew` (3 agents) · `TriageRuralOversightCrew` · `TriageRuralAuditCrew` | Offline during AI pipeline → online at teleconsult review 10 min later |
| 2 | [`chronic_monitoring_flow.py`](../../agent/flows/chronic_monitoring_flow.py) | `ChronicMonitoringClinicalCrew` (4 agents) · `ChronicMonitoringOversightCrew` · `ChronicMonitoringAuditCrew` | Offline per daily handoff → online at next sync window → offline overnight → online next day for nurse review |
| 3 | [`chw_mental_health_flow.py`](../../agent/flows/chw_mental_health_flow.py) | `CHWMentalHealthClinicalCrew` (3 AI agents) · `CHWMentalHealthOversightCrew` · `CHWMentalHealthAuditCrew` | Offline during CHW home visit → online on return to clinic → district specialist async review |

## Offline persistence layer

The flows use [`OfflineContextMixin`](../../agent/protocol/offline_context_mixin.py) instead of the production `ContextMixin`. Each handoff's envelope is signed locally and enqueued into a per-scenario SQLite file ([`OfflineQueue`](../../agent/protocol/offline_queue.py)) with a predecessor-hash chain.

When the flow finishes, [`SyncManager`](../../agent/protocol/sync_manager.py) replays the scripted connectivity timeline and drains the queue. On each drain it:

1. Re-hashes the stored `envelope_json` and compares it to the recorded `content_hash` → marks **tampered** if they disagree.
2. Checks `predecessor_hash` against the previous synced envelope in the same context → marks **chain_broken** if the chain is broken.
3. If `(drain_time - queued_at)` exceeds a threshold (default 6 h), marks **late**.
4. POSTs successful drains to an upstream client — the default is a [`MockUpstreamClient`](../../agent/protocol/mock_upstream.py); swap in `JHContextClient` to exercise the real Chalice/DynamoDB path.

## Connectivity timelines

See the `SCENARIO_TIMELINES` dict in [`offline_simulate.py`](../../agent/offline_simulate.py). Each entry is a list of `(iso_timestamp, "offline"|"online")` transitions. An implicit `offline` state is assumed before the first event. The schedule is fully deterministic — replaying a run produces the same sync log.

## Run

```bash
# From jhcontext-crewai/
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...

# All three scenarios (one run directory, shared queue base)
python -m agent.offline_simulate all

# Just one
python -m agent.offline_simulate triage
python -m agent.offline_simulate chronic
python -m agent.offline_simulate chw
```

## Outputs per scenario (`output/runs/vNN/`)

```
<scenario>_envelopes.json        Per-task envelope snapshots (JSON-LD)
<scenario>_prov.ttl              Full W3C PROV graph (Turtle)
<scenario>_audit.json            Programmatic + narrative audit
<scenario>_metrics.json          Per-step timing (StepPersister)
<scenario>_queue.sqlite          The offline queue
<scenario>_sync_log.json         Drain report + full event log
<scenario>_upstream_received.json  Envelopes + PROV the mock upstream received
healthcare_offline_summary.json  Combined queued/drained/tampered/chain_broken counts
```

## Claim ↔ code mapping

| Claim | Implemented by |
|------------------------|----------------|
| "Self-contained envelopes interpretable offline" | Each enqueue signs the flow envelope; reading the SQLite row yields a complete JSON-LD artifact |
| "Each envelope binds to a hash of its predecessor" | `OfflineContextMixin._enqueue_snapshot` sets `predecessor_hash = previous content_hash` |
| "Tampering during the offline interval is detectable on sync" | `SyncManager.run()` re-hashes `envelope_json` at drain time |
| "Queue for batch synchronisation on reconnect" | `OfflineQueue.pending()` ordered by `queued_at`; drained in batches per online window |
| "`verify_temporal_oversight` confirms review AFTER the AI recommendation" | Oversight crews run after `clinical_pipeline`; PROV activities carry real timestamps; `verify_temporal_oversight` checks `started_at > ai_time` |
| "`verify_negative_proof` on structurally-absent variables" | Each flow sets `feature_suppression` + calls `verify_negative_proof` at audit time |
| "Time-to-review as an auditable programme-evaluation metric" | The CHW scenario records `time_to_review_seconds` in the audit JSON |
| "Model-version upgrade v1.2 → v1.3 captured as PROV Activity" | `ChronicMonitoringFlow._seed_model_upgrade()` adds the upgrade activity before the pipeline runs |

## Deltas to flag

1. **FlatEnvelope fidelity** — the SDK `FlatEnvelope` used for CrewAI structured output collapses a few fields (e.g. `data_category` tiers) that the full envelope schema shows in their final form. The reconstructed envelope matches the reference structurally but the LLM-produced `semantic_payload` may vary between runs (use stubs for exact reproduction).
2. **Sync latency** — the `min_review_seconds` thresholds are set to 3 s in-flow (so simulated runs complete fast). Production values are 5 min (triage) and 5–10 min (chronic monitoring, CHW mental-health).
3. **Upstream** — the simulation drives the `MockUpstreamClient`. To drain against the real Chalice API, set `UPSTREAM_IMPL=jhcontext.client.api_client:JHContextClient` and make sure the API is reachable at `JHCONTEXT_API_URL`.
