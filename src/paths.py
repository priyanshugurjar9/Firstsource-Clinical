from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(os.getenv("CLINICAL_HUB_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models" / "bioclinicalbert-ner"
LOG_DIR = PROJECT_ROOT / "logs"
