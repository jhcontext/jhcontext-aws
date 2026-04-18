"""CHW Mental-Health Screening (offline flow).

Pipeline: PHQ-9 interview → risk classification → referral
          → district-specialist supervisor review (async, post-sync)
          → programmatic + narrative audit.

CHW visits occur offline on a tablet; envelopes queue locally and sync
on return to clinic. Time-to-review is recorded as an auditable
programme-evaluation metric.
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from agent.crews.chw_mental_health.crew import (
    CHWMentalHealthAuditCrew,
    CHWMentalHealthClinicalCrew,
    CHWMentalHealthOversightCrew,
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


SPECIALIST_REVIEW_ACTIVITIES = [
    ("act-review-phq9",      "Review PHQ-9 structured result",
     "art-interview-structured", "Structured PHQ-9 interpretation", 3),
    ("act-review-risk",      "Review risk classification",
     "art-risk-classification",  "Risk classification output",      2),
    ("act-review-referral",  "Review referral recommendation",
     "art-referral",             "Referral recommendation",         1),
]


class CHWMentalHealthFlow(Flow, OfflineContextMixin):
    """Offline-first flow for the CHW mental-health screening pipeline."""

    @start()
    def init(self):
        _out.current.mkdir(parents=True, exist_ok=True)
        queue_path = _out.current / "chw_mental_health_queue.sqlite"
        context_id = self._init_context(
            scope="chw_mental_health_screening",
            producer="did:chw:interview-agent",
            risk_level=RiskLevel.HIGH,
            human_oversight=True,
            queue_path=queue_path,
            # Programme-excluded variables for negative-proof verification
            feature_suppression=["ethnicity", "religion", "household_income"],
        )

        self._register_crew(
            crew_id="crew:chw-mh-pipeline",
            label="CHW Mental-Health Screening Crew",
            agent_ids=[
                "did:chw:interview-agent",
                "did:chw:risk-classifier",
                "did:chw:referral-agent",
            ],
        )

        print(f"[CHW-MH] Initialized context: {context_id}")
        print(f"[CHW-MH] Offline queue: {queue_path}")
        return self.state.get("patient_input", self._default_patient())

    @listen(init)
    def clinical_pipeline(self, input_data):
        print("[CHW-MH] Steps 1-3: clinical pipeline (offline enqueue)...")
        clinical = CHWMentalHealthClinicalCrew()
        crew_instance = clinical.crew()
        crew_instance.task_callback = self._persist_task_callback

        preamble = self.state["_forwarding_preamble"]
        result = crew_instance.kickoff(inputs={
            **input_data,
            "_forwarding_preamble": preamble,
        })

        self._log_decision(
            outcome={"referral": result.raw[:200], "requires_oversight": True},
            agent_id="did:chw:referral-agent",
        )
        return result.raw

    @listen(clinical_pipeline)
    def specialist_oversight(self, referral_output):
        print("[CHW-MH] Step 4: District specialist async review...")

        events = []
        overall_t0 = datetime.now(timezone.utc)
        for event_id, label, entity_id, entity_label, duration in SPECIALIST_REVIEW_ACTIVITIES:
            t0 = datetime.now(timezone.utc)
            _time.sleep(duration)
            t1 = datetime.now(timezone.utc)
            events.append({
                "event_id": event_id, "label": label,
                "started_at": t0.isoformat(), "ended_at": t1.isoformat(),
                "accessed_entity": entity_id, "entity_label": entity_label,
            })

        result = CHWMentalHealthOversightCrew().crew().kickoff(
            inputs={"recommendation": referral_output}
        )
        overall_t1 = datetime.now(timezone.utc)

        # Programme-evaluation metric
        self.state["_time_to_review_seconds"] = (
            overall_t1 - overall_t0
        ).total_seconds()

        self._persist_oversight_events(
            events=events,
            oversight_agent_id="did:district:dr-matumbo",
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
                    agent_id="did:district:dr-matumbo",
                    alternatives=alternatives,
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        return result.raw

    @listen(specialist_oversight)
    def compliance_audit(self, oversight_output):
        print("[CHW-MH] Step 5: Compliance audit...")

        prov = self.state["_prov"]
        builder = self.state["_builder"]

        human_activities = [e[0] for e in SPECIALIST_REVIEW_ACTIVITIES]
        temporal = verify_temporal_oversight(
            prov=prov, ai_activity_id="act-risk-classification",
            human_activities=human_activities,
            min_review_seconds=3.0,
        )
        env = builder.sign("did:district:audit-agent").build()
        integrity = verify_integrity(env)
        pii = verify_pii_detachment(env)
        negative = verify_negative_proof(
            prov=prov, decision_entity_id="art-risk-classification",
            excluded_artifact_types=["ethnicity", "religion", "household_income"],
        )

        programmatic = generate_audit_report(
            env, prov, [temporal, integrity, pii, negative],
        )
        print(f"[CHW-MH] temporal: {'PASS' if temporal.passed else 'FAIL'} | "
              f"integrity: {'PASS' if integrity.passed else 'FAIL'} | "
              f"pii: {'PASS' if pii.passed else 'FAIL'} | "
              f"negative: {'PASS' if negative.passed else 'FAIL'}")

        t0 = datetime.now(timezone.utc)
        result = CHWMentalHealthAuditCrew().crew().kickoff(inputs={
            "oversight_report": oversight_output,
            "context_id": self.state["_context_id"],
        })
        t1 = datetime.now(timezone.utc)

        self._persist_step(
            step_name="audit",
            agent_id="did:district:audit-agent",
            output=result.raw,
            artifact_type=ArtifactType.TOOL_RESULT,
            started_at=t0.isoformat(), ended_at=t1.isoformat(),
            used_artifacts=[
                "art-oversight", "art-referral",
                "art-risk-classification", "art-interview-structured",
            ],
        )

        self._save_outputs(result.raw, programmatic)
        return result.raw

    # ------------------------------------------------------------------
    def _save_outputs(self, audit_output: str, programmatic) -> None:
        ctx = self.state["_context_id"]
        base = _out.current
        (base / "chw_mental_health_envelopes.json").write_text(
            json.dumps(self.state["_task_envelopes"], indent=2)
        )
        (base / "chw_mental_health_prov.ttl").write_text(
            self.state["_prov"].serialize("turtle")
        )
        (base / "chw_mental_health_audit.json").write_text(json.dumps({
            "context_id": ctx,
            "programmatic_checks": programmatic.to_dict() if programmatic else {},
            "narrative_audit": audit_output,
            "overall_passed": programmatic.overall_passed if programmatic else None,
            "time_to_review_seconds": self.state.get("_time_to_review_seconds"),
        }, indent=2))
        (base / "chw_mental_health_metrics.json").write_text(
            json.dumps(self._finalize_metrics(), indent=2)
        )
        print(f"[CHW-MH] Outputs written to {base}/")

    @staticmethod
    def _default_patient() -> dict:
        return {
            "patient_id":  "P-CHW0042",
            "phq9_total":  "19",
            "phq9_item_9": "2",
            "language":    "sw-TZ",
        }
