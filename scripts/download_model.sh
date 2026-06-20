#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$ROOT_DIR/models/bioclinicalbert-ner"
MODEL_FILE="$MODEL_DIR/model.safetensors"
MODEL_URL="https://huggingface.co/spaces/gurjar01/clinical-document-intelligence-hub/resolve/main/models/bioclinicalbert-ner/model.safetensors"

if [[ -f "$MODEL_FILE" ]]; then
  echo "BioClinicalBERT checkpoint already exists: $MODEL_FILE"
  exit 0
fi

mkdir -p "$MODEL_DIR"
echo "Downloading the fine-tuned BioClinicalBERT checkpoint..."
curl --fail --location --progress-bar "$MODEL_URL" --output "$MODEL_FILE"
echo "Checkpoint saved to: $MODEL_FILE"
