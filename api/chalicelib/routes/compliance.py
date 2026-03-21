"""Compliance route handlers."""

from __future__ import annotations

import base64
import io
import json
import zipfile

from chalice import NotFoundError, Response

from jhcontext.audit import generate_audit_report, verify_integrity
from jhcontext.prov import PROVGraph


def export_compliance_package(app, storage, context_id: str):
    envelope = storage.get_envelope(context_id)
    if not envelope:
        raise NotFoundError("Envelope not found")

    turtle = storage.get_prov_graph(context_id)

    integrity_result = verify_integrity(envelope)
    prov = PROVGraph(context_id=context_id)
    if turtle:
        prov._graph.parse(data=turtle, format="turtle")

    report = generate_audit_report(envelope, prov, [integrity_result])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("envelope.json", json.dumps(envelope.to_jsonld(), indent=2))
        if turtle:
            zf.writestr("provenance.ttl", turtle)
        zf.writestr("audit_report.json", json.dumps(report.to_dict(), indent=2))
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "context_id": context_id,
                    "envelope_hash": envelope.proof.content_hash,
                    "prov_digest": prov.digest() if turtle else None,
                    "pii_status": {
                        "detached": envelope.privacy.pii_detached,
                        "feature_suppression": envelope.privacy.feature_suppression,
                    },
                    "generated_at": report.timestamp,
                },
                indent=2,
            ),
        )
    buf.seek(0)

    # Chalice doesn't support StreamingResponse — return base64-encoded ZIP
    return Response(
        body=base64.b64encode(buf.read()).decode("utf-8"),
        status_code=200,
        headers={
            "Content-Type": "application/zip",
            "Content-Disposition": f"attachment; filename=compliance_{context_id}.zip",
            "Content-Transfer-Encoding": "base64",
        },
    )
