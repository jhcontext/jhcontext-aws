"""Rural Emergency Cardiac Triage (offline flow).

Pipeline: physio-signal → triage → resource-allocation
          → teleconsult oversight (async, after uplink returns)
          → programmatic + narrative audit.

Uses ``OfflineContextMixin`` so every envelope is enqueued into a local
SQLite queue during the AI pipeline (uplink offline), and drained by the
``SyncManager`` once the scripted connectivity timeline turns online.
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from agent.crews.triage_rural.crew import (
    TriageRuralAuditCrew,
    TriageRuralClinicalCrew,
    TriageRuralOversightCrew,
)
from agent.protocol.offline_context_mixin import OfflineContextMixin

from jhcontext import ArtifactType, RiskLevel
from jhcontext.audit import (
    generate_audit_report,
    verify_integrity,
    verify_negative_proof,
    verify_temporal_oversight,
)

import agent.output_dir as _out


# Teleconsult specialist "accesses" the triage artifacts, each access
# becoming a PROV Activity with real timestamps.
SOURCE_DOCUMENTS = [
    ("act-review-ecg",       "Review ECG embedding",
     "art-physio-extraction", "ECG + semantic extraction", 3),
    ("act-review-priority",  "Review triage priority",
     "art-triage-priority",   "Triage priority",            2),
    ("act-review-allocation","Review resource allocation",
     "art-allocation",        "Bed + specialist route",     1),
]


class TriageRuralFlow(Flow, OfflineContextMixin):
    """Offline-first flow for the rural cardiac triage pipeline."""

    @start()
    def init(self):
        _out.current.mkdir(parents=True, exist_ok=True)
        queue_path = _out.current / "triage_rural_queue.sqlite"
        context_id = self._init_context(
            scope="rural_cardiac_triage",
            producer="did:hospital:physio-signal-agent",
            risk_level=RiskLevel.HIGH,
            human_oversight=True,
            queue_path=queue_path,
            feature_suppression=["insurance_status", "socio_economic_indicator"],
        )

        self._register_crew(
            crew_id="crew:triage-rural-pipeline",
            label="Rural Cardiac Triage Crew",
            agent_ids=[
                "did:hospital:physio-signal-agent",
                "did:hospital:triage-agent",
                "did:hospital:resource-agent",
            ],
        )
        print(f"[Triage-Rural] Initialized context: {context_id}")
        print(f"[Triage-Rural] Offline queue: {queue_path}")
        return self.state.get("patient_input", self._default_patient())

    @listen(init)
    def clinical_pipeline(self, input_data):
        """Run the 3-task clinical crew. Each task_callback enqueues offline."""
        print("[Triage-Rural] Steps 1-3: clinical pipeline (offline enqueue)...")

        clinical = TriageRuralClinicalCrew()
        crew_instance = clinical.crew()
        crew_instance.task_callback = self._persist_task_callback

        preamble = self.state["_forwarding_preamble"]
        result = crew_instance.kickoff(inputs={
            **input_data,
            "_forwarding_preamble": preamble,
        })

        self._log_decision(
            outcome={"recommendation": result.raw[:200], "requires_oversight": True},
            agent_id="did:hospital:resource-agent",
        )
        return result.raw

    @listen(clinical_pipeline)
    def specialist_oversight(self, triage_output):
        """Teleconsult cardiology specialist review (async, post-uplink)."""
        print("[Triage-Rural] Step 4: Specialist oversight (offline enqueue)...")

        events = []
        overall_t0 = datetime.now(timezone.utc)
        for event_id, label, entity_id, entity_label, duration in SOURCE_DOCUMENTS:
            t0 = datetime.now(timezone.utc)
            _time.sleep(duration)
            t1 = datetime.now(timezone.utc)
            events.append({
                "event_id": event_id, "label": label,
                "started_at": t0.isoformat(), "ended_at": t1.isoformat(),
                "accessed_entity": entity_id, "entity_label": entity_label,
            })

        result = TriageRuralOversightCrew().crew().kickoff(
            inputs={"recommendation": triage_output}
        )
        overall_t1 = datetime.now(timezone.utc)

        self._persist_oversight_events(
            events=events,
            oversight_agent_id="did:hospital:dr-rivera",
            summary_output=result.raw,
            overall_started_at=overall_t0.isoformat(),
            overall_ended_at=overall_t1.isoformat(),
        )

        try:
            parsed = json.loads(result.raw)
            alternatives = parsed.get("alternatives_considered", [])
            if alternatives:
                self._log_decision(
                    outcome={"decision": parsed.get("decision", "unknown"),
                             "justification": parsed.get("justification", "")},
                    agent_id="did:hospital:dr-rivera",
                    alternatives=alternatives,
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        return result.raw

    @listen(specialist_oversight)
    def compliance_audit(self, oversight_output):
        """Programmatic + narrative audit."""
        print("[Triage-Rural] Step 5: Compliance audit...")

        prov = self.state["_prov"]
        builder = self.state["_builder"]

        human_activities = [e[0] for e in SOURCE_DOCUMENTS]
        temporal = verify_temporal_oversight(
            prov=prov,
            ai_activity_id="act-triage-priority",
            human_activities=human_activities,
            min_review_seconds=3.0,  # simulated (5 minutes in paper)
        )

        env = builder.sign("did:hospital:audit-agent").build()
        integrity = verify_integrity(env)
        negative = verify_negative_proof(
            prov=prov,
            decision_entity_id="art-triage-priority",
            excluded_artifact_types=["insurance_record", "socio_economic_indicator"],
        )

        programmatic = generate_audit_report(
            env, prov, [temporal, integrity, negative],
        )

        print(f"[Triage-Rural] temporal: {'PASS' if temporal.passed else 'FAIL'} | "
              f"integrity: {'PASS' if integrity.passed else 'FAIL'} | "
              f"negative: {'PASS' if negative.passed else 'FAIL'}")

        t0 = datetime.now(timezone.utc)
        result = TriageRuralAuditCrew().crew().kickoff(inputs={
            "oversight_report": oversight_output,
            "context_id": self.state["_context_id"],
        })
        t1 = datetime.now(timezone.utc)

        self._persist_step(
            step_name="audit",
            agent_id="did:hospital:audit-agent",
            output=result.raw,
            artifact_type=ArtifactType.TOOL_RESULT,
            started_at=t0.isoformat(),
            ended_at=t1.isoformat(),
            used_artifacts=[
                "art-oversight", "art-allocation",
                "art-triage-priority", "art-physio-extraction",
            ],
        )

        self._save_outputs(result.raw, programmatic)
        return result.raw

    # ------------------------------------------------------------------
    def _save_outputs(self, audit_output: str, programmatic) -> None:
        ctx = self.state["_context_id"]
        base = _out.current

        (base / "triage_rural_envelopes.json").write_text(
            json.dumps(self.state["_task_envelopes"], indent=2)
        )
        (base / "triage_rural_prov.ttl").write_text(
            self.state["_prov"].serialize("turtle")
        )
        (base / "triage_rural_audit.json").write_text(json.dumps({
            "context_id": ctx,
            "programmatic_checks": programmatic.to_dict() if programmatic else {},
            "narrative_audit": audit_output,
            "overall_passed": programmatic.overall_passed if programmatic else None,
        }, indent=2))
        (base / "triage_rural_metrics.json").write_text(
            json.dumps(self._finalize_metrics(), indent=2)
        )
        # Queue stays open; SyncManager will drain after flow exit.
        print(f"[Triage-Rural] Outputs written to {base}/")

    @staticmethod
    def _default_patient() -> dict:
        return {
            "patient_id":   "P-R042",
            "ecg_ref":      "sig:ECG-2026-04-18-R042",
            "bp_systolic":  "148",
            "bp_diastolic": "92",
            "spo2":         "94",
        }
