"""Post-hoc cohort review scenario.

Builds a 312-receipt corpus deterministically (no LLM calls) and runs the
corpus-level helpers + verify_incident_attestation against it.
"""

from __future__ import annotations

import sys

from agent.flows.hiring_flow import run_hiring_cohort


def main() -> None:
    inject = "--inject-violation" in sys.argv[1:]
    summary = run_hiring_cohort(inject_violation=inject)
    ff = summary["four_fifths"]
    print("=" * 64)
    print("Hiring -- Cohort Audit Scenario (CrewAI)")
    print("=" * 64)
    print(f"  corpus_size:       {summary['corpus_size']}")
    print(f"  four-fifths ratio: protected={ff['selection_rate_protected']:.3f} "
          f"reference={ff['selection_rate_reference']:.3f} "
          f"ratio={ff['ratio']:.3f}  "
          f"[{'PASS' if ff['passed'] else 'FAIL'}]")
    inc = summary["incident_attestation"]
    print(f"  incident audit:    [{'PASS' if inc['passed'] else 'FAIL'}] {inc['message']}")
    print("=" * 64)


if __name__ == "__main__":
    main()
