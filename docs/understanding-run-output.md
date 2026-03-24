# Understanding Crew Execution Output

When you run a scenario (`python -m agent.run --local --scenario all`), each crew
produces a set of files in `output/latest/` (and `output/runs/vNN/`). After all
scenarios complete, `--validate` generates a validation report and summary.

This guide explains how to read each file type and what to look for.

## Output Files per Scenario

| Scenario | Envelope | PROV Graph(s) | Audit | Metrics | Other |
|----------|----------|---------------|-------|---------|-------|
| Healthcare | `healthcare_envelope.json` | `healthcare_prov.ttl` | `healthcare_audit.json` | `healthcare_metrics.json` | — |
| Education | `education_grading_envelope.json` | `education_grading_prov.ttl`, `education_equity_prov.ttl` | `education_audit.json` | `education_grading_metrics.json` | — |
| Recommendation | `recommendation_envelope.json` | `recommendation_prov.ttl` | — | `recommendation_metrics.json` | `recommendation_output.json` |

Cross-scenario files: `validation_report.json`, `summary.md`.

## Reading the Envelope (`*_envelope.json`)

The envelope is the core protocol artifact. Key sections:

```
{
  "context_id": "ctx-...",          ← unique ID linking all files for this run
  "schema_version": "jh:0.3",
  "producer": "did:hospital:...",   ← DID of the system that created it
  "scope": "healthcare_...",        ← what domain this envelope covers

  "semantic_payload": [...],        ← structured UserML data (may be [] if LLM
                                       didn't produce valid format — see
                                       semantic_conformance check)

  "artifacts_registry": [           ← every artifact each agent produced
    {
      "artifact_id": "art-sensor",
      "type": "token_sequence",     ← artifact type (token_sequence, semantic_extraction, tool_result)
      "content_hash": "sha256:...", ← tamper-detection hash
      "timestamp": "...",           ← when this artifact was created
    }
  ],

  "passed_artifact_pointer": "art-audit",  ← final output of the pipeline

  "decision_influence": [...],      ← which agents influenced the decision,
                                       what data categories they used

  "privacy": {                      ← GDPR metadata
    "data_category": "behavioral",
    "legal_basis": "consent",
    "retention": "P7D",             ← 7-day retention
  },

  "compliance": {                   ← regulatory classification
    "risk_level": "high",           ← HIGH requires semantic_forward + oversight
    "human_oversight_required": true,
    "forwarding_policy": "semantic_forward"
  },

  "proof": {                        ← cryptographic seal
    "content_hash": "sha256:...",   ← hash of envelope contents
    "signature": "base64:...",      ← Ed25519 signature
    "signer": "did:hospital:..."    ← who signed it
  }
}
```

**What to check:**
- `artifacts_registry` should have one entry per pipeline step (e.g., 5 for healthcare)
- `content_hash` values should be unique per artifact (no duplicates = no empty outputs)
- `compliance.risk_level` should match expected (high for healthcare/education, low for
  recommendation)
- `semantic_payload` — if empty (`[]`), the `semantic_conformance` validation check will
  FAIL. This means the LLM produced free-form text instead of structured UserML.

## Reading the PROV Graph (`*_prov.ttl`)

Turtle RDF format. Three node types to look for:

### Agents (`prov:Agent`)
```turtle
<did:hospital:sensor-agent> a prov:Agent ;
    rdfs:label "did:hospital:sensor-agent" ;
    jh:role "sensor" .
```
Each agent has a DID identifier and a role. Count agents to verify all pipeline
participants are recorded.

### Activities (`prov:Activity`)
```turtle
jh:act-situation a prov:Activity ;
    rdfs:label "situation" ;
    prov:startedAtTime "2026-03-24T13:13:26..."^^xsd:dateTime ;
    prov:endedAtTime "2026-03-24T13:13:26..."^^xsd:dateTime ;
    prov:used jh:art-sensor ;
    prov:wasAssociatedWith <did:hospital:situation-agent> .
```
**What to check:**
- `wasAssociatedWith` links the activity to its agent
- `used` shows what inputs were consumed (dependency chain)
- `startedAtTime`/`endedAtTime` provide temporal evidence — for healthcare, verify
  oversight activities start AFTER `act-decision`

### Entities (`prov:Entity`)
```turtle
jh:art-situation a prov:Entity ;
    rdfs:label "Task output: situation" ;
    prov:wasDerivedFrom jh:art-sensor ;
    prov:wasGeneratedBy jh:act-situation ;
    jh:contentHash "9ed190..." .
```
**What to check:**
- `wasGeneratedBy` links the entity to its producing activity
- `wasDerivedFrom` traces the dependency chain (what inputs produced this output)
- `jh:contentHash` should match the corresponding entry in the envelope's
  `artifacts_registry`

### Healthcare-Specific: Oversight Events

The healthcare PROV includes fine-grained document access activities:
```turtle
jh:act-access-ct-scan a prov:Activity ;
    prov:startedAtTime "..."^^xsd:dateTime ;
    prov:endedAtTime "..."^^xsd:dateTime ;
    prov:used jh:ent-ct-scan ;
    prov:wasAssociatedWith <did:hospital:dr-chen> .
```
These prove the physician accessed each source document with timestamps. The
`temporal_oversight` check verifies all these occur AFTER `act-decision`.

### Education-Specific: Isolation

Two separate `.ttl` files with **zero shared entity URIs**. The `workflow_isolation`
check compares entity sets across both graphs. If any `jh:art-*` URI appears in both
files, isolation is broken.

## Reading the Audit (`*_audit.json`)

