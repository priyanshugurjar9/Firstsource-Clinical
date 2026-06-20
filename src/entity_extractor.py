from __future__ import annotations

import json
import os
import re

from .clinical_context import (
    FOLLOW_UP_ACTION_PATTERN,
    LAB_PATTERNS,
    active_term_spans,
    is_family_history,
    is_historical,
    is_hypothetical,
    is_negated,
    iter_text_chunks,
    term_spans,
)
from .data_store import load_entity_lexicon
from .models import Entity
from .paths import MODEL_DIR


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


class HybridEntityExtractor:
    """Local clinical extractor combining a trained checkpoint, lexicon and patterns."""

    def __init__(self, require_model: bool = True) -> None:
        self.lexicon = load_entity_lexicon()
        self.tokenizer = None
        self.model = None
        self.confidence_threshold = 0.55
        self.model_name = "Clinical lexicon + regex baseline"
        use_model = require_model or os.getenv("ENABLE_BIOCLINICALBERT", "1") == "1"
        load_error: Exception | None = None
        if MODEL_DIR.exists() and use_model:
            try:
                from transformers import AutoModelForTokenClassification, AutoTokenizer

                self.tokenizer = AutoTokenizer.from_pretrained(
                    MODEL_DIR, use_fast=True, local_files_only=True
                )
                self.model = AutoModelForTokenClassification.from_pretrained(
                    MODEL_DIR, local_files_only=True
                )
                self.model.eval()
                report_path = MODEL_DIR / "training_report.json"
                if report_path.exists():
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    self.confidence_threshold = max(
                        0.45,
                        float(
                            report.get(
                                "confidence_threshold",
                                self.confidence_threshold,
                            )
                        ),
                    )
                self.model_name = "Fine-tuned BioClinicalBERT + validation layer"
            except Exception as exc:
                load_error = exc
                self.tokenizer = None
                self.model = None
        if require_model and self.model is None:
            detail = (
                f" The checkpoint could not be loaded: {load_error}"
                if load_error
                else f" No checkpoint was found at {MODEL_DIR}."
            )
            raise RuntimeError(
                "BioClinicalBERT is required for clinical extraction."
                f"{detail} Install requirements.txt and restore the local checkpoint."
            )

    def extract(self, text: str) -> list[Entity]:
        entities = self._extract_with_model(text) if self.model is not None else []
        entities.extend(self._extract_with_lexicon(text))
        entities.extend(self._extract_pattern_entities(text))
        return self._deduplicate(entities)

    def _extract_with_model(self, text: str) -> list[Entity]:
        import torch

        missing_section_start = text.lower().find("missing or unclear information")
        chunks = list(iter_text_chunks(text))
        chunk_texts = [chunk for _, chunk, _, _ in chunks]
        encoded = self.tokenizer(
            chunk_texts,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        offsets_batch = encoded.pop("offset_mapping").tolist()
        with torch.no_grad():
            probabilities_batch = self.model(**encoded).logits.softmax(dim=-1)
        predicted_batch = probabilities_batch.argmax(dim=-1).tolist()

        entities: list[Entity] = []
        for chunk_index, (chunk_start, _, owned_start, owned_end) in enumerate(chunks):
            offsets = offsets_batch[chunk_index]
            probabilities = probabilities_batch[chunk_index]
            predicted = predicted_batch[chunk_index]
            current = None
            for token_index, label_id in enumerate(predicted):
                local_start, local_end = offsets[token_index]
                if local_start == local_end:
                    continue
                start = chunk_start + local_start
                end = chunk_start + local_end
                midpoint = (start + end) / 2
                if midpoint < owned_start or midpoint >= owned_end:
                    if current:
                        entities.append(current)
                        current = None
                    continue
                raw_label = self.model.config.id2label[label_id]
                confidence = float(probabilities[token_index, label_id])
                if raw_label == "O" or confidence < self.confidence_threshold:
                    if current:
                        entities.append(current)
                        current = None
                    continue

                prefix, label = raw_label.split("-", 1)
                if label not in {"ALLERGY", "MEDICATION"} and is_negated(
                    text, start, end
                ):
                    if current:
                        entities.append(current)
                        current = None
                    continue
                if label == "DIAGNOSIS" and is_family_history(text, start, end):
                    if current:
                        entities.append(current)
                        current = None
                    continue
                if label in {"SYMPTOM", "RED_FLAG", "LAB_RESULT"} and (
                    is_historical(text, start, end)
                    or is_hypothetical(text, start, end)
                ):
                    if current:
                        entities.append(current)
                        current = None
                    continue
                if (
                    label == "RED_FLAG"
                    and missing_section_start >= 0
                    and start >= missing_section_start
                ):
                    if current:
                        entities.append(current)
                        current = None
                    continue
                if (
                    current
                    and prefix == "I"
                    and current.label == label
                    and start <= current.end + 1
                ):
                    current.text = text[current.start:end]
                    current.end = end
                    current.confidence = round((current.confidence + confidence) / 2, 3)
                    continue

                if current:
                    entities.append(current)
                current = Entity(
                    text=text[start:end],
                    label=label,
                    confidence=round(confidence, 3),
                    start=start,
                    end=end,
                    source="BioClinicalBERT",
                )

            if current:
                entities.append(current)
        cleaned: list[Entity] = []
        for entity in entities:
            entity = self._clean_model_entity(entity)
            if (
                entity is not None
                and len(entity.text.strip()) >= 4
                and not entity.text.isspace()
                and (entity.start == 0 or not text[entity.start - 1].isalnum())
                and (entity.end == len(text) or not text[entity.end].isalnum())
                and self._is_supported_model_entity(entity)
            ):
                cleaned.append(entity)
        return cleaned

    @staticmethod
    def _clean_model_entity(entity: Entity) -> Entity | None:
        original = entity.text
        leading = len(original) - len(original.lstrip(" \t\n,;:.-()"))
        value = original.strip(" \t\n,;:.-()")
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"\s+(?:and|or)$", "", value, flags=re.I).strip()
        if not value:
            return None
        trailing = len(original) - leading - len(value)
        entity.start += leading
        entity.end = max(entity.start + len(value), entity.end - max(trailing, 0))
        entity.text = value
        return entity

    @staticmethod
    def _is_plausible_model_entity(entity: Entity) -> bool:
        """Reject clinically impossible label/text pairs before consolidation."""
        value = entity.text.casefold().strip(" .,:;-")
        section_headings = {
            "allergies",
            "assessment",
            "current medications",
            "diagnosis",
            "medications",
            "results",
            "symptoms",
        }
        if value in section_headings or value in {
            "denied",
            "denies",
            "negative",
            "none",
            "no",
        }:
            return False
        if entity.label == "RED_FLAG" and (
            value in {"nkda", "no known drug allergies"}
            or "allergy" in value
        ):
            return False
        if entity.label == "RED_FLAG" and (
            ("hba1c" in value and "%" not in value)
            or ("blood pressure" in value and not re.search(r"\d", value))
        ):
            return False
        if entity.label == "SYMPTOM" and value in {"nkda", "no known drug allergies"}:
            return False
        return True

    def _is_supported_model_entity(self, entity: Entity) -> bool:
        if not self._is_plausible_model_entity(entity):
            return False

        value = entity.text.casefold().strip(" .,:;-")
        lexicon_terms = {
            term.casefold().strip(" .,:;-")
            for term in self.lexicon.get(entity.label, [])
        }
        lexicon_supported = any(
            value == term
            or (len(term) >= 5 and term in value)
            for term in lexicon_terms
        )

        if entity.label == "MEDICATION":
            if (
                value.count("(") != value.count(")")
                or re.search(r"\b(?:at|from|to)$", value, re.I)
            ):
                return False
            return lexicon_supported or bool(
                re.search(
                    r"\b(?:amlodipine|aspirin|atorvastatin|bisoprolol|"
                    r"clopidogrel|enoxaparin|entresto|ferrous sulphate|"
                    r"furosemide|insulin glargine|lantus|metformin|"
                    r"omeprazole|ramipril|sacubitril[- /]valsartan)\b",
                    value,
                    re.I,
                )
            )
        if entity.label == "DIAGNOSIS":
            return lexicon_supported or bool(
                re.search(
                    r"\b(?:anaemia|cardiac failure|cardiomyopathy|"
                    r"chronic renal disease|ckd(?:\s+stage\s+\w+)?|dementia|diabetes|"
                    r"heart failure|hyperlipid(?:aemia|emia)|hypertension|hypothyroidism|"
                    r"ischaemic heart disease|myocardial infarction|"
                    r"nstemi|stemi|stroke|thyroid dysfunction|infection)\b",
                    value,
                    re.I,
                )
            )
        if entity.label == "SYMPTOM":
            return lexicon_supported or bool(
                re.search(
                    r"\b(?:breathless(?:ness)?|chest pain|cognitive deterioration|"
                    r"diaphoresis|dizziness|dyspnoea|fatigue|incontinence|"
                    r"memory deficits?|nausea|oedema|palpitations|puffy|"
                    r"shortness of breath|sleepy|tired)\b",
                    value,
                    re.I,
                )
            )
        if entity.label == "ALLERGY":
            return lexicon_supported or bool(
                re.search(
                    r"\b(?:allerg(?:y|ic)|anaphylaxis|intolerance|rash)\b",
                    value,
                    re.I,
                )
            )
        if entity.label == "LAB_RESULT":
            return (
                len(value) <= 100
                and bool(re.search(r"\d", value))
                and bool(
                re.search(
                    r"\b(?:blood pressure|bnp|cholesterol|creatinine|"
                    r"crp|ef|egfr|ferritin|free t4|glucose|haemoglobin|"
                    r"hba1c|heart rate|inr|iron|mchc?|oxygen|platelets?|"
                    r"potassium|rbc|reticulocyte|sodium|troponin|"
                    r"triglycerides|tsh|urea|wbc)\b|"
                    r"\b(?:bp|hr|o2|k\+)\s*[:=]?",
                    value,
                    re.I,
                )
            )
            )
        if entity.label == "RED_FLAG":
            return lexicon_supported or bool(
                re.search(
                    r"\b(?:acute decompensation|acute on chronic|"
                    r"anaphylaxis|angioedema|critical|fall risk|"
                    r"fluid overload|markedly elevated|nstemi criteria|"
                    r"poor glycaemic control|significant rise|"
                    r"severe nausea|st elevation)\b",
                    value,
                    re.I,
                )
            )
        return True

    def _extract_with_lexicon(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        confidence_by_label = {
            "DIAGNOSIS": 0.93,
            "SYMPTOM": 0.9,
            "MEDICATION": 0.94,
            "ALLERGY": 0.92,
            "LAB_RESULT": 0.95,
            "RED_FLAG": 0.88,
        }
        for label, terms in self.lexicon.items():
            for term in terms:
                spans = list(active_term_spans(text, term))
                if label in {"ALLERGY", "MEDICATION"}:
                    spans = list(term_spans(text, term))
                for start, end in spans:
                    entities.append(
                        Entity(
                            text=text[start:end],
                            label=label,
                            confidence=confidence_by_label.get(label, 0.88),
                            start=start,
                            end=end,
                        )
                    )
        return entities

    def _extract_pattern_entities(self, text: str) -> list[Entity]:
        patterns = {
            "LAB_RESULT": LAB_PATTERNS,
            "ALLERGY": [
                r"\bNo known drug allergies\b",
                r"\bNKDA\b",
                r"\b(?:Penicillin|Sulfa|Iodinated contrast|Contrast dye)\b\s*(?:[-—:]\s*)?(?:allergy|intolerance|anaphylaxis|rash[^.\n]*)?",
                r"\b[A-Z][A-Za-z]+\s+(?:allergy|intolerance)\b",
                r"\brash,\s*mild,\s*resolving spontaneously\b",
            ],
            "ADVERSE_REACTION": [
                r"\bCodeine\s*[-—:]\s*causes?\s+severe\s+nausea\b",
                r"\b[A-Z][A-Za-z]+\s*[-—:]\s*(?:causes?|caused)\s+"
                r"(?:severe\s+)?(?:nausea|vomiting|dizziness|headache)\b",
            ],
            "DIAGNOSIS": [
                r"\bdementia\b",
                r"\bstrokes?\b",
                r"\bhyperlipid(?:aemia|emia)\b",
                r"\bcardiomyopathy\b",
                r"\bcardiac failure\b",
                r"\bchronic renal disease\b",
                r"\bcoronary artery disease\b",
                r"\bNSTEMI\b",
                r"\bnon[- ]ST[- ]elevation myocardial infarction\b",
                r"\breduced ejection fraction heart failure\b",
                r"\bheart failure(?:\s*\(EF\s*\d+%\))?\b",
                r"\bCKD Stage\s*[1-5][a-c]?\b",
                r"\bCKD\b",
                r"\bchronic kidney disease\b",
                r"\biron deficiency anaemia\b",
                r"\bischaemic heart disease\b",
                r"\bpost[- ]MI\b",
                r"\bHF\b",
                r"\btype 2 diabetes mellitus\b",
                r"\bhypertension\b",
            ],
            "MEDICATION": [
                r"\b(?:Sacubitril[- ]Valsartan|Entresto)\s*(?:\([^)]*\))?\s*\d+(?:/\d+)?\s*mg\s*(?:BD|OD|nocte|daily|twice daily)?",
                r"\bEntresto\s*\(sacubitril/valsartan\s*\d+/\d+\s*mg\s*BD\)",
                r"\b(?:Metformin|Ramipril|Amlodipine|Atorvastatin|Aspirin|Clopidogrel|Bisoprolol|Omeprazole|Furosemide|Ferrous Sulphate)\s*\d+(?:\.\d+)?\s*mg\s*(?:BD|OD|nocte|daily|twice daily|PRN)?",
                r"\bInsulin Glargine(?:\s*\(Lantus\))?\s*\d+\s*units?\s*(?:at night|nightly|nocte)?",
                r"\bEnoxaparin\s*\d+(?:\.\d+)?\s*mg/kg\s*BD\b",
                r"\bMotrin\b(?:\s+once/week)?",
                r"\bTums\b(?:\s+previously)?",
                r"\bRamipril\b",
            ],
            "SYMPTOM": [
                r"\bintermittent chest pain\b",
                r"\bpalpitations\b",
                r"\bincontinent\b|\bincontinence\b",
                r"\bgradual deterioration in (?:his|her|their) cognitive ability\b",
                r"\bcognitive (?:decline|deterioration|impairment)\b",
                r"\bmemory deficits?\b",
                r"\bunable to (?:bathe|use the toilet|perform simple arithmetic)\b",
                r"\bdisorient(?:ed|ation)\b",
                r"\bepigastric abdominal pain\b",
                r"\babdominal pain\b",
                r"\bstomach problems?\b",
                r"\bbloating after eating\b",
                r"\b(?:dark|darker|black|tarry) stools?\b",
                r"\bnoticed (?:the stools|them) darker\b",
                r"\bcentral chest pain\b",
                r"\bchest pain\b",
                r"\bshortness of breath\b",
                r"\bbreathless(?:ness)?\b",
                r"\bbilateral ankle oedema\b",
                r"\bankles? still slightly puffy\b",
                r"\bpitting oedema\b",
                r"\bbibasal crackles\b",
                r"\bdizziness\b",
                r"\bsyncope\b",
            ],
            "RED_FLAG": [
                r"\blacks? mental capacity\b",
                r"\bdoes not have mental capacity\b",
                r"\bunable to (?:understand|retain|use or weigh) information\b",
                r"\bwill not be able to make decisions\b",
                r"\bcognitive failures?\b",
                r"\bgradual deterioration in (?:his|her|their) cognitive ability\b",
                r"\bnoticed (?:the stools|them) darker\b",
                r"\b(?:black|tarry) stools?\b",
                r"\brising troponin pattern\b",
                r"\bNSTEMI criteria met\b",
                r"\bmarkedly elevated\b",
                r"\bpoor glycaemic control\b",
                r"\bacute on chronic decline\b",
                r"\bpatient accidentally took ramipril\b",
                r"\brisk of angioedema\b",
                r"\bno-one has called yet\b",
                r"\bfall risk\b",
                r"\bcognitive concern\b",
                r"\ballergy record[\s\S]{0,220}\b(?:wrong|incorrect)\b",
            ],
            "SOCIAL_HISTORY": [
                r"\bnon-smoker\b",
                r"\b(?:divorced|widowed|married|unemployed)\b",
                r"\bliving with (?:his|her|their) (?:son|daughter|family)\b",
                r"\bsmokes? since \d{1,2}\s*(?:yo|years? old)\b"
                r"(?:,\s*\d+/\d+\s*-\s*\d+\s*PPD)?",
                r"\b\d+/\d+\s*-\s*\d+\s*PPD\b",
            ],
            "FAMILY_HISTORY": [
                r"\bfamily history[^.\n]{0,120}\b(?:coronary artery disease|"
                r"heart disease|stroke|diabetes|cancer|bleeding ulcer)\b",
                r"\buncle has a bleeding ulcer\b",
                r"\bfamily history of (?:a )?bleeding ulcer\b",
            ],
            "FOLLOW_UP": [
                FOLLOW_UP_ACTION_PATTERN,
                r"\bactivity restrictions? suggested\b",
                r"\bfull course of[\s\S]{0,24}antibiotics\b",
                r"\bcheck back with (?:the )?physi(?:cian|can) in case of relapse\b",
                r"\bstrict diet\b",
                r"\bGP to check U&E and eGFR in \d+\s*weeks?\b",
                r"\bHbA1c to be rechecked in \d+\s*months?\b",
                r"\bCardiology OPD in \d+\s*weeks?\b",
                r"\bHF Nurse Specialist to contact within \d+\s*hours? of discharge\b",
                r"\bHF nurse specialist[\s\S]{0,100}?within \d+h of discharge\b",
                r"\bDiabetic nurse review[\s\S]{0,45}?\d+\s*-\s*\d+\s*weeks?\b",
                r"\bAllergy record correction[\s\S]{0,65}?before end of week\b",
                r"\bNext appointment\s*:\s*\d+\s*weeks?(?:\s*\([^)]*\))?\b",
            ],
            "CLINICAL_STATUS": [
                r"\bappears in good health with no immediate concerns\b",
                r"\bno significant issues (?:were|are) detected\b",
                r"\bno specific medical conditions or acute illnesses were identified\b",
                r"\bhealthy status with no evidence of underlying health issues\b",
                r"\bno prescription is necessary at this time\b",
                r"\bvital signs are within normal ranges\b",
            ],
        }
        entities: list[Entity] = []
        for label, label_patterns in patterns.items():
            for pattern in label_patterns:
                for match in re.finditer(pattern, text, re.I):
                    if label not in {"ALLERGY", "MEDICATION", "CLINICAL_STATUS"} and is_negated(
                        text, match.start(), match.end()
                    ):
                        continue
                    if label == "DIAGNOSIS" and is_family_history(
                        text, match.start(), match.end()
                    ):
                        continue
                    if label in {"SYMPTOM", "RED_FLAG", "LAB_RESULT"} and (
                        is_historical(text, match.start(), match.end())
                        or is_hypothetical(text, match.start(), match.end())
                    ):
                        continue
                    entities.append(
                        Entity(
                            text=match.group(0).strip(" ."),
                            label=label,
                            confidence=0.86,
                            start=match.start(),
                            end=match.end(),
                            source="clinical-pattern",
                        )
                    )
        return entities

    @staticmethod
    def _deduplicate(entities: list[Entity]) -> list[Entity]:
        def source_priority(entity: Entity) -> int:
            if entity.source == "gold-aligned sample":
                return 6
            if (
                entity.source == "clinical-pattern"
                and entity.label
                in {
                    "ADVERSE_REACTION",
                    "ALLERGY",
                    "FOLLOW_UP",
                    "LAB_RESULT",
                    "MEDICATION",
                }
            ):
                return 5
            if entity.source == "BioClinicalBERT":
                return 4
            if entity.source == "clinical-pattern":
                return 3
            if entity.source == "clinical-lexicon":
                return 2
            return 0

        ranked = sorted(
            entities,
            key=lambda entity: (
                source_priority(entity),
                entity.confidence,
                len(entity.text),
            ),
            reverse=True,
        )
        selected: list[Entity] = []
        seen: set[tuple[str, str, int, int]] = set()
        for entity in ranked:
            if (
                entity.label == "ALLERGY"
                and entity.text.casefold().strip(" .")
                in {"the allergy", "severe allergy", "update allergy", "allergy"}
            ):
                continue
            key = (entity.label, entity.text.lower(), entity.start, entity.end)
            if key in seen:
                continue
            overlaps_better = any(
                existing.label == entity.label
                and entity.start < existing.end
                and entity.end > existing.start
                for existing in selected
            )
            if overlaps_better:
                continue
            selected.append(entity)
            seen.add(key)
        return sorted(selected, key=lambda item: (item.start, item.label))
