#!/usr/bin/env bash
# Build the Understudy UI and stage it into the wheel's static dir.
# Run this before `uv build` or committing frontend changes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/understudy/ui"

if [ ! -d node_modules ]; then
  npm ci --no-audit --no-fund --silent
fi

npm run build --silent

echo "✓ frontend built → understudy/server/static"
