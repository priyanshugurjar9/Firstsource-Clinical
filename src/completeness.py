from __future__ import annotations


COMPLETENESS_DETAILS = {
    "Patient identity": set(),
    "Age or date of birth": set(),
    "Document dates": set(),
    "Current conditions": set(),
    "Symptoms or clinical signs": set(),
    "Medication reconciliation": {
        "medication adherence history",
        "medication list",
    },
    "Allergies and reactions": {
        "allergy status",
        "contrast reaction details",
    },
    "Important test results": {
        "pending vitamin B12 and folate",
        "repeat troponin result",
    },
    "Follow-up plan": {
        "follow-up plan",
        "home glucose monitoring plan",
        "recent spirometry",
    },
    "Social or cognitive context": {
        "smoking cessation date",
        "smoking status",
        "formal cognitive assessment",
    },
}


def information_to_confirm(
    missing_information: list[str],
    incomplete_fields: list[str],
) -> list[str]:
    specific = list(dict.fromkeys(missing_information))
    specific_keys = {item.casefold() for item in specific}
    for field in incomplete_fields:
        covered_by = {
            item.casefold()
            for item in COMPLETENESS_DETAILS.get(field, set())
        }
        if covered_by and specific_keys.intersection(covered_by):
            continue
        if field.casefold() not in specific_keys:
            specific.append(field.casefold())
            specific_keys.add(field.casefold())
    return specific
