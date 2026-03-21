#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== jhcontext-mcp deploy ==="

# 1. Sync DynamoDB storage module from api/ (single source of truth)
echo "Syncing DynamoDB storage from api/..."
cp "$SCRIPT_DIR/../api/chalicelib/storage/dynamodb.py" \
   "$SCRIPT_DIR/chalicelib/dynamodb_storage.py"

# 2. Install MCP-only deps (lightweight — no crewai)
echo "Installing MCP dependencies from mcp/requirements.txt..."
pip install -q -r requirements.txt

# 3. Deploy via Chalice (separate Lambda from API)
echo "Deploying with Chalice..."
chalice deploy

# 4. Print MCP URL
echo ""
echo "=== Deploy complete ==="
ENDPOINT=$(chalice url 2>/dev/null || echo "(run 'chalice url' to see endpoint)")
echo "MCP endpoint: $ENDPOINT/mcp"
echo ""
echo "Test with:"
echo "  curl \$ENDPOINT/health"
echo "  curl -X POST \$ENDPOINT/mcp -H 'Content-Type: application/json' \\"
echo "    -d '{\"tool_name\": \"get_envelope\", \"arguments\": {\"context_id\": \"ctx-test\"}}'"
