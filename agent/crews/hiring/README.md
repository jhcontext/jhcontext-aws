# Hiring Multi-Agent Crew

Six CrewAI agents simulating a hiring pipeline (sourcing → parsing → screening
→ async-interview → ranking → decision-support). Every task outputs a
`jhcontext.flat_envelope.FlatEnvelope`; the flow's task callback rehydrates
each into a full `Envelope`, signs it, and applies `ForwardingEnforcer`
between tasks so each downstream agent only sees the prior agent's
`semantic_payload` — never the raw artifacts.

This is the protocol claim made visible: a reviewer can `diff` the
before/after JSON for any post-boundary step and see exactly what the
recruiter's view strips out.

## Where things live

```
agent/crews/hiring/
  config/agents.yaml        role/goal/backstory for the 6 agents
  config/tasks.yaml         6 tasks; each declares output_pydantic=FlatEnvelope
  hiring_crew.py            @CrewBase wiring agents to tasks (LLM injectable)
  llm_mock.py               deterministic stub LLM (offline reproduction)
  _verifiers/               vendored from jhcontext-usecases (see __init__.py)
agent/flows/hiring_flow.py  PROVGraph + ForwardingEnforcer + audit checkpoints
agent/scenarios/hiring/
  run_procurement.py        Scenario A entry point
  run_inflight.py           Scenario B entry point
  run_cohort.py             Scenario C entry point (no LLM calls)
  run_all.py                runs all three with combined summary
  render_forwarding_diff.py before/after size + key delta per step
output/hiring/               envelopes/, forwarding_diff/, prov/, audit/
```

## How `jhcontext` v0.5 (PyPI) is used

| SDK primitive | Where it appears | What the reviewer reads |
|---|---|---|
| `EnvelopeBuilder` | `hiring_flow.py` task callback re-bakes signed envelopes | one signed envelope per handoff in `output/hiring/envelopes/` |
| `FlatEnvelope` (from `jhcontext.flat_envelope`) | every task's `output_pydantic` | `tasks.yaml` shows the canonical shape every agent emits |
| `ForwardingEnforcer.resolve()` + `filter_output()` | `make_task_callback()` after every task | `output/hiring/forwarding_diff/<step>_{before,after}.json` |
| `PROVGraph` + crew/agent registration | `run_hiring_pipeline()` allocates one graph per scenario | `output/hiring/prov/hiring.ttl` |
| `RiskLevel.HIGH` auto → `ForwardingPolicy.SEMANTIC_FORWARD` | `EnvelopeBuilder.set_risk_level()` | the boundary trips at `parsing` (the first SEMANTIC_FORWARD step) |
| `verify_negative_proof`, `verify_temporal_oversight`, `verify_integrity` | audit checkpoints | `output/hiring/audit/{procurement,inflight}.json` |
| 7 HR-specific verifiers (vendored) | same checkpoints | same audit JSON |
| `feature_usage_census` + `four_fifths_ratio` | `run_hiring_cohort` | `output/hiring/audit/cohort.json` |

## Running it

```bash
# Offline (no API key, deterministic — recommended for review)
HIRING_USE_MOCK_LLM=1 python -m agent.scenarios.hiring.run_all

# Real LLMs (requires ANTHROPIC_API_KEY)
python -m agent.scenarios.hiring.run_all

# Inject the violation each scenario is built to detect
python -m agent.scenarios.hiring.run_all --offline --inject-violation

# Render the side-by-side forwarding-boundary effect
python -m agent.scenarios.hiring.render_forwarding_diff
```

Sample renderer output (offline, default fixtures):

```
step                       before      after      delta   keys
--------------------------------------------------------------
sourcing                     2140       2140 +        0   kept=...,semantic_payload,...   (raw_forward)
parsing                      3012       1485     -1527   kept=semantic_payload  dropped=artifacts_registry,compliance,...
screening                    2407        817     -1590   kept=semantic_payload  dropped=artifacts_registry,compliance,...
interview                    1980        437     -1543   kept=semantic_payload  dropped=artifacts_registry,compliance,...
ranking                      2336        801     -1535   kept=semantic_payload  dropped=artifacts_registry,compliance,...
decision_support             1956        336     -1620   kept=semantic_payload  dropped=artifacts_registry,compliance,...
```

## Three audit checkpoints

| Checkpoint | When | Verifiers fired |
|---|---|---|
| **Procurement** | after the crew kickoff returns | `verify_sourcing_neutrality`, `verify_no_prohibited_practice`, `verify_workforce_notice`, `verify_input_data_attestation`, `verify_integrity` |
| **In-flight** | after recruiter review activity is recorded | `verify_negative_proof`, `verify_candidate_notice`, `verify_temporal_oversight`, `verify_ai_literacy_attestation`, `verify_integrity` |
| **Cohort** | after `run_hiring_cohort` builds the corpus | `feature_usage_census`, `four_fifths_ratio`, `verify_incident_attestation` |

Default fixtures: procurement and in-flight PASS; cohort fails the
four-fifths test (seeded disparity 0.18 vs 0.30 → ratio 0.6) and
`verify_incident_attestation` (one of two suspensions has no Art. 73
notification). Both failures are deliberate demonstrations.

## Tests

```
python -m pytest tests/test_hiring_flow.py -v
```

Four tests, mock-LLM, offline, ~5 s:

- all six handoffs run + boundary trips on
- forwarding-diff strips `artifacts_registry`/`compliance`/etc. after the boundary
- rubber-stamp recruiter review → in-flight audit fails on temporal oversight
- 312-receipt cohort → four-fifths ratio is exactly 0.600

## Constraints

- Uses ONLY public `jhcontext>=0.5,<0.6` PyPI exports — `EnvelopeBuilder`,
  `PROVGraph`, `ForwardingEnforcer`, `ForwardingPolicy`, `RiskLevel`,
  `ArtifactType`, `FlatEnvelope`. No SDK changes.
- No conference / venue names anywhere in this directory or in
  `agent/flows/hiring_flow.py` / `agent/scenarios/hiring/` /
  `tests/test_hiring_flow.py`. The CI guard lives at
  `tools/check_no_venues.sh` (or run the canonical `grep` on the
  `jhcontext-bib/banned_venues` list).
- Verifier and cohort modules are vendored (one-way) from
  `jhcontext-usecases/usecases/hiring/`. See `_verifiers/__init__.py` for
  the source path + vendor date.
