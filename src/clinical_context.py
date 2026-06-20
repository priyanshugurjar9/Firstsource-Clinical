from __future__ import annotations

import re
from collections.abc import Iterator


PSEUDO_NEGATION = (
    r"\bnot including\b",
    r"\bnot only\b",
    r"\bnot necessarily\b",
    r"\bcannot rule out\b",
    r"\bcan(?:not|'t) exclude\b",
    r"\bno change in\b",
    r"\bno increase in\b",
)

PRE_NEGATION = (
    r"\bdenies?\b",
    r"\bdenied\b",
    r"\bwithout\b",
    r"\bnegative for\b",
    r"\babsence of\b",
    r"\bfree of\b",
    r"\bno evidence of\b",
    r"\bno signs? of\b",
    r"\bnot experiencing\b",
    r"\bnot reporting\b",
    r"\bnot had\b",
    r"\bhas not had\b",
    r"\bhad not had\b",
    r"\bhasn['’]t had\b",
    r"\bno longer (?:has|had|experiences?|reports?)\b",
    r"\bno\b",
)

POST_NEGATION = (
    r"^\s*[:,=-]?\s*(?:none|no|negative|denied|absent|not present|ruled out|excluded)\b",
    r"^\s*(?:is|was|were|has been)?\s*(?:denied|absent|negative|not present|ruled out|excluded)\b",
    r"^\s*[:,=-]?\s*none\s+(?:reported|identified|observed|documented)\b",
)

HISTORICAL_CUES = (
    r"\bhistory of\b",
    r"\bpast history of\b",
    r"\bprevious(?:ly)?\b",
    r"\bremote history of\b",
    r"\bresolved\b",
    r"\bfamily history of\b",
)

HYPOTHETICAL_CUES = (
    r"\bif\s*:",
    r"\bif (?:the )?patient (?:develops?|experiences?|reports?)\b",
    r"\bshould (?:the )?patient (?:develop|experience|report)\b",
    r"\bseek (?:urgent )?(?:help|review|care).{0,30}\bif\b",
    r"\b(?:return|go|attend|present) .{0,40}\bif\b",
    r"\bsafety[- ]?net(?:ting)?\b",
    r"\bwatch (?:for|out for)\b",
)

LAB_PATTERNS = (
    r"\bHbA1c\s*(?::|is|=|of)?\s*\d+(?:\.\d+)?%",
    r"\b(?:eGFR(?:\s*\(CKD-EPI\))?|Creatinine|Potassium|TSH|Free T4|BNP(?:\s*\(B-type Natriuretic Peptide\))?|CRP|Haemoglobin|Ferritin|Random Glucose)\s*(?::|is|=|of)?\s*\d+(?:\.\d+)?\s*(?:mL/min/1\.73m2|umol/L|mmol/L|mU/L|mIU/L|pmol/L|pg/mL|mg/L|g/dL|ng/mL|ug/L|%)?",
    r"\bTroponin I(?:\s*\(hsTnI\))?(?:\s*@\s*\d{2}:\d{2})?\s*(?::|is|=|of)?\s*\d+(?:\.\d+)?\s*ng/L",
    r"\bBlood pressure\s*(?:is|=|of)?\s*\d{2,3}/\d{2,3}\s*mmHg",
    r"\bBP\s*:\s*\d{2,3}/\d{2,3}",
    r"\bOxygen saturation\s*(?:is|=|of)?\s*\d{2,3}%",
    r"\bO2 sats?\s*:\s*\d{2,3}%",
    r"\b(?:Potassium|K\+)\s*(?:is|=|of)?\s*\d+(?:\.\d+)?(?:\s*mmol/L)?",
)

FOLLOW_UP_ACTION_PATTERN = (
    r"\b(?:route|refer|arrange|schedule|contact|check|repeat|review)"
    r"[^.\n]{0,120}?\b(?:within|in|on|by)\s+"
    r"(?:\d+\s*(?:hours?|days?|weeks?|months?)|"
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b"
)


def has_follow_up_plan(text: str) -> bool:
    patterns = (
        r"\bfollow[- ]?up\b",
        r"\bnext appointment\b",
        r"\b(?:cardiology|respiratory|diabetes|renal|heart failure)\s+OPD\b",
        r"\bcheck back with\b",
        r"\bactivity restrictions?\b",
        r"\bstrict diet\b",
        FOLLOW_UP_ACTION_PATTERN,
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def bounded_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I)


