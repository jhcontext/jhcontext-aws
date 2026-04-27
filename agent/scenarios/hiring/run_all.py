"""Run all three hiring CrewAI scenarios and print a combined summary."""

from __future__ import annotations

import os
import sys

from agent.flows.hiring_flow import run_hiring_cohort, run_hiring_pipeline


def main() -> None:
    inject = "--inject-violation" in sys.argv[1:]
    offline = "--offline" in sys.argv[1:] or os.environ.get("HIRING_USE_MOCK_LLM")
    use_mock = bool(offline) or None

    print(f"\n[hiring/run_all] inject={inject} offline={bool(offline)}\n")
    pipeline_metrics = run_hiring_pipeline(
        inject_violation=inject, use_mock_llm=use_mock,
    )
    print()
    cohort_summary = run_hiring_cohort(inject_violation=inject)

    ff = cohort_summary["four_fifths"]
    inc = cohort_summary["incident_attestation"]

    print()
    print("=" * 64)
    print("Hiring CrewAI scenarios -- combined summary")
    print("=" * 64)
    print(f"  Procurement audit: "
          f"{'PASS' if pipeline_metrics['procurement_passed'] else 'FAIL'}  "
          f"({pipeline_metrics['total_ms']:.1f} ms)")
    print(f"  In-flight audit:   "
          f"{'PASS' if pipeline_metrics['inflight_passed'] else 'FAIL'}")
    print(f"  Cohort 4/5 ratio:  {ff['ratio']:.3f}  "
          f"[{'PASS' if ff['passed'] else 'FAIL'}]")
    print(f"  Cohort incidents:  [{'PASS' if inc['passed'] else 'FAIL'}]")
    print(f"  Semantic boundary reached: {pipeline_metrics['semantic_boundary_reached']}")
    print("=" * 64)


if __name__ == "__main__":
    main()
