"""Mock upstream client for offline-simulation drains.

The real ``jhcontext.client.api_client.JHContextClient`` POSTs to a Chalice
Lambda that writes to DynamoDB. For the offline-simulation flows we
want a deterministic upstream that records everything it receives without
requiring the Chalice API to be running. Drop in either the real client or
this mock depending on whether you want to exercise the full stack.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MockUpstreamClient:
    """Write-only mock that records submitted envelopes + PROV to a file.

    Drop-in replacement for ``JHContextClient`` for the ``submit_envelope``
    and ``submit_prov`` methods used by ``SyncManager``.
    """

    def __init__(self, record_path: Path | str | None = None) -> None:
        self.record_path = Path(record_path) if record_path else None
        self.envelopes: list[dict[str, Any]] = []
        self.prov_graphs: list[dict[str, Any]] = []

    def submit_envelope(self, envelope_json: str) -> None:
        self.envelopes.append(
            {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "envelope_json": envelope_json,
            }
        )
        self._flush()

    def submit_prov(self, context_id: str, prov_ttl: str) -> None:
        self.prov_graphs.append(
            {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "context_id": context_id,
                "prov_ttl": prov_ttl,
            }
        )
        self._flush()

    def _flush(self) -> None:
        if not self.record_path:
            return
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.write_text(
            json.dumps(
                {"envelopes": self.envelopes, "prov_graphs": self.prov_graphs},
                indent=2,
            ),
            encoding="utf-8",
        )

    def close(self) -> None:
        self._flush()
