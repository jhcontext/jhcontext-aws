# Finance Envelopes vs PAC-AI Reference — Discrepancies

Comparison of `finance_envelopes.json` (v03) against the PAC-AI reference specification and jhcontext-protocol v0.3 spec.

## Investigation Result

The discrepancies are **systemic, not finance-specific**. All 13 envelopes across 4 scenarios (finance, healthcare, education, recommendation) share the same patterns. The root cause is a **paper vs protocol/SDK misalignment** — the protocol and SDK are in sync with each other.

## Paper Fixes Applied (03pacp.tex + figure1-prompt.md)

| What | Old (paper) | Corrected to (protocol v0.3) |
|------|-------------|------------------------------|
| Envelope timestamp field | `timestamp` | `created_at` |
| Cryptographic block name | `integrity` | `proof` |
| Provenance reference field | `audit_reference` | `provenance_ref` |
| Escalation field | `escalation_paths` (plural) | `escalation_path` (singular) |
| Figure 1 caption | Referenced old field names | Updated to `created_at`, `proof` |
| Figure 1 prompt | Listed `transformations` | Removed (handled by PROV graph) |

## Remaining Issues (crew/SDK level)

### 1. Forwarding Policy Violation for High-Risk

Envelope 1 (Data Collector) has `risk_level: "high"` with `forwarding_policy: "raw_forward"`. The protocol states HIGH risk requires `semantic_forward`. The SDK's `EnvelopeBuilder.set_risk_level(HIGH)` auto-sets `semantic_forward`, but the FlatEnvelope (LLM output) hardcodes `raw_forward` as default and the task YAML explicitly requests `raw_forward`.

**Note:** The protocol does allow per-task overrides for initial data collection steps, but the monotonic constraint should prevent subsequent tasks from downgrading.

### 2. PII Detachment Not Demonstrated

`feature_suppression: []` and `pii_detached: false` across all envelopes. The finance flow initializes feature suppression in `_init_context()` but it doesn't cascade to LLM-generated FlatEnvelopes.

### 3. Optional Compliance Fields Never Populated

`model_card_ref`, `test_suite_ref`, `escalation_path` exist in the SDK's ComplianceBlock but are never set in any scenario.

### 4. Empty Provenance References

`provenance_ref: {}` in all envelopes — `prov_graph_id` and `prov_digest` never populated despite PROV graphs being generated.

### 5. Sparse Audit Envelope

Envelope 4 (Audit Agent) has empty `semantic_payload` and `decision_influence`.

### 6. DTI Value Mismatch

Paper says 32%, sample uses 11%. Minor (example values).
