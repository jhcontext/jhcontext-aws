"""Envelope route handlers."""

from __future__ import annotations

from chalice import NotFoundError, Response

from jhcontext.models import Envelope
from jhcontext.pii import DefaultPIIDetector, detach_pii


def submit_envelope(app, storage, pii_vault=None):
    body = app.current_request.json_body
    data = body.get("envelope", body)
    data.pop("@context", None)
    data.pop("@type", None)
    envelope = Envelope.model_validate(data)

    # Enforce PII detachment if feature_suppression is set
    if envelope.privacy.feature_suppression and not envelope.privacy.pii_detached and pii_vault:
        detector = DefaultPIIDetector(
            suppressed_fields=envelope.privacy.feature_suppression,
        )
        envelope.semantic_payload = detach_pii(
            envelope.semantic_payload,
            envelope.context_id,
            detector,
            pii_vault,
        )
        envelope.privacy.pii_detached = True

    context_id = storage.save_envelope(envelope)
    return Response(
        body={"context_id": context_id, "content_hash": envelope.proof.content_hash},
        status_code=201,
    )


def get_envelope(app, storage, context_id: str):
    envelope = storage.get_envelope(context_id)
    if not envelope:
        raise NotFoundError("Envelope not found")
    return envelope.to_jsonld()


def list_envelopes(app, storage):
    params = app.current_request.query_params or {}
    filters = {}
    if "scope" in params:
        filters["scope"] = params["scope"]
    if "risk_level" in params:
        filters["risk_level"] = params["risk_level"]
    envelopes = storage.list_envelopes(**filters)
    return [
        {"context_id": e.context_id, "scope": e.scope, "created_at": e.created_at}
        for e in envelopes
    ]


def purge_pii(app, pii_vault, context_id: str):
    """Purge all PII associated with a context (GDPR Art. 17 erasure)."""
    if not pii_vault:
        return Response(body={"error": "PII vault not configured"}, status_code=501)
    deleted = pii_vault.purge_by_context(context_id)
    return {"context_id": context_id, "tokens_purged": deleted}
