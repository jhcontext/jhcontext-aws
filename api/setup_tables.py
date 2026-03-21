"""Create DynamoDB tables and S3 bucket for jhcontext-api."""

from __future__ import annotations

import json
import os

import boto3
from botocore.exceptions import ClientError

TABLES = {
    "jhcontext-envelopes": {
        "KeySchema": [{"AttributeName": "context_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "context_id", "AttributeType": "S"},
            {"AttributeName": "scope", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "ScopeIndex",
                "KeySchema": [
                    {"AttributeName": "scope", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "jhcontext-artifacts": {
        "KeySchema": [{"AttributeName": "artifact_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "artifact_id", "AttributeType": "S"},
            {"AttributeName": "context_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "ContextIndex",
                "KeySchema": [
                    {"AttributeName": "context_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "jhcontext-prov-graphs": {
        "KeySchema": [{"AttributeName": "context_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "context_id", "AttributeType": "S"},
        ],
    },
    "jhcontext-decisions": {
        "KeySchema": [{"AttributeName": "decision_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "decision_id", "AttributeType": "S"},
            {"AttributeName": "context_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "ContextIndex",
                "KeySchema": [
                    {"AttributeName": "context_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "jhcontext-pii-vault": {
        "KeySchema": [{"AttributeName": "token_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "token_id", "AttributeType": "S"},
            {"AttributeName": "context_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "ContextIndex",
                "KeySchema": [
                    {"AttributeName": "context_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
}

S3_BUCKET = os.environ.get("S3_ARTIFACTS_BUCKET", "jhcontext-artifacts-dev")


def create_tables():
    dynamodb = boto3.client("dynamodb")

    for table_name, schema in TABLES.items():
        try:
            kwargs = {
                "TableName": table_name,
                "KeySchema": schema["KeySchema"],
                "AttributeDefinitions": schema["AttributeDefinitions"],
                "BillingMode": "PAY_PER_REQUEST",
            }
            if "GlobalSecondaryIndexes" in schema:
                kwargs["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]

            dynamodb.create_table(**kwargs)
            print(f"  Created table: {table_name}")

            waiter = dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=table_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"  Table exists: {table_name}")
            else:
                raise


def create_s3_bucket():
    s3 = boto3.client("s3")
    try:
        region = boto3.session.Session().region_name or "us-east-1"
        kwargs = {"Bucket": S3_BUCKET}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        print(f"  Created S3 bucket: {S3_BUCKET}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  S3 bucket exists: {S3_BUCKET}")
        else:
            raise


if __name__ == "__main__":
    print("Creating DynamoDB tables...")
    create_tables()
    print("Creating S3 bucket...")
    create_s3_bucket()
    print("Done.")
