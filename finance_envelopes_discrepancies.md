# Finance Envelopes vs PAC-AI Reference — Discrepancies

Comparison of `finance_envelopes.json` (v03) against the PAC-AI reference specification (Sections 3, 3.2, 5 and Figure 1).

## 1. Field Naming Mismatches

| Paper (Fig. 1 / Sec. 3) | Samples | Notes |
|---|---|---|
| `timestamp` | `created_at` | Different field name |
| `audit_reference` | `provenance_ref` | Different name; also empty `{}` in all envelopes |
| `integrity` block (`payload_hash`, `signature`, `optional_anchor`) | `proof` block (`canonicalization`, `content_hash`, `signature`, `signer`) | Restructured block |

## 2. Missing Fields from Paper Spec

- **`transformations`** — listed under Artifact Management in Figure 1, absent from all envelopes.
- **`model_card_ref`**, **`test_suite_ref`**, **`escalation_paths`** — listed in the compliance block spec, absent from samples.
- **`feature_suppression`** is present but empty `[]`, and **`pii_detached: false`** — the paper (Sec. 3.2) describes PII detachment as a key mechanism for the finance scenario (tax ID, account numbers should be tokenized), but it is not demonstrated here.

## 3. Forwarding Policy Violation for High-Risk

The paper explicitly states: *"High risk (healthcare, credit, justice): Semantic-Forward required."*

However, **envelope 1** (Data Collector Agent) has `risk_level: "high"` with `forwarding_policy: "raw_forward"`. This contradicts the paper's risk-tier rules.

## 4. Extra Fields Not in Paper Spec

- `producer` (DID identifier), `status`, `@context`, `@type` — reasonable JSON-LD additions but not described in the paper's envelope structure (Figure 1 / Section 3).

## 5. Sparse Audit Envelope

Envelope 4 (Audit Agent) has `semantic_payload: []` and `decision_influence: []` — carries no semantic content or influence data. The paper's scenarios describe richer audit artifacts.

## 6. DTI Value Discrepancy

The paper's finance scenario mentions a DTI of **32%**, but the sample uses **11%** (0.11). Minor difference (example values), but worth aligning for consistency.

---

## Recommendations

1. **Fix the high-risk raw_forward violation** — change envelope 1's `forwarding_policy` to `semantic_forward`, or lower its `risk_level` to match the paper's tier rules.
2. **Align field names** with the paper spec: `timestamp`, `audit_reference`, `integrity`.
3. **Add missing spec fields** (`transformations`, `model_card_ref`, `escalation_paths`) even if empty, to match the described schema.
4. **Demonstrate PII detachment** — tokenize financial identifiers in at least one envelope to match Section 3.2's finance scenario description.
5. **Enrich the audit envelope** — add at least summary semantic content to show the audit trail is substantive.
