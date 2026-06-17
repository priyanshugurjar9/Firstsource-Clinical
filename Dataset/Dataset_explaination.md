## Dataset

This project uses a purpose-built synthetic clinical document dataset created specifically for the **Clinical Document Intelligence Hub** proof of concept. The goal of the dataset is to simulate realistic healthcare document review scenarios where clinical and administrative teams need to read unstructured documents and convert them into structured, decision-ready information.

The dataset does **not** contain any real patient data, protected health information, or client data. All patient names, clinical notes, findings, medications, lab values, risk flags, and recommendations are synthetic. This makes the dataset safe to use in a public GitHub repository while still being realistic enough to demonstrate clinical NLP, GenAI extraction, triage logic, and explainable decision support.

The dataset is split into two CSV files:

```text
data/clinical_poc_synthetic_dataset.csv
data/clinical_poc_entity_annotations.csv
