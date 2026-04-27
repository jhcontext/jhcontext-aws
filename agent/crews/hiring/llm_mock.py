"""Deterministic stubbed LLM for offline reproduction of the hiring crew.

CrewAI's ``LLM`` class is duck-typed -- any object exposing a ``call(messages,
**kw)`` method that returns a string works. ``MockHiringLLM`` returns canned
``FlatEnvelope`` JSON keyed by which task is being executed.

This lets the entire crew run without network access or API keys, so unit
tests and ``run_*.py --offline`` produce byte-identical envelopes every time.
"""

from __future__ import annotations

import json
from typing import Any

from crewai.llms.base_llm import BaseLLM

from ._verifiers.fixtures import (
    SCREENING_WEIGHTS,
    synthetic_candidates,
)


def _flat(producer, scope, artifact_id, payload, di_categories,
          forwarding_policy="semantic_forward",
          artifact_type="semantic_extraction"):
    """Build a FlatEnvelope-shaped dict the LLM stub returns as JSON."""
    return {
        "producer": producer,
        "scope": scope,
        "semantic_payload_json": json.dumps(payload, ensure_ascii=False),
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "di_agent": producer.split(":")[-1],
        "di_categories": list(di_categories),
        "risk_level": "high",
        "human_oversight_required": True,
        "forwarding_policy": forwarding_policy,
    }


# ---------------------------------------------------------------------------
# Canned responses keyed by which task is executing
# ---------------------------------------------------------------------------

def _sourcing_response() -> dict:
    payload = [{
        "observations": [
            {"subject": "policy:targeting", "predicate": "ad_param", "object": p}
            for p in ["geo:EU", "language:en", "industry:software", "seniority:mid-senior"]
        ],
    }]
    return _flat(
        producer="did:vendor:sourcing-agent",
        scope="hiring_sourcing",
        artifact_id="art-sourcing-decision",
        payload=payload,
        di_categories=["geo", "language", "industry"],
        forwarding_policy="raw_forward",
    )


def _parsing_response() -> dict:
    candidates = synthetic_candidates(n=5)
    payload = [{
        "observations": [
            {"subject": c.candidate_id, "predicate": "experience_band",
             "object": c.experience_band}
            for c in candidates
        ],
        "interpretations": [
            {"subject": c.candidate_id, "predicate": "skills_overlap",
             "object": round(c.skills_overlap, 3), "confidence": 0.9}
            for c in candidates
        ],
    }]
    return _flat(
        producer="did:vendor:parsing-agent",
        scope="hiring_parsing",
        artifact_id="art-parsed-cohort",
        payload=payload,
        di_categories=["experience_band", "skills_overlap"],
    )


def _screening_response() -> dict:
    candidates = synthetic_candidates(n=5)
    rank_scores = [
        round(c.skills_overlap * SCREENING_WEIGHTS["skills_overlap"]
              + c.tenure_pattern_score * SCREENING_WEIGHTS["tenure_pattern"]
              + c.language_signal_score * SCREENING_WEIGHTS["language_signal"]
              + 0.5 * SCREENING_WEIGHTS["years_experience"], 3)
        for c in candidates
    ]
    payload = [{
        "interpretations": [
            {"subject": c.candidate_id, "predicate": "rank_score",
             "object": s, "confidence": 0.88}
            for c, s in zip(candidates, rank_scores)
        ],
    }]
    return _flat(
        producer="did:vendor:screening-agent",
        scope="hiring_screening",
        artifact_id="art-screening-rank",
        payload=payload,
        di_categories=list(SCREENING_WEIGHTS.keys()),
    )


def _interview_response() -> dict:
    candidates = synthetic_candidates(n=5)
    payload = [{
        "interpretations": [
            {"subject": c.candidate_id, "predicate": "competency",
             "object": "demonstrated systems-design fluency",
             "confidence": 0.82}
            for c in candidates if c.skills_overlap >= 0.6
        ],
    }]
    return _flat(
        producer="did:vendor:interview-agent",
        scope="hiring_interview",
        artifact_id="art-interview-competencies",
        payload=payload,
        di_categories=["communication", "problem_solving"],
    )


