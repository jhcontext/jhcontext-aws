"""DynamoDB + S3 storage backend implementing jhcontext StorageBackend Protocol."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from jhcontext.models import Artifact, ArtifactType, Decision, Envelope


# Table names from environment (set in .chalice/config.json)
ENVELOPES_TABLE = os.environ.get("DYNAMODB_ENVELOPES_TABLE", "jhcontext-envelopes")
ARTIFACTS_TABLE = os.environ.get("DYNAMODB_ARTIFACTS_TABLE", "jhcontext-artifacts")
PROV_TABLE = os.environ.get("DYNAMODB_PROV_TABLE", "jhcontext-prov-graphs")
DECISIONS_TABLE = os.environ.get("DYNAMODB_DECISIONS_TABLE", "jhcontext-decisions")
S3_BUCKET = os.environ.get("S3_ARTIFACTS_BUCKET", "jhcontext-artifacts-dev")


class DynamoDBStorage:
    """DynamoDB + S3 storage backend for jhcontext server.

    Implements the StorageBackend Protocol from jhcontext.server.storage.
    Envelopes, PROV graphs, and decisions go to DynamoDB.
    Artifact binary content goes to S3, metadata to DynamoDB.
    """

    def __init__(
        self,
        dynamodb_resource=None,
        s3_client=None,
    ) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._s3 = s3_client or boto3.client("s3")

        self._envelopes = self._dynamodb.Table(ENVELOPES_TABLE)
        self._artifacts = self._dynamodb.Table(ARTIFACTS_TABLE)
        self._prov = self._dynamodb.Table(PROV_TABLE)
        self._decisions = self._dynamodb.Table(DECISIONS_TABLE)

    # ── Envelopes ──────────────────────────────────────────────────

    def save_envelope(self, envelope: Envelope) -> str:
        item = {
            "context_id": envelope.context_id,
            "envelope_json": json.dumps(envelope.to_jsonld()),
            "scope": envelope.scope or "default",
            "risk_level": envelope.compliance.risk_level.value,
            "status": envelope.status.value,
            "created_at": envelope.created_at,
        }
        if envelope.proof.content_hash:
            item["content_hash"] = envelope.proof.content_hash
        if envelope.proof.signature:
            item["signature"] = envelope.proof.signature
        if envelope.proof.signer:
            item["signer"] = envelope.proof.signer
        if envelope.ttl:
            item["ttl"] = envelope.ttl

        self._envelopes.put_item(Item=item)
        return envelope.context_id

    def get_envelope(self, context_id: str) -> Envelope | None:
        resp = self._envelopes.get_item(Key={"context_id": context_id})
        item = resp.get("Item")
        if not item:
            return None
        data = json.loads(item["envelope_json"])
        data.pop("@context", None)
        data.pop("@type", None)
        return Envelope.model_validate(data)

    def list_envelopes(self, **filters: Any) -> list[Envelope]:
        # For a prototype, scan with filters. Production would use GSIs.
        scan_kwargs: dict[str, Any] = {}
        filter_parts: list[str] = []
        expr_values: dict[str, Any] = {}
        expr_names: dict[str, str] = {}

        if "scope" in filters:
            filter_parts.append("#s = :scope")
            expr_values[":scope"] = filters["scope"]
            expr_names["#s"] = "scope"
        if "risk_level" in filters:
            filter_parts.append("risk_level = :rl")
            expr_values[":rl"] = filters["risk_level"]
        if "status" in filters:
            filter_parts.append("#st = :status")
            expr_values[":status"] = filters["status"]
            expr_names["#st"] = "status"

        if filter_parts:
            scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
            scan_kwargs["ExpressionAttributeValues"] = expr_values
        if expr_names:
            scan_kwargs["ExpressionAttributeNames"] = expr_names

        resp = self._envelopes.scan(**scan_kwargs)
        envelopes = []
        for item in resp.get("Items", []):
            data = json.loads(item["envelope_json"])
            data.pop("@context", None)
            data.pop("@type", None)
            envelopes.append(Envelope.model_validate(data))
        return sorted(envelopes, key=lambda e: e.created_at, reverse=True)

    # ── Artifacts ──────────────────────────────────────────────────

    def save_artifact(self, artifact_id: str, content: bytes, metadata: Artifact) -> str:
        s3_key = f"artifacts/{artifact_id}"
        self._s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType="application/octet-stream",
        )

        item = {
            "artifact_id": artifact_id,
            "artifact_type": metadata.type.value,
            "content_hash": metadata.content_hash or "",
            "s3_key": s3_key,
            "s3_bucket": S3_BUCKET,
            "deterministic": metadata.deterministic,
            "created_at": metadata.timestamp,
        }
        if metadata.model:
            item["model"] = metadata.model
        context_id = metadata.metadata.get("context_id")
        if context_id:
            item["context_id"] = context_id

        self._artifacts.put_item(Item=item)
        return f"s3://{S3_BUCKET}/{s3_key}"

    def get_artifact(self, artifact_id: str) -> tuple[bytes, Artifact] | None:
        resp = self._artifacts.get_item(Key={"artifact_id": artifact_id})
        item = resp.get("Item")
        if not item:
            return None

        s3_resp = self._s3.get_object(
            Bucket=item["s3_bucket"],
            Key=item["s3_key"],
        )
        content = s3_resp["Body"].read()

        artifact = Artifact(
            artifact_id=item["artifact_id"],
            type=ArtifactType(item["artifact_type"]),
            content_hash=item.get("content_hash"),
            storage_ref=f"s3://{item['s3_bucket']}/{item['s3_key']}",
            model=item.get("model"),
            deterministic=item.get("deterministic", False),
            timestamp=item.get("created_at", ""),
        )
        return content, artifact

    # ── PROV Graphs ────────────────────────────────────────────────

    def save_prov_graph(self, context_id: str, graph_turtle: str, digest: str) -> str:
        # Store Turtle in DynamoDB (typically <10KB for our scenarios).
        # If >400KB, would need S3 — but healthcare PROV is ~5KB.
        item = {
            "context_id": context_id,
            "graph_turtle": graph_turtle,
            "graph_digest": digest,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._prov.put_item(Item=item)
        return context_id

    def get_prov_graph(self, context_id: str) -> str | None:
        resp = self._prov.get_item(Key={"context_id": context_id})
        item = resp.get("Item")
        return item["graph_turtle"] if item else None

    # ── Decisions ──────────────────────────────────────────────────

    def save_decision(self, decision: Decision) -> str:
        item = {
            "decision_id": decision.decision_id,
            "context_id": decision.context_id,
            "outcome": json.dumps(decision.outcome),
            "agent_id": decision.agent_id,
            "created_at": decision.created_at,
        }
        if decision.passed_artifact_id:
            item["passed_artifact_id"] = decision.passed_artifact_id

        self._decisions.put_item(Item=item)
        return decision.decision_id

    def get_decision(self, decision_id: str) -> Decision | None:
        resp = self._decisions.get_item(Key={"decision_id": decision_id})
        item = resp.get("Item")
        if not item:
            return None
        return Decision(
            decision_id=item["decision_id"],
            context_id=item["context_id"],
            passed_artifact_id=item.get("passed_artifact_id"),
            outcome=json.loads(item["outcome"]) if item.get("outcome") else {},
            agent_id=item.get("agent_id", ""),
            created_at=item.get("created_at", ""),
        )
