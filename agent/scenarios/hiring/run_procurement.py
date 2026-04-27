"""Procurement-time governance scenario via the CrewAI hiring flow.

Runs the six-task crew once and prints the procurement-checkpoint audit.
"""

from __future__ import annotations

import os
import sys

from agent.flows.hiring_flow import run_hiring_pipeline


def main() -> None:
    inject = "--inject-violation" in sys.argv[1:]
    offline = "--offline" in sys.argv[1:] or os.environ.get("HIRING_USE_MOCK_LLM")
    metrics = run_hiring_pipeline(
        inject_violation=inject,
        use_mock_llm=bool(offline) or None,  # None -> auto-detect
    )
    print("=" * 64)
    print("Hiring -- Procurement Scenario (CrewAI)")
    print("=" * 64)
    print(f"  inject_violation:  {metrics['inject_violation']}")
    print(f"  use_mock_llm:      {metrics['use_mock_llm']}")
    print(f"  steps:             {metrics['steps']}")
    print(f"  semantic boundary: {metrics['semantic_boundary_reached']}")
    print(f"  procurement audit: {'PASS' if metrics['procurement_passed'] else 'FAIL'}")
    print(f"  total runtime:     {metrics['total_ms']:.1f} ms")
    print("=" * 64)


if __name__ == "__main__":
    main()