def _ranking_response() -> dict:
    candidates = synthetic_candidates(n=5)
    sorted_c = sorted(candidates, key=lambda c: c.skills_overlap, reverse=True)
    tiers = {}
    n = len(sorted_c)
    for i, c in enumerate(sorted_c):
        tiers[c.candidate_id] = "advance" if i < max(1, n // 3) else (
            "hold" if i < 2 * n // 3 else "decline"
        )
    payload = [{
        "interpretations": [
            {"subject": cid, "predicate": "tier", "object": tier,
             "confidence": 0.85}
            for cid, tier in tiers.items()
        ],
    }]
    return _flat(
        producer="did:vendor:ranking-agent",
        scope="hiring_ranking",
        artifact_id="art-tiered-shortlist",
        payload=payload,
        di_categories=["screening_rank", "interview_competency"],
    )


def _decision_support_response() -> dict:
    candidates = synthetic_candidates(n=5)
    sorted_c = sorted(candidates, key=lambda c: c.skills_overlap, reverse=True)
    advance = [c for i, c in enumerate(sorted_c) if i < max(1, len(sorted_c) // 3)]
    payload = [{
        "applications": [
            {"subject": c.candidate_id, "predicate": "recommend",
             "object": {
                 "tier": "advance",
                 "rationale": (
                     "Strong skills_overlap + tenure_pattern under the "
                     "rubric weights (0.31 + 0.18)."
                 ),
             }}
            for c in advance
        ],
    }]
    return _flat(
        producer="did:vendor:decision-support-agent",
        scope="hiring_decision_support",
        artifact_id="art-recruiter-packet",
        payload=payload,
        di_categories=list(SCREENING_WEIGHTS.keys()),
    )


_RESPONSES = {
    "sourcing":         _sourcing_response,
    "parsing":          _parsing_response,
    "screening":        _screening_response,
    "interview":        _interview_response,
    "ranking":          _ranking_response,
    "decision_support": _decision_support_response,
    "decision-support": _decision_support_response,
}


def _which_task(messages: list[dict]) -> str | None:
    """Identify which task is being run from the prompt's stage hints."""
    blob = json.dumps(messages, default=str).lower()
    # Most specific first.
    if "decision-support handoff" in blob or "decision_support handoff" in blob:
        return "decision_support"
    if "final-ranking handoff" in blob:
        return "ranking"
    if "async-interview handoff" in blob:
        return "interview"
    if "screening handoff" in blob:
        return "screening"
    if "parsing handoff" in blob:
        return "parsing"
    if "sourcing handoff" in blob:
        return "sourcing"
    return None


class MockHiringLLM(BaseLLM):
    """Deterministic LLM stub. Returns canned FlatEnvelope JSON per task.

    Subclasses ``crewai.llms.base_llm.BaseLLM`` so CrewAI's Agent pydantic
    validator accepts it. Implements the abstract ``call`` method only --
    every other BaseLLM affordance falls back to defaults.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(model="mock-hiring/v1", temperature=0.0, **kwargs)
        # Counter so we can debug ordering if tests fail.
        self._calls: list[str] = []

    def call(self, messages, tools=None, callbacks=None,
             available_functions=None, from_task=None, from_agent=None,
             **_: Any) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        which = _which_task(messages)
        if which is None:
            return json.dumps(_flat(
                producer="did:vendor:unknown",
                scope="unknown",
                artifact_id="art-unknown",
                payload=[],
                di_categories=[],
            ))
        self._calls.append(which)
        return json.dumps(_RESPONSES[which]())

    async def acall(self, messages, tools=None, callbacks=None,
                    available_functions=None, from_task=None, from_agent=None,
                    **kwargs: Any) -> str:
        return self.call(messages, tools=tools, callbacks=callbacks,
                         available_functions=available_functions,
                         from_task=from_task, from_agent=from_agent,
                         **kwargs)

    def get_context_window_size(self) -> int:
        return 200_000

    def supports_stop_words(self) -> bool:
        return False

    def supports_function_calling(self) -> bool:
        return False
