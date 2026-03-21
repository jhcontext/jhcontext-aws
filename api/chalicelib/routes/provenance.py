"""Provenance route handlers."""

from __future__ import annotations

from chalice import BadRequestError, NotFoundError, Response

from jhcontext.crypto import compute_sha256
from jhcontext.prov import PROVGraph


def submit_prov_graph(app, storage):
    body = app.current_request.json_body
    context_id = body["context_id"]
    graph_turtle = body["graph_turtle"]
    digest = compute_sha256(graph_turtle.encode("utf-8"))
    path = storage.save_prov_graph(context_id, graph_turtle, digest)
    return Response(
        body={"context_id": context_id, "digest": digest, "path": path},
        status_code=201,
    )


def get_prov_graph(app, storage, context_id: str):
    turtle = storage.get_prov_graph(context_id)
    if not turtle:
        raise NotFoundError("PROV graph not found")
    return {"context_id": context_id, "graph_turtle": turtle}


def query_provenance(app, storage):
    body = app.current_request.json_body
    context_id = body["context_id"]
    query_type = body["query_type"]
    entity_id = body.get("entity_id")

    turtle = storage.get_prov_graph(context_id)
    if not turtle:
        raise NotFoundError("PROV graph not found")

    prov = PROVGraph(context_id=context_id)
    prov._graph.parse(data=turtle, format="turtle")

    if query_type == "causal_chain" and entity_id:
        chain = prov.get_causal_chain(entity_id)
        return {"query_type": "causal_chain", "entity_id": entity_id, "chain": chain}
    elif query_type == "used_entities" and entity_id:
        used = prov.get_used_entities(entity_id)
        return {"query_type": "used_entities", "activity_id": entity_id, "entities": used}
    elif query_type == "temporal_sequence":
        seq = prov.get_temporal_sequence()
        return {"query_type": "temporal_sequence", "activities": seq}
    else:
        raise BadRequestError(f"Unknown query_type: {query_type}")
