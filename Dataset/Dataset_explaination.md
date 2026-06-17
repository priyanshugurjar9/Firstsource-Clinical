## Dataset

This project uses a purpose-built synthetic clinical document dataset created specifically for the **Clinical Document Intelligence Hub** proof of concept. The goal of the dataset is to simulate realistic healthcare document review scenarios where clinical and administrative teams need to read unstructured documents and convert them into structured, decision-ready information.

The dataset does **not** contain any real patient data, protected health information, or client data. All patient names, clinical notes, findings, medications, lab values, risk flags, and recommendations are synthetic. This makes the dataset safe to use in a public GitHub repository while still being realistic enough to demonstrate clinical NLP, GenAI extraction, triage logic, and explainable decision support.

The dataset is split into two CSV files:

```text
data/clinical_poc_synthetic_dataset.csv
data/clinical_poc_entity_annotations.csv
These two files serve different purposes. The first file is the main document-level dataset used by the application. The second file is an entity-level annotation dataset that can be used for model training, fine-tuning, or extraction evaluation.

1. Main Clinical Document Dataset
data/clinical_poc_synthetic_dataset.csv
This is the primary dataset used by the prototype. It contains 144 synthetic clinical documents.

Each row represents one complete clinical document. The document includes an unstructured clinical note and its expected structured output. This allows the system to be tested end-to-end: from clinical document input to extracted fields, risk classification, causal explanation, and recommended next action.

The dataset includes multiple realistic document types:

Discharge summaries
Emergency department notes
Referral letters
Lab reports
Intake forms
Medication reviews
Physician progress notes
Using multiple document types is important because real healthcare teams do not review only one kind of document. Clinical and administrative staff often work across mixed document formats, each with different structure, language, and information density. This makes the dataset more realistic for a clinical document intelligence use case.

Columns in clinical_poc_synthetic_dataset.csv
Column	Description	Why It Is Useful
doc_id	Unique document identifier for each synthetic clinical note	Helps track documents during processing, evaluation, logging, and audit review
document_type	Type of clinical document, such as discharge summary, lab report, referral letter, or ED note	Allows the model and UI to understand document context and adapt the output format
patient_name	Synthetic patient name	Used to populate the patient intelligence card and demonstrate structured patient-level extraction
age	Synthetic patient age	Useful for patient summary generation and risk interpretation
gender	Synthetic patient gender	Adds realistic demographic context to the structured output
clinical_note	The main unstructured clinical document text	This is the input text that the AI system processes and extracts information from
gold_diagnoses	Expected diagnosis entities from the note	Used to evaluate whether the model correctly identifies clinical conditions
gold_symptoms	Expected symptom entities from the note	Used to evaluate symptom extraction and clinical summarisation
gold_medications	Expected medication entities from the note	Supports medication extraction, medication review workflows, and safety checks
gold_allergies	Expected allergy entities from the note	Important for patient safety and clinical/admin alerts
gold_lab_results	Expected lab or investigation results	Helps evaluate extraction of structured observations such as HbA1c, creatinine, potassium, ECG findings, or blood pressure
gold_red_flags	Expected clinical or operational risk indicators	Used by the triage engine to identify high-priority cases
gold_missing_information	Important missing or unclear information in the document	Helps the system recommend admin follow-up, such as requesting missing medication lists or repeat lab results
gold_risk_level	Expected risk level: Low, Medium, or High	Used to evaluate triage classification accuracy
gold_recommended_action	Expected next action for clinical or administrative review	Helps evaluate whether the system produces actionable recommendations
gold_causal_reasoning	Explanation connecting findings to risk and action	Supports explainability by showing why a case was flagged or routed
gold_structured_output_json	Full expected structured output in JSON format	Useful for comparing AI-generated JSON against the expected output
split	Train, validation, or test split	Allows proper model development and evaluation without testing only on training examples
2. Entity Annotation Dataset
data/clinical_poc_entity_annotations.csv
This second dataset contains entity-level annotations extracted from the main clinical documents.

While the main dataset works at the document level, this file works at the entity level. Each row represents one labelled clinical entity found in a document.

For example, if a clinical note contains:

The patient has Type 2 diabetes mellitus and is taking Metformin 1000 mg twice daily. HbA1c is 9.4%.
The entity annotation file may include rows such as:

doc_id	entity_text	entity_label
CLIN-0001	Type 2 diabetes mellitus	DIAGNOSIS
CLIN-0001	Metformin 1000 mg twice daily	MEDICATION
CLIN-0001	HbA1c 9.4%	LAB_RESULT
Columns in clinical_poc_entity_annotations.csv
Column	Description	Why It Is Useful
doc_id	Links the entity back to the original clinical document	Allows entity-level predictions to be connected to the full document context
entity_text	The exact clinical phrase or value to be extracted	Used as the target text for entity extraction
entity_label	The category of the entity	Used to train or evaluate a clinical named entity recognition model
The entity labels include:

Entity Label	Meaning
DIAGNOSIS	Clinical condition or working diagnosis
SYMPTOM	Patient-reported or documented symptom
MEDICATION	Medication name, dose, or medication instruction
ALLERGY	Allergy or intolerance information
LAB_RESULT	Lab value, investigation result, observation, or clinical measurement
RED_FLAG	Clinical or operational risk signal
MISSING_INFO	Missing or unclear information requiring follow-up
Why Two Dataset Files Are Used
Two dataset files are used because the prototype has two different AI needs:

Document-level intelligence
Entity-level extraction
The main dataset supports the full end-to-end workflow:

clinical document → structured summary → risk level → causal explanation → recommended action
The entity annotation dataset supports the extraction layer:

clinical text → diagnosis / medication / lab / symptom / allergy entities
This separation makes the project cleaner and more realistic. In a real clinical NLP system, document-level outputs and entity-level annotations are often handled separately because they support different tasks.

The document-level dataset is useful for:

testing the full application workflow
generating patient intelligence cards
evaluating risk classification
validating recommended next actions
comparing generated structured JSON against gold output
demonstrating the user-facing prototype
The entity-level dataset is useful for:

fine-tuning a biomedical NER model such as BioClinicalBERT
evaluating extraction accuracy
measuring precision, recall, and F1 score for entity labels
improving confidence scoring
supporting the structured extraction pipeline
Together, the two files allow the system to demonstrate both GenAI reasoning and machine learning extraction.

Why Synthetic Data Was Used
Synthetic data was used because healthcare data is highly sensitive and real patient records are protected by strict privacy and governance requirements. The POC brief allows candidates to use publicly available data or generate a suitable dataset.

Using synthetic data provides several advantages:

No real patient data is exposed
No protected health information is used
The dataset can be safely uploaded to GitHub
The examples can be designed to match the POC requirements exactly
The dataset can include a balanced range of document types and risk levels
The labels are known, so the system can be evaluated clearly
The dataset supports fast development within the 5-day POC timeline
This makes synthetic data a practical and responsible choice for a proof of concept.

Why This Dataset Is Good For The Clinical Document Intelligence Hub
This dataset is suitable for the Clinical Document Intelligence Hub because it directly matches the expected behaviour of the prototype.

The POC requires the system to:

accept unstructured clinical documents
extract key structured information
generate a readable clinical or administrative summary
identify risk flags
recommend a next step
present outputs clearly for clinical or administrative users
The dataset supports all of these requirements.

Each document contains unstructured clinical text, and each row includes expected structured outputs such as diagnoses, symptoms, medications, allergies, lab results, red flags, missing information, risk level, recommended action, and causal reasoning.

This makes it possible to evaluate whether the AI system is only summarising text or actually converting documents into decision-ready intelligence.
