"""Envelope route handlers."""

from __future__ import annotations

from chalice import NotFoundError, Response

from jhcontext.models import Envelope


def submit_envelope(app, storage):
    body = app.current_request.json_body
    data = body.get("envelope", body)
    data.pop("@context", None)
    data.pop("@type", None)
    envelope = Envelope.model_validate(data)
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
