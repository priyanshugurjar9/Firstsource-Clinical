from __future__ import annotations

import re

from .models import MedicationRecord


def medication_status_label(status: str) -> str:
    return {
        "Stopped": "Discontinued",
        "Withheld": "Temporarily withheld",
        "Taken in error": "Unintended dose reported",
    }.get(status, status)


def medication_safety_detail(record: MedicationRecord) -> str:
    """Return one clear action for one medication without leaking adjacent text."""
    medication = record.medication
    if record.status == "Taken in error":
        return (
            f"Confirm the current {medication} plan and check that no further "
            "unintended doses are taken."
        )
    if record.status == "Withheld":
        return (
            f"Keep {medication} on hold until the prescribing team confirms "
            "the documented restart criteria."
        )
    if record.status == "Stopped":
        if re.search(r"\bramipril\b", medication, re.I):
            return (
                "Medication reconciliation required: verify ramipril has been "
                "discontinued, confirm it is not used concurrently with Entresto, "
                "and update the active medication record."
            )
        return (
            f"Medication reconciliation required: verify {medication} has been "
            "discontinued and update the active medication record."
        )
    if record.status == "New" and re.search(
        r"\bentresto|sacubitril", medication, re.I
    ):
        return (
            "Confirm that no ACE inhibitor, including ramipril, is taken with "
            "this medicine."
        )
    return f"Review the current status of {medication} with the prescribing team."
