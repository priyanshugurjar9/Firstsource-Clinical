# Clinical Document Intelligence Hub - Model Pipeline

## Objective

The objective of this prototype is to convert unstructured clinical documents into structured, explainable, and action-ready intelligence for clinical and administrative review.

The system is designed to process documents such as discharge summaries, emergency department notes, lab reports, referral letters, intake forms, medication reviews, and physician progress notes.

The prototype focuses on:

- clinical entity extraction
- structured patient summary generation
- confidence-scored outputs
- red flag detection
- risk and triage classification
- causal explainability
- optional causal graph and what-if risk simulation
- recommended next actions
- human-in-the-loop review

This system is not designed to provide autonomous diagnosis. It supports document review and operational decision-making.

---

## Model Strategy

The prototype uses a hybrid AI architecture instead of relying on a single model.

The reason for this design is that clinical document intelligence requires multiple capabilities:

- understanding clinical language
- extracting structured entities
- generating readable summaries
- explaining risk signals
- recommending workflow actions
- keeping the output auditable

No single model is ideal for all of these tasks. A hybrid design provides better reliability, explainability, and control.

### Selected Model Approach

```text
Domain-adapted BioClinicalBERT
+ LLM structured reasoning
+ deterministic causal explainability
+ risk and triage logic
```

### Why BioClinicalBERT

BioClinicalBERT is used as the biomedical language model layer because it is already trained on clinical text and is better suited to medical terminology than a general-purpose language model.

It is suitable for:

- diagnosis extraction
- symptom extraction
- medication extraction
- allergy extraction
- lab result extraction
- clinical red flag identification

For this POC, the entity annotation dataset can be used to fine-tune or evaluate the BioClinicalBERT extraction layer.

### Why An LLM Is Still Used

BioClinicalBERT is strong for entity extraction, but it is not ideal for producing polished clinical summaries or workflow-ready explanations.

An LLM is used for:

- converting extracted entities into structured JSON
- generating a readable patient summary
- identifying missing information
- polishing the final explanation for clinical/admin users
- formatting the final output for the UI

This separation keeps the pipeline practical and explainable.

The LLM does not own the final causal reasoning or risk decision. Those are produced by deterministic rules so the explanation remains faithful to the logic that generated the output.

### Why Causal Reasoning Is Added

The causal reasoning layer improves explainability by showing how extracted findings lead to a risk flag or recommended action.

The system does not claim to prove medical causality. Instead, it uses causal-style reasoning for transparent decision support.

This layer is deterministic: it maps finding patterns to explanation templates and action rules. The LLM may polish the wording, but it does not invent the causal logic.

Example:

```text
HbA1c 9.4%
-> poor glycaemic control
-> increased risk of diabetes complications
-> high-priority follow-up recommended
```

This makes the system easier to understand, audit, and trust.

---

## Dataset

The project uses a synthetic clinical document dataset created for this POC.

Main dataset:

```text
data/clinical_poc_synthetic_dataset.csv
```

Entity annotation dataset:

```text
data/clinical_poc_entity_annotations.csv
```

The dataset contains:

- 144 synthetic clinical documents
- 1,632 entity annotations
- entity-level character offsets for extraction evaluation
- train, validation, and test splits
- document-level gold labels
- entity-level gold labels
- expected risk level
- recommended action
- causal reasoning explanation
- full structured JSON output

Synthetic data is used to avoid patient privacy risk while still simulating realistic clinical document review workflows.

---

## End-to-End Pipeline

```text
1. Clinical document input
2. Text extraction and cleaning
3. Clinical text preprocessing
4. BioClinicalBERT entity extraction
5. Structured entity validation
6. LLM structured reasoning
7. Deterministic causal explainability layer
8. Risk and triage engine
9. Patient intelligence card generation
10. Human-in-the-loop review
11. Export and audit output
```

---

## Step 1: Clinical Document Input

The system accepts clinical documents in multiple formats:

- pasted text
- sample clinical note from dataset
- PDF upload
- optional image upload in future extension

The input is treated as an unstructured clinical document.

Example input types:

