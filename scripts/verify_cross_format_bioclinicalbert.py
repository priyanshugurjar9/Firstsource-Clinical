"""Verify mandatory BioClinicalBERT extraction across every supported format."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import ClinicalPipeline
from src.text_processing import extract_uploaded_text, infer_document_date


EXAMPLE_DIR = ROOT / "examples" / "cross_format"
FORMATS = ("png", "pdf", "docx", "md", "txt")


class LocalUpload:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def normalised_values(result, label: str) -> set[str]:
    return {
        entity.text.casefold().strip(" .")
        for entity in result.entities
        if entity.label == label
    }


def main() -> None:
    pipeline = ClinicalPipeline(require_model=True)
    report: dict[str, object] = {
        "model": pipeline.extractor.model_name,
        "formats": {},
    }
    failures: list[str] = []

    for suffix in FORMATS:
        path = EXAMPLE_DIR / f"clinical_review_note.{suffix}"
        text = extract_uploaded_text(LocalUpload(path))
        result = pipeline.analyse(text, document_id=suffix.upper())
        model_entities = [
            {
                "label": entity.label,
                "text": entity.text,
                "confidence": entity.confidence,
            }
            for entity in result.entities
            if entity.source == "BioClinicalBERT"
        ]
        symptoms = normalised_values(result, "SYMPTOM")
        medications = normalised_values(result, "MEDICATION")
        allergies = normalised_values(result, "ALLERGY")
        diagnoses = normalised_values(result, "DIAGNOSIS")
        lab_results = normalised_values(result, "LAB_RESULT")
        checks = {
            "patient_name": result.patient_details.get("name") == "Amelia Hart",
            "age": result.patient_details.get("age") == 67,
            "gender": result.patient_details.get("gender") == "Female",
            "document_date": infer_document_date(text) == "2026-06-18",
            "model_entities_present": bool(model_entities),
            "type_2_diabetes": any(
                "type 2 diabetes mellitus" in value for value in diagnoses
            ),
            "hypertension": any("hypertension" in value for value in diagnoses),
            "fatigue": any("fatigue" in value for value in symptoms),
            "blurred_vision": any("blurred vision" in value for value in symptoms),
            "dizziness": any("dizziness" in value for value in symptoms),
            "negated_chest_pain_excluded": not any(
                "chest pain" in value for value in symptoms
            ),
            "metformin": any("metformin" in value for value in medications),
            "amlodipine": any("amlodipine" in value for value in medications),
            "penicillin_allergy": any("penicillin" in value for value in allergies),
            "hba1c": any("hba1c" in value and "9.4" in value for value in lab_results),
            "blood_pressure": any(
                "168/96" in value for value in lab_results
            ),
            "follow_up_text": "within 7 days" in text.casefold(),
            "priority": result.risk_level == "Medium",
        }
        failed_checks = [name for name, passed in checks.items() if not passed]
        if failed_checks:
            failures.append(f"{suffix}: {', '.join(failed_checks)}")
        report["formats"][suffix] = {
            "extracted_characters": len(text),
            "patient": result.patient_details,
            "priority": result.risk_level,
            "model_entities": model_entities,
            "checks": checks,
        }

    report["passed"] = not failures
    report["failures"] = failures
    output_path = EXAMPLE_DIR / "verification_report.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit("Cross-format verification failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
