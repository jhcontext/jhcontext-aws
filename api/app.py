"""jhcontext-api — Chalice REST API for PAC-AI protocol on AWS."""

from chalice import Chalice

from chalicelib.routes import envelopes, artifacts, provenance, decisions, compliance

app = Chalice(app_name="jhcontext-api")


# ── Storage singleton ──────────────────────────────────────────────

_storage = None


def get_storage():
    """Lazy-init DynamoDB storage backend (singleton per Lambda container)."""
    global _storage
    if _storage is None:
        from chalicelib.storage.dynamodb import DynamoDBStorage
        _storage = DynamoDBStorage()
    return _storage


# ── Health ─────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"], cors=True)
def health():
    import os
    return {
        "status": "ok",
        "service": "jhcontext-api",
        "version": os.environ.get("JHCONTEXT_VERSION", "0.1.0"),
    }


# ── Envelopes ──────────────────────────────────────────────────────

@app.route("/envelopes", methods=["GET", "POST"], cors=True)
def envelopes_root():
    if app.current_request.method == "POST":
        return envelopes.submit_envelope(app, get_storage())
    return envelopes.list_envelopes(app, get_storage())


@app.route("/envelopes/{context_id}", methods=["GET"], cors=True)
def get_envelope(context_id):
    return envelopes.get_envelope(app, get_storage(), context_id)


# ── Artifacts ──────────────────────────────────────────────────────

@app.route("/artifacts", methods=["POST"], cors=True)
def artifacts_root():
    return artifacts.upload_artifact(app, get_storage())


@app.route("/artifacts/{artifact_id}", methods=["GET"], cors=True)
def get_artifact(artifact_id):
    return artifacts.get_artifact(app, get_storage(), artifact_id)


# ── Provenance ─────────────────────────────────────────────────────

@app.route("/provenance", methods=["POST"], cors=True)
def submit_prov_graph():
    return provenance.submit_prov_graph(app, get_storage())


@app.route("/provenance/{context_id}", methods=["GET"], cors=True)
def get_prov_graph(context_id):
    return provenance.get_prov_graph(app, get_storage(), context_id)


@app.route("/provenance/query", methods=["POST"], cors=True)
def query_provenance():
    return provenance.query_provenance(app, get_storage())


# ── Decisions ──────────────────────────────────────────────────────

@app.route("/decisions", methods=["POST"], cors=True)
def decisions_root():
    return decisions.log_decision(app, get_storage())


@app.route("/decisions/{decision_id}", methods=["GET"], cors=True)
def get_decision(decision_id):
    return decisions.get_decision(app, get_storage(), decision_id)


# ── Compliance ─────────────────────────────────────────────────────

@app.route("/compliance/package/{context_id}", methods=["GET"], cors=True)
def export_compliance_package(context_id):
    return compliance.export_compliance_package(app, get_storage(), context_id)
