"""jhcontext-mcp — Chalice HTTP proxy for MCP tools on AWS Lambda.

Wraps the jhcontext MCP server's tool handlers in a REST endpoint.
Deployed as a separate Lambda to keep the API Lambda lightweight.
"""

from __future__ import annotations

import asyncio
import json

from chalice import Chalice, BadRequestError

app = Chalice(app_name="jhcontext-mcp")

_storage = None


def get_storage():
    global _storage
    if _storage is None:
        from chalicelib.dynamodb_storage import DynamoDBStorage
        _storage = DynamoDBStorage()
    return _storage


@app.route("/health", methods=["GET"], cors=True)
def health():
    return {"status": "ok", "service": "jhcontext-mcp"}


@app.route("/mcp", methods=["POST"], cors=True)
def mcp_tool_call():
    """HTTP proxy for MCP tool calls.

    Request body:
        {"tool_name": "submit_envelope", "arguments": {...}}

    Response:
        {"result": [...]}  (MCP TextContent list)
    """
    body = app.current_request.json_body
    tool_name = body.get("tool_name")
    arguments = body.get("arguments", {})

    if not tool_name:
        raise BadRequestError("Missing tool_name")

    result = asyncio.get_event_loop().run_until_complete(
        _call_tool(tool_name, arguments)
    )
    return {"result": result}


async def _call_tool(tool_name: str, arguments: dict) -> list[dict]:
    """Execute an MCP tool using the jhcontext SDK's MCP server logic."""
    from jhcontext.models import Envelope
    from jhcontext.prov import PROVGraph
    from jhcontext.audit import (
        verify_integrity,
        generate_audit_report,
    )
    from jhcontext.crypto import compute_sha256

    storage = get_storage()

    if tool_name == "submit_envelope":
        data = json.loads(arguments["envelope_json"])
        data.pop("@context", None)
        data.pop("@type", None)
        envelope = Envelope.model_validate(data)
        context_id = storage.save_envelope(envelope)
        return [{"type": "text", "text": json.dumps({"context_id": context_id})}]

    elif tool_name == "get_envelope":
        envelope = storage.get_envelope(arguments["context_id"])
        if not envelope:
            return [{"type": "text", "text": '{"error": "not found"}'}]
        return [{"type": "text", "text": json.dumps(envelope.to_jsonld())}]

    elif tool_name == "submit_prov_graph":
        turtle = arguments["graph_turtle"]
        digest = compute_sha256(turtle.encode("utf-8"))
        storage.save_prov_graph(arguments["context_id"], turtle, digest)
        return [{"type": "text", "text": json.dumps({"digest": digest})}]

    elif tool_name == "query_provenance":
        turtle = storage.get_prov_graph(arguments["context_id"])
        if not turtle:
            return [{"type": "text", "text": '{"error": "PROV graph not found"}'}]
        prov = PROVGraph(context_id=arguments["context_id"])
        prov._graph.parse(data=turtle, format="turtle")

        qt = arguments["query_type"]
        eid = arguments.get("entity_id")
        if qt == "causal_chain" and eid:
            result = prov.get_causal_chain(eid)
        elif qt == "used_entities" and eid:
            result = prov.get_used_entities(eid)
        elif qt == "temporal_sequence":
            result = prov.get_temporal_sequence()
        else:
            result = {"error": f"Unknown query_type: {qt}"}
        return [{"type": "text", "text": json.dumps(result, default=str)}]

    elif tool_name == "run_audit":
        envelope = storage.get_envelope(arguments["context_id"])
        if not envelope:
            return [{"type": "text", "text": '{"error": "Envelope not found"}'}]

        turtle = storage.get_prov_graph(arguments["context_id"])
        prov = PROVGraph(context_id=arguments["context_id"])
        if turtle:
            prov._graph.parse(data=turtle, format="turtle")

        results = []
        for check in arguments.get("checks", []):
            if check == "integrity":
                results.append(verify_integrity(envelope))
        report = generate_audit_report(envelope, prov, results)
        return [{"type": "text", "text": json.dumps(report.to_dict())}]

    return [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}]
