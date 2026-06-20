"""Fail fast unless the required BioClinicalBERT checkpoint loads and predicts."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import ClinicalPipeline
from src.paths import MODEL_DIR


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    weights = MODEL_DIR / "model.safetensors"
    if not weights.exists():
        raise SystemExit(f"Missing required model weights: {weights}")

    pipeline = ClinicalPipeline(require_model=True)
    result = pipeline.analyse(
        "Patient: Test Patient. Age: 60. Female. "
        "Fatigue and blurred vision. Metformin 1000 mg twice daily."
    )
    predictions = [
        entity for entity in result.entities if entity.source == "BioClinicalBERT"
    ]
    if not predictions:
        raise SystemExit("The checkpoint loaded but produced no model-sourced entities.")

    print(f"model={pipeline.extractor.model_name}")
    print(f"weights={weights}")
    print(f"size_bytes={weights.stat().st_size}")
    print(f"sha256={sha256(weights)}")
    print(f"model_entities={len(predictions)}")


if __name__ == "__main__":
    main()
