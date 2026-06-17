# Causal Explainability And What-If UI

## Purpose

This UI view explains why the system marked a case as low, medium, or high priority.

The idea is inspired by Judea Pearl's causal framing: a useful explanation should not only say what was found, but also show how a finding may lead to an outcome and what action could change the situation.

For this POC, the causal layer is deliberately simple and transparent. It is not a full causal model and it does not prove medical causality. It is a rule-based explanation layer for clinical and administrative review.

---

## What The User Sees

The user sees a causal graph like this:

```text
Clinical finding
-> clinical meaning
-> risk driver
-> operational priority
-> recommended action
```

Example:

```text
Potassium 5.7 mmol/L
-> raised potassium
-> medication safety concern
-> high priority
-> escalate for renal review
```

This helps the reviewer understand what is making the case more serious.

---

## Graph Design

The graph contains a small number of readable nodes, not a large complex network.

Node types:

- patient factor
- symptom
- diagnosis
- lab result
- medication factor
- red flag
- missing information
- risk driver
- recommended action

Edge types:

- indicates
- contributes to
- increases priority
- requires follow-up
- reduces uncertainty if resolved

The graph is designed to be understandable in a short demo.

---

## Risk Driver Ranking

Next to the graph, the UI ranks the strongest risk drivers.

Example:

```text
Top drivers
1. Potassium 5.7 mmol/L - high severity contribution
2. eGFR 28 mL/min/1.73m2 - reduced renal function
3. Missing repeat potassium result - unresolved safety check
4. Ramipril use - medication review required
```

This makes the output more auditable because the reviewer can see which findings influenced the priority score.

---

## What-If Simulation

The what-if panel is an optional stretch feature.

It lets the reviewer change a few selected inputs and see how the prototype's rule-based priority score changes.

Example:

```text
Current case
HbA1c: 9.4%
Medication adherence: uncertain
Follow-up: not scheduled
Priority: High

What-if case
HbA1c: 7.2%
Medication adherence: confirmed
Follow-up: scheduled
Priority: Medium
```

This is not presented as a medical prediction. It is an explanation of how the rule logic reacts when modifiable factors change.

---

## Scoring Logic

The what-if score uses transparent weights.

Example:

```text
Base score = 0

High HbA1c = +25
Critical potassium = +35
Low oxygen saturation = +30
Chest pain = +35
Missing follow-up plan = +15
Medication safety issue = +20
Follow-up completed = -15
No red flags = -10
```

Risk bands:

```text
0-34   = Low
35-69  = Medium
70-100 = High
```

The weights are prototype rules. They are used for explainability and demonstration, not for real clinical outcome prediction.

---

## UI Layout

The Streamlit app will include this as a separate tab:

```text
Tab 1: Document Input
Tab 2: Patient Intelligence Card
Tab 3: Extracted Entities
Tab 4: Causal Graph And What-If
Tab 5: Export And Audit Trace
```

The causal tab contains:

- interactive causal graph
- ranked risk drivers
- current priority score
- optional what-if controls
- explanation of the changed score
- recommended next action

---

## Safety Statement

The causal graph and what-if simulation are designed for explainable workflow support.

They do not provide autonomous diagnosis, treatment advice, or clinically validated outcome prediction.

All outputs are intended for human review.
