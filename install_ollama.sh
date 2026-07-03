#!/bin/bash
# Run this from Terminal — it will prompt for your password via sudo.
set -e

echo "=== Downloading and installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

echo ""
echo "=== Pulling qwen3:32b model (this may take several minutes) ==="
ollama pull qwen3:32b

echo ""
echo "✅  Done! Ollama is ready. Launch the app and use the URL IMPORT tab."