def term_spans(text: str, term: str) -> Iterator[tuple[int, int]]:
    for match in bounded_pattern(term).finditer(text):
        yield match.start(), match.end()


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(
        text.rfind(".", 0, start),
        text.rfind(";", 0, start),
        text.rfind("\n", 0, start),
    )
    right_candidates = [
        index for index in (
            text.find(".", end),
            text.find(";", end),
            text.find("\n", end),
        )
        if index >= 0
    ]
    right = min(right_candidates) if right_candidates else len(text)
    return left + 1, right


def is_negated(text: str, start: int, end: int | None = None) -> bool:
    end = end if end is not None else start
    clause_start, clause_end = _clause_bounds(text, start, end)
    before = text[max(clause_start, start - 120) : start].lower()
    after = text[end : min(clause_end, end + 60)].lower()

    pseudo_window = before[-80:]
    if any(re.search(pattern, pseudo_window) for pattern in PSEUDO_NEGATION):
        return False

    contrast = re.split(r"\b(?:but|however|although|yet)\b", before)
    before = contrast[-1]
    before_words = before.split()
    local_before = " ".join(before_words[-8:])
    if any(re.search(pattern + r"(?:\s+\w+){0,5}\s*$", local_before) for pattern in PRE_NEGATION):
        return True

    return any(re.search(pattern, after) for pattern in POST_NEGATION)


def is_historical(text: str, start: int, end: int | None = None) -> bool:
    end = end if end is not None else start
    clause_start, _ = _clause_bounds(text, start, end)
    before = text[max(clause_start, start - 100) : start].lower()
    local_before = " ".join(before.split()[-10:])
    return any(re.search(pattern + r"(?:\s+\w+){0,5}\s*$", local_before) for pattern in HISTORICAL_CUES)


def is_family_history(text: str, start: int, end: int | None = None) -> bool:
    end = end if end is not None else start
    clause_start, _ = _clause_bounds(text, start, end)
    before = text[max(clause_start, start - 180) : start].lower()
    return bool(
        re.search(
            r"\bfamily history\b|\b(?:father|mother|parent|sibling|brother|sister|"
            r"uncle|aunt|grandparent)\b[^.\n]{0,100}\b(?:had|has|with)\b",
            before,
        )
    )


def is_hypothetical(text: str, start: int, end: int | None = None) -> bool:
    end = end if end is not None else start
    clause_start, _ = _clause_bounds(text, start, end)
    before = text[max(clause_start, start - 220) : start].lower()
    return any(re.search(pattern, before, re.I | re.S) for pattern in HYPOTHETICAL_CUES)


def non_negated_term_spans(text: str, term: str) -> list[tuple[int, int]]:
    return [
        (start, end)
        for start, end in term_spans(text, term)
        if not is_negated(text, start, end)
    ]


def active_term_spans(text: str, term: str) -> list[tuple[int, int]]:
    return [
        (start, end)
        for start, end in term_spans(text, term)
        if not is_negated(text, start, end)
        and not is_historical(text, start, end)
        and not is_hypothetical(text, start, end)
    ]


def non_negated_pattern_matches(text: str, pattern: str) -> list[re.Match[str]]:
    return [
        match
        for match in re.finditer(pattern, text, re.I)
        if not is_negated(text, match.start(), match.end())
    ]


def active_pattern_matches(text: str, pattern: str) -> list[re.Match[str]]:
    return [
        match
        for match in re.finditer(pattern, text, re.I)
        if not is_negated(text, match.start(), match.end())
        and not is_historical(text, match.start(), match.end())
        and not is_hypothetical(text, match.start(), match.end())
    ]


def iter_text_chunks(
    text: str,
    chunk_size: int = 1800,
    overlap: int = 80,
) -> Iterator[tuple[int, str, int, int]]:
    """Yield chunks plus a unique ownership range for overlap-safe extraction."""
    if len(text) <= chunk_size:
        yield 0, text, 0, len(text)
        return

    segments: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        target_end = min(start + chunk_size, len(text))
        end = target_end
        if target_end < len(text):
            break_at = max(
                text.rfind("\n", start + chunk_size // 2, target_end),
                text.rfind(". ", start + chunk_size // 2, target_end),
            )
            if break_at > start:
                end = break_at + 1
        segments.append((start, end))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    for index, (start, end) in enumerate(segments):
        owned_start = start if index == 0 else (segments[index - 1][1] + start) // 2
        owned_end = end if index == len(segments) - 1 else (end + segments[index + 1][0]) // 2
        yield start, text[start:end], owned_start, owned_end
