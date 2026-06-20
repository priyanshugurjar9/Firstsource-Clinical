from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import CaseAnalysis


INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#61707C")
BORDER = colors.HexColor("#D8E0E5")
SOFT = colors.HexColor("#F3F6F8")
HIGH = colors.HexColor("#B73F35")
MEDIUM = colors.HexColor("#A87611")
LOW = colors.HexColor("#36734C")


def _text(value: object) -> str:
    return escape(str(value or "Not identified"))


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            textColor=INK,
            spaceAfter=5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=INK,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyCompact",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=INK,
            spaceAfter=1.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9.5,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Footer",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=MUTED,
        )
    )
    return styles


def _table(rows, widths, style, repeat_rows=1):
    table = Table(rows, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), INK),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        18 * mm,
        8 * mm,
        "Demonstration only - findings require review by a qualified professional.",
    )
    canvas.drawRightString(192 * mm, 8 * mm, f"Page {document.page}")
    canvas.restoreState()


def generate_case_pdf(case: CaseAnalysis) -> bytes:
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title="Clinical Document Intelligence Report",
        author="Clinical Document Intelligence Hub",
    )
    story = []
    result = case.consolidated
    patient = result.patient_details
    recommendation = case.overall_recommendation

    story.append(Paragraph("Clinical Document Intelligence Report", styles["ReportTitle"]))
    patient_rows = [
        [
            Paragraph("<b>Patient</b>", styles["Small"]),
            Paragraph(_text(patient.get("name")), styles["Small"]),
            Paragraph("<b>Age</b>", styles["Small"]),
            Paragraph(_text(patient.get("age")), styles["Small"]),
        ],
        [
            Paragraph("<b>Date of birth</b>", styles["Small"]),
            Paragraph(_text(patient.get("date_of_birth")), styles["Small"]),
            Paragraph("<b>Patient ID</b>", styles["Small"]),
            Paragraph(_text(patient.get("patient_id")), styles["Small"]),
        ],
        [
            Paragraph("<b>Gender</b>", styles["Small"]),
            Paragraph(_text(patient.get("gender")), styles["Small"]),
            Paragraph("<b>Case ID</b>", styles["Small"]),
            Paragraph(_text(case.case_id), styles["Small"]),
        ],
        [
            Paragraph("<b>Sources</b>", styles["Small"]),
            Paragraph(str(len(case.documents)), styles["Small"]),
            Paragraph("", styles["Small"]),
            Paragraph("", styles["Small"]),
        ],
    ]
    story.append(_table(patient_rows, [24 * mm, 61 * mm, 19 * mm, 70 * mm], styles, 0))
    story.append(Spacer(1, 4 * mm))

    risk_color = {"High": HIGH, "Medium": MEDIUM, "Low": LOW}.get(
        recommendation.priority, MUTED
    )
    risk_table = Table(
        [
            [
                Paragraph(
                    f"<b>{_text(recommendation.priority.upper())} PRIORITY</b><br/>"
                    f"{_text(recommendation.rationale)}<br/>"
                    f"<b>Act first:</b> {_text(recommendation.immediate_next_step)} "
                    f"({_text(recommendation.timeframe)})",
                    styles["BodyCompact"],
                )
            ]
        ],
        colWidths=[174 * mm],
    )
    risk_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF6F3")),
                ("BOX", (0, 0), (-1, -1), 1.2, risk_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(risk_table)

    story.append(Paragraph("Combined Summary", styles["Section"]))
    story.append(Paragraph(_text(result.summary), styles["BodyCompact"]))
    story.append(
        Paragraph(
            "<b>Reasoning mode:</b> Transparent clinical rules with source evidence",
            styles["BodyCompact"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Overall recommendation:</b> {_text(recommendation.headline)}. "
            f"{_text(recommendation.coordination_plan)}",
            styles["BodyCompact"],
        )
    )

    grouped = result.grouped_entities()
    overview_rows = [[
        Paragraph("<b>Field</b>", styles["Small"]),
        Paragraph("<b>Extracted information</b>", styles["Small"]),
    ]]
    overview_fields = [
        ("Current conditions", "DIAGNOSIS"),
        ("Clinical assessment", "CLINICAL_STATUS"),
        ("Symptoms and signs", "SYMPTOM"),
        ("Important results", "LAB_RESULT"),
        ("Confirmed allergies", "ALLERGY"),
        ("Adverse reactions", "ADVERSE_REACTION"),
    ]
    for label, entity_label in overview_fields:
        values = list(dict.fromkeys(entity.text for entity in grouped.get(entity_label, [])))
        overview_rows.append(
            [
                Paragraph(_text(label), styles["Small"]),
                Paragraph(_text("; ".join(values) or "Not identified"), styles["Small"]),
            ]
        )
    story.append(_table(overview_rows, [39 * mm, 135 * mm], styles))
    story.append(
        Paragraph(
            f"<b>Safety warnings:</b> "
            f"{_text('; '.join(case.safety_warnings) or 'No urgent safety warning identified')}",
            styles["BodyCompact"],
        )
    )

    story.append(Paragraph("Medication Reconciliation", styles["Section"]))
    medication_rows = [[
        Paragraph("<b>Medication</b>", styles["Small"]),
        Paragraph("<b>Journey</b>", styles["Small"]),
        Paragraph("<b>Current</b>", styles["Small"]),
        Paragraph("<b>Confidence</b>", styles["Small"]),
        Paragraph("<b>Source</b>", styles["Small"]),
    ]]
    for record in case.medication_records:
        journey = " -> ".join(
            f"{item['stage']}: {item['status']}"
            for item in record.history
        ) or f"{record.phase}: {record.status}"
        medication_rows.append(
            [
                Paragraph(_text(record.medication), styles["Small"]),
                Paragraph(_text(journey), styles["Small"]),
                Paragraph(_text(record.status), styles["Small"]),
                Paragraph(_text(record.confidence), styles["Small"]),
                Paragraph(_text(record.source_document), styles["Small"]),
            ]
        )
    story.append(
        _table(
            medication_rows,
            [39 * mm, 57 * mm, 22 * mm, 18 * mm, 38 * mm],
            styles,
        )
    )

    review_title = (
        "Cross-Document Review"
        if len(case.documents) > 1
        else "Clinical Trend and Record Review"
    )
    story.append(Paragraph(review_title, styles["Section"]))
    if case.discrepancies:
        for item in case.discrepancies:
            story.append(
                KeepTogether(
                    [
                        Paragraph(
                            f"<b>{_text(item.category)} - {_text(item.field)} "
                            f"({_text(item.clinical_risk)} risk)</b>",
                            styles["BodyCompact"],
                        ),
                        Paragraph(
                            f"<b>{_text(item.document_a)}:</b> {_text(item.value_a)}<br/>"
                            f"<b>{_text(item.document_b)}:</b> {_text(item.value_b)}<br/>"
                            f"<b>Action:</b> {_text(item.action_required)}",
                            styles["Small"],
                        ),
                        Spacer(1, 2 * mm),
                    ]
                )
            )
    else:
        story.append(
            Paragraph(
                "No material cross-document conflict or clinical change was detected.",
                styles["BodyCompact"],
            )
        )

    completeness = case.completeness
    missing = list(dict.fromkeys(result.missing_information))
    story.append(Paragraph("Record Completeness", styles["Section"]))
    story.append(
        Paragraph(
            f"<b>{completeness.score}/{completeness.total} areas complete.</b> "
            f"Incomplete areas: {_text(', '.join(completeness.missing_fields) or 'None identified')}. "
            f"Specific items to confirm: {_text(', '.join(missing) or 'None identified')}.",
            styles["BodyCompact"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("Action Queue", styles["Section"]))
    action_rows = [[
        Paragraph("<b>Priority</b>", styles["Small"]),
        Paragraph("<b>Action</b>", styles["Small"]),
        Paragraph("<b>Route to</b>", styles["Small"]),
        Paragraph("<b>Due</b>", styles["Small"]),
        Paragraph("<b>Source</b>", styles["Small"]),
    ]]
    for item in case.action_items:
        action_rows.append(
            [
                Paragraph(_text(item.priority), styles["Small"]),
                Paragraph(_text(item.action), styles["Small"]),
                Paragraph(_text(item.route_to), styles["Small"]),
                Paragraph(_text(item.due_by), styles["Small"]),
                Paragraph(_text(", ".join(item.source_documents)), styles["Small"]),
            ]
        )
    story.append(
        _table(action_rows, [18 * mm, 63 * mm, 34 * mm, 25 * mm, 34 * mm], styles)
    )

    story.append(Paragraph("Record Timeline", styles["Section"]))
    for event in case.record_timeline:
        story.append(
            KeepTogether(
                [
                    Paragraph(
                        f"<b>{event['sequence']}. {_text(event['document_name'])}</b> - "
                        f"{_text(event.get('document_date') or 'Date not identified')}",
                        styles["BodyCompact"],
                    ),
                    Paragraph(
                        f"<b>Type:</b> {_text(event['document_type'])}<br/>"
                        f"<b>Conditions:</b> {_text(', '.join(event['conditions']) or 'Not identified')}<br/>"
                        f"<b>Evidence:</b> {_text(', '.join(event['key_findings']) or 'Not identified')}<br/>"
                        f"<b>Next action:</b> {_text(event['next_action'])}",
                        styles["Small"],
                    ),
                    Spacer(1, 3 * mm),
                ]
            )
        )

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
