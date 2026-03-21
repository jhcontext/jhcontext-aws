"""DynamoDB-backed PII vault with independent lifecycle management.

Stores PII tokens in a SEPARATE DynamoDB table from envelopes, enabling:
- Independent encryption via AWS KMS
- GDPR Art. 17 erasure without touching envelope/PROV tables
- Access control via IAM policies on the table
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import boto3

PII_TABLE = os.environ.get("DYNAMODB_PII_TABLE", "jhcontext-pii-vault")


class DynamoDBPIIVault:
    """DynamoDB-backed PII vault implementing the jhcontext PIIVault protocol."""

    def __init__(self, dynamodb_resource=None) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(PII_TABLE)

    def store(self, token_id: str, context_id: str, original_value: str, field_path: str) -> None:
        self._table.put_item(
            Item={
                "token_id": token_id,
                "context_id": context_id,
                "field_path": field_path,
                "original_value": original_value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def retrieve(self, token_id: str) -> str | None:
        resp = self._table.get_item(Key={"token_id": token_id})
        item = resp.get("Item")
        return item["original_value"] if item else None

    def retrieve_by_context(self, context_id: str) -> list[dict[str, str]]:
        resp = self._table.query(
            IndexName="ContextIndex",
            KeyConditionExpression="context_id = :ctx",
            ExpressionAttributeValues={":ctx": context_id},
        )
        return [
            {
                "token_id": item["token_id"],
                "field_path": item["field_path"],
                "original_value": item["original_value"],
                "created_at": item["created_at"],
            }
            for item in resp.get("Items", [])
        ]

    def purge_by_context(self, context_id: str) -> int:
        """Delete all PII tokens for a context (GDPR Art. 17 erasure)."""
        tokens = self.retrieve_by_context(context_id)
        with self._table.batch_writer() as batch:
            for token in tokens:
                batch.delete_item(Key={"token_id": token["token_id"]})
        return len(tokens)

    def purge_expired(self, before_iso: str) -> int:
        """Delete all PII tokens created before the given ISO timestamp."""
        resp = self._table.scan(
            FilterExpression="created_at < :before",
            ExpressionAttributeValues={":before": before_iso},
        )
        items = resp.get("Items", [])
        with self._table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"token_id": item["token_id"]})
        return len(items)
