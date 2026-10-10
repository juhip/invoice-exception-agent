"""Stage 4: the one place free text is generated. Code writes a template email with the exact
numbers; the model may rewrite it to read better; the fact check rejects any rewrite that adds a
number, date, ID or name that is not in the facts. The template is always the fallback."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .factcheck import check_invented
from .llm import LLMError, OpenAICompatibleClient, ask_json

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "draft_email.md"
BUYER = json.loads((Path(__file__).resolve().parents[1] / "data" / "policy.json").read_text())["company"]


def facts_for(invoice: dict, resolved: dict, outcome: dict) -> dict:
    pos = resolved.get("pos", [])
    return {"invoice_number": invoice["invoice_number"], "invoice_date": invoice.get("invoice_date"),
            "invoice_total": invoice.get("total"), "supplier": (resolved.get("supplier") or {}).get("name") or invoice["supplier_name"],
            "purchase_orders": [po["po_number"] for po in pos],
            "problems": [f["detail"] for f in outcome["findings"] if f["severity"] == "critical"],
            "we_will": {"dispute_price": "pay at the purchase-order price and ask for a corrected invoice or credit note",
                          "short_pay": "pay for the quantity received and ask for a credit note for the balance",
                          "dispute_freight": "pay for the goods and ask for the freight charge to be removed or justified",
                          "reject_duplicate": "not pay this invoice because it was already paid"}.get(outcome["decision"], "hold the invoice"),
            "amount_we_will_pay": outcome["payable"],
            "amounts": sorted({round(x, 2) for x in _amounts(invoice, outcome)}),
            "quantities": sorted({ln["invoiced_qty"] for ln in outcome.get("lines", [])}
                                 | {ln.get("received_qty") for ln in outcome.get("lines", []) if ln.get("received_qty") is not None})}


def _amounts(invoice: dict, outcome: dict) -> set[float]:
    """Every money figure a correct email could cite: totals, payable, line prices and amounts, and the
    differences the findings mention."""
    out = {invoice.get("total") or 0, outcome["payable"], invoice.get("freight") or 0, invoice.get("tax") or 0}
    for ln in outcome.get("lines", []):
        out |= {ln.get("invoiced_unit_price") or 0, ln.get("po_unit_price") or 0, ln.get("pay_amount") or 0,
                (ln.get("invoiced_qty") or 0) * (ln.get("invoiced_unit_price") or 0)}
    for f in outcome.get("findings", []):
        out |= {float(n.replace(",", "")) for n in re.findall(r"(?<![\w-])\d[\d,]*\.\d{2}\b", f["detail"])}
    return {float(x) for x in out if x is not None}


def template(facts: dict) -> str:
    probs = " ".join(facts["problems"]) or "a discrepancy against our records"
    return (f"Dear {facts['supplier']},\n\nWe are reviewing your invoice {facts['invoice_number']}"
            f"{' dated ' + facts['invoice_date'] if facts.get('invoice_date') else ''} for {facts['invoice_total']:.2f} "
            f"against purchase order {', '.join(facts['purchase_orders']) or 'on file'}. We found the following: {probs} "
            f"We will {facts['we_will']}. The amount we will pay against this invoice is {facts['amount_we_will_pay']:.2f}. "
            f"Please reply with a corrected invoice or credit note, or let us know if our records differ from yours.\n\n"
            f"{BUYER} Accounts Payable")


def draft(client: OpenAICompatibleClient | None, facts: dict, known_names: set[str]) -> dict:
    tpl = template(facts)
    if client is None:
        return {"email": tpl, "written_by": "template", "model_rejected": None}
    try:
        obj, _ = ask_json(client, [{"role": "system", "content": PROMPT.read_text()},
                                   {"role": "user", "content": "FACTS\n" + json.dumps(facts, indent=1)}], "draft_email",
                          validate=lambda o: None if isinstance(o.get("email"), str) and o["email"].strip() else (_ for _ in ()).throw(ValueError("email missing")))
    except LLMError as e:
        return {"email": tpl, "written_by": "template", "model_rejected": f"model failed: {str(e)[:120]}"}
    text = obj["email"].strip()
    source = json.dumps(facts) + " " + tpl
    problem = check_invented(source, text, known_names | {BUYER}, amounts=facts.get("amounts"))
    if problem:
        return {"email": tpl, "written_by": "template", "model_rejected": problem}
    low = text.lower()
    if any(w in low for w in ("bank", "swift", "iban", "routing", "account number")):
        return {"email": tpl, "written_by": "template", "model_rejected": "mentioned payment details"}
    return {"email": text, "written_by": "model", "model_rejected": None}
