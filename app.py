from __future__ import annotations

import html
import json
import re

import streamlit as st

from src.audit import write_audit_event
from src.causal_ui import causal_journey_html
from src.completeness import information_to_confirm
from src.data_store import patient_journey_options
from src.pipeline import ClinicalPipeline
from src.pdf_report import generate_case_pdf
from src.presentation import medication_safety_detail, medication_status_label
from src.text_processing import extract_uploaded_text, sanitize_display_text


ANALYSIS_VERSION = "2026-06-20-bioclinicalbert-v5"


st.set_page_config(
    page_title="Clinical Document Intelligence Hub",
    page_icon="CD",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    html, body, [class*="css"], .stApp {
        font-family: "Fragment Core Roman", "Fragment Core", Georgia, serif;
        color: #17212B;
    }
    [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
    header[data-testid="stHeader"] {background: transparent;}
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
    .block-container {max-width: 1160px; padding-top: 2.1rem; padding-bottom: 3rem;}
    h1, h2, h3, p, label, button {letter-spacing: 0 !important;}
    h1 {font-size: 2.35rem !important; font-weight: 600 !important; margin-bottom: 0.2rem !important;}
    h2 {font-size: 1.35rem !important; font-weight: 600 !important;}
    h3 {font-size: 1.02rem !important; font-weight: 600 !important;}
    .subtitle {color: #61707C; font-size: 1rem; margin: 0 0 1.6rem;}
    .input-shell {
        background: #FFFFFF;
        border: 1px solid #DCE3E8;
        border-radius: 8px;
        padding: 1.2rem 1.35rem 0.4rem;
        margin-bottom: 1.2rem;
    }
    .section-label {font-size: 0.78rem; color: #6C7882; text-transform: uppercase; margin-bottom: 0.3rem;}
    .patient-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        border-top: 1px solid #DDE4E8;
        border-bottom: 1px solid #DDE4E8;
        margin: 1.7rem 0;
    }
    .patient-item {padding: .85rem 1rem .85rem 0;}
    .patient-item + .patient-item {border-left: 1px solid #DDE4E8; padding-left: 1rem;}
    .patient-key {display: block; color: #74808A; font-size: .74rem; text-transform: uppercase;}
    .patient-value {display: block; font-size: 1.05rem; margin-top: .18rem;}
    .fact-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1px;
        background: #DCE3E8;
        border: 1px solid #DCE3E8;
        margin: 1rem 0 1.8rem;
    }
    .fact-block {background: #FFFFFF; padding: 1rem 1.1rem; min-height: 112px;}
    .fact-title {font-size: .76rem; color: #6D7983; text-transform: uppercase; margin-bottom: .55rem;}
    .fact-block ul {margin: 0; padding-left: 1.1rem;}
    .fact-block li {margin: .25rem 0; line-height: 1.35;}
    .missing-note {
        border: 1px solid #DCE3E8;
        background: #F8FAFB;
        padding: .8rem 1rem;
        margin: 0 0 1.5rem;
    }
    .record-step {
        border-left: 3px solid #668598;
        padding: .25rem 0 .95rem 1rem;
        margin-left: .35rem;
    }
    .record-step strong {font-size: .98rem;}
    .record-meta {color: #6C7882; font-size: .8rem; margin: .15rem 0 .35rem;}
    .evidence-note {
        border: 1px solid #DCE3E8;
        padding: .8rem 1rem;
        background: #F8FAFB;
        margin-bottom: 1rem;
        font-size: .9rem;
    }
    .overall-recommendation {
        border: 1px solid #C9D5DC;
        border-left: 4px solid #486F84;
        background: #F7FAFB;
        padding: 1rem 1.15rem;
        margin: 1rem 0 1.4rem;
    }
    .overall-recommendation h3 {margin: 0 0 .6rem !important;}
    .recommendation-row {margin: .35rem 0; line-height: 1.4;}
    .risk-banner {
        border-left: 5px solid #B73F35;
        background: #FFF4F1;
        padding: 1rem 1.15rem;
        margin: 0 0 1.25rem;
    }
    .risk-banner.medium {border-color: #A87611; background: #FFF9E8;}
    .risk-banner.low {border-color: #36734C; background: #F1F8F3;}
    .risk-title {font-size: 1.05rem; font-weight: 700; margin-bottom: .25rem;}
    .safety-alert {
        border-left: 4px solid #B73F35;
        padding: .7rem 1rem;
        background: #FFF7F4;
        margin: .55rem 0;
    }
    .discrepancy {
        border: 1px solid #D6DEE3;
        padding: .9rem 1rem;
        margin: .65rem 0;
        background: #FFFFFF;
    }
    .discrepancy-title {font-weight: 700; margin-bottom: .35rem;}
    .completeness {
        border: 1px solid #D6DEE3;
        padding: 1rem;
        margin: 1rem 0;
        background: #F8FAFB;
    }
    .table-wrap {overflow-x: auto; margin: .75rem 0 1.2rem;}
    .data-table {width: 100%; border-collapse: collapse; font-size: .86rem;}
    .data-table th {
        text-align: left; padding: .65rem .7rem; background: #F2F5F7;
        border: 1px solid #D8E0E5; white-space: nowrap;
    }
    .data-table td {
        padding: .65rem .7rem; border: 1px solid #D8E0E5;
        vertical-align: top; line-height: 1.35;
    }
    .safety {color: #6C7882; font-size: .82rem; margin-top: 1.6rem;}
    div[data-testid="stRadio"] > label {display: none;}
    div[data-testid="stRadio"] [role="radiogroup"] {gap: .5rem;}
    div[data-testid="stRadio"] [role="radio"] + div {font-size: .94rem;}
    [data-testid="InputInstructions"] {display: none;}
    .stButton button, .stDownloadButton button {border-radius: 4px; min-height: 42px;}
    @media (max-width: 760px) {
        .block-container {padding: 1.2rem .9rem 2rem;}
        h1 {font-size: 1.85rem !important;}
        .patient-strip, .fact-grid {grid-template-columns: 1fr;}
        .patient-item + .patient-item {border-left: 0; border-top: 1px solid #DDE4E8; padding-left: 0;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_pipeline() -> ClinicalPipeline:
    return ClinicalPipeline(require_model=True)


def values(result, label: str, limit: int = 5) -> list[str]:
    grouped = result.grouped_entities()
    unique = list(dict.fromkeys(entity.text for entity in grouped.get(label, [])))
    return unique[:limit]


def list_html(items: list[str], empty: str = "Not identified") -> str:
    if not items:
        return f"<span>{html.escape(empty)}</span>"
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def table_html(rows: list[dict[str, str]], columns: list[str]) -> str:
    if not rows:
        return "<p>No records identified.</p>"
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap"><table class="data-table">'
        f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def entity_confidence_label(entity) -> str:
    explicit_sources = {
        "clinical-pattern",
        "gold-aligned sample",
    }
    if entity.source in explicit_sources and entity.confidence >= 0.85:
        return "High"
    if entity.confidence >= 0.9:
        return "High"
    if entity.confidence >= 0.7:
        return "Medium"
    return "Low"


st.title("Clinical Document Intelligence Hub")
st.markdown(
    '<p class="subtitle">Combine fragmented clinical documents into one decision-ready patient record.</p>',
    unsafe_allow_html=True,
)

documents = []
input_error = None
with st.container(border=True):
    st.markdown('<div class="section-label">Build a patient record</div>', unsafe_allow_html=True)
    input_mode = st.radio(
        "Document source",
        ["Upload documents", "Paste text", "Sample patient records"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if input_mode == "Upload documents":
        uploaded_files = st.file_uploader(
            "Upload one or more PNG images, PDFs, Word, Markdown or text files",
            type=[
                "png", "pdf", "docx", "md", "txt",
            ],
            accept_multiple_files=True,
            help="Images use OCR. Text-based documents are read directly.",
        )
        for index, uploaded in enumerate(uploaded_files or [], start=1):
            try:
                documents.append(
                    {
                        "document_id": f"UPLOAD-{index:02d}",
                        "document_name": uploaded.name,
                        "text": extract_uploaded_text(uploaded),
                        "reference_doc_id": None,
                    }
                )
            except (RuntimeError, ValueError) as exc:
                input_error = f"{uploaded.name}: {exc}"
        if documents:
            st.caption(f"{len(documents)} document{'s' if len(documents) != 1 else ''} ready to analyse.")
    elif input_mode == "Paste text":
        document_text = st.text_area(
            "Clinical document",
            height=230,
            placeholder="Paste a discharge summary, lab report, referral letter or clinical note.",
            label_visibility="collapsed",
        )
        if document_text.strip():
            documents = [
                {
                    "document_id": "PASTE-01",
                    "document_name": "Pasted clinical note",
                    "text": document_text,
                    "reference_doc_id": None,
                }
            ]
    else:
        journeys = patient_journey_options()
        patient_choice = st.selectbox(
            "Choose a patient journey",
            list(journeys),
        )
        journey = journeys[patient_choice]
        labels = {
            f"{row['document_type']} | {row['doc_id']}": row
            for row in journey
        }
        selected_labels = st.multiselect(
            "Select documents to combine",
            list(labels),
            default=list(labels)[:3],
        )
        for label in selected_labels:
            row = labels[label]
            documents.append(
                    {
                        "document_id": row["doc_id"],
                        "document_name": f"{row['document_type']} ({row['doc_id']})",
                        "text": row["clinical_note"],
                        # Samples use the same inference path as uploaded documents.
                        "reference_doc_id": None,
                    }
                )
        st.caption("Synthetic documents for the same patient are ready to combine.")

    if input_error:
        st.error(input_error)

    analyse = st.button(
        "Create patient summary",
        type="primary",
        use_container_width=True,
        disabled=not bool(documents),
    )

if analyse:
    try:
        with st.spinner("Reading the documents, checking identity and consolidating the record..."):
            case = get_pipeline().analyse_many(documents)
            st.session_state["case_analysis"] = case
            st.session_state["analysis_version"] = ANALYSIS_VERSION
            try:
                combined_source = "\n\n".join(str(document["text"]) for document in documents)
                st.session_state["audit_event_id"] = write_audit_event(
                    combined_source,
                    case.consolidated,
                )
            except OSError:
                st.session_state["audit_event_id"] = None
    except (RuntimeError, ValueError) as exc:
        st.error(str(exc))

case = st.session_state.get("case_analysis")
if case and st.session_state.get("analysis_version") != ANALYSIS_VERSION:
    st.session_state.pop("case_analysis", None)
    st.session_state.pop("audit_event_id", None)
    case = None
if case and not all(
    hasattr(case, field)
    for field in (
        "overall_recommendation",
        "medication_records",
        "discrepancies",
        "completeness",
        "safety_warnings",
    )
):
    st.session_state.pop("case_analysis", None)
    case = None
if case and not all(
    hasattr(document, field)
    for document in case.documents
    for field in ("admission_date", "discharge_date")
):
    st.session_state.pop("case_analysis", None)
    st.session_state.pop("audit_event_id", None)
    case = None
if not case:
    st.markdown(
        '<p class="safety">This prototype supports human review. It does not diagnose disease or replace professional clinical judgement.</p>',
        unsafe_allow_html=True,
    )
    st.stop()

result = case.consolidated
patient = result.patient_details
patient_name = html.escape(str(patient.get("name", "Not identified")))
patient_age = html.escape(str(patient.get("age", "Not identified")))
patient_dob = html.escape(str(patient.get("date_of_birth", "Not identified")))
patient_id = html.escape(str(patient.get("patient_id", "Not identified")))
patient_gender = html.escape(str(patient.get("gender", "Not identified")))
document_type = html.escape(result.document_type)

st.markdown(
    f"""
    <div class="patient-strip">
      <div class="patient-item"><span class="patient-key">Patient</span><span class="patient-value">{patient_name}</span></div>
      <div class="patient-item"><span class="patient-key">Age</span><span class="patient-value">{patient_age}</span></div>
      <div class="patient-item"><span class="patient-key">Date of birth</span><span class="patient-value">{patient_dob}</span></div>
      <div class="patient-item"><span class="patient-key">Patient ID</span><span class="patient-value">{patient_id}</span></div>
      <div class="patient-item"><span class="patient-key">Gender</span><span class="patient-value">{patient_gender}</span></div>
      <div class="patient-item"><span class="patient-key">Document</span><span class="patient-value">{document_type}</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

overall = case.overall_recommendation
risk_class = overall.priority.lower()
risk_message = {
    "High": (
        "Immediate action required"
        if "immediate" in overall.timeframe.casefold()
        else "Urgent review required"
    ),
    "Medium": "Follow-up action required",
    "Low": "Routine review",
}.get(overall.priority, "Human review required")
st.markdown(
    f"""
    <div class="risk-banner {html.escape(risk_class)}">
      <div class="risk-title">{html.escape(overall.priority.upper())} PRIORITY · {html.escape(risk_message)}</div>
      <div><b>Reason:</b> {html.escape(overall.rationale)}</div>
      <div><b>Act first:</b> {html.escape(overall.immediate_next_step)} · {html.escape(overall.timeframe)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

immediate_links = [
    link
    for link in result.causal_links
    if "immediate" in link.follow_up_window.casefold()
]
priority_basis = (
    "Time-critical evidence identified"
    if overall.priority == "High" and immediate_links
    else (
        f"The operational review index reached the {overall.priority.lower()} threshold"
        if result.causal_links
        else "No specific escalation pathway was identified"
    )
)
with st.expander("Why this priority", expanded=True):
    st.write(
        f"**{overall.priority} priority** · operational review index **{result.risk_score}/100** · "
        f"{priority_basis}."
    )
    if result.causal_links:
        priority_rows = [
            {
                "Observed evidence": link.finding,
                "Interpretation": link.meaning,
                "Contribution": str(link.weight),
                "Response window": link.follow_up_window,
                "Source": ", ".join(link.source_documents) or "Current record",
            }
            for link in result.causal_links
        ]
        st.markdown(
            table_html(
                priority_rows,
                [
                    "Observed evidence",
                    "Interpretation",
                    "Contribution",
                    "Response window",
                    "Source",
                ],
            ),
            unsafe_allow_html=True,
        )
    st.caption(
        "This evidence-based index supports workflow prioritisation. It is not a calibrated probability of clinical deterioration."
    )

conditions = values(result, "DIAGNOSIS")
clinical_status = values(result, "CLINICAL_STATUS")
symptoms = values(result, "SYMPTOM")
medications = values(result, "MEDICATION")
results = values(result, "LAB_RESULT")
allergies = values(result, "ALLERGY")
adverse_reactions = values(result, "ADVERSE_REACTION")
social_history = values(result, "SOCIAL_HISTORY")
family_history = values(result, "FAMILY_HISTORY")
follow_up_items = values(result, "FOLLOW_UP")
encounter_dates = list(
    dict.fromkeys(
        date_value
        for document in case.documents
        for date_value in (
            (
                f"Admitted: {document.admission_date}"
                if getattr(document, "admission_date", None)
                else None
            ),
            (
                f"Discharged: {document.discharge_date}"
                if getattr(document, "discharge_date", None)
                else None
            ),
        )
        if date_value
    )
)
document_dates = list(
    dict.fromkeys(
        f"{document.document_name}: {document.document_date}"
        for document in case.documents
        if document.document_date
    )
)
relevant_context = [
    *document_dates,
    *encounter_dates,
    *social_history,
    *family_history,
]
current_medications = list(
    dict.fromkeys(
        record.medication
        for record in case.medication_records
        if record.phase in {"At discharge", "Post-discharge review", "Current / documented"}
        and record.status not in {
            "Stopped",
            "Withheld",
            "Taken in error",
            "Previously used",
        }
    )
)
if not current_medications:
    current_medications = medications

summary_tab, action_tab, timeline_tab, reasoning_tab = st.tabs(
    ["Patient summary", "Action queue", "Record timeline", "Reasoning trace"]
)

with summary_tab:
    st.subheader("What the combined record says")
    st.write(sanitize_display_text(result.summary))

    st.markdown(
        f"""
        <div class="overall-recommendation">
          <h3>Overall recommendation</h3>
          <div class="recommendation-row"><b>{html.escape(overall.headline)}</b> · {html.escape(overall.timeframe)}</div>
          <div class="recommendation-row"><b>Act first:</b> {html.escape(overall.immediate_next_step)}</div>
          <div class="recommendation-row"><b>Coordinate:</b> {html.escape(overall.coordination_plan)}</div>
          <div class="recommendation-row"><b>Why:</b> {html.escape(overall.rationale)}</div>
          <div class="recommendation-row"><b>Evidence from:</b> {html.escape(", ".join(overall.source_documents))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
          <div class="fact-grid">
          <div class="fact-block"><div class="fact-title">Current conditions and assessment</div>{list_html([*conditions, *clinical_status], "No active condition or assessment extracted")}</div>
          <div class="fact-block"><div class="fact-title">Current / discharge medications</div>{list_html(current_medications)}</div>
          <div class="fact-block"><div class="fact-title">Symptoms and clinical signs</div>{list_html(symptoms)}</div>
          <div class="fact-block"><div class="fact-title">Important test results</div>{list_html(results)}</div>
          <div class="fact-block"><div class="fact-title">Confirmed allergies</div>{list_html(allergies, "No allergy information documented")}</div>
          <div class="fact-block"><div class="fact-title">Adverse reactions and intolerances</div>{list_html(adverse_reactions, "No adverse reaction documented")}</div>
          <div class="fact-block"><div class="fact-title">Safety warnings</div>{list_html(case.safety_warnings, "No urgent safety warning identified")}</div>
          <div class="fact-block"><div class="fact-title">Relevant history and dates</div>{list_html(relevant_context, "No dated history documented")}</div>
          <div class="fact-block"><div class="fact-title">Discharge and follow-up plan</div>{list_html(follow_up_items, "No follow-up plan documented")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Medication reconciliation")
    medication_rows = [
        {
            "Medication": record.medication,
            "Medication journey": " → ".join(
                f"{item['stage']}: {item['status']}"
                for item in record.history
            ) or f"{record.phase}: {record.status}",
            "Current status": record.status,
            "Confidence": record.confidence,
            "Source": record.source_document,
        }
        for record in case.medication_records
    ]
    if medication_rows:
        st.markdown(
            table_html(
                medication_rows,
                [
                    "Medication",
                    "Medication journey",
                    "Current status",
                    "Confidence",
                    "Source",
                ],
            ),
            unsafe_allow_html=True,
        )
    else:
        st.caption("No medication record was extracted.")

    safety_alerts: dict[str, tuple[str, str]] = {}
    for item in case.discrepancies:
        if item.category == "Medication safety issue":
            key = (
                "ace-entresto"
                if re.search(r"\bramipril|entresto|sacubitril", item.field, re.I)
                else item.field.casefold()
            )
            safety_alerts[key] = (item.field, item.action_required)
    for record in case.medication_records:
        medication_key = (
            "ace-entresto"
            if re.search(r"\bramipril|entresto|sacubitril", record.medication, re.I)
            else re.sub(r"\W+", "-", record.medication.casefold()).strip("-")
        )
        if medication_key in safety_alerts:
            continue
        if record.status in {"Stopped", "Withheld", "Taken in error"}:
            safety_alerts[medication_key] = (
                f"{record.medication} · {medication_status_label(record.status)}",
                medication_safety_detail(record),
            )
        elif record.status == "New" and re.search(
            r"\bentresto|sacubitril", record.medication, re.I
        ):
            safety_alerts[medication_key] = (
                f"{record.medication} · New",
                medication_safety_detail(record),
            )
    if safety_alerts:
        st.subheader("Medication safety alerts")
        for title, detail in safety_alerts.values():
            st.markdown(
                f'<div class="safety-alert"><b>{html.escape(title)}</b><br/>{html.escape(detail)}</div>',
                unsafe_allow_html=True,
            )

    review_heading = (
        "Cross-document review"
        if len(case.documents) > 1
        else "Clinical trend and record review"
    )
    st.subheader(review_heading)
    if case.discrepancies:
        for discrepancy in case.discrepancies:
            st.markdown(
                f"""
                <div class="discrepancy">
                  <div class="discrepancy-title">{html.escape(discrepancy.category)} · {html.escape(discrepancy.field)} · {html.escape(discrepancy.clinical_risk)} risk</div>
                  <div><b>{html.escape(discrepancy.document_a)}:</b> {html.escape(discrepancy.value_a)}</div>
                  <div><b>{html.escape(discrepancy.document_b)}:</b> {html.escape(discrepancy.value_b)}</div>
                  <div><b>Action:</b> {html.escape(discrepancy.action_required)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("No material cross-document conflict or clinical change was detected.")

    completeness = case.completeness
    incomplete_details = information_to_confirm(
        result.missing_information,
        completeness.missing_fields,
    )
    st.markdown(
        f"""
        <div class="completeness">
          <b>Record completeness: {completeness.score}/{completeness.total} areas complete</b><br/>
          <span>Incomplete areas: {html.escape(", ".join(completeness.missing_fields) or "None identified")}</span><br/>
          <span>Specific items to confirm: {html.escape(", ".join(incomplete_details) or "None identified")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Information to confirm")
    reviewed_items: set[str] = set()
    if incomplete_details:
        completed_items = 0
        for index, item in enumerate(incomplete_details):
            confirmed = st.checkbox(
                item,
                key=f"missing-{case.case_id}-{index}",
            )
            completed_items += int(confirmed)
            if confirmed:
                reviewed_items.add(item.casefold())
        st.caption(f"{completed_items}/{len(incomplete_details)} reviewed")
        st.caption(
            "Checking an item records that it has been reviewed. It does not alter source-document completeness or imply that the information was clinically resolved."
        )
    else:
        st.caption("No unresolved information item was identified.")

    document_names = {
        document.document_id: document.document_name for document in case.documents
    }
    with st.expander("Extraction confidence and evidence"):
        evidence_rows = [
            {
                "Field": entity.label.replace("_", " ").title(),
                "Value": entity.text,
                "Confidence": entity_confidence_label(entity),
                "Source text": entity.text,
                "Document": document_names.get(entity.document_id, "Combined record"),
            }
            for entity in result.entities
        ]
        st.markdown(
            table_html(
                evidence_rows,
                ["Field", "Value", "Confidence", "Source text", "Document"],
            ),
            unsafe_allow_html=True,
        )

with action_tab:
    st.subheader("Decision-ready action queue")
    st.caption("Each item shows who should receive it, when it is due, why it was raised and which document supports it.")
    action_rows = [
        {
            "Priority": item.priority,
            "Action": item.action,
            "Route to": item.route_to,
            "Due": item.due_by,
            "Reason": item.reason,
            "Source": ", ".join(item.source_documents),
            "Status": (
                "Reviewed - confirmation still required"
                if item.evidence_basis == "Completeness check"
                and item.action.removeprefix("Confirm ").casefold() in reviewed_items
                else item.status
            ),
        }
        for item in case.action_items
    ]
    st.markdown(
        table_html(
            action_rows,
            ["Priority", "Action", "Route to", "Due", "Reason", "Source", "Status"],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="evidence-note"><strong>Human review required:</strong> These workflow recommendations are not treatment orders.</div>',
        unsafe_allow_html=True,
    )

with timeline_tab:
    st.subheader("Consolidated record timeline")
    st.caption("The sequence follows the supplied record order unless a reliable document date is available.")
    for event in case.record_timeline:
        findings = ", ".join(event["key_findings"]) or "No key finding extracted"
        conditions_text = ", ".join(event["conditions"]) or "No condition extracted"
        timeline_date = event.get("document_date") or "Date not identified"
        st.markdown(
            f"""
            <div class="record-step">
              <strong>{event['sequence']}. {html.escape(str(event['document_name']))}</strong>
              <div class="record-meta">{html.escape(str(timeline_date))} · {html.escape(str(event['document_type']))} · {html.escape(str(event['priority']))} priority</div>
              <div><b>Conditions:</b> {html.escape(conditions_text)}</div>
              <div><b>Key evidence:</b> {html.escape(findings)}</div>
              <div><b>Next action:</b> {html.escape(str(event['next_action']))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with reasoning_tab:
    st.metric("Evidence rules matched", len(result.causal_links))
    st.caption("Reasoning: transparent clinical rules with source evidence")
    st.subheader("Evidence and action map")
    st.caption("Choose a detected concern to redraw the graph from this patient's evidence and required next step.")

    selected_link = None
    if result.causal_links:
        pathway_labels = {
            f"{link.meaning} · {', '.join(link.source_documents) or 'Current record'}": link
            for link in result.causal_links
        }
        selected_pathway = st.selectbox(
            "Choose a health concern",
            list(pathway_labels),
        )
        selected_link = pathway_labels[selected_pathway]

    st.iframe(
        causal_journey_html(result, selected_link),
        height=590,
        width="stretch",
        tab_index=0,
    )

    if result.causal_links:
        sources = ", ".join(selected_link.source_documents) or "Current record"
        st.markdown("**Selected evidence trace**")
        st.write(
            f"- **{selected_link.meaning}** — {selected_link.implication}. "
            f"Basis: {selected_link.evidence_basis}. Source: {sources}. "
            f"Proposed next step: {selected_link.action}"
        )
        if selected_link.display_intervention:
            st.write(f"Intervention explanation: {selected_link.display_intervention}")

    with st.expander("How to interpret this map"):
        st.write(
            "The map connects documented evidence to a transparent workflow rule and proposed action. "
            "It explains the prototype's decision path; it does not predict a patient outcome or prove medical causation."
        )

payload = case.to_dict()
st.subheader("Download structured summary")
download_json, download_pdf = st.columns(2)
with download_json:
    st.download_button(
        "Download JSON",
        data=json.dumps(payload, indent=2),
        file_name="clinical_consolidated_case.json",
        mime="application/json",
        use_container_width=True,
    )
with download_pdf:
    st.download_button(
        "Download PDF",
        data=generate_case_pdf(case),
        file_name="clinical_consolidated_case.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

if st.session_state.get("audit_event_id"):
    st.caption(f"Audit reference: {st.session_state['audit_event_id']}")

st.markdown(
    '<p class="safety">For demonstration only. All findings and future concerns require review by an appropriately qualified professional.</p>',
    unsafe_allow_html=True,
)
