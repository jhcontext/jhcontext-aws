"""Render side-by-side before/after snapshots produced by the hiring flow.

After ``run_hiring_pipeline`` completes, each step has two artifacts under
``output/hiring/forwarding_diff/``:

  <step>_before.json    -- the full Envelope produced by the agent
  <step>_after.json     -- what the next agent actually receives, after
                           ForwardingEnforcer.filter_output() has stripped
                           every non-semantic field

This renderer prints the size delta + top-level key delta for each step,
so a reviewer can see the boundary's effect at a glance.

Usage::

    python -m agent.scenarios.hiring.render_forwarding_diff
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.flows.hiring_flow import OUTPUT_ROOT


def _summarize(blob: str) -> tuple[int, list[str]]:
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return len(blob), []
    if isinstance(obj, dict):
        return len(blob), sorted(obj.keys())
    return len(blob), []


def main() -> int:
    diff_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (OUTPUT_ROOT / "forwarding_diff")
    if not diff_dir.exists():
        print(f"[render_forwarding_diff] no snapshots at {diff_dir}; "
              f"run a hiring scenario first.")
        return 1

    steps = sorted({
        p.name.removesuffix("_before.json").removesuffix("_after.json")
        for p in diff_dir.glob("*.json")
    })
    if not steps:
        print(f"[render_forwarding_diff] no before/after pairs in {diff_dir}")
        return 1

    header = f"{'step':<22} {'before':>10} {'after':>10} {'delta':>10}   keys"
    print(header)
    print("-" * len(header))
    for step in steps:
        before_path = diff_dir / f"{step}_before.json"
        after_path = diff_dir / f"{step}_after.json"
        if not (before_path.exists() and after_path.exists()):
            continue
        before_blob = before_path.read_text()
        after_blob = after_path.read_text()
        b_size, b_keys = _summarize(before_blob)
        a_size, a_keys = _summarize(after_blob)
        delta = a_size - b_size
        sign = "+" if delta >= 0 else ""
        kept = sorted(set(a_keys) & set(b_keys))
        dropped = sorted(set(b_keys) - set(a_keys))
        keys_repr = "kept=" + ",".join(kept) + (
            "  dropped=" + ",".join(dropped) if dropped else ""
        )
        print(f"{step:<22} {b_size:>10} {a_size:>10} {sign}{delta:>9}   {keys_repr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
