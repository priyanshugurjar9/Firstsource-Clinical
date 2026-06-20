from __future__ import annotations

from dataclasses import dataclass

from .clinical_context import active_pattern_matches
from .models import CausalLink, Entity


@dataclass(frozen=True)
class Rule:
    patterns: tuple[str, ...]
    meaning: str
    implication: str
    action: str
    weight: int
    evidence_basis: str
    routing_destination: str
    follow_up_window: str


RULES = [
    Rule(
        (
            r"\bepigastric abdominal pain\b|\babdominal pain\b",
            r"\bnoticed (?:the stools|them) darker\b|\b(?:black|tarry|dark) stools?\b",
            r"\bmotrin\b|\b(?:ibuprofen|naproxen|nsaid)\b",
        ),
        "Possible upper gastrointestinal bleeding concern",
        "Epigastric pain, darker stools and NSAID exposure together require prompt assessment",
        "Escalate for same-day gastrointestinal or acute clinical review",
        40,
        "Upper gastrointestinal bleeding safety pattern",
        "Acute clinical / gastroenterology team",
        "Immediate / same day",
    ),
    Rule(
        (r"\bchest pain\b", r"\bst[- ]?depression\b"),
        "Possible acute cardiac concern",
        "Urgent review is required because symptoms and electrocardiogram findings occur together",
        "Escalate to the acute cardiac pathway",
        40,
        "Chest pain plus electrocardiogram change safety rule",
        "Acute cardiac team",
        "Immediate / same day",
    ),
    Rule(
        (
            r"\b(?:intermittent |exertional )?chest pain\b",
            r"\bpalpitations\b|\bshortness of breath\b|\bbreathless(?:ness)?\b",
        ),
        "Symptomatic cardiac concern",
        "Chest pain with palpitations or exertional breathlessness warrants timely cardiac review",
        "Arrange expedited cardiac assessment",
        30,
        "Symptomatic cardiac review workflow rule",
        "Cardiology / acute assessment team",
        "Within 2 working days",
    ),
    Rule(
        (r"\bst[- ]?elevation\b|\bstemi\b",),
        "Possible ST-elevation myocardial infarction",
        "ST elevation can indicate a time-critical acute heart attack",
        "Escalate immediately to the emergency cardiac pathway",
        50,
        "ST-elevation emergency pathway rule",
        "Emergency cardiac team",
        "Immediate",
    ),
    Rule(
        (r"\bnstemi\b|\bnon[- ]ST[- ]elevation myocardial infarction\b",),
        "Documented non-ST-elevation myocardial infarction",
        "A documented NSTEMI is a time-critical cardiac condition requiring acute review",
        "Escalate to the acute cardiac pathway",
        45,
        "Documented NSTEMI emergency workflow rule",
        "Acute cardiac team",
        "Immediate / same day",
    ),
    Rule(
        (
            r"\btroponin I(?:\s*\(hsTnI\))?(?:\s*@\s*\d{2}:\d{2})?\s*(?::|is|=|of)?\s*(?:[1-9]\d{2,}|[6-9]\d)\s*ng/L",
            r"\b(?:significant rise|acute myocardial injury|NSTEMI criteria met|NSTEMI confirmed)\b",
        ),
        "Acute myocardial injury pattern",
        "A rising troponin pattern with documented acute myocardial injury requires urgent cardiac review",
        "Escalate to the acute cardiac pathway",
        45,
        "Troponin trend and myocardial-injury safety rule",
        "Acute cardiac team",
        "Immediate / same day",
    ),
    Rule(
        (
            r"\b(?:potassium|k\+)\s*(?:is|=|of)?\s*(?:5\.[5-9]\d*|[6-9]\d*(?:\.\d+)?)",
            r"\begfr\s*(?:is|=|of)?\s*(?:[12]?\d|3[0-4])\b",
        ),
        "Raised potassium with reduced renal function",
        "Possible medication and electrolyte safety concern",
        "Escalate for renal review and repeat potassium confirmation",
        40,
        "Potassium and renal-function safety rule",
        "Renal team",
        "Immediate / same day",
    ),
    Rule(
        (r"\b(?:potassium|k\+)\s*(?:is|=|of)?\s*(?:6(?:\.\d+)?|[7-9]\d*(?:\.\d+)?)",),
        "Critical potassium result",
        "A severely raised potassium result can require urgent clinical action",
        "Escalate the critical potassium result for immediate human review",
        45,
        "Critical potassium safety rule",
        "Urgent clinical review",
        "Immediate",
    ),
    Rule(
        (r"\bhba1c\s*(?:is|=|of)?\s*(?:9(?:\.\d+)?|[1-9]\d(?:\.\d+)?)%",),
        "Poor glycaemic control",
        "Higher follow-up priority and risk of diabetes complications",
        "Route to the diabetes nurse specialist within 7 days",
        30,
        "Glycaemic-control follow-up rule",
        "Diabetes nurse specialist",
        "Within 7 days",
    ),
    Rule(
        (r"\boxygen saturation\s*(?:is|=|of)?\s*(?:8\d|9[0-1])%", r"\bworsening breathlessness\b"),
        "Possible respiratory deterioration",
        "Reduced oxygenation increases urgency",
        "Arrange urgent respiratory assessment",
        35,
        "Oxygenation and respiratory-symptom safety rule",
        "Respiratory team",
        "Immediate / same day",
    ),
    Rule(
        (
            r"\bbnp(?:\s*\(B-type Natriuretic Peptide\))?\s*(?::|is|=|of)?\s*(?:[8-9]\d{2}|[1-9]\d{3,})\b",
            r"\b(?:fluid|volume) overload\b",
        ),
        "Potentially unstable heart failure",
        "Higher risk of deterioration or readmission",
        "Arrange early heart failure follow-up",
        35,
        "Heart-failure deterioration follow-up rule",
        "Heart failure service",
        "Within 48 hours",
    ),
    Rule(
        (r"\b(?:ramipril|ACEi)\b", r"\b(?:entresto|sacubitril[- ]valsartan)\b", r"\brisk of angioedema\b"),
        "Potential ACE inhibitor and Entresto interaction",
        "Taking ramipril close to Entresto can create a serious medication-safety concern",
        "Escalate for same-day medication safety review and confirm ramipril is stopped",
        40,
        "ACE inhibitor and neprilysin-inhibitor medication safety rule",
        "Prescribing clinician / heart failure team",
        "Immediate / same day",
    ),
    Rule(
        (
            r"\biodinated contrast allergy\b",
            r"\ballergy record[\s\S]{0,220}\b(?:wrong|incorrect)\b",
        ),
        "Incorrect allergy severity may be recorded",
        "An inaccurate severe-allergy label could affect future imaging and treatment decisions",
        "Verify the original contrast reaction and correct the allergy record",
        30,
        "Cross-record allergy documentation safety rule",
        "Clinical records team / prescribing clinician",
        "Before end of week",
    ),
    Rule(
        (r"\bhaemoglobin\s*(?:is|=|of)?\s*8(?:\.\d+)?", r"\bferritin\s*(?:is|=|of)?\s*(?:[0-9]|1[0-4])\b"),
        "Iron deficiency anaemia",
        "Low haemoglobin requires investigation and monitoring",
        "Route to the anaemia or gastroenterology pathway",
        25,
        "Anaemia investigation workflow rule",
        "Gastroenterology / anaemia pathway",
        "Within 2 working days",
    ),
    Rule(
        (r"\bblood pressure\s*(?:is|=|of)?\s*1(?:6[0-9]|[7-9][0-9])/\d{2,3}",),
        "Blood pressure above target",
        "Increased cardiovascular risk without documented acute instability",
        "Arrange expedited primary care review",
        20,
        "Hypertension follow-up workflow rule",
        "Primary care",
        "Within 2 working days",
    ),
    Rule(
        (r"\btsh\s*(?:is|=|of)?\s*1[2-9](?:\.\d+)?", r"\bfree t4\s*(?:is|=|of)?\s*(?:[0-8](?:\.\d+)?)"),
        "Under-treated hypothyroidism",
        "Routine medication adjustment may be required",
        "Arrange primary care medication review",
        12,
        "Thyroid medication-review workflow rule",
        "Primary care",
        "Routine queue",
    ),
    Rule(
        (
            r"\bdementia\b|\bstroke\b",
            r"\blacks? mental capacity\b|\bdoes not have mental capacity\b|"
            r"\bunable to (?:understand|retain|use or weigh) information\b|"
            r"\bwill not be able to make decisions\b|\bcognitive failures?\b",
        ),
        "Documented cognitive and functional impairment",
        "The record documents impaired decision-making capacity and requires a clear supported-care plan",
        "Route for mental-capacity, safeguarding and care-plan review",
        30,
        "Mental-capacity documentation workflow rule",
        "Mental capacity / safeguarding review team",
        "Within 2 working days",
    ),
]

