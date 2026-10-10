"""No invented facts: a model-written text may only contain numbers, amounts, dates, IDs and names that
appear in the source facts it was given. Reused from an earlier agent's message writer, with
numeric comparison (so 2025.0, 2,025.00 and $2025.00 are one fact) and one stricter rule: an amount
written with a currency sign must be an amount in the facts, not a quantity wearing a dollar sign."""
from __future__ import annotations

import re

MONEY = re.compile(r"(?:\$|USD\s?)\s?(\d[\d,]*(?:\.\d+)?)")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
IDS = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")      # PO-2025-0012, INV-GLS-7781, CMP-004
NUMBER = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?")


def canon(n: str) -> str:
    try:
        return f"{float(n.replace(',', '')):.2f}"
    except ValueError:
        return n


def _facts(text: str, known: set[str]) -> dict[str, set[str]]:
    plain = DATE.sub(" ", IDS.sub(" ", text))
    return {"ids": set(IDS.findall(text)),
            "numbers": {canon(n) for n in NUMBER.findall(plain)},
            "money": {canon(m) for m in MONEY.findall(text)},
            "dates": set(DATE.findall(text)),
            "names": {n for n in known if n.lower() in text.lower()}}


def check_invented(source: str, text: str, known_names: set[str], amounts: list[float] | None = None) -> str | None:
    """None if every number, amount, date, ID and known name in `text` also appears in `source`.
    If `amounts` is given, every currency-marked number in `text` must be one of them."""
    o, r = _facts(source, known_names), _facts(text, known_names)
    invented: set[str] = set()
    for kind in ("ids", "numbers", "dates", "names"):
        invented |= r[kind] - o[kind]
    if amounts is not None:
        allowed = {f"{a:.2f}" for a in amounts}
        invented |= {f"${m}" for m in r["money"] - allowed}
    else:
        invented |= {f"${m}" for m in r["money"] - o["numbers"]}
    return f"added {', '.join(sorted(invented))}" if invented else None
