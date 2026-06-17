# Causal Explainability And What-If Simulation UI

## Purpose

The Clinical Document Intelligence Hub can include a causal explainability and what-if simulation view to make the model output more transparent and interactive.

The goal is to help clinical and administrative reviewers understand:

- which extracted findings are contributing most to the current risk level
- how findings are connected to downstream risk
- what missing information may increase uncertainty
- what follow-up action is most appropriate
- how the rule-based priority score may change if key factors improve or worsen

This layer is designed for explainable decision support. It does not claim to prove medical causality or replace clinical judgement.

---

## UI Concept

The causal explainability UI will be shown as an interactive graph and optional what-if simulation panel.

The user will see:

```text
Extracted clinical findings
        ↓
Clinical meaning
        ↓
Risk drivers
        ↓
Operational priority
        ↓
Recommended action
```

Example:

```text
HbA1c 9.4%
        ↓
Poor glycaemic control
        ↓
Higher follow-up priority
        ↓
High follow-up priority
        ↓
Route to diabetes nurse specialist
```

---

## Interactive Causal Graph

The UI will show a graph with connected nodes.

### Node Types

| Node Type | Example | Purpose |
|---|---|---|
| Patient Factor | Age 74 | Adds patient context |
| Clinical Finding | HbA1c 9.4% | Shows extracted evidence |
| Symptom | Shortness of breath | Shows patient-reported concern |
| Lab Result | Potassium 5.7 mmol/L | Highlights objective abnormal result |
| Medication Factor | Insulin glargine | Shows treatment context |
| Red Flag | Hyperkalaemia | Highlights serious concern |
| Risk Driver | Poor glycaemic control | Explains why risk is increasing |
| Outcome Risk | High follow-up priority | Shows likely operational risk |
| Recommended Action | Urgent clinician review | Shows next workflow step |

### Edge Types

| Edge | Meaning |
|---|---|
| contributes to | A finding increases a risk driver |
| indicates | A value suggests a clinical meaning |
| increases risk of | A risk driver increases downstream risk |
| requires | A risk state requires an action |
| reduces uncertainty if available | Missing information would improve confidence |

---

## Risk Driver Ranking

The UI will include a ranked list of the most important factors driving the risk score.

Example:

```text
Top risk drivers
1. Potassium 5.7 mmol/L - high severity contribution
2. eGFR 28 mL/min/1.73m2 - high severity contribution
3. Missing repeat potassium result - increases uncertainty
4. Ramipril use - medication safety review needed
```

This makes the output easier to trust because the reviewer can see what caused the system to prioritise the case.

---

## What-If Risk Simulation

The UI may include a simple interactive simulation panel as a stretch feature after the core extraction and patient card are complete.

The reviewer can adjust key factors and observe how the transparent rule-based priority score changes.

Example controls:

- HbA1c value
- potassium level
- eGFR value
- oxygen saturation
- blood pressure
- symptom severity
- red flag present or absent
- follow-up completed or not completed
- missing information resolved or unresolved

Example:

```text
Current case:
HbA1c = 9.4%
Medication adherence = uncertain
Follow-up = not scheduled
Rule-based priority = High

Simulated case:
HbA1c = 7.2%
Medication adherence = confirmed
Follow-up = scheduled
Rule-based priority = Medium
```

This helps demonstrate how intervention or missing information can affect the case priority inside the prototype rules.

---

## How The What-If Score Is Estimated

The what-if simulation uses an explainable scoring model rather than a black-box clinical prediction model.

Each risk factor receives a weighted contribution.

Example:

```text
Base risk score = 0

High HbA1c above threshold = +25
Critical potassium = +35
Low oxygen saturation = +30
Chest pain = +35
Missing follow-up plan = +15
Medication safety issue = +20
No red flags = -10
Follow-up completed = -15
```

Risk bands:

```text
0-34   = Low
35-69  = Medium
70-100 = High
```

This is transparent, easy to explain, and appropriate for a POC, but it is not a validated clinical prediction score.

---

## Why This Improves The POC

The causal inference UI makes the prototype stronger because it goes beyond simple summarisation.

It demonstrates:

- explainable AI
- clinical reasoning transparency
- risk factor attribution
- limited what-if simulation
- human-in-the-loop decision support
- operational action planning
- auditability

This directly supports the POC requirement to generate structured, actionable intelligence from clinical documents.

---

## Important Safety Boundary

The causal explainability and what-if simulation layer is not a clinically validated prediction model.

It is an explainable prototype feature that helps users understand how extracted findings influence risk priority and recommended workflow actions.

The system should always be used with human review.

Recommended safety statement:

```text
The causal graph and what-if simulation are designed for explainable workflow support. The simulation shows how this prototype's rule-based priority score changes under selected assumptions; it does not provide autonomous diagnosis, treatment advice, or clinically validated outcome prediction.
```

---

## Planned UI Layout

The Streamlit interface will include a dedicated tab:

```text
Tab 1: Document Input
Tab 2: Patient Intelligence Card
Tab 3: Extracted Clinical Entities
Tab 4: Causal Graph And What-If Simulation
Tab 5: JSON Export And Audit Trace
```

### Causal Graph Tab

The causal graph tab will contain:

- interactive network graph
- risk driver ranking
- current risk score
- optional what-if rule score
- sliders for modifiable factors
- explanation of changed risk
- recommended next action

### Example Graph Flow

```text
Lab Result: Potassium 5.7
        ↓
Risk Driver: Hyperkalaemia
        ↓
Outcome Risk: Urgent safety concern
        ↓
Action: Escalate to renal review
```

### Example Simulation Output

```text
Current rule-based priority: High
Main drivers: high potassium, low eGFR, missing repeat potassium

If repeat potassium normalises and renal follow-up is scheduled:
Rule-based priority changes from High to Medium

Explanation:
The immediate safety concern is reduced because the critical lab abnormality is resolved and a follow-up pathway is in place.
```
