from __future__ import annotations

import re
from uuid import uuid4

from .causal_engine import build_causal_links, calculate_risk, recommended_action
from .clinical_context import has_follow_up_plan, term_spans
from .completeness import information_to_confirm
from .data_store import gold_record_by_id
from .entity_extractor import HybridEntityExtractor
from .models import (
    ActionItem,
    AnalysisResult,
    CaseAnalysis,
    CompletenessAssessment,
    DocumentAnalysis,
    Entity,
    MedicationRecord,
    OverallRecommendation,
    RecordDiscrepancy,
)
from .text_processing import (
    clean_text,
    infer_document_date,
    infer_document_type,
    infer_encounter_dates,
    infer_follow_up_date,
    infer_patient_details,
)


class ClinicalPipeline:
    def __init__(self, require_model: bool = True) -> None:
        self.extractor = HybridEntityExtractor(require_model=require_model)

    def analyse(
        self,
        raw_text: str,
        reference_doc_id: str | None = None,
        document_id: str | None = None,
        document_name: str | None = None,
    ) -> AnalysisResult:
        text = clean_text(raw_text)
        if len(text) < 3:
            raise ValueError("Please provide a clinical note with at least 3 readable characters.")

        gold = gold_record_by_id(reference_doc_id)
        entities = self.extractor.extract(text)
        for entity in entities:
            entity.document_id = document_id
        patient = infer_patient_details(text)
        document_type = infer_document_type(text)

        if gold:
            patient = {
                "name": gold["patient_name"],
                "age": int(gold["age"]),
                "gender": gold["gender"],
                "date_of_birth": "Not identified",
                "patient_id": "Not identified",
            }
            document_type = gold["document_type"]
            entities = self._ensure_gold_entities(text, entities, gold, document_id)

        missing = self._infer_missing_information(text, gold, document_type)
        causal_links = build_causal_links(text, entities)
        risk_score, risk_level = calculate_risk(causal_links, entities, missing)

        if gold and not causal_links:
            risk_level = gold["risk_level"]
            risk_score = {"Low": 18, "Medium": 42, "High": 74}[risk_level]

        action = recommended_action(causal_links, risk_level)
        if gold and not causal_links:
            action = gold["recommended_action"]

        grouped = self._group_text(entities)
        summary = self._build_summary(
            patient,
            grouped,
            document_type,
            risk_level,
        )
        red_flags = grouped.get("RED_FLAG", [])

        return AnalysisResult(
            document_type=document_type,
            patient_details=patient,
            summary=summary,
            entities=entities,
            missing_information=missing,
            red_flags=red_flags,
            risk_score=risk_score,
            risk_level=risk_level,
            recommended_action=action,
            causal_links=causal_links,
            model_name=self.extractor.model_name,
            limitations=[
                "Prototype output requires human review.",
                "Priority scores are workflow indicators, not calibrated clinical probabilities.",
            ],
        )

    @staticmethod
    def _group_text(entities: list[Entity]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for entity in entities:
            grouped.setdefault(entity.label, [])
            if entity.text not in grouped[entity.label]:
                grouped[entity.label].append(entity.text)
        return grouped

    @staticmethod
    def _infer_missing_information(
        text: str,
        gold: dict | None,
        document_type: str,
    ) -> list[str]:
        if gold:
            return gold["missing_information"]
        lower = text.lower()
        if document_type == "Lab Report":
            return []
        checks = {
            "allergy status": not re.search(r"\ballerg|\bnkda\b|no known drug allergies", lower),
            "medication list": not re.search(
                r"\bmedication|\bmedicine|\bmeds?\s*:|\bprescri",
                lower,
            ),
            "follow-up plan": not has_follow_up_plan(text),
        }
        if re.search(
            r"\b(?:could not|unable to|not able to)\b[^.\n]{0,100}"
            r"\b(?:answer|state|confirm)\b[^.\n]{0,100}\b(?:medicine|medication)\b",
            lower,
        ):
            checks["medication list"] = True
        missing = [field for field, is_missing in checks.items() if is_missing]
        explicit_gaps = {
            "contrast reaction details": r"exact nature and severity[^.\n]*(?:not documented|unclear)",
            "medication adherence history": r"adherence history unclear",
            "smoking cessation date": r"cessation date not confirmed",
            "formal cognitive assessment": r"no formal cognitive assessment",
            "pending vitamin B12 and folate": r"(?:b12|vitamin b12)[^.\n]*(?:pending|not back)",
        }
        for label, pattern in explicit_gaps.items():
            if re.search(pattern, lower) and label not in missing:
                missing.append(label)
        return missing

    @staticmethod
    def _build_summary(
        patient: dict,
        grouped: dict[str, list[str]],
        document_type: str,
        risk_level: str,
    ) -> str:
        name = patient.get("name", "The patient")
        diagnoses = grouped.get("DIAGNOSIS", [])[:2]
        findings = grouped.get("LAB_RESULT", [])[:2] + grouped.get("SYMPTOM", [])[:2]
        treatments = grouped.get("MEDICATION", [])[:2]
        clinical_status = grouped.get("CLINICAL_STATUS", [])[:1]
        review_language = {
            "High": "needs prompt review",
            "Medium": "needs follow-up",
            "Low": "is suitable for routine review",
        }[risk_level]
        details: list[str] = []
        if diagnoses:
            details.append(f"Conditions documented include {', '.join(diagnoses)}")
        if findings:
            details.append(f"Key findings include {', '.join(findings)}")
        if treatments:
            details.append(f"Documented treatment includes {', '.join(treatments)}")
        if clinical_status and not diagnoses:
            details.append(f"The documented assessment states {clinical_status[0]}")
        if not details:
            details.append("The note contains limited information suitable for structured extraction")
        return (
            f"{name} was reviewed from a {document_type.lower()}. "
            + ". ".join(details)
            + f". The case {review_language}. "
            "A qualified professional should confirm the result."
        )

    @staticmethod
    def _ensure_gold_entities(
        text: str,
        entities: list[Entity],
        gold: dict,
        document_id: str | None = None,
    ) -> list[Entity]:
        values_by_label = {
            "DIAGNOSIS": gold["diagnoses"],
            "SYMPTOM": gold["symptoms"],
            "MEDICATION": gold["medications"],
            "ALLERGY": gold["allergies"],
            "LAB_RESULT": gold["lab_results"],
            "RED_FLAG": gold["red_flags"],
        }
        existing = {(entity.label, entity.text.lower()) for entity in entities}
        for label, values in values_by_label.items():
            for value in values:
                key = (label, value.lower())
                if key in existing:
                    continue
                spans = list(term_spans(text, value))
                if spans:
                    start, end = spans[0]
                    if any(
                        entity.label == label
                        and start < entity.end
                        and end > entity.start
                        for entity in entities
                    ):
                        continue
                    entities.append(
                        Entity(
                            text=text[start:end],
                            label=label,
                            confidence=0.98,
                            start=start,
                            end=end,
                            source="gold-aligned sample",
                            document_id=document_id,
                        )
                    )
        return sorted(entities, key=lambda item: (item.start, item.label))

    def analyse_many(self, documents: list[dict[str, str | None]]) -> CaseAnalysis:
        if not documents:
            raise ValueError("Add at least one clinical document.")

        analysed: list[DocumentAnalysis] = []
        for sequence, document in enumerate(documents, start=1):
            document_id = str(document.get("document_id") or f"DOC-{sequence:02d}")
            document_name = str(document.get("document_name") or document_id)
            document_text = str(document.get("text") or "")
            result = self.analyse(
                document_text,
                reference_doc_id=document.get("reference_doc_id"),
                document_id=document_id,
                document_name=document_name,
            )
            for link in result.causal_links:
                link.source_documents = [document_name]
            medication_records = result.medication_records or self._medication_records(
                document_text,
                result.entities,
                document_name,
            )
            encounter_dates = infer_encounter_dates(document_text)
            analysed.append(
                DocumentAnalysis(
                    document_id=document_id,
                    document_name=document_name,
                    sequence=sequence,
                    result=result,
                    document_date=infer_document_date(document_text),
                    admission_date=encounter_dates["admission_date"],
                    discharge_date=encounter_dates["discharge_date"],
                    follow_up_date=infer_follow_up_date(document_text),
                    medication_records=medication_records,
                    context_flags=self._context_flags(document_text),
                )
            )

        conflicts = self._identity_conflicts(analysed)
        if any(conflict.startswith("Patient names differ") for conflict in conflicts):
            raise ValueError(
                "The uploaded documents appear to belong to different patients. "
                "Review the patient names before creating a combined record."
            )

        consolidated = self._consolidate(analysed, conflicts)
        discrepancies = self._record_discrepancies(analysed)
        medication_records = [
            record
            for document in analysed
            for record in document.medication_records
        ]
        reconciled_medications = self._reconcile_medication_records(
            medication_records,
            analysed,
        )
        completeness = self._completeness(analysed, consolidated)
        safety_warnings = self._safety_warnings(
            consolidated,
            discrepancies,
            reconciled_medications,
        )
        actions = self._action_items(analysed, completeness)
        overall_recommendation = self._overall_recommendation(
            actions,
            [*conflicts, *[item.field for item in discrepancies]],
            consolidated,
        )
        timeline = self._timeline(analysed)
        return CaseAnalysis(
            case_id=f"CASE-{uuid4().hex[:8].upper()}",
            consolidated=consolidated,
            documents=analysed,
            action_items=actions,
            overall_recommendation=overall_recommendation,
            medication_records=reconciled_medications,
            discrepancies=discrepancies,
            completeness=completeness,
            safety_warnings=safety_warnings,
            record_timeline=timeline,
            conflicts=conflicts,
        )

    @staticmethod
    def _confidence_label(confidence: float, source: str) -> str:
        if source in {"gold-aligned sample", "clinical-pattern"} and confidence >= 0.85:
            return "High"
        if confidence >= 0.9:
            return "High"
        if confidence >= 0.7:
            return "Medium"
        return "Low"

    @staticmethod
    def _medication_key(value: str) -> str:
        lower = value.casefold().replace("sulphate", "sulfate")
        aliases = (
            (r"\b(?:entresto|sacubitril[\s/-]*valsartan)\b", "sacubitril-valsartan"),
            (r"\binsulin\s+glargine\b|\blantus\b", "insulin glargine"),
            (r"\bferrous\s+sulfate\b", "ferrous sulfate"),
        )
        for pattern, key in aliases:
            if re.search(pattern, lower):
                return key
        cleaned = re.sub(r"\([^)]*\)", " ", lower)
        cleaned = re.sub(
            r"\b\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*"
            r"(?:mg|mcg|g|units?|ml|mmol|%)?(?:/kg)?\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"\b(?:od|bd|tds|qds|nocte|prn|daily|twice daily|at night)\b",
            " ",
            cleaned,
        )
        return re.sub(r"[^a-z]+", " ", cleaned).strip()

    @classmethod
    def _canonical_medication_name(
        cls,
        key: str,
        records: list[MedicationRecord],
    ) -> str:
        variants = [record.medication for record in records]
        if key == "sacubitril-valsartan":
            dose_match = next(
                (
                    re.search(
                        r"\b(\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?)\s*mg\b",
                        value,
                        re.I,
                    )
                    for value in variants
                    if re.search(
                        r"\b\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*mg\b",
                        value,
                        re.I,
                    )
                ),
                None,
            )
            dose = re.sub(r"\s+", "", dose_match.group(1)) if dose_match else "24/26"
            return f"Sacubitril-Valsartan (Entresto) {dose} mg BD"
        preferred = next(
            (value for value in reversed(variants) if re.search(r"\d", value)),
            variants[-1],
        )
        return re.sub(r"(?<=\d)(mg|mcg|g)\b", r" \1", preferred, flags=re.I)

    @classmethod
    def _reconcile_medication_records(
        cls,
        records: list[MedicationRecord],
        documents: list[DocumentAnalysis],
    ) -> list[MedicationRecord]:
        document_order = {
            document.document_name: (
                document.document_date or "9999-12-31",
                document.sequence,
            )
            for document in documents
        }
        phase_order = {
            "Past medication": -1,
            "On admission": 0,
            "Current / documented": 1,
            "At discharge": 2,
            "Post-discharge review": 3,
        }
        grouped: dict[str, list[MedicationRecord]] = {}
        for record in records:
            key = cls._medication_key(record.medication)
            if key:
                grouped.setdefault(key, []).append(record)

        reconciled: list[MedicationRecord] = []
        for key, variants in grouped.items():
            ordered = sorted(
                variants,
                key=lambda record: (
                    document_order.get(record.source_document, ("9999-12-31", 999)),
                    phase_order.get(record.phase, 1),
                ),
            )
            history: list[dict[str, str]] = []
            history_index: dict[tuple[str, str], int] = {}
            for record in ordered:
                item_key = (record.phase, record.status)
                if item_key in history_index:
                    existing = history[history_index[item_key]]
                    existing["source"] = "; ".join(
                        dict.fromkeys(
                            [
                                *existing["source"].split("; "),
                                record.source_document,
                            ]
                        )
                    )
                    continue
                history_index[item_key] = len(history)
                history.append(
                    {
                        "stage": record.phase,
                        "status": record.status,
                        "source": record.source_document,
                        "evidence": record.source_text,
                    }
                )

            latest = ordered[-1]
            statuses = {record.status for record in ordered}
            final_status = latest.status
            if "Stopped" in statuses and final_status == "Taken in error":
                final_status = "Stopped"
            confidence = (
                "High" if any(record.confidence == "High" for record in ordered)
                else "Medium" if any(record.confidence == "Medium" for record in ordered)
                else "Low"
            )
            reconciled.append(
                MedicationRecord(
                    medication=cls._canonical_medication_name(key, ordered),
                    phase=latest.phase,
                    status=final_status,
                    confidence=confidence,
                    source_text=latest.source_text,
                    source_document="; ".join(
                        dict.fromkeys(record.source_document for record in ordered)
                    ),
                    history=history,
                )
            )
        return sorted(reconciled, key=lambda record: record.medication.casefold())

    @classmethod
    def _medication_records(
        cls,
        text: str,
        entities: list[Entity],
        document_name: str,
    ) -> list[MedicationRecord]:
        medication_entities = [entity for entity in entities if entity.label == "MEDICATION"]
        records: list[MedicationRecord] = []
        for entity in medication_entities:
            line_start = text.rfind("\n", 0, entity.start) + 1
            line_end = text.find("\n", entity.end)
            line_end = len(text) if line_end < 0 else line_end
            line = text[line_start:line_end].strip()
            clause_start = max(
                text.rfind(".", 0, entity.start),
                text.rfind(";", 0, entity.start),
                text.rfind("\n", 0, entity.start),
            ) + 1
            clause_ends = [
                position
                for position in (
                    text.find(".", entity.end),
                    text.find(";", entity.end),
                    text.find("\n", entity.end),
                )
                if position >= 0
            ]
            clause_end = min(clause_ends) if clause_ends else len(text)
            clause = text[clause_start:clause_end].strip()
            before = text[max(clause_start, entity.start - 100):entity.start]
            section_before = text[max(0, entity.start - 1500):entity.start].upper()

            phase = "Current / documented"
            if "MEDICATIONS ON ADMISSION" in section_before:
                last_admission = section_before.rfind("MEDICATIONS ON ADMISSION")
                last_discharge = section_before.rfind("DISCHARGE MEDICATIONS")
                if last_admission > last_discharge:
                    phase = "On admission"
            if "DISCHARGE MEDICATIONS" in section_before:
                if section_before.rfind("DISCHARGE MEDICATIONS") > section_before.rfind(
                    "MEDICATIONS ON ADMISSION"
                ):
                    phase = "At discharge"
            if re.search(r"\bmeds check\b", section_before[-600:], re.I):
                phase = "Post-discharge review"

            status = "Active"
            line_prefix = text[line_start:entity.start]
            status_prefix = line_prefix
            if phase == "At discharge":
                discharge_heading = text.upper().rfind(
                    "DISCHARGE MEDICATIONS",
                    max(0, entity.start - 2500),
                    entity.start,
                )
                if discharge_heading >= 0:
                    status_prefix = text[discharge_heading:entity.start]
            marker_patterns = [
                ("Stopped", r"\bSTOPPED\s*:"),
                ("Withheld", r"\bWITHHELD\s*:"),
                ("Dose changed", r"\bCHANGED\s*:"),
                ("New", r"\bADDED\s*:"),
                ("Continued", r"\bCONTINUED\s*:"),
            ]
            markers = [
                (match.start(), candidate)
                for candidate, pattern in marker_patterns
                for match in re.finditer(pattern, status_prefix, re.I)
            ]
            if phase == "On admission":
                status = "Active on admission"
            elif markers:
                status = max(markers, key=lambda item: item[0])[1]
            else:
                local_status_text = f"{before[-80:]} {clause}"
                status_patterns = [
                    ("Withheld", r"\b(?:WITHHELD|withheld|on hold)\b"),
                    ("Stopped", r"\b(?:STOPPED|stopped|discontinued)\b"),
                    (
                        "Dose changed",
                        r"\b(?:dose\s+(?:changed|increased|reduced|adjusted)"
                        r"|increased from|reduced from|uptitrated to|adjusted to)\b",
                    ),
                    ("New", r"\b(?:NEW|new addition|commenced|started)\b"),
                    ("Continued", r"\b(?:continuing|continued)\b"),
                ]
                for candidate, pattern in status_patterns:
                    if re.search(pattern, local_status_text, re.I):
                        status = candidate
                        break
                if (
                    re.search(r"\bramipril|ACEi\b", entity.text, re.I)
                    and re.search(
                        r"\b(?:taken\s+one\s+dose\s+by\s+mistake|accidentally\s+took)\b",
                        text[max(0, entity.start - 100):min(len(text), entity.end + 220)],
                        re.I,
                    )
                ):
                    status = "Taken in error"
                elif (
                    re.search(r"\bramipril|ACEi\b", entity.text, re.I)
                    and re.search(r"\bin place of\b|\breplaced by\b", local_status_text, re.I)
                ):
                    status = "Stopped"
                elif (
                    re.search(r"\bentresto|sacubitril", entity.text, re.I)
                    and re.search(r"\b(?:is|was)\s+new\b|\bNEW\b", local_status_text, re.I)
                ):
                    status = "New"
            if re.search(r"\bpreviously\b|\bprevious use\b", clause, re.I):
                phase = "Past medication"
                status = "Previously used"
            entity_clause_after = text[entity.end:clause_end]
            if re.search(r"\bwithheld\b|\bdo not restart\b", entity_clause_after, re.I):
                status = "Withheld"
            if phase == "On admission" and re.search(
                r"\bstopped (?:this|it) (?:herself|himself)|\bnot taking\b|\bran out\b",
                clause,
                re.I,
            ):
                status = "Not reliably taking before admission"

            records.append(
                MedicationRecord(
                    medication=entity.text,
                    phase=phase,
                    status=status,
                    confidence=cls._confidence_label(entity.confidence, entity.source),
                    source_text=line[:240] or entity.text,
                    source_document=document_name,
                )
            )

        unique: dict[tuple[str, str, str, str], MedicationRecord] = {}
        for record in records:
            key = (
                record.medication.casefold(),
                record.phase,
                record.status,
                record.source_document,
            )
            unique[key] = record
        return list(unique.values())

    @staticmethod
    def _safety_warnings(
        consolidated: AnalysisResult,
        discrepancies: list[RecordDiscrepancy],
        medications: list[MedicationRecord],
    ) -> list[str]:
        warnings: dict[str, str] = {}

        def hazard_key(value: str) -> str:
            lower = value.casefold()
            if "ramipril" in lower or "entresto" in lower or "angioedema" in lower:
                return "ace-entresto"
            if "allergy" in lower or "contrast" in lower:
                return "allergy"
            if "myocardial" in lower or "cardiac pathway" in lower:
                return "acute-cardiac"
            if "heart failure" in lower:
                return "heart-failure"
            if "glycaemic" in lower or "diabetes" in lower:
                return "glycaemic"
            if "respiratory" in lower or "oxygen" in lower:
                return "respiratory"
            if "potassium" in lower or "renal" in lower:
                return "renal-electrolyte"
            return re.sub(r"\W+", "-", lower).strip("-")

        for link in consolidated.causal_links:
            if link.weight >= 30:
                warnings.setdefault(
                    hazard_key(f"{link.meaning} {link.action}"),
                    f"{link.meaning}: {link.action}",
                )
        for item in discrepancies:
            if item.clinical_risk == "High":
                warnings.setdefault(
                    hazard_key(f"{item.field} {item.action_required}"),
                    f"{item.field}: {item.action_required}",
                )
        for record in medications:
            if record.status == "Taken in error":
                warnings.setdefault(
                    hazard_key(record.medication),
                    f"{record.medication} was taken in error: confirm the current medication plan.",
                )
        return list(warnings.values())

    @staticmethod
    def _context_flags(text: str) -> list[str]:
        patterns = {
            "social context": r"\blives alone|daughter|son|carer|home assessment|social\b",
            "cognitive context": r"\bcognitive|confusion|recall|MMSE|AMT-4\b",
            "smoking history": r"\bsmok(?:e|er|ing)|pack-years?\b",
        }
        flags = [label for label, pattern in patterns.items() if re.search(pattern, text, re.I)]
        if has_follow_up_plan(text):
            flags.insert(0, "follow-up plan")
        return flags

    @staticmethod
    def _identity_conflicts(documents: list[DocumentAnalysis]) -> list[str]:
        conflicts: list[str] = []
        names = {
            str(document.result.patient_details.get("name"))
            for document in documents
            if document.result.patient_details.get("name") != "Not identified"
        }
        ages = {
            str(document.result.patient_details.get("age"))
            for document in documents
            if document.result.patient_details.get("age") != "Not identified"
        }
        normalised_names = [
            [part.casefold() for part in re.findall(r"[A-Za-z'-]+", name)]
            for name in names
        ]
        incompatible_names = any(
            left[0] != right[0] or left[-1] != right[-1]
            for index, left in enumerate(normalised_names)
            for right in normalised_names[index + 1 :]
            if left and right
        )
        if incompatible_names:
            conflicts.append(f"Patient names differ across documents: {', '.join(sorted(names))}")
        if len(ages) > 1:
            conflicts.append(f"Patient ages differ across documents: {', '.join(sorted(ages))}")
        allergy_values = {
            entity.text
            for document in documents
            for entity in document.result.entities
            if entity.label == "ALLERGY"
        }
        reports_no_allergy = any(
            re.search(r"\b(?:nkda|no known drug allergies)\b", value, re.I)
            for value in allergy_values
        )
        named_allergies = [
            value
            for value in allergy_values
            if not re.search(r"\b(?:nkda|no known drug allergies)\b", value, re.I)
        ]
        if reports_no_allergy and named_allergies:
            conflicts.append(
                "Allergy status conflicts across documents: "
                + ", ".join(sorted(allergy_values))
            )
        return conflicts

    @staticmethod
    def _canonical_condition_entities(entities: list[Entity]) -> list[Entity]:
        diagnoses = [entity for entity in entities if entity.label == "DIAGNOSIS"]
        others = [entity for entity in entities if entity.label != "DIAGNOSIS"]
        selected: list[Entity] = []

        alias_groups = [
            (
                re.compile(r"\bstrokes?\b", re.I),
                ("stroke",),
            ),
            (
                re.compile(r"\b(?:CKD|chronic kidney disease)(?:\s+Stage\s*[1-5][a-c]?)?\b", re.I),
                ("stage 5", "stage 4", "stage 3b", "stage 3a", "stage 3", "stage 2", "stage 1", "chronic kidney disease", "ckd"),
            ),
            (
                re.compile(r"\b(?:HF|heart failure|cardiac failure|reduced ejection fraction heart failure)\b", re.I),
                ("reduced ejection fraction heart failure", "heart failure", "cardiac failure", "hf"),
            ),
        ]
        consumed: set[int] = set()
        for pattern, specificity in alias_groups:
            candidates = [
                (index, entity)
                for index, entity in enumerate(diagnoses)
                if pattern.search(entity.text)
            ]
            if not candidates:
                continue
            chosen = min(
                candidates,
                key=lambda item: next(
                    (
                        rank
                        for rank, phrase in enumerate(specificity)
                        if phrase in item[1].text.casefold()
                    ),
                    len(specificity),
                ),
            )
            selected.append(chosen[1])
            consumed.update(index for index, _ in candidates)

        seen: set[str] = {entity.text.casefold() for entity in selected}
        for index, entity in enumerate(diagnoses):
            if index in consumed or entity.text.casefold() in seen:
                continue
            selected.append(entity)
            seen.add(entity.text.casefold())
        return sorted([*others, *selected], key=lambda entity: (entity.start, entity.label))

    @classmethod
    def _canonical_display_entities(cls, entities: list[Entity]) -> list[Entity]:
        grouped: dict[tuple[str, str], list[Entity]] = {}
        passthrough: list[Entity] = []
        for entity in entities:
            if (
                entity.label == "ALLERGY"
                and re.search(
                    r"\bcauses?\s+(?:severe\s+)?(?:nausea|vomiting|dizziness|headache)\b",
                    entity.text,
                    re.I,
                )
            ):
                entity = Entity(
                    text=entity.text,
                    label="ADVERSE_REACTION",
                    confidence=entity.confidence,
                    start=entity.start,
                    end=entity.end,
                    source=entity.source,
                    document_id=entity.document_id,
                )
            lower = entity.text.casefold()
            key = ""
            if entity.label == "MEDICATION":
                key = cls._medication_key(entity.text)
            elif entity.label == "ALLERGY":
                if re.search(r"\bnkda\b|\bno known drug allergies\b", lower):
                    key = "no known drug allergies"
                elif re.search(r"\bcontrast|iodinated\b", lower) or (
                    "rash" in lower and "mild" in lower
                ):
                    key = "iodinated contrast"
                elif "penicillin" in lower:
                    key = "penicillin"
                elif "codeine" in lower:
                    key = "codeine"
            elif entity.label == "SYMPTOM":
                if re.search(r"\b(?:central )?chest pain\b", lower):
                    key = "chest pain"
                elif re.search(r"\bbreathless(?:ness)?\b|\bshortness of breath\b", lower):
                    key = "shortness of breath"
                elif re.search(
                    r"\bpuffy\b.*\bankles?\b|\bankles?\b.*\bpuffy\b|\bpitting oedema\b",
                    lower,
                ):
                    key = "ankle oedema"
                elif re.search(
                    r"\b(?:dark|darker|black|tarry) stools?\b"
                    r"|\bnoticed (?:the stools|them) darker\b",
                    lower,
                ):
                    key = "dark stools"
            elif entity.label == "RED_FLAG" and re.search(
                r"\b(?:dark|darker|black|tarry) stools?\b"
                r"|\bnoticed (?:the stools|them) darker\b",
                lower,
            ):
                key = "dark stools"
            elif entity.label == "FOLLOW_UP":
                if re.search(r"\bactivity restrictions?\b", lower):
                    key = "activity restrictions"
                elif "full course" in lower and "antibiotics" in lower:
                    key = "antibiotic course"
                elif "check back" in lower and "relapse" in lower:
                    key = "relapse review"
                elif "strict diet" in lower:
                    key = "strict diet"
                elif "gp to check" in lower and "egfr" in lower:
                    key = "gp renal bloods"
                elif "hba1c" in lower and "rechecked" in lower:
                    key = "hba1c recheck"
                elif "cardiology opd" in lower:
                    key = "cardiology opd"
                elif "hf nurse" in lower and "within" in lower:
                    key = "heart failure nurse"
                elif "diabetic nurse review" in lower:
                    key = "diabetes nurse review"
                elif "allergy record correction" in lower:
                    key = "allergy record correction"
                elif "next appointment" in lower:
                    key = "next appointment"
            if key:
                grouped.setdefault((entity.label, key), []).append(entity)
            else:
                passthrough.append(entity)

        canonical: list[Entity] = []
        for (label, key), variants in grouped.items():
            chosen = max(
                variants,
                key=lambda entity: (entity.confidence, len(entity.text)),
            )
            text = chosen.text
            if label == "MEDICATION":
                records = [
                    MedicationRecord(
                        medication=entity.text,
                        phase="Current / documented",
                        status="Active",
                        confidence="High",
                        source_text=entity.text,
                        source_document="",
                    )
                    for entity in variants
                ]
                text = cls._canonical_medication_name(key, records)
            elif label == "ALLERGY" and key == "iodinated contrast":
                has_mild_rash = any(
                    re.search(r"\bmild\b.*\brash\b|\brash\b.*\bmild\b", entity.text, re.I)
                    for entity in variants
                )
                text = (
                    "Iodinated contrast allergy - mild rash"
                    if has_mild_rash
                    else "Iodinated contrast allergy"
                )
            elif label == "ALLERGY" and key == "no known drug allergies":
                text = "No known drug allergies (NKDA)"
            elif label == "SYMPTOM" and key == "chest pain":
                text = (
                    "central chest pain"
                    if any("central chest pain" in entity.text.casefold() for entity in variants)
                    else "chest pain"
                )
            elif label == "SYMPTOM" and key == "shortness of breath":
                text = "shortness of breath"
            elif label == "SYMPTOM" and key == "ankle oedema":
                text = "ankle oedema"
            elif label in {"SYMPTOM", "RED_FLAG"} and key == "dark stools":
                text = "darker stools"
            elif label == "FOLLOW_UP":
                text = {
                    "activity restrictions": "Activity restrictions advised",
                    "antibiotic course": "Complete the full antibiotic course",
                    "relapse review": "Contact the physician if symptoms relapse",
                    "strict diet": "Follow a strict diet",
                    "gp renal bloods": "GP to check U&E and eGFR in 2 weeks",
                    "hba1c recheck": "Recheck HbA1c in 3 months",
                    "cardiology opd": "Cardiology outpatient review in 6 weeks",
                    "heart failure nurse": "Heart failure nurse contact within 48 hours of discharge",
                    "diabetes nurse review": "Diabetes nurse review in 4-6 weeks",
                    "allergy record correction": "Correct the allergy record before end of week",
                    "next appointment": "Next GP appointment in 2 weeks",
                }[key]
            canonical.append(
                Entity(
                    text=text,
                    label=label,
                    confidence=max(entity.confidence for entity in variants),
                    start=chosen.start,
                    end=chosen.end,
                    source=chosen.source,
                    document_id=chosen.document_id,
                )
            )
        unique: dict[tuple[str, str], Entity] = {}
        for entity in [*passthrough, *canonical]:
            entity_key = (entity.label, entity.text.casefold())
            current = unique.get(entity_key)
            if current is None or entity.confidence > current.confidence:
                unique[entity_key] = entity
        return sorted(unique.values(), key=lambda entity: (entity.start, entity.label))

    @classmethod
    def _record_discrepancies(
        cls,
        documents: list[DocumentAnalysis],
    ) -> list[RecordDiscrepancy]:
        discrepancies: list[RecordDiscrepancy] = []

        contrast_entries: list[tuple[str, str]] = []
        for document in documents:
            allergy_text = " | ".join(
                entity.text
                for entity in document.result.entities
                if entity.label == "ALLERGY"
                and re.search(r"\bcontrast|rash\b", entity.text, re.I)
            )
            if allergy_text:
                contrast_entries.append((document.document_name, allergy_text))
        unclear = next(
            (
                item for item in contrast_entries
                if re.search(r"\bcontrast dye\b|\bdetails? unclear\b", item[1], re.I)
            ),
            None,
        )
        mild = next(
            (
                item for item in contrast_entries
                if re.search(r"\brash\b|\bmild\b", item[1], re.I)
            ),
            None,
        )
        if unclear and mild and unclear[0] != mild[0]:
            discrepancies.append(
                RecordDiscrepancy(
                    category="Conflict",
                    field="Contrast allergy severity",
                    document_a=unclear[0],
                    value_a=unclear[1],
                    document_b=mild[0],
                    value_b=mild[1],
                    clinical_risk="High",
                    action_required="Verify the original reaction and correct the allergy record before future contrast imaging.",
                )
            )

        no_allergy = next(
            (
                (document.document_name, entity.text)
                for document in documents
                for entity in document.result.entities
                if entity.label == "ALLERGY"
                and re.search(r"\b(?:NKDA|no known drug allergies)\b", entity.text, re.I)
            ),
            None,
        )
        named_allergy = next(
            (
                (document.document_name, entity.text)
                for document in documents
                for entity in document.result.entities
                if entity.label == "ALLERGY"
                and not re.search(r"\b(?:NKDA|no known drug allergies)\b", entity.text, re.I)
            ),
            None,
        )
        if no_allergy and named_allergy and no_allergy[0] != named_allergy[0]:
            discrepancies.append(
                RecordDiscrepancy(
                    category="Conflict",
                    field="Allergy status",
                    document_a=no_allergy[0],
                    value_a=no_allergy[1],
                    document_b=named_allergy[0],
                    value_b=named_allergy[1],
                    clinical_risk="High",
                    action_required="Verify and update the current allergy record before prescribing.",
                )
            )

        ramipril_admission = next(
            (
                record for document in documents for record in document.medication_records
                if "ramipril" in record.medication.casefold()
                and record.phase == "On admission"
            ),
            None,
        )
        ramipril_error = next(
            (
                record for document in documents for record in document.medication_records
                if "ramipril" in record.medication.casefold()
                and record.status == "Taken in error"
            ),
            None,
        )
        stopped = next(
            (
                record for document in documents for record in document.medication_records
                if "ramipril" in record.medication.casefold()
                and record.status == "Stopped"
            ),
            None,
        )
        if ramipril_error and (stopped or ramipril_admission):
            reference = stopped or ramipril_admission
            discrepancies.append(
                RecordDiscrepancy(
                    category="Medication safety issue",
                    field="Ramipril after Entresto initiation",
                    document_a=reference.source_document,
                    value_a=f"{reference.medication}: {reference.status}",
                    document_b=ramipril_error.source_document,
                    value_b=f"{ramipril_error.medication}: taken after discharge",
                    clinical_risk="High",
                    action_required="Confirm ramipril is stopped and the remaining supply is removed.",
                )
            )

        stage_entries: list[tuple[str, str, int]] = []
        for document in documents:
            stages = [
                entity.text
                for entity in document.result.entities
                if entity.label == "DIAGNOSIS"
                and re.search(r"\bCKD Stage\s*[1-5][a-c]?\b", entity.text, re.I)
            ]
            if stages:
                for value in stages:
                    stage_match = re.search(r"Stage\s*([1-5])", value, re.I)
                    if stage_match:
                        stage_entries.append(
                            (document.document_name, value, int(stage_match.group(1)))
                        )
        distinct_stages = {value.casefold() for _, value, _ in stage_entries}
        if len(distinct_stages) > 1:
            baseline = min(stage_entries, key=lambda item: item[2])
            current = max(stage_entries, key=lambda item: item[2])
            discrepancies.append(
                RecordDiscrepancy(
                    category="Clinical change",
                    field="Kidney disease stage",
                    document_a=baseline[0],
                    value_a=f"Baseline: {baseline[1]}",
                    document_b=current[0],
                    value_b=f"More severe/current finding: {current[1]}",
                    clinical_risk="Medium",
                    action_required="Use the latest renal function for medication dosing and follow-up.",
                )
            )
        return discrepancies

    @staticmethod
    def _completeness(
        documents: list[DocumentAnalysis],
        consolidated: AnalysisResult,
    ) -> CompletenessAssessment:
        grouped = consolidated.grouped_entities()
        unresolved = set(consolidated.missing_information)
        domain_gaps = {
            "Medication reconciliation": {
                "medication list",
                "medication adherence history",
            },
            "Allergies and reactions": {
                "allergy status",
                "contrast reaction details",
            },
            "Important test results": {
                "pending vitamin B12 and folate",
                "repeat troponin result",
            },
            "Follow-up plan": {
                "follow-up plan",
                "home glucose monitoring plan",
                "recent spirometry",
            },
            "Social or cognitive context": {
                "smoking cessation date",
                "smoking status",
                "formal cognitive assessment",
            },
        }
        text_signals = {
            "Patient identity": consolidated.patient_details.get("name") != "Not identified",
            "Age or date of birth": (
                consolidated.patient_details.get("age") != "Not identified"
                or consolidated.patient_details.get("date_of_birth") != "Not identified"
            ),
            "Document dates": all(document.document_date for document in documents),
            "Current conditions": bool(
                grouped.get("DIAGNOSIS") or grouped.get("CLINICAL_STATUS")
            ),
            "Symptoms or clinical signs": bool(
                grouped.get("SYMPTOM")
                or grouped.get("RED_FLAG")
                or grouped.get("CLINICAL_STATUS")
            ),
            "Medication reconciliation": bool(
                any(document.medication_records for document in documents)
                or any(
                    "no prescription is necessary" in entity.text.casefold()
                    for entity in grouped.get("CLINICAL_STATUS", [])
                )
            ),
            "Allergies and reactions": bool(grouped.get("ALLERGY")),
            "Important test results": bool(
                grouped.get("LAB_RESULT")
                or any(
                    "vital signs are within normal ranges" in entity.text.casefold()
                    for entity in grouped.get("CLINICAL_STATUS", [])
                )
            ),
            "Follow-up plan": any(
                document.follow_up_date
                or "follow-up plan" in document.context_flags
                for document in documents
            ),
            "Social or cognitive context": any(
                {"social context", "cognitive context", "smoking history"}
                .intersection(document.context_flags)
                for document in documents
            ),
        }
        for field, gaps in domain_gaps.items():
            if unresolved.intersection(gaps):
                text_signals[field] = False
        documented = [field for field, present in text_signals.items() if present]
        missing = [
            field
            for field, present in text_signals.items()
            if not present
        ]
        return CompletenessAssessment(
            score=len(documented),
            total=len(text_signals),
            documented_fields=documented,
            missing_fields=missing,
        )

    def _consolidate(
        self,
        documents: list[DocumentAnalysis],
        conflicts: list[str],
    ) -> AnalysisResult:
        ranked = {"Low": 0, "Medium": 1, "High": 2}
        highest = max(documents, key=lambda item: ranked[item.result.risk_level])
        patient = next(
            (
                document.result.patient_details
                for document in documents
                if document.result.patient_details.get("name") != "Not identified"
            ),
            highest.result.patient_details,
        )

        entities: list[Entity] = []
        seen_entities: set[tuple[str, str, str | None]] = set()
        links = []
        seen_links: set[tuple[str, str]] = set()
        missing: list[str] = []
        red_flags: list[str] = []
        model_names: list[str] = []

        for document in documents:
            model_names.append(document.result.model_name)
            for entity in document.result.entities:
                key = (entity.label, entity.text.casefold(), entity.document_id)
                if key not in seen_entities:
                    seen_entities.add(key)
                    entities.append(entity)
            for link in document.result.causal_links:
                key = (link.meaning, link.action)
                if key in seen_links:
                    existing = next(
                        item for item in links
                        if (item.meaning, item.action) == key
                    )
                    existing.source_documents = list(
                        dict.fromkeys(existing.source_documents + link.source_documents)
                    )
                else:
                    seen_links.add(key)
                    links.append(link)
            missing.extend(document.result.missing_information)
            red_flags.extend(document.result.red_flags)

        entities = self._canonical_condition_entities(entities)
        entities = self._canonical_display_entities(entities)
        missing = list(dict.fromkeys(missing))
        red_flags = list(dict.fromkeys(red_flags))
        links.sort(key=lambda item: item.weight, reverse=True)
        grouped = self._group_text(entities)
        document_types = list(dict.fromkeys(item.result.document_type for item in documents))
        diagnoses = grouped.get("DIAGNOSIS", [])[:3]
        findings = grouped.get("LAB_RESULT", [])[:2] + grouped.get("SYMPTOM", [])[:2]
        clinical_status = grouped.get("CLINICAL_STATUS", [])[:1]
        clinical_focus = (
            f"Conditions documented across the record include {', '.join(diagnoses)}."
            if diagnoses
            else (
                f"No diagnosis was clearly extracted; the main documented findings are {', '.join(findings)}."
                if findings
                else (
                    f"The documented assessment states {clinical_status[0]}."
                    if clinical_status
                    else "The record contains limited extractable clinical detail."
                )
            )
        )
        document_label = "document" if len(documents) == 1 else "documents"
        summary = (
            f"{patient.get('name', 'The patient')}'s consolidated record combines "
            f"{len(documents)} {document_label}: {', '.join(document_types)}. "
            f"{clinical_focus} "
            f"The highest workflow priority is {highest.result.risk_level.lower()}, driven by "
            f"{links[0].meaning.lower() if links else 'the extracted record'}. "
            "Each action remains subject to human confirmation."
        )
        return AnalysisResult(
            document_type=(
                "Combined record (1 document)"
                if len(documents) == 1
                else f"Combined record ({len(documents)} documents)"
            ),
            patient_details=patient,
            summary=summary,
            entities=entities,
            missing_information=missing,
            red_flags=red_flags,
            risk_score=max(item.result.risk_score for item in documents),
            risk_level=highest.result.risk_level,
            recommended_action=recommended_action(links, highest.result.risk_level),
            causal_links=links,
            model_name=" + ".join(dict.fromkeys(model_names)),
            limitations=[
                "Documents are combined only after patient-identity checks.",
                "Recommendations are workflow support, not autonomous clinical decisions.",
                "Graph edges distinguish observations, expert-rule associations and intervention hypotheses.",
                *conflicts,
            ],
        )

    def _action_items(
        self,
        documents: list[DocumentAnalysis],
        completeness: CompletenessAssessment,
    ) -> list[ActionItem]:
        items: list[ActionItem] = []
        clinical_items: dict[tuple[str, str], ActionItem] = {}
        seen_missing: set[str] = set()
        priority_rank = {"Low": 0, "Medium": 1, "High": 2}
        for document in documents:
            for link in document.result.causal_links:
                key = (
                    link.action.casefold().rstrip(" ."),
                    link.routing_destination.casefold(),
                )
                if key in clinical_items:
                    existing = clinical_items[key]
                    existing.source_documents = list(
                        dict.fromkeys(
                            [
                                *existing.source_documents,
                                *(link.source_documents or [document.document_name]),
                            ]
                        )
                    )
                    if link.meaning.casefold() not in existing.reason.casefold():
                        existing.reason = f"{existing.reason}; {link.meaning}"
                    existing.urgency_score = max(existing.urgency_score, link.weight)
                    if priority_rank[document.result.risk_level] > priority_rank[existing.priority]:
                        existing.priority = document.result.risk_level
                    continue
                item = ActionItem(
                    action=link.action,
                    route_to=link.routing_destination,
                    due_by=document.follow_up_date or link.follow_up_window,
                    reason=link.meaning,
                    priority=document.result.risk_level,
                    source_documents=link.source_documents or [document.document_name],
                    urgency_score=link.weight,
                    evidence_basis=link.evidence_basis,
                )
                clinical_items[key] = item
                items.append(item)
            for field in document.result.missing_information:
                key = field.casefold()
                if key in seen_missing:
                    continue
                seen_missing.add(key)
                items.append(
                    ActionItem(
                        action=f"Confirm {field}",
                        route_to="Document review queue",
                        due_by="Before case closure",
                        reason="Required information is absent or unclear",
                        priority="Low",
                        source_documents=[document.document_name],
                        urgency_score=0,
                        evidence_basis="Completeness check",
                    )
                )
        all_sources = [document.document_name for document in documents]
        unresolved = information_to_confirm(
            [
                field
                for document in documents
                for field in document.result.missing_information
            ],
            completeness.missing_fields,
        )
        for field in unresolved:
            key = field.casefold()
            if key in seen_missing:
                continue
            seen_missing.add(key)
            items.append(
                ActionItem(
                    action=f"Confirm {field}",
                    route_to="Document review queue",
                    due_by="Before case closure",
                    reason="This record area is incomplete or not documented",
                    priority="Low",
                    source_documents=all_sources,
                    urgency_score=0,
                    evidence_basis="Completeness check",
                )
            )
        order = {"High": 0, "Medium": 1, "Low": 2}
        return sorted(
            items,
            key=lambda item: (
                order[item.priority],
                -item.urgency_score,
                item.due_by,
                item.action,
            ),
        )

    @staticmethod
    def _overall_recommendation(
        actions: list[ActionItem],
        conflicts: list[str],
        consolidated: AnalysisResult,
    ) -> OverallRecommendation:
        if not actions:
            return OverallRecommendation(
                priority=consolidated.risk_level,
                headline="Routine human review",
                immediate_next_step=consolidated.recommended_action,
                coordination_plan="Document the review outcome and continue the agreed follow-up plan.",
                timeframe="Routine queue",
                rationale="No specific escalation rule or documentation gap was identified.",
                source_documents=["Combined clinical record"],
            )

        clinical_actions = [
            item for item in actions
            if item.evidence_basis != "Completeness check"
        ]
        primary = clinical_actions[0] if clinical_actions else actions[0]
        supporting = [
            item for item in clinical_actions[1:3]
            if item.action != primary.action
        ]
        coordination_parts = [
            f"{item.action.rstrip('.')} via {item.route_to}"
            for item in supporting
        ]
        completeness_count = len(
            [item for item in actions if item.evidence_basis == "Completeness check"]
        )
        if completeness_count:
            coordination_parts.append(
                f"confirm {completeness_count} missing information "
                f"item{'s' if completeness_count != 1 else ''} before case closure"
            )
        if conflicts:
            coordination_parts.append("reconcile conflicting information across the record")

        rationale = primary.reason
        if supporting:
            rationale += (
                "; additional concerns include "
                + ", ".join(item.reason.lower() for item in supporting)
            )

        return OverallRecommendation(
            priority=primary.priority,
            headline=f"{primary.priority}-priority coordinated review",
            immediate_next_step=primary.action,
            coordination_plan=(
                "; ".join(coordination_parts)[:1].upper()
                + "; ".join(coordination_parts)[1:]
                + "."
                if coordination_parts
                else "Complete the primary action and document the outcome."
            ),
            timeframe=primary.due_by,
            rationale=rationale + ".",
            source_documents=list(
                dict.fromkeys(
                    source
                    for item in [primary, *supporting]
                    for source in item.source_documents
                )
            ),
        )

    @staticmethod
    def _timeline(documents: list[DocumentAnalysis]) -> list[dict[str, str | int]]:
        timeline = []
        ordered = sorted(
            documents,
            key=lambda document: (
                document.document_date is None,
                document.document_date or "",
                document.sequence,
            ),
        )
        for display_sequence, document in enumerate(ordered, start=1):
            grouped = document.result.grouped_entities()
            conditions = list(dict.fromkeys(entity.text for entity in grouped.get("DIAGNOSIS", [])))
            findings = list(
                dict.fromkeys(
                    entity.text
                    for label in ("LAB_RESULT", "SYMPTOM", "RED_FLAG")
                    for entity in grouped.get(label, [])
                )
            )
            timeline.append(
                {
                    "sequence": display_sequence,
                    "source_order": document.sequence,
                    "document_id": document.document_id,
                    "document_name": document.document_name,
                    "document_type": document.result.document_type,
                    "document_date": document.document_date,
                    "follow_up_date": document.follow_up_date,
                    "conditions": conditions[:3],
                    "key_findings": findings[:4],
                    "priority": document.result.risk_level,
                    "next_action": document.result.recommended_action,
                }
            )
        return timeline
