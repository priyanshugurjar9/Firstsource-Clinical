import csv
import json
from pathlib import Path


OUTPUT_DIR = Path("data")
DOCUMENT_CSV = OUTPUT_DIR / "clinical_poc_synthetic_dataset.csv"
ENTITY_CSV = OUTPUT_DIR / "clinical_poc_entity_annotations.csv"


PATIENTS = [
    ("Eleanor Grant", 74, "Female"),
    ("Michael Turner", 62, "Male"),
    ("Aisha Khan", 48, "Female"),
    ("Daniel Hughes", 55, "Male"),
    ("Priya Nair", 39, "Female"),
    ("George Williams", 81, "Male"),
    ("Sofia Martinez", 67, "Female"),
    ("Thomas Reid", 59, "Male"),
    ("Mei Chen", 52, "Female"),
    ("Samuel Brooks", 70, "Male"),
    ("Nadia Ali", 45, "Female"),
    ("Robert Evans", 76, "Male"),
]


SCENARIOS = [
    {
        "document_type": "Discharge Summary",
        "diagnosis": "Type 2 diabetes mellitus",
        "symptoms": ["fatigue", "polyuria", "blurred vision"],
        "medications": ["Metformin 1000 mg twice daily", "Insulin glargine 18 units nightly"],
        "allergies": ["No known drug allergies"],
        "labs": ["HbA1c 9.4%", "fasting glucose 198 mg/dL"],
        "red_flags": ["HbA1c above target", "persistent hyperglycaemia"],
        "risk_level": "High",
        "recommended_action": "Route to diabetes nurse specialist and schedule endocrinology follow-up within 7 days.",
        "causal_reasoning": "High HbA1c and persistent hyperglycaemia indicate poor glycaemic control, increasing risk of complications and requiring urgent follow-up.",
        "missing_information": ["home glucose monitoring plan"],
        "confidence": 0.94,
    },
    {
        "document_type": "Emergency Department Note",
        "diagnosis": "Possible acute coronary syndrome",
        "symptoms": ["central chest pain", "shortness of breath", "diaphoresis"],
        "medications": ["Aspirin 300 mg given", "Nitroglycerin spray as needed"],
        "allergies": ["Penicillin allergy"],
        "labs": ["Troponin pending", "ECG shows ST depression in lateral leads"],
        "red_flags": ["chest pain", "ECG abnormality", "troponin pending"],
        "risk_level": "High",
        "recommended_action": "Escalate for urgent clinician review and cardiac pathway assessment.",
        "causal_reasoning": "Chest pain with ECG abnormality can indicate acute cardiac risk; pending troponin increases uncertainty and supports urgent review.",
        "missing_information": ["repeat troponin result"],
        "confidence": 0.96,
    },
    {
        "document_type": "Referral Letter",
        "diagnosis": "Chronic obstructive pulmonary disease",
        "symptoms": ["worsening breathlessness", "productive cough", "reduced exercise tolerance"],
        "medications": ["Salbutamol inhaler", "Tiotropium inhaler"],
        "allergies": ["No known drug allergies"],
        "labs": ["Oxygen saturation 91% on room air", "Chest X-ray requested"],
        "red_flags": ["oxygen saturation below expected baseline", "worsening breathlessness"],
        "risk_level": "High",
        "recommended_action": "Route to respiratory team and arrange urgent assessment within 48 hours.",
        "causal_reasoning": "Reduced oxygen saturation plus worsening breathlessness suggests possible COPD exacerbation requiring prompt respiratory review.",
        "missing_information": ["smoking status", "recent spirometry"],
        "confidence": 0.91,
    },
    {
        "document_type": "Lab Report",
        "diagnosis": "Chronic kidney disease",
        "symptoms": ["ankle swelling", "fatigue"],
        "medications": ["Ramipril 5 mg daily", "Furosemide 40 mg daily"],
        "allergies": ["Ibuprofen intolerance"],
        "labs": ["eGFR 28 mL/min/1.73m2", "Creatinine 215 umol/L", "Potassium 5.7 mmol/L"],
        "red_flags": ["hyperkalaemia", "low eGFR"],
        "risk_level": "High",
        "recommended_action": "Escalate abnormal potassium result and route to renal review.",
        "causal_reasoning": "Raised potassium with reduced kidney function can create immediate safety risk and requires urgent clinical follow-up.",
        "missing_information": ["repeat potassium confirmation"],
        "confidence": 0.95,
    },
    {
        "document_type": "Intake Form",
        "diagnosis": "Hypertension",
        "symptoms": ["headache", "occasional dizziness"],
        "medications": ["Amlodipine 10 mg daily"],
        "allergies": ["No known drug allergies"],
        "labs": ["Blood pressure 168/96 mmHg", "BMI 31"],
        "red_flags": ["blood pressure above target"],
        "risk_level": "Medium",
        "recommended_action": "Route to primary care hypertension review and request home blood pressure readings.",
        "causal_reasoning": "Elevated blood pressure increases cardiovascular risk, but absence of acute symptoms supports routine expedited follow-up.",
        "missing_information": ["home blood pressure log"],
        "confidence": 0.9,
    },
    {
        "document_type": "Medication Review",
        "diagnosis": "Atrial fibrillation",
        "symptoms": ["palpitations", "mild dizziness"],
        "medications": ["Apixaban 5 mg twice daily", "Bisoprolol 2.5 mg daily"],
        "allergies": ["Sulfa allergy"],
        "labs": ["Heart rate 104 bpm", "INR not applicable"],
        "red_flags": ["tachycardia", "anticoagulant therapy"],
        "risk_level": "Medium",
        "recommended_action": "Confirm anticoagulant adherence and route to cardiology medication review.",
        "causal_reasoning": "Atrial fibrillation with tachycardia and anticoagulant use requires medication safety review and adherence confirmation.",
        "missing_information": ["renal dosing review"],
        "confidence": 0.89,
    },
    {
        "document_type": "Physician Progress Note",
        "diagnosis": "Community-acquired pneumonia",
        "symptoms": ["fever", "productive cough", "pleuritic chest pain"],
        "medications": ["Amoxicillin 500 mg three times daily", "Paracetamol as needed"],
        "allergies": ["No known drug allergies"],
        "labs": ["CRP 86 mg/L", "Temperature 38.6 C", "Chest X-ray right lower lobe infiltrate"],
        "red_flags": ["fever", "raised inflammatory marker", "radiographic infiltrate"],
        "risk_level": "Medium",
        "recommended_action": "Route to clinician for antibiotic response review within 48-72 hours.",
        "causal_reasoning": "Fever, raised CRP and X-ray infiltrate support active infection requiring treatment monitoring.",
        "missing_information": ["CURB-65 score"],
        "confidence": 0.93,
    },
    {
        "document_type": "Discharge Summary",
        "diagnosis": "Heart failure",
        "symptoms": ["shortness of breath", "orthopnoea", "leg swelling"],
        "medications": ["Furosemide 40 mg daily", "Ramipril 2.5 mg daily", "Bisoprolol 1.25 mg daily"],
        "allergies": ["No known drug allergies"],
        "labs": ["BNP 920 pg/mL", "Chest X-ray pulmonary congestion"],
        "red_flags": ["fluid overload", "high BNP"],
        "risk_level": "High",
        "recommended_action": "Route to heart failure nurse and arrange early post-discharge follow-up.",
        "causal_reasoning": "Fluid overload symptoms plus high BNP indicate unstable heart failure and higher readmission risk.",
        "missing_information": ["daily weight monitoring advice"],
        "confidence": 0.94,
    },
    {
        "document_type": "Referral Letter",
        "diagnosis": "Iron deficiency anaemia",
        "symptoms": ["fatigue", "pallor", "reduced exercise tolerance"],
        "medications": ["Ferrous sulfate 200 mg daily"],
        "allergies": ["No known drug allergies"],
        "labs": ["Haemoglobin 8.9 g/dL", "Ferritin 8 ng/mL"],
        "red_flags": ["low haemoglobin", "possible occult blood loss"],
        "risk_level": "Medium",
        "recommended_action": "Route to gastroenterology referral pathway and request repeat full blood count.",
        "causal_reasoning": "Low haemoglobin with low ferritin suggests iron deficiency; investigation is needed to identify source and prevent deterioration.",
        "missing_information": ["stool blood test result"],
        "confidence": 0.92,
    },
    {
        "document_type": "Lab Report",
        "diagnosis": "Hypothyroidism",
        "symptoms": ["tiredness", "weight gain", "cold intolerance"],
        "medications": ["Levothyroxine 50 micrograms daily"],
        "allergies": ["No known drug allergies"],
        "labs": ["TSH 12.8 mIU/L", "Free T4 8 pmol/L"],
        "red_flags": ["abnormal thyroid function"],
        "risk_level": "Low",
        "recommended_action": "Route to routine primary care medication titration review.",
        "causal_reasoning": "Raised TSH with low free T4 supports under-treated hypothyroidism; routine medication adjustment is appropriate if clinically stable.",
        "missing_information": ["medication adherence history"],
        "confidence": 0.9,
    },
    {
        "document_type": "Intake Form",
        "diagnosis": "Migraine",
        "symptoms": ["unilateral headache", "nausea", "photophobia"],
        "medications": ["Sumatriptan 50 mg as needed", "Ibuprofen 400 mg as needed"],
        "allergies": ["No known drug allergies"],
        "labs": ["Neurological exam documented as normal"],
        "red_flags": [],
        "risk_level": "Low",
        "recommended_action": "Provide routine neurology advice and log as non-urgent follow-up.",
        "causal_reasoning": "Typical migraine features with normal neurological exam and no red flags support low urgency management.",
        "missing_information": ["headache frequency diary"],
        "confidence": 0.88,
    },
    {
        "document_type": "Physician Progress Note",
        "diagnosis": "Urinary tract infection",
        "symptoms": ["dysuria", "urinary frequency", "suprapubic discomfort"],
        "medications": ["Nitrofurantoin 100 mg twice daily"],
        "allergies": ["Trimethoprim allergy"],
        "labs": ["Urine dip positive nitrites", "Temperature 37.4 C"],
        "red_flags": [],
        "risk_level": "Low",
        "recommended_action": "Route to routine antimicrobial follow-up and safety-net advice.",
        "causal_reasoning": "Localized urinary symptoms with positive urine dip and no systemic features suggest low-risk infection suitable for routine follow-up.",
        "missing_information": ["urine culture result"],
        "confidence": 0.91,
    },
]