# These are transparent POC workflow weights, not a clinical scoring standard.
OPERATIONAL_THRESHOLDS = {"High": 50, "Medium": 25}


def build_causal_links(text: str, entities: list[Entity]) -> list[CausalLink]:
    links: list[CausalLink] = []
    for rule in RULES:
        matches = [active_pattern_matches(text, pattern) for pattern in rule.patterns]
        if all(matches):
            findings = [group[0].group(0) for group in matches]
            links.append(
                CausalLink(
                    finding=" + ".join(findings),
                    meaning=rule.meaning,
                    implication=rule.implication,
                    action=rule.action,
                    weight=rule.weight,
                    evidence_basis=rule.evidence_basis,
                    routing_destination=rule.routing_destination,
                    follow_up_window=rule.follow_up_window,
                )
            )

    if not links:
        red_flags = [entity.text for entity in entities if entity.label == "RED_FLAG"]
        if red_flags:
            links.append(
                CausalLink(
                    finding=" + ".join(red_flags[:3]),
                    meaning="Clinical or operational warning signal",
                    implication="The case needs prioritised human review",
                    action="Review the source evidence and confirm the next clinical workflow",
                    weight=min(15 + len(red_flags) * 5, 35),
                    evidence_basis="Extracted warning signal requiring human triage",
                    routing_destination="Clinical review team",
                    follow_up_window="Prompt human review",
                )
            )
    return sorted(links, key=lambda link: link.weight, reverse=True)


