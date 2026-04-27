"""In-flight Art. 14 oversight scenario via the CrewAI hiring flow.

Same pipeline as run_procurement, but the focus is the in-flight checkpoint
that fires after the recruiter review activity is recorded.
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
        use_mock_llm=bool(offline) or None,
    )
    print("=" * 64)
    print("Hiring -- In-flight Oversight Scenario (CrewAI)")
    print("=" * 64)
    print(f"  inject_violation:  {metrics['inject_violation']}")
    print(f"  use_mock_llm:      {metrics['use_mock_llm']}")
    print(f"  recruiter review:  {metrics['recruiter_review_seconds']:.0f} s")
    print(f"  in-flight audit:   {'PASS' if metrics['inflight_passed'] else 'FAIL'}")
    print(f"  total runtime:     {metrics['total_ms']:.1f} ms")
    print("=" * 64)


if __name__ == "__main__":
    main()
