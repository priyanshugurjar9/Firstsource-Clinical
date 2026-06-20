# Requirements Traceability

| Brief requirement | Implementation | Evidence |
|---|---|---|
| Accept text, PDF or image | Paste text and upload PNG, PDF, DOCX, MD or TXT | `app.py`, `src/text_processing.py` |
| Extract key structured information | Patient details, conditions, symptoms, medicines, allergies, results, dates, follow-up and red flags | `src/entity_extractor.py`, `src/pipeline.py` |
| Generate a clear summary or recommendation | Combined plain-language summary and overall recommendation | Patient summary view |
| Present decision-ready output | Priority banner, action queue, routing, deadline and source evidence | Action queue view |
| Demonstrate end-to-end processing | Input to analysis to UI to JSON/PDF export | Streamlit application |
| Confidence scoring, optional | High/Medium/Low extraction confidence with evidence | Extraction confidence expander |
| Multi-document comparison, optional | Identity checks, timeline, conflict and change detection | Patient summary and timeline views |
| Triage or routing, optional | Dynamic workflow priority, route and deadline | Priority banner and action queue |
| README with approach, tools and assumptions | Setup, workflow, operation, model choice and boundaries | `README.md` |
| Sample input and output | One equivalent case in PNG, PDF, DOCX, MD and TXT, plus JSON/PDF case output | `examples/` |

## Tool Choice

The brief lists an LLM API as a suggested pro-code tool and explicitly allows open-source alternatives. This implementation uses a mandatory local, fine-tuned BioClinicalBERT transformer for clinical NER, with deterministic validation and rule-grounded summarisation. It avoids API cost and keeps document content local.

## Demonstration Scope

The prototype meets the requested POC workflow. It does not claim production readiness, autonomous treatment recommendations, validated clinical risk prediction or proven medical causality.
