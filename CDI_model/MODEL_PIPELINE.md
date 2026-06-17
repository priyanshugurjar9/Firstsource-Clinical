# Clinical Document Intelligence Hub - Model Pipeline

## Purpose

This POC converts unstructured clinical documents into structured, explainable outputs that a clinical or administrative team can review quickly.

The goal is not to diagnose patients. The goal is to reduce manual document review by extracting the important information, highlighting risk signals, and recommending the next workflow action for human review.

The prototype is designed for documents such as discharge summaries, emergency notes, lab reports, referral letters, intake forms, medication reviews, and physician notes.

---

## High-Level Approach

The pipeline uses a hybrid design:

```text
Clinical document
-> text extraction
-> clinical entity extraction
-> structured reasoning
-> deterministic causal explanation
-> risk and triage output
-> patient intelligence card
```

I am using a hybrid approach because one model should not be responsible for everything. Clinical document intelligence needs extraction, summarisation, reasoning, explanation, and auditability. Separating these responsibilities makes the system easier to test and easier to explain.

---

## Model Choices

### 1. Domain-Adapted BioClinicalBERT

BioClinicalBERT is used for the clinical entity extraction layer because it is already trained on clinical language and is better suited to medical terminology than a general-purpose BERT model.

It is used to identify entities such as:

- diagnoses
- symptoms
- medications
- allergies
- lab results
- red flags

For this POC, the labelled entity dataset can be used to fine-tune or evaluate this layer.

### 2. LLM Structured Reasoning Layer

An LLM is used where natural language understanding and formatting are useful.

It helps with:

- converting extracted information into structured JSON
- producing a readable patient summary
- identifying missing or unclear information
- formatting the final output for the UI

The LLM does not own the final risk decision or causal explanation. Those are handled by deterministic logic so the explanation is tied to the actual decision path.

### 3. Deterministic Causal Explanation Layer

The causal layer explains why a case was flagged.

It follows a simple structure inspired by Judea Pearl's causal reasoning ideas, especially the idea that explanations should connect cause, effect, and intervention rather than only show correlation.

For this POC, the causal layer is not a full causal discovery system. It is a transparent rule-based explanation layer:

```text
Finding -> clinical meaning -> risk implication -> recommended action
```

Example:

```text
HbA1c 9.4%
-> poor glycaemic control
-> higher follow-up priority
-> route to diabetes nurse specialist
```

This makes the output more useful than a black-box summary because the reviewer can see what drove the recommendation.

---

## Dataset

The project uses a synthetic clinical dataset created for this POC.

Main document dataset:

```text
data/clinical_poc_synthetic_dataset.csv
```

Entity annotation dataset:

```text
data/clinical_poc_entity_annotations.csv
```

The dataset contains:

- 144 synthetic clinical documents
- 1,476 entity annotations
- train, validation, and test splits
- document-level gold labels
- entity-level labels with character offsets
- expected risk level
- recommended action
- causal reasoning explanation
- full structured JSON output

Synthetic data is used because healthcare data is sensitive. This gives us realistic clinical document patterns without using real patient data or protected health information.

---

## Pipeline Steps

### Step 1: Document Input

The user can provide:

- a sample note from the dataset
- pasted clinical text
- a PDF document

The input is treated as an unstructured clinical document.

### Step 2: Text Extraction And Cleaning

The document is converted into clean text.

Cleaning includes:

- removing unnecessary whitespace
- preserving clinical sections
- normalising line breaks
- keeping lab values and medication doses intact

### Step 3: Clinical Entity Extraction

The BioClinicalBERT layer extracts the clinical entities needed for the patient intelligence card.

Target labels:

- `DIAGNOSIS`
- `SYMPTOM`
- `MEDICATION`
- `ALLERGY`
- `LAB_RESULT`
- `RED_FLAG`

Missing information is handled separately because it is usually an inference about what is absent, not a text span that can be extracted directly.

### Step 4: Entity Validation

