#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== jhcontext-api deploy ==="

# 1. Install API-only deps (lightweight — no crewai, no mcp)
echo "Installing API dependencies from api/requirements.txt..."
pip install -q -r requirements.txt

# 2. Verify jhcontext SDK is available
python -c "import jhcontext; print(f'  jhcontext SDK v{jhcontext.__version__}')" || {
    echo "ERROR: jhcontext SDK not found. Check requirements.txt."
    exit 1
}

# 3. Ensure DynamoDB tables + S3 bucket exist
echo "Checking DynamoDB tables and S3 bucket..."
python setup_tables.py

# 4. Deploy via Chalice (packages only api/requirements.txt into Lambda ZIP)
echo "Deploying with Chalice..."
chalice deploy

# 5. Print API URL
echo ""
echo "=== Deploy complete ==="
ENDPOINT=$(chalice url 2>/dev/null || echo "(run 'chalice url' to see endpoint)")
echo "API endpoint: $ENDPOINT"
echo ""
echo "Test with:"
echo "  curl \$ENDPOINT/health"
