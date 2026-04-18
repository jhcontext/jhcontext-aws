"""Chronic-Disease Remote Monitoring (offline flow).

Pipeline: sensor-aggregation → trend-analysis → alert → care-plan
          → nurse oversight (next-day, post-sync)
          → programmatic + narrative audit.

Model-version upgrade v1.2 → v1.3 is seeded into the PROV graph in
``init()`` so auditors can distinguish clinical deterioration from
model drift.
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from agent.crews.chronic_monitoring.crew import (
    ChronicMonitoringAuditCrew,
    ChronicMonitoringClinicalCrew,
    ChronicMonitoringOversightCrew,
)
from agent.protocol.offline_context_mixin import OfflineContextMixin

from jhcontext import ArtifactType, RiskLevel
from jhcontext.audit import (
    generate_audit_report,
    verify_integrity,
    verify_negative_proof,
    verify_pii_detachment,
    verify_temporal_oversight,
)

import agent.output_dir as _out


NURSE_REVIEW_ACTIVITIES = [
    ("act-review-trend",     "Review weekly trend",
     "art-weekly-trend",      "Weekly trend artifact", 2),
    ("act-review-alert",     "Review alert",
     "art-alert",             "Alert artifact",        1),
    ("act-review-care-plan", "Review proposed care plan",
     "art-care-plan",         "Care plan artifact",    2),
]


class ChronicMonitoringFlow(Flow, OfflineContextMixin):
    """Offline-first flow for the chronic-disease remote monitoring pipeline."""

    @start()
    def init(self):
        _out.current.mkdir(parents=True, exist_ok=True)
        queue_path = _out.current / "chronic_monitoring_queue.sqlite"
        context_id = self._init_context(
            scope="chronic_remote_monitoring",
            producer="did:clinic:sensor-aggregation-agent",
            risk_level=RiskLevel.HIGH,
            human_oversight=True,
            queue_path=queue_path,
            feature_suppression=["home_address", "raw_geolocation"],
        )

        self._register_crew(
            crew_id="crew:chronic-monitoring-pipeline",
            label="Chronic Remote Monitoring Crew",
            agent_ids=[
                "did:clinic:sensor-aggregation-agent",
                "did:clinic:trend-analysis-agent",
                "did:clinic:alert-agent",
                "did:clinic:care-plan-agent",
            ],
        )

        # Seed the model-upgrade PROV Activity (paper §5.2)
        self._seed_model_upgrade()

        print(f"[Chronic] Initialized context: {context_id}")
        print(f"[Chronic] Offline queue: {queue_path}")
        return self.state.get("patient_input", self._default_patient())

    def _seed_model_upgrade(self) -> None:
        prov = self.state["_prov"]
        now = datetime.now(timezone.utc)
        upgrade_start = (now - timedelta(days=7)).isoformat()
        upgrade_end = (now - timedelta(days=7) + timedelta(hours=1)).isoformat()

        prov.add_agent("did:clinic:mlops-team", "MLOps team",
                       role="model_operator")
        prov.add_entity("art-trend-model-v1.2", "Trend model v1.2 (retired)",
                        artifact_type="model_version",
                        content_hash="sha256:0001...")
        prov.add_entity("art-trend-model-v1.3", "Trend model v1.3 (active)",
                        artifact_type="model_version",
                        content_hash="sha256:0002...")
        prov.add_activity(
            "act-model-upgrade-v1.2-v1.3", "Trend model upgrade",
            started_at=upgrade_start, ended_at=upgrade_end,
            method="rolling OTA",
        )
        prov.was_associated_with("act-model-upgrade-v1.2-v1.3",
                                 "did:clinic:mlops-team")
        prov.was_generated_by("art-trend-model-v1.3",
                              "act-model-upgrade-v1.2-v1.3")
        prov.was_derived_from("art-trend-model-v1.3",
                              "art-trend-model-v1.2")

    @listen(init)
    def clinical_pipeline(self, input_data):
        print("[Chronic] Steps 1-4: clinical pipeline (offline enqueue)...")
        clinical = ChronicMonitoringClinicalCrew()
        crew_instance = clinical.crew()
        crew_instance.task_callback = self._persist_task_callback

        preamble = self.state["_forwarding_preamble"]
        result = crew_instance.kickoff(inputs={
            **input_data,
            "_forwarding_preamble": preamble,
        })

        self._log_decision(
            outcome={"recommendation": result.raw[:200], "requires_oversight": True},
            agent_id="did:clinic:care-plan-agent",
        )
        return result.raw

    @listen(clinical_pipeline)
    def nurse_oversight(self, care_plan_output):
        """Nurse reviews the chain the day after opportunistic sync."""
        print("[Chronic] Step 5: Nurse oversight (offline enqueue)...")

        events = []
        overall_t0 = datetime.now(timezone.utc)
        for event_id, label, entity_id, entity_label, duration in NURSE_REVIEW_ACTIVITIES:
            t0 = datetime.now(timezone.utc)
            _time.sleep(duration)
            t1 = datetime.now(timezone.utc)
            events.append({
                "event_id": event_id, "label": label,
                "started_at": t0.isoformat(), "ended_at": t1.isoformat(),
                "accessed_entity": entity_id, "entity_label": entity_label,
            })

        result = ChronicMonitoringOversightCrew().crew().kickoff(
            inputs={"recommendation": care_plan_output}
        )
        overall_t1 = datetime.now(timezone.utc)

        self._persist_oversight_events(
            events=events,
            oversight_agent_id="did:clinic:nurse-amani",
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
                    agent_id="did:clinic:nurse-amani",
                    alternatives=alternatives,
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        return result.raw

    @listen(nurse_oversight)
    def compliance_audit(self, oversight_output):
        print("[Chronic] Step 6: Compliance audit...")

        prov = self.state["_prov"]
        builder = self.state["_builder"]

        human_activities = [e[0] for e in NURSE_REVIEW_ACTIVITIES]
        temporal = verify_temporal_oversight(
            prov=prov, ai_activity_id="act-alert",
            human_activities=human_activities,
            min_review_seconds=3.0,
        )
        env = builder.sign("did:clinic:audit-agent").build()
        integrity = verify_integrity(env)
        pii = verify_pii_detachment(env)
        negative = verify_negative_proof(
            prov=prov, decision_entity_id="art-alert",
            excluded_artifact_types=["home_address", "raw_geolocation"],
        )

        programmatic = generate_audit_report(
            env, prov, [temporal, integrity, pii, negative],
        )
        print(f"[Chronic] temporal: {'PASS' if temporal.passed else 'FAIL'} | "
              f"integrity: {'PASS' if integrity.passed else 'FAIL'} | "
              f"pii: {'PASS' if pii.passed else 'FAIL'} | "
              f"negative: {'PASS' if negative.passed else 'FAIL'}")

        t0 = datetime.now(timezone.utc)
        result = ChronicMonitoringAuditCrew().crew().kickoff(inputs={
            "oversight_report": oversight_output,
            "context_id": self.state["_context_id"],
        })
        t1 = datetime.now(timezone.utc)

        self._persist_step(
            step_name="audit",
            agent_id="did:clinic:audit-agent",
            output=result.raw,
            artifact_type=ArtifactType.TOOL_RESULT,
            started_at=t0.isoformat(), ended_at=t1.isoformat(),
            used_artifacts=[
                "art-oversight", "art-care-plan", "art-alert",
                "art-weekly-trend", "art-daily-aggregate",
            ],
        )

        self._save_outputs(result.raw, programmatic)
        return result.raw

    # ------------------------------------------------------------------
    def _save_outputs(self, audit_output: str, programmatic) -> None:
        ctx = self.state["_context_id"]
        base = _out.current
        (base / "chronic_monitoring_envelopes.json").write_text(
            json.dumps(self.state["_task_envelopes"], indent=2)
        )
        (base / "chronic_monitoring_prov.ttl").write_text(
            self.state["_prov"].serialize("turtle")
        )
        (base / "chronic_monitoring_audit.json").write_text(json.dumps({
            "context_id": ctx,
            "programmatic_checks": programmatic.to_dict() if programmatic else {},
            "narrative_audit": audit_output,
            "overall_passed": programmatic.overall_passed if programmatic else None,
        }, indent=2))
        (base / "chronic_monitoring_metrics.json").write_text(
            json.dumps(self._finalize_metrics(), indent=2)
        )
        print(f"[Chronic] Outputs written to {base}/")

    @staticmethod
    def _default_patient() -> dict:
        return {
            "patient_id":       "P-M318",
            "hr_mean":          "92",
            "bp_systolic_mean": "142",
            "spo2_min":         "91",
            "glucose_fasting":  "168",
            "weight_kg":        "81.4",
            "steps":            "2100",
        }