- discharge summary
- emergency department note
- lab report
- referral letter
- intake form
- medication review
- physician progress note

---

## Step 2: Text Extraction And Cleaning

The document is converted into plain text.

For PDF inputs, a PDF parser extracts readable text. For pasted text or sample notes, the text is passed directly into the pipeline.

Cleaning includes:

- removing repeated whitespace
- normalising line breaks
- preserving clinical sections
- removing obvious formatting noise
- keeping clinically meaningful values intact

The goal is to prepare the text without losing medical meaning.

---

## Step 3: Clinical Text Preprocessing

The cleaned document is prepared for model processing.

Preprocessing includes:

- section detection
- sentence segmentation
- clinical phrase preservation
- document type identification
- preparation for entity extraction

This step helps the model understand whether a phrase appears in a medication list, diagnosis section, lab section, or follow-up section.

---

## Step 4: BioClinicalBERT Entity Extraction

The BioClinicalBERT layer extracts key clinical entities from the document.

Target entity labels:

- `DIAGNOSIS`
- `SYMPTOM`
- `MEDICATION`
- `ALLERGY`
- `LAB_RESULT`
- `RED_FLAG`

The entity annotation file is used to train, fine-tune, or evaluate this extraction layer.

Missing information is not treated as a NER target because it is usually an absence or inference, not an extractable text span. Missing information is handled by the LLM structured reasoning layer and checked against document-level gold labels.

The output of this step is a structured list of clinical entities.

Example:

```json
{
  "diagnoses": ["Type 2 diabetes mellitus"],
  "symptoms": ["fatigue", "polyuria", "blurred vision"],
  "medications": ["Metformin 1000 mg twice daily"],
  "lab_results": ["HbA1c 9.4%"],
  "red_flags": ["HbA1c above target"]
}
```

---

## Step 5: Structured Entity Validation

Extracted entities are validated before being passed into the reasoning layer.

Validation checks include:

- required fields are present where possible
- duplicate entities are removed
- entity labels are mapped to the expected schema
- entity confidence scores are attached
- character offsets are retained where available

This step improves reliability and prevents the final output from depending only on free-form generation.

---

## Step 6: LLM Structured Reasoning

The LLM receives the cleaned document and extracted entities.

It produces a structured output using a fixed schema.

The LLM is responsible for summary wording, structured formatting, and missing-information detection. It does not decide the final risk level or causal explanation.

Expected output:

```json
{
  "patient_details": {
    "name": "",
    "age": "",
    "gender": "",
    "document_type": ""
  },
  "clinical_summary": "",
  "diagnoses": [],
  "symptoms": [],
  "medications": [],
  "allergies": [],
  "lab_results": [],
  "red_flags": [],
  "missing_information": [],
  "draft_clinical_summary": "",
  "draft_recommended_action": ""
}
```

The LLM is used for summarisation and formatting, while extraction, causal explanation, and triage remain grounded by structured entities and deterministic rules.

---

## Step 7: Deterministic Causal Explainability Layer

The causal explainability layer explains why the system produced a risk flag or recommended action.

This layer is the single source of truth for causal reasoning. It overwrites any draft explanation and produces the final causal trace from explicit rules.

It follows this structure:

```text
Finding -> clinical meaning -> risk implication -> recommended action
```

Examples:

```text
Chest pain + ECG abnormality
-> possible acute cardiac concern
-> high clinical risk
-> urgent clinician review recommended
```

```text
Low eGFR + high potassium
-> impaired renal clearance with hyperkalaemia risk
-> urgent safety concern
-> renal review and repeat potassium confirmation recommended
```

```text
Missing discharge medication list
-> incomplete medication reconciliation
-> administrative and patient safety risk
-> request missing medication information
```

This layer makes the output more transparent and supports human review.

The optional UI extension includes a causal graph and what-if simulation panel. This allows reviewers to see which findings contribute most to severity and explore how the rule-based priority score changes if selected factors improve, worsen, or remain unresolved.

Example:

```text
Current:
HbA1c 9.4% + follow-up not scheduled -> High risk

Simulated:
HbA1c 7.2% + follow-up scheduled -> Medium risk
```

