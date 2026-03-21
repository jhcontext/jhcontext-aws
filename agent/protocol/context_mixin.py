"""CrewAI ↔ PAC-AI protocol bridge mixin.

Pattern mirrors vendia-agent's ContentGenerationMixin: after each crew step,
persist the envelope + PROV graph via the jhcontext API.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from jhcontext import (
    ArtifactType,
    EnvelopeBuilder,
    PROVGraph,
    RiskLevel,
    compute_content_hash,
    compute_sha256,
)
from jhcontext.client.api_client import JHContextClient
from jhcontext.pii import InMemoryPIIVault

API_URL = os.environ.get("JHCONTEXT_API_URL", "http://localhost:8400")
LARGE_ARTIFACT_THRESHOLD = 100_000  # 100KB


class ContextMixin:
    """Mixin for CrewAI Flows that automatically persists PAC-AI envelopes.

    Usage:
        class MyFlow(Flow, ContextMixin):
            @start()
            def init(self):
                self._init_context(scope="healthcare", producer="did:hospital:system",
                                   risk_level=RiskLevel.HIGH)
    """

    def _init_context(
        self,
        scope: str,
        producer: str,
        risk_level: RiskLevel = RiskLevel.HIGH,
        human_oversight: bool = True,
        feature_suppression: list[str] | None = None,
    ) -> str:
        """Call in @start() — creates initial envelope + PROV.

        If *feature_suppression* is provided, PII detachment is automatically
        enabled — specified fields in the semantic payload will be tokenized
        before signing and persistence.
        """
        builder = EnvelopeBuilder()
        builder.set_producer(producer)
        builder.set_scope(scope)
        builder.set_risk_level(risk_level)
        builder.set_human_oversight(human_oversight)

        # PII detachment setup
        pii_vault = InMemoryPIIVault()
        if feature_suppression:
            builder.set_privacy(feature_suppression=feature_suppression)
            builder.enable_pii_detachment(vault=pii_vault)

        # Build to get context_id
        env = builder.build()
        context_id = env.context_id

        self.state["_builder"] = builder
        self.state["_prov"] = PROVGraph(context_id=context_id)
        self.state["_context_id"] = context_id
        self.state["_api_client"] = JHContextClient(base_url=API_URL)
        self.state["_pii_vault"] = pii_vault
        self.state["_step_artifacts"] = []
        self.state["_metrics"] = {
            "steps": [],
            "total_start": time.time(),
        }

        return context_id

    def _persist_step(
        self,
        step_name: str,
        agent_id: str,
        output: str,
        artifact_type: ArtifactType,
        started_at: str,
        ended_at: str,
        used_artifacts: list[str] | None = None,
    ) -> str:
        """Call after each crew.kickoff() — extends envelope + PROV, persists."""
        t0 = time.time()

        content = output.encode("utf-8")
        content_hash = compute_sha256(content)
        artifact_id = f"art-{step_name}"
        client: JHContextClient = self.state["_api_client"]
        context_id: str = self.state["_context_id"]

        # Upload large artifacts to S3 via artifacts endpoint
        storage_ref = None
        if len(content) > LARGE_ARTIFACT_THRESHOLD:
            resp = client.upload_artifact(
                artifact_id=artifact_id,
                context_id=context_id,
                artifact_type=artifact_type.value,
                content=content,
            )
            storage_ref = resp.get("storage_path")

        # Extend envelope
        builder: EnvelopeBuilder = self.state["_builder"]
        builder.add_artifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content_hash=content_hash,
            storage_ref=storage_ref,
        )
        builder.set_passed_artifact(artifact_id)

        # Extend PROV graph
        prov: PROVGraph = self.state["_prov"]
        prov.add_agent(agent_id, agent_id, role=step_name)
        prov.add_entity(
            artifact_id,
            f"Output of {step_name}",
            artifact_type=artifact_type.value,
            content_hash=content_hash,
        )
        activity_id = f"act-{step_name}"
        prov.add_activity(
            activity_id, step_name, started_at=started_at, ended_at=ended_at
        )
        prov.was_generated_by(artifact_id, activity_id)
        prov.was_associated_with(activity_id, agent_id)

        if used_artifacts:
            for used in used_artifacts:
                prov.used(activity_id, used)
                prov.was_derived_from(artifact_id, used)

        # Sign and persist
        env = builder.sign(agent_id).build()
        client.submit_envelope(env)
        client.submit_prov_graph(context_id, prov.serialize("turtle"))

        # Track step artifacts
        self.state["_step_artifacts"].append(artifact_id)

        # Metrics
        persist_ms = (time.time() - t0) * 1000
        self.state["_metrics"]["steps"].append(
            {
                "step": step_name,
                "agent": agent_id,
                "artifact_id": artifact_id,
                "content_size_bytes": len(content),
                "persist_ms": round(persist_ms, 2),
                "started_at": started_at,
                "ended_at": ended_at,
            }
        )

        return artifact_id

    def _persist_task_callback(self, output) -> None:
        """Non-blocking task-level persistence via CrewAI task_callback.

        Pass this as `task_callback` on Crew to record each task output
        as an auditable artifact without blocking the next task.
        """
        def _do_persist():
            desc = getattr(output, "description", "task")[:30].replace(" ", "_")
            raw = getattr(output, "raw", str(output))
            agent_name = getattr(output, "agent", "unknown")

            artifact_id = f"art-task-{desc}"
            content = raw.encode("utf-8")
            content_hash = compute_sha256(content)

            builder: EnvelopeBuilder = self.state["_builder"]
            builder.add_artifact(
                artifact_id=artifact_id,
                artifact_type=ArtifactType.TOKEN_SEQUENCE,
                content_hash=content_hash,
            )

            prov: PROVGraph = self.state["_prov"]
            prov.add_entity(
                artifact_id,
                f"Task output: {desc}",
                artifact_type="token_sequence",
                content_hash=content_hash,
            )

        threading.Thread(target=_do_persist, daemon=True).start()

    def _get_latest_context(self) -> dict[str, Any]:
        """Call at start of each step — retrieves latest envelope from API."""
        client: JHContextClient = self.state["_api_client"]
        context_id: str = self.state["_context_id"]
        return client.get_envelope(context_id)

    def _log_decision(
        self,
        outcome: dict[str, Any],
        agent_id: str,
    ) -> str:
        """Log a decision via the API."""
        client: JHContextClient = self.state["_api_client"]
        context_id: str = self.state["_context_id"]
        artifacts = self.state.get("_step_artifacts", [])
        passed = artifacts[-1] if artifacts else None
        return client.log_decision(
            context_id=context_id,
            passed_artifact_id=passed,
            outcome=outcome,
            agent_id=agent_id,
        )

    def _finalize_metrics(self) -> dict[str, Any]:
        """Call at end of flow to collect timing metrics."""
        metrics = self.state["_metrics"]
        metrics["total_ms"] = round((time.time() - metrics["total_start"]) * 1000, 2)
        metrics.pop("total_start", None)
        metrics["context_id"] = self.state["_context_id"]
        return metrics

    def _cleanup(self) -> None:
        """Close API client."""
        client = self.state.get("_api_client")
        if client:
            client.close()
