"""Entry point for running jhcontext-aws agent scenarios.

Usage:
    python -m agent.run --scenario healthcare
    python -m agent.run --scenario education
    python -m agent.run --scenario all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def run_healthcare():
    """Run the healthcare human oversight scenario (Article 14)."""
    from agent.flows.healthcare_flow import HealthcareFlow

    print("=" * 60)
    print("SCENARIO: Healthcare Human Oversight (EU AI Act Art. 14)")
    print("=" * 60)

    flow = HealthcareFlow()
    result = flow.kickoff()

    print("\n" + "=" * 60)
    print("Healthcare scenario complete.")
    print(f"Outputs in: {OUTPUT_DIR}/healthcare_*")
    return result


def run_education():
    """Run the education fair assessment scenario (Article 13).

    Runs three sub-flows:
    1. Grading workflow (identity-free)
    2. Equity reporting workflow (isolated)
    3. Audit workflow (verifies isolation)
    """
    from agent.flows.education_flow import (
        EducationAuditFlow,
        EducationEquityFlow,
        EducationGradingFlow,
    )

    print("=" * 60)
    print("SCENARIO: Education Fair Assessment (EU AI Act Art. 13)")
    print("=" * 60)

    print("\n--- Grading Workflow ---")
    grading_flow = EducationGradingFlow()
    grading_flow.kickoff()

    print("\n--- Equity Reporting Workflow (isolated) ---")
    equity_flow = EducationEquityFlow()
    equity_flow.kickoff()

    print("\n--- Audit: Workflow Isolation Verification ---")
    audit_flow = EducationAuditFlow()
    result = audit_flow.kickoff()

    print("\n" + "=" * 60)
    print("Education scenario complete.")
    print(f"Outputs in: {OUTPUT_DIR}/education_*")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run jhcontext-aws agent scenarios")
    parser.add_argument(
        "--scenario",
        choices=["healthcare", "education", "all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.scenario in ("healthcare", "all"):
        run_healthcare()

    if args.scenario in ("education", "all"):
        run_education()

    # Print summary
    print("\n" + "=" * 60)
    print("ALL SCENARIOS COMPLETE")
    print("=" * 60)
    output_files = sorted(OUTPUT_DIR.glob("*"))
    for f in output_files:
        size = f.stat().st_size
        print(f"  {f.name:45s} {size:>8,d} bytes")


if __name__ == "__main__":
    main()