Audit files have two sections:

### Programmatic Checks (SDK-verified)
```json
{
  "programmatic_checks": {
    "results": [
      {
        "check_name": "temporal_oversight",
        "passed": true,
        "evidence": {
          "ai_timestamp": "...",
          "human_activities_after_ai": ["act-access-ct-scan", ...],
          "total_review_seconds": 10.0,
          "min_required_seconds": 5.0
        },
        "message": "Human oversight verified: 4/4 activities after AI, 10s review time"
      }
    ]
  }
}
```

**Reading evidence fields:**
- `temporal_oversight`: Look at `total_review_seconds` vs `min_required_seconds`.
  In production, min should be 300s (5 minutes). The simulated minimum is 5s.
- `integrity`: `has_signature: true` but `passed: false` means the envelope was modified
  after signing (expected when the audit step adds artifacts post-signature).
- `workflow_isolation`: `shared_entities: []` means zero overlap (PASS).
- `negative_proof`: `violations: []` means no identity artifacts in grading chain (PASS).

### Narrative Audit (LLM-generated)
```json
{
  "narrative_audit": "# EU AI Act Article 14 Compliance Audit Report\n..."
}
```

A detailed, human-readable report produced by the audit agent. For healthcare, this
includes the full decision chain reconstruction with timestamps, temporal verification,
and compliance assessment. This is the artifact that would go to a regulatory auditor.

## Reading the Metrics (`*_metrics.json`)

```json
{
  "context_id": "ctx-...",
  "total_ms": 169053.25,
  "steps": [
    {
      "step": "sensor",
      "agent": "did:hospital:sensor-agent",
      "artifact_id": "art-sensor",
      "content_size_bytes": 653,
      "persist_ms": 0,
      "started_at": "2026-03-24T13:13:20...",
      "ended_at": "2026-03-24T13:13:20..."
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `total_ms` | Wall-clock time for the entire flow (init → last step) |
| `step` | Pipeline step name (matches agent task name) |
| `content_size_bytes` | Size of the agent's output (larger = more detailed response) |
| `persist_ms` | Time spent saving to backend API (0 = async/background persist) |
| `started_at` / `ended_at` | LLM call timestamps (same = CrewAI didn't expose real duration) |

**What to look for:**
- `total_ms` gives the end-to-end flow duration (healthcare ~170s, recommendation ~35s)
- `persist_ms > 0` only shows for steps that persist synchronously (usually the last step)
- Large `content_size_bytes` gaps between steps may indicate the LLM produced very
  different output lengths

## Reading the Validation Report (`validation_report.json`)

Machine-readable report covering all three scenarios:

```json
{
  "scenarios": [
    {
      "scenario": "healthcare",
      "checks": {
        "risk_level": {"passed": true, "value": "high"},
        "forwarding_policy": {"passed": true, "value": "semantic_forward"},
        "semantic_conformance": {"passed": false, "message": "No UserML payload..."},
        "temporal_oversight": {"passed": true, "evidence": {...}},
        "integrity": {"passed": false, "evidence": {...}},
        "overall_passed": {"passed": false}
      },
      "metrics": {
        "envelope_bytes": 3682,
        "prov_bytes": 5608,
        "entity_count": 9,
        "activity_count": 9,
        "agent_count": 5,
        "artifact_count": 5,
        "performance": {...}
      }
    }
  ],
  "overall_passed": false
}
```

Each scenario has `checks` (pass/fail per audit check) and `metrics` (sizes and counts).
The top-level `overall_passed` is `true` only if ALL checks across ALL scenarios pass.

## Reading the Summary (`summary.md`)

Human-readable interpretation of `validation_report.json`. Contains:
- Artifact characteristics table (envelope/PROV sizes, entity/activity/agent counts)
- Audit checks table with PASS/FAIL/n/a per scenario
- Explanation of each check and what it verifies
- List of all files in the run

This is the file to read first when reviewing a run.

## Common Failure Patterns

### `semantic_conformance: FAIL` (all scenarios)

**Cause:** LLM agents output free-form JSON instead of the structured UserML format
(`{"@model": "UserML", "layers": {...}}`).

**Impact:** Protocol still functions — envelopes, PROV, and audit all work. But payloads
are not formally typed, which weakens the semantic auditing claim.

**Fix:** Use `FlatEnvelope` with `output_pydantic` to force the LLM into the schema.
Or improve task YAML prompts with stricter output instructions.

### `integrity: FAIL` (healthcare)

**Cause:** The envelope is signed by the sensor-agent at the beginning of the pipeline.
Subsequent steps (oversight, audit) add artifacts to the same envelope, changing its
content hash. The original signature no longer matches.

**Impact:** Expected in multi-step pipelines where the envelope accumulates artifacts.
The fix is to re-sign after the final step.

**Fix:** Call `builder.sign(final_agent_did)` after all artifacts are registered, not
after the first step.

### `workflow_isolation: FAIL` (education)

**Cause:** A shared artifact URI appears in both the grading and equity PROV graphs.

**Impact:** Critical — breaks the non-discrimination proof.

**Fix:** Verify the equity flow uses a completely separate `context_id` and doesn't
reference any `art-grading` or `art-ingestion` entities.

### `temporal_oversight: FAIL` (healthcare)

**Cause:** Either physician activities have timestamps BEFORE the AI decision, or total
review duration is below the minimum threshold.

**Impact:** Critical — breaks the human oversight proof.

**Fix:** Check that `_persist_oversight_events()` is called with correct timestamps and
that the simulated review delays sum to > `min_required_seconds`.
