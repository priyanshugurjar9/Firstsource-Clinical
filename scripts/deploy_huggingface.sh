#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 HUGGINGFACE_USERNAME/SPACE_NAME"
  exit 1
fi

SPACE_ID="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_FILE="$ROOT_DIR/models/bioclinicalbert-ner/model.safetensors"

if ! command -v hf >/dev/null 2>&1; then
  echo "The Hugging Face CLI is required."
  echo "Install it with: curl -LsSf https://hf.co/cli/install.sh | bash"
  exit 1
fi

if ! hf auth whoami >/dev/null 2>&1; then
  echo "Authenticate first with: hf auth login"
  exit 1
fi

if [[ ! -f "$MODEL_FILE" ]]; then
  echo "Required checkpoint not found: $MODEL_FILE"
  exit 1
fi

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

cp "$ROOT_DIR/app.py" "$STAGE_DIR/"
cp "$ROOT_DIR/Dockerfile" "$STAGE_DIR/"
cp "$ROOT_DIR/README.md" "$STAGE_DIR/"
cp "$ROOT_DIR/requirements.txt" "$STAGE_DIR/"

mkdir -p "$STAGE_DIR/.streamlit"
cp "$ROOT_DIR/.streamlit/config.toml" "$STAGE_DIR/.streamlit/"

for directory in src data models; do
  cp -R "$ROOT_DIR/$directory" "$STAGE_DIR/$directory"
done

find "$STAGE_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$STAGE_DIR" -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete

echo "Creating public Docker Space: $SPACE_ID"
hf repos create "$SPACE_ID" \
  --type space \
  --space-sdk docker \
  --flavor cpu-basic \
  --public \
  --exist-ok

echo "Uploading the application and BioClinicalBERT checkpoint..."
hf upload "$SPACE_ID" "$STAGE_DIR" . \
  --type space \
  --commit-message "Deploy Clinical Document Intelligence Hub"

SPACE_SLUG="$(printf '%s' "$SPACE_ID" | tr '[:upper:]_/' '[:lower:]--')"
echo
echo "Deployment submitted."
echo "Space page: https://huggingface.co/spaces/$SPACE_ID"
echo "Public app: https://${SPACE_SLUG}.hf.space"
