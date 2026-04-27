"""Hiring scenario entry points (CrewAI flow runners).

Three scenarios mirror the SDK-only paper-gating suite in
jhcontext-usecases, but here the receipts are produced by a real CrewAI
multi-agent crew. Set ``HIRING_USE_MOCK_LLM=1`` (or pass ``--offline``)
to use the deterministic mock LLM and reproduce without API keys.
"""