TEMPLATES = [
    (
        "Patient: {name}, {age}-year-old {gender}. Document type: {document_type}. "
        "Presenting concerns include {symptoms}. Known condition or working diagnosis: {diagnosis}. "
        "Current medication list: {medications}. Allergy status: {allergies}. "
        "Relevant results: {labs}. Plan notes mention follow-up and review requirements. "
        "Items requiring attention: {red_flags}. Missing or unclear information: {missing_information}."
    ),
    (
        "{document_type}\n"
        "Name: {name}\nAge: {age}\nSex: {gender}\n"
        "Clinical impression: {diagnosis}.\n"
        "History: The patient reports {symptoms}. Medication history includes {medications}. "
        "Allergies: {allergies}. Investigations/results: {labs}. "
        "Assessment flags: {red_flags}. Documentation gaps: {missing_information}."
    ),
    (
        "Clinical note for {name} ({age}, {gender}). The record is a {document_type}. "
        "The main clinical issue is {diagnosis}. Symptoms documented: {symptoms}. "
        "Medicines documented: {medications}. Allergies documented: {allergies}. "
        "Objective findings and labs: {labs}. Safety concerns: {red_flags}. "
        "Follow-up gap: {missing_information}."
    ),
]


def join_items(items):
    return "; ".join(items) if items else "none documented"