def calculate_risk(
    links: list[CausalLink],
    entities: list[Entity],
    missing: list[str],
) -> tuple[int, str]:
    ordered_weights = sorted((link.weight for link in links), reverse=True)
    score = ordered_weights[0] if ordered_weights else 0
    score += min(round(sum(ordered_weights[1:]) * 0.2), 20)
    score += min(len(missing) * 2, 8)
    score = min(score, 100)
    immediate_evidence = any(
        link.weight >= 40 and "immediate" in link.follow_up_window.lower()
        for link in links
    )
    if immediate_evidence:
        return score, "High"
    if score >= OPERATIONAL_THRESHOLDS["High"]:
        return score, "High"
    if score >= OPERATIONAL_THRESHOLDS["Medium"]:
        return score, "Medium"
    return score, "Low"


def recommended_action(links: list[CausalLink], risk_level: str) -> str:
    if links:
        actions = list(dict.fromkeys(link.action for link in links))
        return " Also: ".join(actions) + ("." if not actions[-1].endswith(".") else "")
    if risk_level == "High":
        return "Escalate for urgent human review."
    if risk_level == "Medium":
        return "Route for expedited clinical or administrative review."
    return "Continue routine follow-up and document review."


def what_if_score(
    current_score: int,
    follow_up_complete: bool,
    critical_result_resolved: bool,
    missing_information_resolved: bool,
) -> int:
    adjusted = current_score
    adjusted -= 15 if follow_up_complete else 0
    adjusted -= 25 if critical_result_resolved else 0
    adjusted -= 10 if missing_information_resolved else 0
    return max(adjusted, 0)


def level_for_score(score: int) -> str:
    if score >= OPERATIONAL_THRESHOLDS["High"]:
        return "High"
    if score >= OPERATIONAL_THRESHOLDS["Medium"]:
        return "Medium"
    return "Low"
