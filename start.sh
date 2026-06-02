#!/bin/bash
# Howard Wire Bot — one-time setup + launch
set -e

cd "$(dirname "$0")"

# Install dependencies if needed
if ! python3 -c "import flask, anthropic" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

# Rebuild catalog if needed
if [ ! -f catalog.json ]; then
  echo "Building product catalog..."
  python3 build_catalog.py
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo ""
  echo "ERROR: Set your Anthropic API key first:"
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  echo ""
  exit 1
fi

echo ""
echo "Starting Howard Wire Product Assistant..."
echo "Open: http://localhost:5050"
echo ""
python3 app.py
