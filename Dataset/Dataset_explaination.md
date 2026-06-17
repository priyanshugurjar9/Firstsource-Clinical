Dataset description:
The dataset contains 144 synthetic clinical documents across multiple real-world document types, including:

- Discharge summaries
- Emergency department notes
- Referral letters
- Lab reports
- Intake forms
- Medication reviews
- Physician progress notes

Each document includes an unstructured clinical note and corresponding gold-standard structured labels. These labels are used to evaluate how well the system extracts clinical information and converts it into decision-ready outputs.

### Dataset Fields

The main dataset file is:

```text
It contains the following key fields:

Field	Description
doc_id	Unique document identifier
document_type	Type of clinical document
patient_name	Synthetic patient name
age	Synthetic patient age
gender	Synthetic patient gender
clinical_note	Unstructured clinical document text
gold_diagnoses	Expected diagnosis entities
gold_symptoms	Expected symptom entities
gold_medications	Expected medication entities
gold_allergies	Expected allergy entities
gold_lab_results	Expected lab result entities
gold_red_flags	Expected clinical or operational risk flags
gold_missing_information	Important missing or unclear information
gold_risk_level	Expected triage level: Low, Medium, or High
gold_recommended_action	Expected next action for clinical/admin review
gold_causal_reasoning	Explanation linking findings to risk and action
gold_structured_output_json	Full expected structured output
split	Train, validation, or test split
