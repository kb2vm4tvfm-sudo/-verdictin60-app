#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="/usr/local/bin/python3"

echo "=== Installing VerdictIn60 browser article reader ==="
"$PY" -m pip install --target "$APP_DIR/vendor" playwright

echo ""
echo "=== Installing local browser runtime ==="
PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/ms-playwright" \
PYTHONPATH="$APP_DIR/vendor" \
"$PY" -m playwright install chromium

echo ""
echo "Done. VerdictIn60 can now try browser-based source reading."