The simulation is an illustrative exploration of rule weights, not a clinically validated outcome prediction model.

---

## Step 8: Risk And Triage Engine

The triage engine assigns a risk level:

- `Low`
- `Medium`
- `High`

The risk level is based on:

- extracted red flags
- abnormal lab results
- document type
- missing critical information
- urgency of follow-up
- clinical context

Example triage logic:

```text
High risk:
- chest pain with ECG abnormality
- severe abnormal lab value
- hyperkalaemia
- uncontrolled diabetes with high HbA1c
- acute shortness of breath
- missing safety-critical medication information

Medium risk:
- chronic condition needing follow-up
- abnormal but non-critical lab result
- medication change requiring review
- referral required but no immediate danger signal

Low risk:
- stable condition
- routine follow-up
- no red flags
- complete documentation
```

The triage output is explainable and connected to the causal reasoning layer.

---

## Step 9: Patient Intelligence Card

The final user-facing output is a patient intelligence card.

It includes:

- patient details
- document type
- clinical summary
- extracted diagnoses
- symptoms
- medications
- allergies
- lab results
- source evidence snippets and offsets where available
- red flags
- missing information
- confidence scores
- risk level
- causal explanation
- recommended next action

The UI will also include a dedicated causal inference view with:

- interactive causal graph
- ranked risk drivers
- current risk score
- optional what-if rule score
- sliders for modifiable factors
- explanation of what is making the case more serious

This card is designed for clinical and administrative teams who need quick, structured review of long documents.

---

## Step 10: Human-In-The-Loop Review

The system keeps human review central.

The output is designed to help users review documents faster, not replace professional judgement.

A reviewer can inspect:

- extracted fields
- confidence scores
- evidence snippets
- risk explanation
- recommended action

This supports safer and more auditable AI-assisted workflows.

---

## Step 11: Export And Audit Output

The final structured output can be exported as:

- JSON
- CSV
- summary report
- audit trace

The export supports downstream integration with:

- case management systems
- clinical admin workflows
- triage queues
- quality review processes

---

## Evaluation Plan

The model pipeline can be evaluated at two levels.

### Entity Extraction Evaluation

Entity extraction can be evaluated using:

- precision
- recall
- F1 score

The predicted entities are compared against:

```text
data/clinical_poc_entity_annotations.csv
```

Entity-level evaluation uses exact text spans and character offsets. Confidence scores for extracted spans are derived from the model probability where available. For rule-based findings, confidence is reported as rule-match strength rather than calibrated clinical probability.

### Document-Level Evaluation

Document-level outputs can be evaluated against:

```text
data/clinical_poc_synthetic_dataset.csv
```

Evaluation areas:

- diagnosis extraction accuracy
- medication extraction accuracy
- allergy extraction accuracy
- lab result extraction accuracy
- red flag detection accuracy
- risk level classification accuracy
- recommended action relevance
- causal reasoning quality
- structured JSON validity

Because the current dataset is synthetic and uses repeated scenario templates, reported metrics should be interpreted as POC validation metrics rather than production clinical performance. This limitation is explicitly documented and should be addressed with de-identified clinical datasets and expert review before real deployment.

---

## Why This Pipeline Is Strong For The POC

This pipeline is well suited to the Clinical Document Intelligence Hub brief because it directly addresses the required outcome:

```text
unstructured clinical document -> structured actionable intelligence
```

It goes beyond simple summarisation by including:

- domain-specific entity extraction
- structured JSON output
- defined confidence scoring
- risk classification
- causal explainability
- recommended workflow actions
- human-in-the-loop review
- exportable audit output

This makes the prototype relevant for both clinical and administrative users.

---

## Safety And Scope

This prototype is intended for proof-of-concept use only.

It does not provide autonomous diagnosis, treatment decisions, or clinical validation.

The system is designed to support human review by extracting and organising information from clinical documents.

Production deployment would require:

- clinical validation
- governance review
- privacy assessment
- bias and safety testing
- real-world dataset validation
- integration with approved healthcare systems
 
