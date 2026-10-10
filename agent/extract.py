"""Stage 1, the semantic step: the model transcribes the invoice into a fixed structure.

What the model does: read messy text (a scan, an email thread, a foreign-format invoice) and fill
the schema. What code does: check the structure, check the arithmetic, normalise dates, and retry
once with the error if the answer fails. An invoice that still fails is escalated, not guessed."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .llm import LLMError, OpenAICompatibleClient, ask_json

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "extract.md"
TOL = 0.05


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v).replace(",", ""))
    return float(s) if s not in ("", "-", ".") else None


def _date(v) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d %b %Y", "%b %d, %Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def validate(obj: dict) -> None:
    """Structure and arithmetic. Raises ValueError with a message the model can act on."""
    if not str(obj.get("invoice_number") or "").strip():
        raise ValueError("invoice_number is missing")
    if not str(obj.get("supplier_name") or "").strip():
        raise ValueError("supplier_name is missing")
    lines = obj.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines must be a non-empty list")
    total = _num(obj.get("total"))
    if total is None:
        raise ValueError("total is missing or not a number")
    lines_sum = 0.0
    for i, ln in enumerate(lines, 1):
        if not isinstance(ln, dict):
            raise ValueError(f"line {i} is not an object")
        q, p, ext = _num(ln.get("quantity")), _num(ln.get("unit_price")), _num(ln.get("extended"))
        if q is None or p is None:
            raise ValueError(f"line {i} needs numeric quantity and unit_price")
        if ext is not None and abs(q * p - ext) > max(TOL, 0.005 * ext):
            raise ValueError(f"line {i}: quantity {q} x unit_price {p} = {q * p:.2f}, but extended is {ext}")
        lines_sum += ext if ext is not None else q * p
    sub = _num(obj.get("subtotal"))
    if sub is not None and abs(sub - lines_sum) > TOL:
        raise ValueError(f"subtotal {sub} does not equal the sum of the lines {lines_sum:.2f}")
    expect = (sub if sub is not None else lines_sum) + (_num(obj.get("freight")) or 0) + (_num(obj.get("tax")) or 0)
    if abs(expect - total) > TOL:
        raise ValueError(f"subtotal + freight + tax = {expect:.2f} but total is {total}")


def normalise(obj: dict) -> dict:
    out = dict(obj)
    out["invoice_number"] = str(obj["invoice_number"]).strip()
    out["supplier_name"] = str(obj["supplier_name"]).strip()
    out["invoice_date"] = _date(obj.get("invoice_date"))
    out["po_references"] = [str(p).strip() for p in (obj.get("po_references") or []) if str(p).strip()]
    out["lines"] = [{"line": int(_num(ln.get("line")) or i), "part_ref": (ln.get("part_ref") or None),
                     "description": str(ln.get("description") or "").strip(), "quantity": _num(ln.get("quantity")),
                     "unit": ln.get("unit"), "unit_price": _num(ln.get("unit_price")), "extended": _num(ln.get("extended"))}
                    for i, ln in enumerate(obj["lines"], 1)]
    for k in ("subtotal", "freight", "tax", "total"):
        out[k] = _num(obj.get(k))
    out["currency"] = (obj.get("currency") or "USD").upper()
    for k in ("payment_instructions", "text_addressed_to_processor", "notes"):
        out[k] = (str(obj[k]).strip() if obj.get(k) else None)
    return out


def repair_lines(obj: dict, text: str) -> list[str]:
    """A small model sometimes misreads a wide table (quantity 2 at 80 for a line whose amount is
    2560.00). The amount is the anchor: if exactly one pair of numbers printed on the invoice
    multiplies to it, use that pair. Code does this, deterministically, and says so."""
    notes = []
    printed = sorted({float(n.replace(",", "")) for n in re.findall(r"(?<![\w-])\d[\d,]*(?:\.\d+)?", text)})
    for i, ln in enumerate(obj.get("lines") or [], 1):
        if not isinstance(ln, dict):
            continue
        q, p, ext = _num(ln.get("quantity")), _num(ln.get("unit_price")), _num(ln.get("extended"))
        if ext is None or q is None or p is None or abs(q * p - ext) <= max(TOL, 0.005 * ext):
            continue
        pairs = {tuple(sorted((a, b))) for a in printed for b in printed
                 if a > 0 and b > 0 and (a == int(a) or b == int(b)) and abs(a * b - ext) <= 0.005 and 1.0 not in (a, b)}
        if len(pairs) == 1:
            lo, hi = pairs.pop()
            # which is the quantity: the integer one; if both, the one printed first on the line
            if lo == int(lo) and hi == int(hi):
                a, b = (lo, hi) if text.find(f"{lo:g}") <= text.find(f"{hi:g}") else (hi, lo)
            else:
                a, b = (lo, hi) if lo == int(lo) else (hi, lo)
            notes.append(f"line {i}: model read {q:g} x {p:g}; the printed amount {ext:.2f} = {a:g} x {b:.2f}, which the invoice also prints; corrected by code")
            ln["quantity"], ln["unit_price"] = a, b
    return notes


def extract(client: OpenAICompatibleClient, text: str) -> tuple[dict, dict]:
    """Returns (invoice, info). info has attempts, repairs and any error. On failure invoice is {}."""
    messages = [{"role": "system", "content": PROMPT.read_text()},
                {"role": "user", "content": f"INVOICE\n<<<\n{text}\n>>>"}]
    repairs: list[str] = []

    def validate_or_repair(obj: dict) -> None:
        try:
            validate(obj)
        except ValueError:
            repairs[:] = repair_lines(obj, text)
            validate(obj)                    # still raises if the repair did not settle it

    try:
        obj, attempts = ask_json(client, messages, "extract", validate=validate_or_repair)
    except LLMError as e:
        return {}, {"attempts": 2, "repairs": repairs, "error": str(e)}
    return normalise(obj), {"attempts": attempts, "repairs": repairs, "error": None}
