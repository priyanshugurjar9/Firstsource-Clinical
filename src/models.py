from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Entity:
    text: str
    label: str
    confidence: float
    start: int
    end: int
    source: str = "clinical-lexicon"
    document_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CausalLink:
    finding: str
    meaning: str
    implication: str
    action: str
    weight: int
    evidence_type: str = "Expert rule association"
    evidence_basis: str = "Transparent POC rule"
    source_documents: list[str] = field(default_factory=list)
    routing_destination: str = "Clinical review team"
    follow_up_window: str = "Routine queue"
    display_interpretation: str | None = None
    display_concern: str | None = None
    display_intervention: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    document_type: str
    patient_details: dict[str, Any]
    summary: str
    entities: list[Entity]
    missing_information: list[str]
    red_flags: list[str]
    risk_score: int
    risk_level: str
    recommended_action: str
    causal_links: list[CausalLink]
    model_name: str
    limitations: list[str] = field(default_factory=list)
    medication_records: list[MedicationRecord] = field(default_factory=list)

    def grouped_entities(self) -> dict[str, list[Entity]]:
        grouped: dict[str, list[Entity]] = {}
        for entity in self.entities:
            grouped.setdefault(entity.label, []).append(entity)
        return grouped

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entities"] = [entity.to_dict() for entity in self.entities]
        payload["causal_links"] = [link.to_dict() for link in self.causal_links]
        payload["medication_records"] = [
            record.to_dict() for record in self.medication_records
        ]
        return payload


@dataclass
class ActionItem:
    action: str
    route_to: str
    due_by: str
    reason: str
    priority: str
    source_documents: list[str]
    urgency_score: int = 0
    status: str = "Open - requires human confirmation"
    evidence_basis: str = "Rule-supported workflow recommendation"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OverallRecommendation:
    priority: str
    headline: str
    immediate_next_step: str
    coordination_plan: str
    timeframe: str
    rationale: str
    source_documents: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MedicationRecord:
    medication: str
    phase: str
    status: str
    confidence: str
    source_text: str
    source_document: str
    history: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecordDiscrepancy:
    category: str
    field: str
    document_a: str
    value_a: str
    document_b: str
    value_b: str
    clinical_risk: str
    action_required: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompletenessAssessment:
    score: int
    total: int
    documented_fields: list[str]
    missing_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentAnalysis:
    document_id: str
    document_name: str
    sequence: int
    result: AnalysisResult
    document_date: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None
    follow_up_date: str | None = None
    medication_records: list[MedicationRecord] = field(default_factory=list)
    context_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "sequence": self.sequence,
            "document_date": self.document_date,
            "admission_date": self.admission_date,
            "discharge_date": self.discharge_date,
            "follow_up_date": self.follow_up_date,
            "medication_records": [record.to_dict() for record in self.medication_records],
            "context_flags": self.context_flags,
            "result": self.result.to_dict(),
        }


@dataclass
class CaseAnalysis:
    case_id: str
    consolidated: AnalysisResult
    documents: list[DocumentAnalysis]
    action_items: list[ActionItem]
    overall_recommendation: OverallRecommendation
    medication_records: list[MedicationRecord]
    discrepancies: list[RecordDiscrepancy]
    completeness: CompletenessAssessment
    safety_warnings: list[str]
    record_timeline: list[dict[str, Any]]
    conflicts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "consolidated": self.consolidated.to_dict(),
            "documents": [document.to_dict() for document in self.documents],
            "action_items": [item.to_dict() for item in self.action_items],
            "overall_recommendation": self.overall_recommendation.to_dict(),
            "medication_records": [record.to_dict() for record in self.medication_records],
            "discrepancies": [item.to_dict() for item in self.discrepancies],
            "completeness": self.completeness.to_dict(),
            "safety_warnings": self.safety_warnings,
            "record_timeline": self.record_timeline,
            "conflicts": self.conflicts,
        }