def confidence_map(base):
    return {
        "patient_details": round(min(base + 0.02, 0.99), 2),
        "diagnosis": round(base, 2),
        "symptoms": round(base - 0.02, 2),
        "medications": round(base - 0.01, 2),
        "allergies": round(base - 0.03, 2),
        "lab_results": round(base - 0.02, 2),
        "red_flags": round(base - 0.04, 2),
        "recommended_action": round(base - 0.05, 2),
    }


def make_summary(patient, scenario):
    name, age, gender = patient
    return (
        f"{name} is a {age}-year-old {gender.lower()} with {scenario['diagnosis']}. "
        f"Key findings include {join_items(scenario['symptoms'])} and {join_items(scenario['labs'])}. "
        f"The recommended operational action is: {scenario['recommended_action']}"
    )


def make_rows():
    rows = []
    entity_rows = []
    doc_id = 1
    for scenario_index, scenario in enumerate(SCENARIOS):
        for patient_index, patient in enumerate(PATIENTS):
            name, age, gender = patient
            template = TEMPLATES[(scenario_index + patient_index) % len(TEMPLATES)]
            clinical_note = template.format(
                name=name,
                age=age,
                gender=gender,
                document_type=scenario["document_type"],
                diagnosis=scenario["diagnosis"],
                symptoms=join_items(scenario["symptoms"]),
                medications=join_items(scenario["medications"]),
                allergies=join_items(scenario["allergies"]),
                labs=join_items(scenario["labs"]),
                red_flags=join_items(scenario["red_flags"]),
                missing_information=join_items(scenario["missing_information"]),
            )

            structured_output = {
                "patient_details": {
                    "name": name,
                    "age": age,
                    "gender": gender,
                    "document_type": scenario["document_type"],
                },
                "clinical_summary": make_summary(patient, scenario),
                "diagnoses": [scenario["diagnosis"]],
                "symptoms": scenario["symptoms"],
                "medications": scenario["medications"],
                "allergies": scenario["allergies"],
                "lab_results": scenario["labs"],
                "red_flags": scenario["red_flags"],
                "missing_information": scenario["missing_information"],
                "risk_level": scenario["risk_level"],
                "recommended_next_action": scenario["recommended_action"],
                "causal_reasoning": scenario["causal_reasoning"],
                "confidence_scores": confidence_map(scenario["confidence"]),
            }

            rows.append(
                {
                    "doc_id": f"CLIN-{doc_id:04d}",
                    "document_type": scenario["document_type"],
                    "patient_name": name,
                    "age": age,
                    "gender": gender,
                    "clinical_note": clinical_note,
                    "gold_diagnoses": json.dumps([scenario["diagnosis"]]),
                    "gold_symptoms": json.dumps(scenario["symptoms"]),
                    "gold_medications": json.dumps(scenario["medications"]),
                    "gold_allergies": json.dumps(scenario["allergies"]),
                    "gold_lab_results": json.dumps(scenario["labs"]),
                    "gold_red_flags": json.dumps(scenario["red_flags"]),
                    "gold_missing_information": json.dumps(scenario["missing_information"]),
                    "gold_risk_level": scenario["risk_level"],
                    "gold_recommended_action": scenario["recommended_action"],
                    "gold_causal_reasoning": scenario["causal_reasoning"],
                    "gold_structured_output_json": json.dumps(structured_output),
                    "split": "test" if patient_index in (10, 11) else "validation" if patient_index in (8, 9) else "train",
                }
            )

            for label, values in [
                ("DIAGNOSIS", [scenario["diagnosis"]]),
                ("SYMPTOM", scenario["symptoms"]),
                ("MEDICATION", scenario["medications"]),
                ("ALLERGY", scenario["allergies"]),
                ("LAB_RESULT", scenario["labs"]),
                ("RED_FLAG", scenario["red_flags"]),
            ]:
                for value in values:
                    start = clinical_note.find(value)
                    end = start + len(value) if start >= 0 else -1
                    entity_rows.append(
                        {
                            "doc_id": f"CLIN-{doc_id:04d}",
                            "entity_text": value,
                            "entity_label": label,
                            "start_char": start,
                            "end_char": end,
                        }
                    )
            doc_id += 1
    return rows, entity_rows


def write_csv(path, rows):
    if not rows:
        raise ValueError("No rows generated")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    rows, entity_rows = make_rows()
    write_csv(DOCUMENT_CSV, rows)
    write_csv(ENTITY_CSV, entity_rows)
    print(f"Wrote {len(rows)} documents to {DOCUMENT_CSV}")
    print(f"Wrote {len(entity_rows)} entity annotations to {ENTITY_CSV}")


if __name__ == "__main__":
    main()
