"""Education flows, organised by pipeline variant.

- ``fair_grading`` — 2-agent pipeline for Article 13 non-discrimination.
- ``rubric_feedback_grading`` — 3-agent pipeline with per-sentence
  feedback envelopes plus TA-review and audit flows (covers three
  scenarios).

See ``agent/flows/education/README.md`` for the full scenario mapping.
"""

from .fair_grading import (
    EducationAuditFlow,
    EducationEquityFlow,
    EducationGradingFlow,
)
from .rubric_feedback_grading import (
    RubricAuditFlow,
    RubricEquityFlow,
    RubricGradingFlow,
    RubricTAReviewFlow,
)

__all__ = [
    # Fair grading (Article 13 non-discrimination)
    "EducationAuditFlow",
    "EducationEquityFlow",
    "EducationGradingFlow",
    # Rubric-grounded grading (three-scenario pipeline)
    "RubricAuditFlow",
    "RubricEquityFlow",
    "RubricGradingFlow",
    "RubricTAReviewFlow",
]
