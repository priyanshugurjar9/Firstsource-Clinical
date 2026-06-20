from __future__ import annotations

import io
import html
import re
import shutil
import subprocess
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_display_text(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", text)
    text = html.unescape(text)
    text = "".join(character for character in text if character.isprintable() or character in "\n\t")
    return text.strip()


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def extract_uploaded_text(uploaded_file) -> str:
    suffix = uploaded_file.name.lower().rsplit(".", 1)[-1]
    payload = uploaded_file.getvalue()
    if suffix == "txt":
        return clean_text(payload.decode("utf-8", errors="replace"))
    if suffix == "md":
        return _clean_markdown(payload.decode("utf-8", errors="replace"))
    if suffix == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF support requires pypdf. Install dependencies with: pip install -r requirements.txt"
            ) from exc
        reader = PdfReader(io.BytesIO(payload))
        return clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
    if suffix == "docx":
        return _extract_docx_text(payload)
    if suffix in {"png", "jpg", "jpeg", "tif", "tiff"}:
        return _extract_image_text(payload)
    raise ValueError("Unsupported document format.")


def _clean_markdown(text: str) -> str:
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"[ \t]{2,}\n", "\n", text)
    return clean_text(text)


def _extract_docx_text(payload: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs: list[str] = []
            for paragraph in root.iter(f"{namespace}p"):
                parts: list[str] = []
                for node in paragraph.iter():
                    if node.tag == f"{namespace}t" and node.text:
                        parts.append(node.text)
                    elif node.tag == f"{namespace}tab":
                        parts.append("\t")
                    elif node.tag in {f"{namespace}br", f"{namespace}cr"}:
                        parts.append("\n")
                value = "".join(parts).strip()
                if value:
                    paragraphs.append(value)
            return clean_text("\n".join(paragraphs))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("The Word document could not be read.") from exc


def _extract_image_text(payload: bytes) -> str:
    tesseract = shutil.which("tesseract")
    if not ocr_available():
        raise RuntimeError(
            "Image OCR requires the Tesseract OCR engine. Install it with: brew install tesseract"
        )
    try:
        from PIL import Image, ImageFilter, ImageOps

        image = Image.open(io.BytesIO(payload))
        image.load()
        grayscale = ImageOps.autocontrast(image.convert("L"))
        scale = max(1, min(3, round(1600 / max(grayscale.width, 1))))
        if scale > 1:
            grayscale = grayscale.resize(
                (grayscale.width * scale, grayscale.height * scale)
            )
        grayscale = grayscale.filter(ImageFilter.SHARPEN)
        prepared = io.BytesIO()
        grayscale.save(prepared, format="PNG")

        candidates = [
            _run_tesseract(tesseract, payload, "6"),
            _run_tesseract(tesseract, prepared.getvalue(), "6"),
            _run_tesseract(tesseract, prepared.getvalue(), "3"),
        ]
        text = max(candidates, key=_ocr_candidate_score)
    except (
        ImportError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise RuntimeError(
            "The image could not be read by OCR. Try a clearer image with higher contrast."
        ) from exc
    text = clean_text(text)
    readable_words = re.findall(r"\b[A-Za-z]{3,}\b", text)
    if len(text) < 40 or len(readable_words) < 12:
        raise ValueError(
            "The image OCR result is too incomplete for reliable analysis. "
            "Upload a clearer, higher-resolution or straightened image."
        )
    return text


def _run_tesseract(tesseract: str, payload: bytes, page_mode: str) -> str:
    completed = subprocess.run(
        [tesseract, "stdin", "stdout", "--psm", page_mode],
        input=payload,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.decode("utf-8", errors="replace")


def _ocr_candidate_score(text: str) -> int:
    lower = text.casefold()
    words = re.findall(r"\b[A-Za-z]{3,}\b", text)
    clinical_anchors = (
        "patient",
        "assessment",
        "admitted",
        "discharged",
        "pain",
        "meds",
        "allerg",
        "history",
        "discharge",
        "follow",
    )
    return (
        len(words)
        + sum(18 for anchor in clinical_anchors if anchor in lower)
        + min(text.count("\n"), 40)
    )


def infer_patient_details(text: str) -> dict[str, str | int]:
    name_patterns = [
        r"\bFull\s+name\s+of\s+patient\s*:\s*(?:Mr|Mrs|Ms|Miss|Dr)?\.?\s*"
        r"([A-Z][A-Za-z'-]+(?:[ \t]+[A-Z][A-Za-z'-]+){1,4})"
        r"(?=[ \t]*(?:\n|$|\||,))",
        r"\bFull\s+Name\s*:\s*(?:Mr|Mrs|Ms|Miss|Dr)?\.?\s*"
        r"([A-Z][A-Za-z'-]+(?:[ \t]+[A-Z][A-Za-z'-]+){1,4})"
        r"(?=[ \t]+(?:Birth\s+Date|DOB|Patient\s+ID|Med\.?\s+Number)\b|[ \t]*(?:\n|$|\||,))",
        r"\bPatient\s*\n+\s*(?:Mr|Mrs|Ms|Miss|Dr)?\.?\s*"
        r"([A-Z][A-Za-z'-]+(?:[ \t]+[A-Z][A-Za-z'-]+){1,4})"
        r"(?=\s*\n+\s*(?:Age|DOB|Date of Birth|Case ID|Patient ID)\b)",
        r"\bPatient\s*:\s*([A-Z][A-Z'-]+),\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2}?)(?=\s+(?:DOB|MRN)\b|$)",
        r"\bPatient(?:[ \t]+name)?[ \t]*:?[ \t]*"
        r"([A-Z][A-Za-z'-]+(?:[ \t]+[A-Z][A-Za-z'-]+){1,3}?)"
        r"(?=[ \t]*(?:\||,|\.|\n|$)|[ \t]+(?:Provider|Patient[ \t]+(?:Gender|ID)|DOB|MRN|Age)\b)",
        r"\bName:[ \t]*([A-Z][A-Za-z'-]+(?:[ \t]+[A-Z][A-Za-z'-]+){1,3})"
        r"(?=[ \t]*(?:\n|$|\||,|\.))",
        r"\bClinical note for\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})",
        r"\bPt(?:\.|ient)?\s+(?:is|named)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})",
        r"\bPt(?:\.|ient)?\s*:\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})",
        r"\b(?:Mr|Mrs|Ms|Miss)\.?\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})",
        r"\bref\s*:\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})\s*,\s*dob\b",
    ]
    name = "Not identified"
    for pattern in name_patterns:
        match = re.search(pattern, text, re.M)
        if match:
            if len(match.groups()) == 2:
                name = f"{match.group(2).strip()} {match.group(1).strip().title()}"
            else:
                name = match.group(1).strip()
            break

    age_match = re.search(
        r"\b(\d{1,3})[- ]year[- ]old\b"
        r"|\bAge(?:\s+of\s+patient)?\s*:?\s*(\d{1,3})\b"
        r"|\b(\d{1,3})\s*(?:y/?o|yo)\b"
        r"|\b(\d{1,3})\s*[MF]\b"
        r"|\(\s*(\d{1,3})\s*,\s*(?:Female|Male|F|M)\s*\)",
        text,
        re.I,
    )
    age = int(next(group for group in age_match.groups() if group)) if age_match else "Not identified"
    if isinstance(age, int) and not 0 < age <= 120:
        age = "Not identified"
    if age == "Not identified":
        dob_match = _find_dob(text)
        reference_date = infer_document_date(text)
        if dob_match and reference_date:
            dob = _parse_flexible_date(dob_match.group(1))
            reference = datetime.strptime(reference_date, "%Y-%m-%d").date()
            if dob:
                age = reference.year - dob.year - (
                    (reference.month, reference.day) < (dob.month, dob.day)
                )

    gender_match = re.search(
        r"\b(Female|Male|Woman|Man)\b"
        r"|\bSex\s*:?\s*(Female|Male|F|M)\b"
        r"|\b\d{1,3}\s*([MF])\b",
        text,
        re.I,
    )
    gender = "Not identified"
    if gender_match:
        raw_gender = next(group for group in gender_match.groups() if group).lower()
        gender = "Female" if raw_gender in {"f", "female", "woman"} else "Male"
    elif re.search(r"\b(?:Ms|Mrs|Miss)\.?\s+(?:[A-Z][A-Za-z'-]+\s*){1,4}", text):
        gender = "Female"
    elif re.search(r"\bMr\.?\s+(?:[A-Z][A-Za-z'-]+\s*){1,4}", text):
        gender = "Male"

    dob_match = _find_dob(text)
    parsed_dob = _parse_flexible_date(dob_match.group(1)) if dob_match else None
    patient_id = _infer_patient_identifier(text)
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "date_of_birth": parsed_dob.isoformat() if parsed_dob else "Not identified",
        "patient_id": patient_id,
    }


def _find_dob(text: str) -> re.Match[str] | None:
    return re.search(
        r"\b(?:DOB|Date\s+of\s+Birth|Birth\s+Date)\s*:?\s*"
        r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        text,
        re.I,
    )


def _parse_flexible_date(value: str) -> date | None:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    numeric = re.fullmatch(r"(\d{1,2})([./-])(\d{1,2})\2(\d{4})", value)
    if not numeric:
        return None
    first, separator, second, year = numeric.groups()
    first_number, second_number = int(first), int(second)
    if separator == "." or first_number > 12:
        formats = ("%d" + separator + "%m" + separator + "%Y",)
    elif second_number > 12:
        formats = ("%m" + separator + "%d" + separator + "%Y",)
    else:
        # UK-style day/month is the default when the value is ambiguous.
        formats = (
            "%d" + separator + "%m" + separator + "%Y",
            "%m" + separator + "%d" + separator + "%Y",
        )
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _infer_patient_identifier(text: str) -> str:
    patterns = (
        r"\b(?:Patient\s+ID|Patient\s+No\.?|Medical\s+Record\s+Number|MRN|"
        r"Med\.?\s+Number|Hospital\s+Number)\s*:?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        r"\bNRIC/FIN/Passport\s+no\.\s+of\s+patient\s*:\s*([A-Z0-9][A-Z0-9/-]{2,})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return "Not identified"


def _normalise_date(value: str) -> str | None:
    value = value.strip()
    numeric = _parse_flexible_date(value)
    if numeric and date(1900, 1, 1) <= numeric <= date(2100, 12, 31):
        return numeric.isoformat()
    for date_format in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            parsed = datetime.strptime(value, date_format).date()
            if date(1990, 1, 1) <= parsed <= date(2100, 12, 31):
                return parsed.isoformat()
        except ValueError:
            continue
    return None


DATE_VALUE = (
    r"(\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{4}"
    r"|\d{1,2}-(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)-\d{4}"
    r"|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4})"
)


def infer_document_date(text: str) -> str | None:
    patterns = [
        rf"\bdischarged\s*:?\s*{DATE_VALUE}",
        rf"\badmitted\s*:?\s*{DATE_VALUE}",
        rf"\bdischarge\s+date\s*:?\s*{DATE_VALUE}",
        rf"\b(?:document|note|report|service|encounter|admission|received|reported|collected)\s*(?:date\s*)?:?\s*{DATE_VALUE}",
        rf"\b(?:visit|assessment|examination)\s+date\s*:?\s*{DATE_VALUE}",
        rf"\bdate\s*:?\s*{DATE_VALUE}",
        rf"\bdated\s+{DATE_VALUE}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _normalise_date(match.group(1))
            if parsed:
                return parsed
    return None


def infer_encounter_dates(text: str) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "admission_date": None,
        "discharge_date": None,
    }
    for key, label in (
        ("admission_date", r"(?:admitted|admission\s+date)"),
        ("discharge_date", r"(?:discharged|discharge\s+date)"),
    ):
        match = re.search(rf"\b{label}\s*:?\s*{DATE_VALUE}", text, re.I)
        if match:
            values[key] = _normalise_date(match.group(1))
    return values


def infer_follow_up_date(text: str) -> str | None:
    patterns = [
        rf"\b(?:follow[- ]?up|review|appointment|repeat test)\s+(?:on|by|due)\s*{DATE_VALUE}",
        rf"\b(?:follow[- ]?up|review|appointment)\s+date\s*:?\s*{DATE_VALUE}",
        rf"\bnext appointment\s*:?\s*{DATE_VALUE}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _normalise_date(match.group(1))
            if parsed:
                return parsed
    return None


def infer_document_type(text: str) -> str:
    candidates = [
        "Medical Report",
        "Mental Capacity Assessment",
        "GP Consultation Note",
        "Emergency Department Note",
        "Physician Progress Note",
        "Discharge Summary",
        "Medication Review",
        "Referral Letter",
        "Lab Report",
        "Intake Form",
    ]
    lower = text.lower()
    if "opinion on patient" in lower and "mental capacity" in lower:
        return "Mental Capacity Assessment"
    if re.search(r"\bmedical reports?\b", lower):
        return "Medical Report"
    if re.search(r"^\s*#?\s*gp (?:consultation|clinical) note\b", lower):
        return "GP Consultation Note"
    if "path labs" in lower or "pathology report" in lower:
        return "Lab Report"
    for candidate in candidates:
        if candidate.lower() in lower:
            return candidate
    if "discharged" in lower or "discharge" in lower:
        return "Discharge Summary"
    if "referred" in lower or "referral" in lower:
        return "Referral Letter"
    if re.search(r"\b(hba1c|egfr|creatinine|potassium|haemoglobin|tsh)\b", lower):
        return "Clinical Note / Lab Report"
    return "Clinical Note"
