"""Artifact route handlers."""

from __future__ import annotations

import base64

from chalice import NotFoundError, Response

from jhcontext.models import Artifact, ArtifactType
from jhcontext.crypto import compute_sha256


def upload_artifact(app, storage):
    body = app.current_request.json_body
    content = base64.b64decode(body["content_base64"])
    content_hash = compute_sha256(content)
    metadata = Artifact(
        artifact_id=body["artifact_id"],
        type=ArtifactType(body["artifact_type"]),
        content_hash=content_hash,
        model=body.get("model"),
        deterministic=body.get("deterministic", False),
        metadata={"context_id": body["context_id"]},
    )
    path = storage.save_artifact(body["artifact_id"], content, metadata)
    return Response(
        body={
            "artifact_id": body["artifact_id"],
            "content_hash": content_hash,
            "storage_path": path,
        },
        status_code=201,
    )


def get_artifact(app, storage, artifact_id: str):
    result = storage.get_artifact(artifact_id)
    if not result:
        raise NotFoundError("Artifact not found")
    content, metadata = result
    return {
        "artifact_id": metadata.artifact_id,
        "type": metadata.type.value,
        "content_hash": metadata.content_hash,
        "content_base64": base64.b64encode(content).decode("utf-8"),
    }
