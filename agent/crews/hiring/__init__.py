"""Hiring multi-agent simulation crew.

Six CrewAI agents (sourcing, parsing, screening, interview, ranking,
decision_support) emit a ``jhcontext.flat_envelope.FlatEnvelope`` at every
handoff. ``ContextMixin._persist_task_callback`` (in ``agent/protocol/``)
applies ``ForwardingEnforcer`` between tasks, so each downstream agent only
sees the prior agent's ``semantic_payload`` -- never the raw artifacts.

Verifiers and cohort helpers are vendored under ``_verifiers/`` from
``jhcontext-usecases``; see that subpackage's ``__init__.py`` for sync notes.
"""
