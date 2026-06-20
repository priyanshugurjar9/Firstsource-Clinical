import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["ENABLE_BIOCLINICALBERT"] = "0"

from src.causal_engine import build_causal_links, level_for_score, recommended_action, what_if_score
from src.causal_ui import causal_journey_html
from src.clinical_context import (
    has_follow_up_plan,
    is_historical,
    is_hypothetical,
    is_negated,
    non_negated_term_spans,
)
from src.completeness import information_to_confirm
from src.data_store import load_documents
from src.entity_extractor import HybridEntityExtractor
from src.models import Entity
from src.pipeline import ClinicalPipeline
from src.pdf_report import generate_case_pdf
from src.presentation import medication_safety_detail, medication_status_label
from src.text_processing import (
    _clean_markdown,
    _extract_docx_text,
    extract_uploaded_text,
    infer_document_date,
    infer_encounter_dates,
    infer_follow_up_date,
    infer_patient_details,
    sanitize_display_text,
)


class ClinicalPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = ClinicalPipeline(require_model=False)
        cls.samples = load_documents()

    def test_high_risk_sample_uses_explicit_reference_id(self):
        sample = next(row for row in self.samples if row["doc_id"] == "CLIN-0037")
        result = self.pipeline.analyse(
            sample["clinical_note"],
            reference_doc_id=sample["doc_id"],
        )
        self.assertEqual(result.risk_level, "High")
        self.assertTrue(result.causal_links)
        self.assertTrue(any(entity.label == "LAB_RESULT" for entity in result.entities))

    def test_low_risk_sample(self):
        sample = next(row for row in self.samples if row["gold_risk_level"] == "Low")
        result = self.pipeline.analyse(
            sample["clinical_note"],
            reference_doc_id=sample["doc_id"],
        )
        self.assertEqual(result.patient_details["name"], sample["patient_name"])
        self.assertGreater(len(result.entities), 0)

    def test_negated_chest_pain_does_not_trigger_cardiac_rule(self):
        text = "Patient denies chest pain. Electrocardiogram shows ST depression."
        links = build_causal_links(text, [])
        self.assertFalse(any("cardiac" in link.meaning.lower() for link in links))

    def test_not_had_chest_pain_is_not_a_current_symptom(self):
        text = "Patient is improving. Not had chest pain since the stent."
        start = text.index("chest pain")
        self.assertTrue(is_negated(text, start, start + len("chest pain")))
        result = self.pipeline.analyse(text)
        self.assertFalse(
            any(
                entity.label == "SYMPTOM"
                and "chest pain" in entity.text.casefold()
                for entity in result.entities
            )
        )

    def test_non_negated_chest_pain_triggers_cardiac_rule(self):
        text = "Patient reports chest pain. Electrocardiogram shows ST depression."
        links = build_causal_links(text, [])
        self.assertTrue(any("cardiac" in link.meaning.lower() for link in links))

    def test_post_negation_is_detected(self):
        text = "Chest pain: none. Diabetes: denied. Pneumonia, ruled out."
        chest_start = text.index("Chest pain")
        diabetes_start = text.index("Diabetes")
        pneumonia_start = text.index("Pneumonia")
        self.assertTrue(is_negated(text, chest_start, chest_start + len("Chest pain")))
        self.assertTrue(is_negated(text, diabetes_start, diabetes_start + len("Diabetes")))
        self.assertTrue(
            is_negated(text, pneumonia_start, pneumonia_start + len("Pneumonia"))
        )

    def test_pseudo_negation_not_including_does_not_remove_history(self):
        text = "Not including the history of chest pain, the patient is otherwise fine."
        start = text.index("chest pain")
        self.assertFalse(is_negated(text, start, start + len("chest pain")))
        self.assertTrue(is_historical(text, start, start + len("chest pain")))

    def test_historical_chest_pain_does_not_trigger_acute_rule(self):
        text = "History of chest pain. ECG shows ST depression."
        links = build_causal_links(text, [])
        self.assertFalse(any("acute cardiac" in link.meaning.lower() for link in links))

    def test_safety_net_symptoms_are_not_extracted_as_current_findings(self):
        text = (
            "Patient is stable today. Safety-net instructions: go urgently to A&E "
            "if: recurrent chest pain, breathlessness at rest, severe dizziness or syncope."
        )
        start = text.index("syncope")
        self.assertTrue(is_hypothetical(text, start, start + len("syncope")))
        result = self.pipeline.analyse(text)
        symptoms = {
            entity.text.casefold()
            for entity in result.entities
            if entity.label == "SYMPTOM"
        }
        self.assertNotIn("syncope", symptoms)
        self.assertFalse(any("chest pain" in symptom for symptom in symptoms))
        self.assertFalse(any("breathless" in symptom for symptom in symptoms))
        self.assertNotIn("dizziness", symptoms)

    def test_explicit_pattern_medication_has_high_confidence_label(self):
        result = self.pipeline.analyse(
            "Patient: Jane Doe. Age: 65. Female. Metformin 500mg BD. "
            "NKDA. Follow-up arranged."
        )
        medication = next(
            entity
            for entity in result.entities
            if entity.label == "MEDICATION" and "metformin" in entity.text.casefold()
        )
        self.assertEqual(
            ClinicalPipeline._confidence_label(
                medication.confidence,
                medication.source,
            ),
            "High",
        )

    def test_st_elevation_triggers_emergency_cardiac_action(self):
        links = build_causal_links("ECG demonstrates ST elevation in the anterior leads.", [])
        self.assertTrue(any("myocardial infarction" in link.meaning.lower() for link in links))
        self.assertTrue(any("immediately" in link.action.lower() for link in links))

    def test_potassium_decimal_precision_is_supported(self):
        text = "Potassium 5.50 mmol/L and eGFR 28 mL/min/1.73m2."
        links = build_causal_links(text, [])
        self.assertTrue(any("renal function" in link.meaning.lower() for link in links))

    def test_multiple_serious_issues_return_all_actions(self):
        text = (
            "Patient reports chest pain. ECG shows ST depression. "
            "K+ 7.2 mmol/L was reported as a critical value."
        )
        links = build_causal_links(text, [])
        action = recommended_action(links, "High")
        self.assertGreaterEqual(len(links), 2)
        self.assertIn("cardiac", action.lower())
        self.assertIn("potassium", action.lower())

    def test_short_critical_note_is_accepted(self):
        result = self.pipeline.analyse("K+ 7.2")
        self.assertEqual(result.risk_level, "High")
        self.assertTrue(any("potassium" in link.meaning.lower() for link in result.causal_links))

    def test_nkda_satisfies_allergy_status(self):
        result = self.pipeline.analyse(
            "Patient John Doe. NKDA. Medication reviewed. Follow-up appointment booked."
        )
        self.assertNotIn("allergy status", result.missing_information)

    def test_patient_name_is_not_clinician_name(self):
        details = infer_patient_details("Dr Smith reviewed Patient John Doe, age 57.")
        self.assertEqual(details["name"], "John Doe")

    def test_compact_patient_demographics_are_extracted(self):
        details = infer_patient_details("Pt is Jane Doe, 62F s/p MI.")
        self.assertEqual(
            details,
            {
                "name": "Jane Doe",
                "age": 62,
                "gender": "Female",
                "date_of_birth": "Not identified",
                "patient_id": "Not identified",
            },
        )

    def test_colon_patient_and_iso_dob_are_supported(self):
        details = infer_patient_details(
            "Document date: 2026-06-20. Pt: Jane Smith. DOB: 1964-06-21."
        )
        self.assertEqual(
            details,
            {
                "name": "Jane Smith",
                "age": 61,
                "gender": "Not identified",
                "date_of_birth": "1964-06-21",
                "patient_id": "Not identified",
            },
        )

    def test_common_document_and_follow_up_dates_are_extracted(self):
        text = "Report date: 18/06/2026. Follow-up on 2026-06-25."
        self.assertEqual(infer_document_date(text), "2026-06-18")
        self.assertEqual(infer_follow_up_date(text), "2026-06-25")

    def test_hyphenated_encounter_dates_are_extracted(self):
        text = "Admitted: 07-Sep-2020. Discharged: 08-Sep-2020."
        self.assertEqual(
            infer_encounter_dates(text),
            {
                "admission_date": "2020-09-07",
                "discharge_date": "2020-09-08",
            },
        )

    def test_routing_sentence_counts_as_a_follow_up_plan(self):
        text = "Route to the diabetes nurse specialist within 7 days."
        self.assertTrue(has_follow_up_plan(text))
        result = self.pipeline.analyse(
            "Patient: Jane Doe. Age: 65. Female. Medication: Metformin 500 mg BD. "
            "NKDA. " + text
        )
        self.assertNotIn("follow-up plan", result.missing_information)
        follow_up = [
            entity.text for entity in result.entities if entity.label == "FOLLOW_UP"
        ]
        self.assertTrue(any("within 7 days" in value for value in follow_up))

    def test_lexicon_matching_respects_word_boundaries(self):
        self.assertEqual(non_negated_term_spans("The face was examined.", "ace"), [])
        self.assertEqual(non_negated_term_spans("ACE was documented.", "ACE"), [(0, 3)])

    def test_long_note_keeps_critical_information_at_end(self):
        text = ("Routine history was reviewed. " * 180) + " K+ 7.2. Critical value."
        result = self.pipeline.analyse(text)
        self.assertEqual(result.risk_level, "High")
        self.assertTrue(any("potassium" in link.meaning.lower() for link in result.causal_links))

    def test_model_prediction_beats_overlapping_lexicon_prediction(self):
        model_entity = Entity("chest pain", "SYMPTOM", 0.99, 0, 10, "BioClinicalBERT")
        lexicon_entity = Entity("chest pain", "SYMPTOM", 0.90, 0, 10, "clinical-lexicon")
        selected = HybridEntityExtractor._deduplicate([lexicon_entity, model_entity])
        self.assertEqual(selected[0].source, "BioClinicalBERT")

    def test_model_prediction_beats_overlapping_pattern_prediction(self):
        model_entity = Entity("fatigue", "SYMPTOM", 0.82, 0, 7, "BioClinicalBERT")
        pattern_entity = Entity("fatigue", "SYMPTOM", 0.95, 0, 7, "clinical-pattern")
        selected = HybridEntityExtractor._deduplicate([pattern_entity, model_entity])
        self.assertEqual(selected[0].source, "BioClinicalBERT")

    def test_exact_medication_pattern_beats_shorter_model_span(self):
        model_entity = Entity("Ramipril 10 mg", "MEDICATION", 0.95, 0, 14, "BioClinicalBERT")
        pattern_entity = Entity(
            "Ramipril 10 mg OD",
            "MEDICATION",
            0.86,
            0,
            17,
            "clinical-pattern",
        )
        selected = HybridEntityExtractor._deduplicate([model_entity, pattern_entity])
        self.assertEqual(selected[0].text, "Ramipril 10 mg OD")
        self.assertEqual(selected[0].source, "clinical-pattern")

    def test_model_cannot_treat_nkda_as_a_red_flag(self):
        entity = Entity("NKDA", "RED_FLAG", 0.99, 0, 4, "BioClinicalBERT")
        self.assertFalse(HybridEntityExtractor._is_plausible_model_entity(entity))

    def test_model_rejects_section_headings_and_negation_cues(self):
        for value in ("Symptoms", "denies"):
            entity = Entity(value, "SYMPTOM", 0.9, 0, len(value), "BioClinicalBERT")
            self.assertFalse(HybridEntityExtractor._is_plausible_model_entity(entity))

    def test_completeness_domain_is_not_duplicated_when_specific_gap_exists(self):
        items = information_to_confirm(
            [
                "contrast reaction details",
                "formal cognitive assessment",
                "pending vitamin B12 and folate",
            ],
            [
                "Allergies and reactions",
                "Important test results",
                "Social or cognitive context",
            ],
        )
        self.assertEqual(
            items,
            [
                "contrast reaction details",
                "formal cognitive assessment",
                "pending vitamin B12 and folate",
            ],
        )

    def test_markdown_formatting_is_removed_before_inference(self):
        text = _clean_markdown("**Patient:** Amelia Hart  \n**Age:** 67")
        self.assertIn("Patient: Amelia Hart", text)
        self.assertIn("Age: 67", text)

    def test_docx_runs_are_joined_within_each_paragraph(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "cross_format"
            / "clinical_review_note.docx"
        )
        text = _extract_docx_text(path.read_bytes())
        self.assertIn("Patient: Amelia Hart", text)
        self.assertIn("Document date: 2026-06-18", text)

    def test_required_model_cannot_silently_fall_back(self):
        with patch("src.entity_extractor.MODEL_DIR", Path("/missing/bioclinicalbert")):
            with self.assertRaisesRegex(RuntimeError, "BioClinicalBERT is required"):
                HybridEntityExtractor(require_model=True)

    def test_medication_alert_does_not_copy_adjacent_medicine_text(self):
        from src.models import MedicationRecord

        record = MedicationRecord(
            medication="Ramipril 10 mg OD",
            phase="At discharge",
            status="Stopped",
            confidence="High",
            source_text=(
                "STOPPED: Ramipril (replaced by Entresto). "
                "Metformin (withheld - do not restart until eGFR > 60)."
            ),
            source_document="Discharge summary",
        )
        detail = medication_safety_detail(record)
        self.assertIn("ramipril has been discontinued", detail.casefold())
        self.assertIn("Entresto", detail)
        self.assertNotIn("Metformin", detail)
        self.assertNotIn("eGFR", detail)
        self.assertEqual(medication_status_label("Stopped"), "Discontinued")

    def test_display_text_is_sanitized(self):
        self.assertEqual(
            sanitize_display_text("<script>alert(1)</script>Clinical summary"),
            "alert(1)Clinical summary",
        )

    def test_default_audit_does_not_store_raw_note(self):
        from src import audit

        result = self.pipeline.analyse("K+ 7.2")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(audit, "LOG_DIR", Path(directory)):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("BREAK_GLASS_AUDIT_KEY", None)
                    audit.write_audit_event("Patient Secret Name. K+ 7.2", result)
                event = json.loads((Path(directory) / "audit.jsonl").read_text().splitlines()[0])
                self.assertNotIn("Patient Secret Name", json.dumps(event))
                self.assertIsNone(event["encrypted_source_ref"])

    def test_break_glass_source_is_encrypted_when_key_is_configured(self):
        from cryptography.fernet import Fernet
        from src import audit

        key = Fernet.generate_key().decode("utf-8")
        result = self.pipeline.analyse("K+ 7.2")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(audit, "LOG_DIR", Path(directory)):
                with patch.dict(os.environ, {"BREAK_GLASS_AUDIT_KEY": key}):
                    event_id = audit.write_audit_event("Patient Secret Name. K+ 7.2", result)
                encrypted = (Path(directory) / "break_glass" / f"{event_id}.enc").read_bytes()
                self.assertNotIn(b"Patient Secret Name", encrypted)
                decrypted = Fernet(key.encode("utf-8")).decrypt(encrypted)
                self.assertIn(b"Patient Secret Name", decrypted)

    def test_what_if_never_negative(self):
        self.assertEqual(what_if_score(20, True, True, True), 0)
        self.assertEqual(level_for_score(0), "Low")

    def test_multiple_documents_are_consolidated_with_provenance(self):
        records = [
            row for row in self.samples
            if row["patient_name"] == "Eleanor Grant"
        ][:3]
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": row["doc_id"],
                    "document_name": f"{row['document_type']} ({row['doc_id']})",
                    "text": row["clinical_note"],
                    "reference_doc_id": row["doc_id"],
                }
                for row in records
            ]
        )
        self.assertEqual(len(case.documents), 3)
        self.assertEqual(case.consolidated.patient_details["name"], "Eleanor Grant")
        self.assertEqual(len(case.record_timeline), 3)
        self.assertTrue(
            all(entity.document_id for entity in case.consolidated.entities)
        )

    def test_different_patient_documents_are_not_merged(self):
        records = self.samples[:2]
        with self.assertRaisesRegex(ValueError, "different patients"):
            self.pipeline.analyse_many(
                [
                    {
                        "document_id": row["doc_id"],
                        "document_name": row["document_type"],
                        "text": row["clinical_note"],
                        "reference_doc_id": row["doc_id"],
                    }
                    for row in records
                ]
            )

    def test_action_queue_contains_route_deadline_and_source(self):
        sample = next(row for row in self.samples if row["doc_id"] == "CLIN-0037")
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": sample["doc_id"],
                    "document_name": "Renal lab report",
                    "text": sample["clinical_note"],
                    "reference_doc_id": sample["doc_id"],
                }
            ]
        )
        clinical_action = next(
            item for item in case.action_items
            if "renal" in item.route_to.lower()
        )
        self.assertEqual(clinical_action.due_by, "Immediate / same day")
        self.assertEqual(clinical_action.source_documents, ["Renal lab report"])

    def test_duplicate_operational_actions_are_merged_with_all_sources(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "ED",
                    "document_name": "Emergency note",
                    "text": (
                        "Patient: Jane Doe. Age: 65. Female. Chest pain. "
                        "ECG shows ST depression. NKDA. Medication reviewed. Follow-up arranged."
                    ),
                },
                {
                    "document_id": "LAB",
                    "document_name": "Lab report",
                    "text": (
                        "Patient: Jane Doe. Age: 65. Female. Troponin I 389 ng/L. "
                        "Acute myocardial injury. NKDA."
                    ),
                },
            ]
        )
        cardiac = [
            item
            for item in case.action_items
            if item.action == "Escalate to the acute cardiac pathway"
        ]
        self.assertEqual(len(cardiac), 1)
        self.assertEqual(
            set(cardiac[0].source_documents),
            {"Emergency note", "Lab report"},
        )

    def test_cross_document_allergy_conflict_is_flagged(self):
        records = [
            row for row in self.samples
            if row["patient_name"] == "Eleanor Grant"
        ][:3]
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": row["doc_id"],
                    "document_name": row["document_type"],
                    "text": row["clinical_note"],
                    "reference_doc_id": row["doc_id"],
                }
                for row in records
            ]
        )
        self.assertTrue(
            any("Allergy status conflicts" in conflict for conflict in case.conflicts)
        )

    def test_overall_recommendation_synthesizes_case_actions(self):
        records = [
            row for row in self.samples
            if row["patient_name"] == "Eleanor Grant"
        ][:3]
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": row["doc_id"],
                    "document_name": f"{row['document_type']} ({row['doc_id']})",
                    "text": row["clinical_note"],
                    "reference_doc_id": row["doc_id"],
                }
                for row in records
            ]
        )
        recommendation = case.overall_recommendation
        self.assertEqual(recommendation.priority, "High")
        self.assertIn("cardiac", recommendation.immediate_next_step.lower())
        self.assertIn("respiratory", recommendation.coordination_plan.lower())
        self.assertGreaterEqual(len(recommendation.source_documents), 2)

    def test_causal_graph_uses_selected_patient_pathway(self):
        records = [
            row for row in self.samples
            if row["patient_name"] == "Eleanor Grant"
        ][:3]
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": row["doc_id"],
                    "document_name": f"{row['document_type']} ({row['doc_id']})",
                    "text": row["clinical_note"],
                    "reference_doc_id": row["doc_id"],
                }
                for row in records
            ]
        )
        respiratory_link = next(
            link for link in case.consolidated.causal_links
            if "respiratory" in link.meaning.lower()
        )
        graph_html = causal_journey_html(case.consolidated, respiratory_link)
        self.assertIn("Eleanor Grant", graph_html)
        self.assertIn("Possible respiratory deterioration", graph_html)
        self.assertIn("Arrange urgent respiratory assessment", graph_html)
        self.assertNotIn("Escalate to the acute cardiac pathway", graph_html)

    def test_timeline_sorts_by_document_date_not_upload_order(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "LATE",
                    "document_name": "Discharge note",
                    "text": (
                        "Patient: Jane Doe. Age: 62. Female. "
                        "Discharge date: 2026-06-18. Medication reviewed."
                    ),
                },
                {
                    "document_id": "EARLY",
                    "document_name": "Emergency note",
                    "text": (
                        "Patient: Jane Doe. Age: 62. Female. "
                        "Encounter date: 2026-06-17. Medication reviewed."
                    ),
                },
            ]
        )
        self.assertEqual(
            [event["document_id"] for event in case.record_timeline],
            ["EARLY", "LATE"],
        )

    def test_explicit_follow_up_date_overrides_rule_window(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "DIABETES",
                    "document_name": "Diabetes review",
                    "text": (
                        "Patient: Jane Doe. Age: 62. Female. HbA1c 9.4%. "
                        "Follow-up on 2026-06-25. Medication reviewed. NKDA."
                    ),
                }
            ]
        )
        diabetes_action = next(
            item for item in case.action_items
            if item.route_to == "Diabetes nurse specialist"
        )
        self.assertEqual(diabetes_action.due_by, "2026-06-25")

    def test_surname_first_patient_and_dob_age_are_supported(self):
        text = (
            "Received: 10/06/2024. Patient: FORSYTHE, Margaret Elaine "
            "DOB: 14/03/1958 MRN: 123."
        )
        self.assertEqual(
            infer_patient_details(text),
            {
                "name": "Margaret Elaine Forsythe",
                "age": 66,
                "gender": "Not identified",
                "date_of_birth": "1958-03-14",
                "patient_id": "123",
            },
        )

    def test_pipe_delimited_patient_header_is_supported(self):
        text = (
            "Patient: Margaret Elaine Forsythe | DOB: 14/03/1958 "
            "(Age 66) | MRN: NGH-2024-087341"
        )
        self.assertEqual(
            infer_patient_details(text),
            {
                "name": "Margaret Elaine Forsythe",
                "age": 66,
                "gender": "Not identified",
                "date_of_birth": "1958-03-14",
                "patient_id": "NGH-2024-087341",
            },
        )

    def test_realistic_pathology_layout_extracts_high_value_results(self):
        result = self.pipeline.analyse(
            "NORTHGATE PATH LABS - PATHOLOGY REPORT\n"
            "Patient: FORSYTHE, Margaret Elaine DOB: 14/03/1958\n"
            "Received: 10/06/2024 03:42\n"
            "Troponin I (hsTnI) @ 02:55: 142 ng/L\n"
            "Troponin I (hsTnI) @ 05:55: 389 ng/L\n"
            "INTERPRETATION: Rising troponin pattern consistent with acute myocardial injury. "
            "NSTEMI criteria met.\n"
            "BNP (B-type Natriuretic Peptide): 810 pg/mL. Acute volume overload.\n"
            "HbA1c: 9.2%. POOR GLYCAEMIC CONTROL."
        )
        labs = [entity.text for entity in result.entities if entity.label == "LAB_RESULT"]
        self.assertTrue(any("389" in value for value in labs))
        self.assertTrue(any("810" in value for value in labs))
        self.assertEqual(result.risk_level, "High")

    def test_gp_medication_safety_and_allergy_correction_are_detected(self):
        result = self.pipeline.analyse(
            "# GP Consultation Note\n"
            "date: 17 June 2024\n"
            "ref: Margaret Forsythe, dob 14/03/1958\n"
            "Entresto (sacubitril/valsartan 24/26mg BD). "
            "Patient accidentally took ramipril. Risk of angioedema. "
            "Iodinated contrast allergy. The allergy record is currently WRONG."
        )
        meanings = [link.meaning for link in result.causal_links]
        self.assertIn("Potential ACE inhibitor and Entresto interaction", meanings)
        self.assertIn("Incorrect allergy severity may be recorded", meanings)
        medications = [
            entity.text for entity in result.entities if entity.label == "MEDICATION"
        ]
        self.assertTrue(any("Entresto" in value for value in medications))

    def test_medication_reconciliation_keeps_admission_and_discharge_states_separate(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "DISCHARGE",
                    "document_name": "Discharge summary",
                    "text": (
                        "Patient: Margaret Forsythe. Age: 66. Female.\n"
                        "Discharge Date: 14 June 2024\n"
                        "MEDICATIONS ON ADMISSION\n"
                        "Ramipril 10mg OD. Metformin 500mg BD.\n"
                        "DISCHARGE MEDICATIONS\n"
                        "STOPPED: Ramipril 10mg OD. Metformin 500mg BD. "
                        "CHANGED: Bisoprolol 7.5mg OD. "
                        "ADDED: Sacubitril-Valsartan (Entresto) 24/26mg BD. "
                        "CONTINUED: Aspirin 75mg OD."
                    ),
                }
            ]
        )
        by_name = {
            ClinicalPipeline._medication_key(record.medication): record
            for record in case.medication_records
        }
        ramipril = by_name["ramipril"]
        self.assertEqual(ramipril.status, "Stopped")
        self.assertEqual(
            [(item["stage"], item["status"]) for item in ramipril.history],
            [
                ("On admission", "Active on admission"),
                ("At discharge", "Stopped"),
            ],
        )
        self.assertEqual(by_name["bisoprolol"].status, "Dose changed")
        self.assertEqual(by_name["sacubitril-valsartan"].status, "New")
        self.assertEqual(
            by_name["sacubitril-valsartan"].medication,
            "Sacubitril-Valsartan (Entresto) 24/26 mg BD",
        )

    def test_cross_document_review_classifies_conflict_change_and_safety_issue(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "DISCHARGE",
                    "document_name": "Discharge summary",
                    "text": (
                        "Patient: Margaret Forsythe. Age: 66. Female. "
                        "Discharge Date: 14 June 2024. "
                        "MEDICATIONS ON ADMISSION Ramipril 10mg OD. "
                        "Allergy: Contrast dye, reaction details unclear. "
                        "Diagnosis: CKD Stage 3a. "
                        "DISCHARGE MEDICATIONS STOPPED: Ramipril 10mg OD. "
                        "ADDED: Sacubitril-Valsartan (Entresto) 24/26mg BD."
                    ),
                },
                {
                    "document_id": "GP",
                    "document_name": "GP note",
                    "text": (
                        "# GP Consultation Note\n"
                        "date: 17 June 2024\n"
                        "ref: Margaret Forsythe, dob 14/03/1958\n"
                        "Entresto (sacubitril/valsartan 24/26mg BD) is new. "
                        "She accidentally took ramipril after discharge. Risk of angioedema. "
                        "Iodinated contrast allergy was a rash, mild, resolving spontaneously. "
                        "The allergy record is WRONG. CKD Stage 2 was baseline."
                    ),
                },
            ]
        )
        categories = {item.category for item in case.discrepancies}
        self.assertEqual(
            categories,
            {"Conflict", "Medication safety issue", "Clinical change"},
        )

    def test_condition_aliases_resolve_to_most_specific_current_condition(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "ONE",
                    "document_name": "Clinical record",
                    "text": (
                        "Patient: Jane Doe. Age: 70. Female. "
                        "CKD. CKD Stage 2. CKD Stage 3a. "
                        "HF. Reduced ejection fraction heart failure."
                    ),
                }
            ]
        )
        diagnoses = [
            entity.text
            for entity in case.consolidated.entities
            if entity.label == "DIAGNOSIS"
        ]
        self.assertIn("CKD Stage 3a", diagnoses)
        self.assertIn("Reduced ejection fraction heart failure", diagnoses)
        self.assertNotIn("CKD", diagnoses)
        self.assertNotIn("HF", diagnoses)

    def test_completeness_score_is_transparent_and_bounded(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "ONE",
                    "document_name": "Clinical record",
                    "text": (
                        "Patient: Jane Doe. Age: 70. Female. "
                        "Document date: 2026-06-18. Diagnosis: Hypertension. "
                        "Medication: Amlodipine 10mg OD. NKDA. "
                        "Blood pressure 168/96 mmHg. Follow-up in 2 weeks. "
                        "Lives alone."
                    ),
                }
            ]
        )
        self.assertLessEqual(case.completeness.score, case.completeness.total)
        self.assertEqual(case.completeness.total, 10)
        self.assertIn("Patient identity", case.completeness.documented_fields)
        completeness_actions = [
            item.action.casefold()
            for item in case.action_items
            if item.evidence_basis == "Completeness check"
        ]
        for field in case.completeness.missing_fields:
            self.assertIn(f"confirm {field.casefold()}", completeness_actions)

    def test_pdf_report_contains_key_case_sections(self):
        from io import BytesIO

        from pypdf import PdfReader

        sample = next(row for row in self.samples if row["doc_id"] == "CLIN-0037")
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": sample["doc_id"],
                    "document_name": "Renal lab report",
                    "text": sample["clinical_note"],
                    "reference_doc_id": sample["doc_id"],
                }
            ]
        )
        pdf_bytes = generate_case_pdf(case)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        extracted = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages
        )
        self.assertIn("Clinical Document Intelligence Report", extracted)
        self.assertIn("Medication Reconciliation", extracted)
        self.assertIn("Action Queue", extracted)
        self.assertIn("Record Timeline", extracted)

    def test_medication_status_is_scoped_to_its_own_clause(self):
        result = self.pipeline.analyse_many(
            [
                {
                    "document_id": "MEDS",
                    "document_name": "Medication note",
                    "text": (
                        "Patient: Jane Doe. Age: 65. Female. "
                        "Commenced Ferrous Sulphate 200mg BD. "
                        "Metformin 500mg BD was withheld and must not restart. "
                        "Follow-up arranged. NKDA."
                    ),
                }
            ]
        )
        states = {
            ClinicalPipeline._medication_key(record.medication): record.status
            for record in result.medication_records
        }
        self.assertEqual(states["ferrous sulfate"], "New")
        self.assertEqual(states["metformin"], "Withheld")

    def test_completeness_cannot_be_full_when_specific_gaps_remain(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "INCOMPLETE",
                    "document_name": "Discharge note",
                    "text": (
                        "Patient: Jane Doe. Age: 65. Female. "
                        "Discharge date: 2026-06-18. Diagnosis: CKD Stage 3a. "
                        "Medication: Ramipril 5mg OD. Penicillin allergy. "
                        "Creatinine 150 umol/L. Follow-up arranged. Lives alone. "
                        "No formal cognitive assessment performed."
                    ),
                }
            ]
        )
        self.assertIn("formal cognitive assessment", case.consolidated.missing_information)
        self.assertLess(case.completeness.score, case.completeness.total)
        self.assertIn("Social or cognitive context", case.completeness.missing_fields)

    def test_safety_warnings_are_actionable_and_not_raw_fragments(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "LAB",
                    "document_name": "Lab report",
                    "text": (
                        "Patient: Jane Doe. Age: 65. Female. "
                        "Troponin I (hsTnI) @ 02:55: 142 ng/L. "
                        "Troponin I (hsTnI) @ 05:55: 389 ng/L. "
                        "SIGNIFICANT RISE. Acute myocardial injury. "
                        "MARKEDLY ELEVATED."
                    ),
                }
            ]
        )
        self.assertTrue(any("Escalate" in warning for warning in case.safety_warnings))
        self.assertFalse(any(warning == "MARKEDLY ELEVATED" for warning in case.safety_warnings))
        self.assertEqual(len(case.safety_warnings), len(set(case.safety_warnings)))

    def test_priority_is_dynamic_across_low_medium_and_high_cases(self):
        low = self.pipeline.analyse(
            "Patient: Jane Doe. Age: 65. Female. NKDA. "
            "Medication reviewed. Follow-up appointment booked."
        )
        medium = self.pipeline.analyse(
            "Patient: Jane Doe. Age: 65. Female. HbA1c 9.4%. NKDA. "
            "Medication reviewed. Follow-up appointment booked."
        )
        high = self.pipeline.analyse(
            "Patient: Jane Doe. Age: 65. Female. ECG demonstrates ST elevation. "
            "NKDA. Medication reviewed. Follow-up documented."
        )
        self.assertEqual(low.risk_level, "Low")
        self.assertEqual(medium.risk_level, "Medium")
        self.assertEqual(high.risk_level, "High")
        self.assertTrue(
            any("Immediate" in link.follow_up_window for link in high.causal_links)
        )

    def test_exact_three_document_case_combines_safely(self):
        base = Path(__file__).resolve().parents[1] / "examples" / "inputs"
        paths = [
            base / "discharge_summary_unstructured.pdf",
            base / "lab_report_unstructured.txt",
            base / "gp_clinical_note.md",
        ]
        if not all(path.exists() for path in paths):
            self.skipTest("Local three-document regression fixtures are unavailable.")

        class Upload:
            def __init__(self, path):
                self.path = path
                self.name = path.name

            def getvalue(self):
                return self.path.read_bytes()

        documents = [
            {
                "document_id": path.name,
                "document_name": path.name,
                "text": extract_uploaded_text(Upload(path)),
            }
            for path in paths
        ]
        case = self.pipeline.analyse_many(documents)
        discharge = next(
            document
            for document in case.documents
            if document.document_name == "discharge_summary_unstructured.pdf"
        )
        self.assertEqual(
            discharge.result.patient_details["name"],
            "Margaret Elaine Forsythe",
        )
        self.assertEqual(discharge.admission_date, "2024-06-09")
        self.assertEqual(discharge.discharge_date, "2024-06-14")
        follow_up = [
            entity.text
            for entity in case.consolidated.entities
            if entity.label == "FOLLOW_UP"
        ]
        self.assertIn("GP to check U&E and eGFR in 2 weeks", follow_up)
        self.assertIn("Cardiology outpatient review in 6 weeks", follow_up)
        self.assertIn(
            "Heart failure nurse contact within 48 hours of discharge",
            follow_up,
        )
        adverse_reactions = [
            entity.text
            for entity in case.consolidated.entities
            if entity.label == "ADVERSE_REACTION"
        ]
        allergies = [
            entity.text
            for entity in case.consolidated.entities
            if entity.label == "ALLERGY"
        ]
        self.assertTrue(any("Codeine" in item for item in adverse_reactions))
        self.assertFalse(any("Codeine" in item for item in allergies))
        medication_keys = [
            ClinicalPipeline._medication_key(record.medication)
            for record in case.medication_records
        ]
        self.assertEqual(len(medication_keys), len(set(medication_keys)))
        self.assertEqual(medication_keys.count("ramipril"), 1)
        self.assertEqual(medication_keys.count("sacubitril-valsartan"), 1)
        self.assertEqual(medication_keys.count("furosemide"), 1)
        ramipril = next(
            record
            for record in case.medication_records
            if ClinicalPipeline._medication_key(record.medication) == "ramipril"
        )
        self.assertEqual(ramipril.status, "Stopped")
        entresto = next(
            record
            for record in case.medication_records
            if ClinicalPipeline._medication_key(record.medication)
            == "sacubitril-valsartan"
        )
        self.assertEqual(
            entresto.medication,
            "Sacubitril-Valsartan (Entresto) 24/26 mg BD",
        )
        insulin = next(
            record
            for record in case.medication_records
            if ClinicalPipeline._medication_key(record.medication) == "insulin glargine"
        )
        self.assertIn("28 units", insulin.medication)
        grouped = case.consolidated.grouped_entities()
        symptom_values = [entity.text.casefold() for entity in grouped.get("SYMPTOM", [])]
        allergy_values = [entity.text.casefold() for entity in grouped.get("ALLERGY", [])]
        self.assertEqual(
            sum("chest pain" in value for value in symptom_values),
            1,
        )
        self.assertEqual(
            sum(
                "ankle oedema" in value
                or "pitting oedema" in value
                or ("ankle" in value and "puffy" in value)
                for value in symptom_values
            ),
            1,
        )
        self.assertEqual(
            sum("contrast" in value for value in allergy_values),
            1,
        )
        ferrous_states = [
            record.status
            for record in case.medication_records
            if "ferrous sulphate" in record.medication.casefold()
        ]
        self.assertTrue(ferrous_states)
        self.assertTrue(all(status == "New" for status in ferrous_states))
        self.assertEqual(case.consolidated.risk_level, "High")
        self.assertIn("Immediate", case.overall_recommendation.timeframe)
        self.assertLess(case.completeness.score, case.completeness.total)
        self.assertTrue(case.safety_warnings)
        self.assertEqual(len(case.documents), 3)

    def test_real_image_ocr_recovers_gi_bleeding_safety_context(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "inputs"
            / "image_discharge_summary.png"
        )
        if not path.exists():
            self.skipTest("Local image OCR regression fixture is unavailable.")

        class Upload:
            name = path.name

            @staticmethod
            def getvalue():
                return path.read_bytes()

        text = extract_uploaded_text(Upload())
        self.assertGreater(len(text), 1000)
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": path.name,
                    "document_name": path.name,
                    "text": text,
                }
            ]
        )
        result = case.consolidated
        self.assertEqual(result.patient_details["name"], "John Doe")
        self.assertEqual(case.documents[0].admission_date, "2020-09-07")
        self.assertEqual(case.documents[0].discharge_date, "2020-09-08")
        grouped = result.grouped_entities()
        symptoms = [entity.text.casefold() for entity in grouped.get("SYMPTOM", [])]
        medications = [entity.text.casefold() for entity in grouped.get("MEDICATION", [])]
        allergies = [entity.text.casefold() for entity in grouped.get("ALLERGY", [])]
        context = [
            entity.text.casefold()
            for label in ("SOCIAL_HISTORY", "FAMILY_HISTORY", "FOLLOW_UP")
            for entity in grouped.get(label, [])
        ]
        self.assertIn("epigastric abdominal pain", symptoms)
        self.assertIn("darker stools", symptoms)
        self.assertTrue(any("motrin" in item for item in medications))
        self.assertTrue(any("nkda" in item for item in allergies))
        self.assertTrue(any("smokes since" in item for item in context))
        self.assertTrue(any("bleeding ulcer" in item for item in context))
        self.assertTrue(any("antibiotic" in item for item in context))
        self.assertTrue(
            any(
                "gastrointestinal bleeding" in link.meaning.casefold()
                for link in result.causal_links
            )
        )
        self.assertEqual(result.risk_level, "High")

    def test_single_document_combined_record_uses_correct_label(self):
        case = self.pipeline.analyse_many(
            [
                {
                    "document_id": "ONE",
                    "document_name": "Clinical note",
                    "text": (
                        "Patient: Jane Doe. Age: 60. Female. "
                        "Medication reviewed. NKDA. Follow-up arranged."
                    ),
                }
            ]
        )
        self.assertEqual(case.consolidated.document_type, "Combined record (1 document)")

    def test_multiline_name_and_parenthesised_demographics_are_supported(self):
        labelled = infer_patient_details(
            "Emergency Department Note\nName: Eleanor Grant\nAge: 74\nSex: Female"
        )
        compact = infer_patient_details(
            "Clinical note for Eleanor Grant (74, Female). Referral letter."
        )
        expected = {
            "name": "Eleanor Grant",
            "age": 74,
            "gender": "Female",
            "date_of_birth": "Not identified",
            "patient_id": "Not identified",
        }
        self.assertEqual(labelled, expected)
        self.assertEqual(compact, expected)

    def test_table_style_demographics_and_dotted_dates_are_supported(self):
        details = infer_patient_details(
            "Visit Date: 14.11.2023\n"
            "Full Name: Sarah Anderson  Birth Date: 01.01.1989\n"
            "Med. Number: MA567891\n"
            "Ms. Anderson appears in good health."
        )
        self.assertEqual(details["name"], "Sarah Anderson")
        self.assertEqual(details["date_of_birth"], "1989-01-01")
        self.assertEqual(details["age"], 34)
        self.assertEqual(details["gender"], "Female")
        self.assertEqual(details["patient_id"], "MA567891")

    def test_line_oriented_report_demographics_are_supported(self):
        details = infer_patient_details(
            "Clinical Document Intelligence Report\n"
            "Patient\nMargaret Elaine Forsythe\nAge\n66\nCase ID\nCASE-1234"
        )
        self.assertEqual(details["name"], "Margaret Elaine Forsythe")
        self.assertEqual(details["age"], 66)

    def test_family_history_diagnosis_is_not_assigned_to_patient(self):
        result = self.pipeline.analyse(
            "Name: Emily Johnson\nDate of Birth: 01/15/1989\n"
            "Medical history: hypertension. "
            "Family history reveals her father had coronary artery disease. "
            "She reports intermittent chest pain, palpitations and shortness of breath."
        )
        diagnoses = {
            entity.text.casefold()
            for entity in result.entities
            if entity.label == "DIAGNOSIS"
        }
        self.assertIn("hypertension", diagnoses)
        self.assertNotIn("coronary artery disease", diagnoses)
        self.assertEqual(result.risk_level, "Medium")

    def test_mental_capacity_report_extracts_broad_clinical_context(self):
        result = self.pipeline.analyse(
            "Full name of patient: Mr Tan Ah Kow\n"
            "NRIC/FIN/Passport no. of patient: S1111111X\n"
            "Age of patient: 55 years old\n"
            "He has had hypertension and hyperlipidemia and suffered several strokes. "
            "He developed cardiomyopathy, cardiac failure and chronic renal disease. "
            "Diagnosis: Dementia and Stroke. His cognitive failures mean he will not "
            "be able to make decisions about personal welfare."
        )
        diagnoses = " | ".join(
            entity.text.casefold()
            for entity in result.entities
            if entity.label == "DIAGNOSIS"
        )
        self.assertEqual(result.patient_details["name"], "Tan Ah Kow")
        self.assertEqual(result.patient_details["patient_id"], "S1111111X")
        for expected in (
            "hypertension",
            "hyperlipidemia",
            "stroke",
            "cardiomyopathy",
            "cardiac failure",
            "chronic renal disease",
            "dementia",
        ):
            self.assertIn(expected, diagnoses)
        self.assertEqual(result.risk_level, "Medium")

if __name__ == "__main__":
    unittest.main()
