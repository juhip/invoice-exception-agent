"""Intake: turn whatever arrived (text, email, PDF) into text, and pull out what code can find."""
from __future__ import annotations

import re
from pathlib import Path

PO_REF = re.compile(r"\bP[O0]\s?-?\s?(20\d\d)\s?-?\s?(\d{4})\b", re.I)      # tolerant of OCR: P0, spaces
INJECTION = re.compile(r"ignore (all |any )?(previous|prior|above) instructions|pre-?approved by|mark (status|as) approved"
                       r"|do not contact|system (note|notice|instruction)|accounts payable system", re.I)
REMIT_CHANGE = re.compile(r"\b(new|updated|changed?) (bank|remit|remittance|account|wire|payment) (details|account|instructions|to)?"
                          r"|\bswift\b|\biban\b|routing (number|no)|account (number|no)\b", re.I)


def read(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("reading PDFs needs pypdf (pip install pypdf); or pass the text") from e
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        fmt = "pdf"
    else:
        text = path.read_text(errors="replace")
        fmt = "email" if re.match(r"^(From|To|Subject):", text) else "text"
    return {"source": path.name, "format": fmt, "text": text, "chars": len(text),
            "po_refs_found_by_code": sorted({f"PO-{y}-{n}" for y, n in PO_REF.findall(text)}),
            "injection_phrases": [m.group(0) for m in INJECTION.finditer(text)],
            "remittance_change_phrases": [m.group(0) for m in REMIT_CHANGE.finditer(text)]}
