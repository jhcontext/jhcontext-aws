# Test Suite

Unit tests for the jhcontext-crewai infrastructure layer. These tests verify the storage
backends, local mode switching, and domain ontology validation — they do **not** run
CrewAI agents or call LLMs.

## Running Tests

```bash
# From the project root
.venv/bin/python -m pytest tests/ --tb=short

# With coverage
.venv/bin/python -m pytest tests/ --cov=api --cov=agent --tb=short

# Single file
.venv/bin/python -m pytest tests/test_sqlite_storage.py -v
```

Requirements: `pip install -e ".[dev]"` (installs pytest, pytest-cov, moto).

## Test Files

### test_sqlite_storage.py — Storage Backend (13 tests)

Tests the SQLite storage implementation that powers local development mode.

**TestSQLiteStorage** (8 tests):

| Test | What it verifies |
|------|-----------------|
| `test_save_and_get_envelope` | Round-trip: build envelope → save → retrieve → fields match |
| `test_get_nonexistent_envelope` | Returns `None` for unknown context_id (no crash) |
| `test_list_envelopes` | Filtering by `scope` returns correct subset |
| `test_list_envelopes_filter_by_risk` | Filtering by `risk_level` (high/low) works |
| `test_save_and_get_prov_graph` | PROV graph serialized as Turtle → saved → retrieved intact |
| `test_get_nonexistent_prov` | Returns `None` for unknown PROV graph |
| `test_save_and_get_decision` | Decision object with outcome JSON → save → retrieve → fields match |
| `test_save_and_get_artifact` | Binary content + metadata → save to filesystem → retrieve both |
| `test_envelope_overwrite` | `INSERT OR REPLACE` updates existing envelope (same context_id) |

**TestSQLitePIIVault** (5 tests):

| Test | What it verifies |
|------|-----------------|
| `test_store_and_retrieve` | PII token round-trip (email → token → retrieve) |
| `test_retrieve_nonexistent` | Returns `None` for unknown token |
| `test_retrieve_by_context` | Retrieves all PII tokens for a given context_id |
| `test_purge_by_context` | Deletes all tokens for a context, leaves others intact |
| `test_purge_expired` | Deletes tokens older than a cutoff timestamp (GDPR retention) |

**Reading results:** All tests use `tmp_path` fixtures — each test gets a fresh SQLite
database in a temp directory. Failures here mean the storage layer has a regression.
Since DynamoDB implements the same `StorageBackend` protocol with the same 9 methods,
a SQLite failure likely indicates a bug that would also affect production.

---

### test_app_local_mode.py — Mode Switching (3 tests)

Tests that the `JHCONTEXT_LOCAL` environment variable correctly switches between
SQLite and DynamoDB backends in the Chalice app.

| Test | What it verifies |
|------|-----------------|
| `test_local_mode_uses_sqlite` | `JHCONTEXT_LOCAL=1` → `get_storage()` returns `SQLiteStorage`, `get_pii_vault()` returns `SQLitePIIVault` |
| `test_default_mode_is_not_local` | Without env var → local mode is `False` (DynamoDB would be used) |
| `test_full_roundtrip` | End-to-end: create envelope → save PROV graph → save decision → retrieve all → verify fields |

**Reading results:** `test_local_mode_uses_sqlite` is **skipped** (`s`) if Chalice is
not installed — this is expected in agent-only dev environments. The roundtrip test
exercises the complete flow: `EnvelopeBuilder → SQLiteStorage → PROVGraph → Decision`,
which is the same sequence the real flows execute.

---

### test_ontologies.py — Domain Ontology Validation (15 tests)

Tests the UserML semantic payload structure and domain-specific predicate vocabularies.

**TestHealthcareOntology** (4 tests):

| Test | What it verifies |
|------|-----------------|
| `test_predicates_defined` | Healthcare predicates exist in all layers (observation, interpretation, situation) |
| `test_sample_healthcare_is_valid` | Sample payload passes `validate_semantic_payload()` with zero violations |
| `test_healthcare_observations` | Helper builds observation triples with correct predicates (demographic, lab_result, imaging_finding) |
| `test_healthcare_payload_structure` | Full UserML payload has `@model: "UserML"` + `layers` dict |

**TestEducationOntology** (3 tests):

| Test | What it verifies |
|------|-----------------|
| `test_predicates_defined` | Education predicates (word_count, argument_quality, grade_assigned) |
| `test_sample_education_is_valid` | Sample payload validates cleanly |
| `test_education_interpretations` | Helper builds interpretation triples with default confidence |

**TestRecommendationOntology** (2 tests):

| Test | What it verifies |
|------|-----------------|
| `test_predicates_defined` | Recommendation predicates (browse_event, category_affinity, active_shopper) |
| `test_sample_recommendation_is_valid` | Sample payload validates cleanly |

**TestValidator** (6 tests):

| Test | What it verifies |
|------|-----------------|
| `test_valid_payload` | Known-good payload → `(True, [])` |
| `test_missing_model` | Missing `@model` key → violation reported |
| `test_invalid_predicate` | Unknown predicate → violation with predicate name in message |
| `test_missing_predicate_key` | Triple without `predicate` key → "missing 'predicate'" violation |
| `test_non_dict_payload` | String input → invalid (type check) |
| `test_missing_layers` | Missing `layers` key → violation reported |

**Reading results:** Ontology test failures mean either:
1. A predicate was renamed/removed in `agent/ontologies/*.py` without updating the sample
2. The validator logic changed (e.g., new required field)
3. The UserML schema structure changed in the jhcontext SDK

These tests are the **compile-time equivalent** for the `semantic_conformance` check
that runs at validation time. If ontology tests pass but `semantic_conformance` fails
in a run, the problem is the LLM output format, not the ontology definitions.

## Test Output Guide

```
tests/test_app_local_mode.py s..                    [  8%]
tests/test_ontologies.py ...............            [ 52%]
tests/test_sqlite_storage.py ................      [100%]

======================== 33 passed, 1 skipped ========================
```

| Symbol | Meaning |
|--------|---------|
| `.` | Test passed |
| `s` | Test skipped (missing optional dependency like Chalice) |
| `F` | Test failed — assertion error (see traceback) |
| `E` | Test errored — unexpected exception (import error, missing fixture) |

A healthy run shows **33 passed, 1 skipped**. The skip is `test_local_mode_uses_sqlite`
when Chalice is not installed.
