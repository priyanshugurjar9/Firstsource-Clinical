from __future__ import annotations

import csv
import json
from functools import lru_cache
from typing import Any

from .paths import DATA_DIR


DOCUMENT_DATA = DATA_DIR / "clinical_poc_synthetic_dataset.csv"
ENTITY_DATA = DATA_DIR / "clinical_poc_entity_annotations.csv"


@lru_cache(maxsize=1)
def load_documents() -> list[dict[str, str]]:
    with DOCUMENT_DATA.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def load_entity_lexicon() -> dict[str, list[str]]:
    lexicon: dict[str, set[str]] = {}
    with ENTITY_DATA.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            lexicon.setdefault(row["entity_label"], set()).add(row["entity_text"])
    return {label: sorted(values, key=len, reverse=True) for label, values in lexicon.items()}


def parse_json_field(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def sample_options() -> dict[str, dict[str, str]]:
    options: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in load_documents():
        key = (row["document_type"], row["gold_risk_level"])
        if key in seen:
            continue
        seen.add(key)
        label = f"{row['document_type']} | {row['gold_risk_level']} priority | {row['doc_id']}"
        options[label] = row
    return options


def patient_journey_options() -> dict[str, list[dict[str, str]]]:
    journeys: dict[str, list[dict[str, str]]] = {}
    for row in load_documents():
        journeys.setdefault(row["patient_name"], []).append(row)
    return {
        name: sorted(records, key=lambda item: item["doc_id"])
        for name, records in journeys.items()
        if len(records) >= 2
    }


def gold_record_by_id(doc_id: str | None) -> dict[str, Any] | None:
    if not doc_id:
        return None
    for row in load_documents():
        if row["doc_id"] == doc_id:
            return {
                "document_type": row["document_type"],
                "patient_name": row["patient_name"],
                "age": row["age"],
                "gender": row["gender"],
                "diagnoses": parse_json_field(row["gold_diagnoses"]),
                "symptoms": parse_json_field(row["gold_symptoms"]),
                "medications": parse_json_field(row["gold_medications"]),
                "allergies": parse_json_field(row["gold_allergies"]),
                "lab_results": parse_json_field(row["gold_lab_results"]),
                "red_flags": parse_json_field(row["gold_red_flags"]),
                "missing_information": parse_json_field(row["gold_missing_information"]),
                "risk_level": row["gold_risk_level"],
                "recommended_action": row["gold_recommended_action"],
            }
    return None
