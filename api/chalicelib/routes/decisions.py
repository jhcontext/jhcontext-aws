"""Decision route handlers."""

from __future__ import annotations

from chalice import NotFoundError, Response

from jhcontext.models import Decision


def log_decision(app, storage):
    body = app.current_request.json_body
    decision = Decision(
        context_id=body["context_id"],
        passed_artifact_id=body.get("passed_artifact_id"),
        outcome=body.get("outcome", {}),
        agent_id=body.get("agent_id", ""),
    )
    decision_id = storage.save_decision(decision)
    return Response(body={"decision_id": decision_id}, status_code=201)


def get_decision(app, storage, decision_id: str):
    decision = storage.get_decision(decision_id)
    if not decision:
        raise NotFoundError("Decision not found")
    return decision.model_dump()
