"""Vendored verifier and cohort modules for the hiring multi-agent simulation.

Source:    /home/jhdarosa/Repos/jhcontext-usecases/usecases/hiring/{verifiers,cohort,fixtures}.py
Vendored:  2026-04-27
Reason:    keep jhcontext-sdk untouched; this crew imports vendored copies
           rather than crossing repo boundaries at runtime.

Re-sync workflow: when the upstream usecases verifiers change, copy them in,
then run `pytest jhcontext-crewai/tests/test_hiring_flow.py` to confirm
nothing drifted.
"""

from .verifiers import (
    DEFAULT_PROHIBITED_CAPABILITIES,
    NOTIFICATION_WINDOW_DAYS,
    verify_ai_literacy_attestation,
    verify_candidate_notice,
    verify_incident_attestation,
    verify_input_data_attestation,
    verify_no_prohibited_practice,
    verify_sourcing_neutrality,
    verify_workforce_notice,
)
from .cohort import (
    FeatureUsageCensus,
    FourFifthsResult,
    feature_usage_census,
    four_fifths_ratio,
)
from . import fixtures

__all__ = [
    "DEFAULT_PROHIBITED_CAPABILITIES",
    "NOTIFICATION_WINDOW_DAYS",
    "verify_ai_literacy_attestation",
    "verify_candidate_notice",
    "verify_incident_attestation",
    "verify_input_data_attestation",
    "verify_no_prohibited_practice",
    "verify_sourcing_neutrality",
    "verify_workforce_notice",
    "FeatureUsageCensus",
    "FourFifthsResult",
    "feature_usage_census",
    "four_fifths_ratio",
    "fixtures",
]