The extracted entities are cleaned and validated before reasoning.

This step:

- removes duplicates
- maps labels to the application schema
- keeps source offsets where available
- attaches confidence scores
- prepares evidence snippets for review

Confidence scores are not presented as clinical probabilities. For extracted entities, they come from model confidence where available. For rule-based outputs, they represent rule-match strength.

### Step 5: Structured Reasoning

The LLM receives the cleaned text and extracted entities, then returns a structured draft.

The expected output includes:

```json
{
  "patient_details": {},
  "clinical_summary": "",
  "diagnoses": [],
  "symptoms": [],
  "medications": [],
  "allergies": [],
  "lab_results": [],
  "red_flags": [],
  "missing_information": []
}
```

The LLM is used for structure and readability, not for final risk ownership.

### Step 6: Causal Explanation

The deterministic causal layer creates the final explanation.

It maps extracted findings to known risk patterns.

Example:

```text
Finding: Potassium 5.7 mmol/L + eGFR 28
Meaning: reduced renal function with raised potassium
Risk implication: possible medication safety concern
Action: escalate for renal review and repeat potassium confirmation
```

This is the part of the system that owns the causal trace.

### Step 7: Risk And Triage

The triage engine assigns:

```text
Low / Medium / High
```

The score is based on:

- red flags
- abnormal lab values
- missing safety-critical information
- urgent symptoms
- follow-up urgency
- document context

The output is designed as workflow prioritisation, not autonomous clinical prediction.

### Step 8: Patient Intelligence Card

The final UI shows:

- patient details
- document type
- clinical summary
- extracted diagnoses
- symptoms
- medications
- allergies
- lab results
- red flags
- missing information
- confidence scores
- evidence snippets
- risk level
- causal explanation
- recommended next action

This is the main demo output.

### Step 9: Human Review And Export

The reviewer can inspect the structured output and download it as JSON or a report.

The export supports auditability and future integration with case management or clinical administration workflows.

---

## Optional What-If View

The UI may include a small causal graph and what-if panel.

This is a stretch feature, not the core model.

It lets the reviewer explore how the rule-based priority score changes if selected factors improve or remain unresolved.

Example:

```text
Current:
HbA1c 9.4% + follow-up not scheduled -> High priority

What-if:
HbA1c 7.2% + follow-up scheduled -> Medium priority
```

This is not a validated clinical prediction model. It is an explanation tool that shows how the prototype's rules behave.

---

## Evaluation Plan

The pipeline is evaluated at two levels.

### Entity Extraction

Predicted entities are compared with:

```text
data/clinical_poc_entity_annotations.csv
```

Metrics:

- precision
- recall
- F1 score

The annotation file includes character offsets, so entity evaluation can be more precise than simple keyword matching.

### Document-Level Output

The full output is compared with:

```text
data/clinical_poc_synthetic_dataset.csv
```

Evaluation checks:

- diagnosis extraction
- medication extraction
- allergy extraction
- lab result extraction
- red flag detection
- missing information detection
- risk level classification
- recommended action relevance
- JSON validity
- causal explanation quality

Because the dataset is synthetic, the metrics are POC validation metrics, not production clinical performance claims.

---

## Why This Pipeline Fits The Brief

The brief asks for a prototype that can ingest unstructured clinical documents and produce structured, actionable intelligence.

This pipeline directly supports that:

```text
unstructured document -> extracted clinical facts -> risk explanation -> recommended next action
```

It goes beyond a basic summariser by adding:

- biomedical entity extraction
- structured JSON output
- confidence scoring
- evidence snippets
- deterministic causal explanation
- risk and triage logic
- human-in-the-loop review

---

## Safety Note

This prototype is for proof-of-concept use only.

It does not provide autonomous diagnosis, treatment advice, or clinically validated outcome prediction.

Before any production use, the system would need validation on approved de-identified clinical datasets, clinical review, privacy assessment, bias testing, and governance approval.
