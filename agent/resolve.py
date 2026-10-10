"""Stage 2: which purchase order(s) and which supplier. Code first; the model only on the branch
where language is needed (no usable PO reference, or lines without part numbers)."""
from __future__ import annotations

import json
from pathlib import Path

from .erp import ERP, model_tools
from .erp import _norm
from .llm import LLMError, OpenAICompatibleClient, ask_json, parse_json_object, run_tool_loop

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
BUYER = json.loads((Path(__file__).resolve().parents[1] / "data" / "policy.json").read_text())["company"]


def resolve(client: OpenAICompatibleClient | None, erp: ERP, invoice: dict, intake: dict) -> dict:
    out: dict = {"supplier": None, "pos": [], "how": [], "flags": [], "model_trace": []}

    # supplier: fuzzy name match in code
    m = erp.find_supplier(invoice["supplier_name"])["matches"]
    if _norm(invoice["supplier_name"]).split()[:1] == _norm(BUYER).split()[:1]:
        out["how"].append(f"the model named {BUYER} (the buyer) as the supplier; ignored")
        out["flags"].append("supplier_misread")
        m = []
    if m and m[0]["score"] >= 0.75:
        out["supplier"] = erp.supplier(m[0]["supplier_id"])
        out["how"].append(f"supplier matched by name ({m[0]['score']:.2f}): {m[0]['name']}")
    else:
        out["flags"].append("supplier_unknown")

    # purchase orders: references the model read, plus the ones code found with a tolerant regex
    refs = list(dict.fromkeys(invoice.get("po_references", []) + intake.get("po_refs_found_by_code", [])))
    for ref in refs:
        po = erp.lookup_po(ref)
        if "error" not in po:
            if out["supplier"] and po["supplier_id"] != out["supplier"]["supplier_id"]:
                out["flags"].append("po_belongs_to_other_supplier")
            out["pos"].append(po)
            out["how"].append(f"{po['po_number']} found from the reference on the invoice")
        else:
            out["how"].append(f"reference {ref!r} is not a purchase order in the ERP")

    # no usable reference: let the model investigate with read-only tools
    if out["pos"] and out["supplier"] is None:
        _supplier_from_po(erp, out)
    if not out["pos"]:
        out["flags"].append("po_reference_missing")
        if client is None:
            out["how"].append("no model available to search for a matching purchase order")
            return out
        summary = {k: invoice.get(k) for k in ("invoice_number", "supplier_name", "invoice_date", "lines", "total")}
        if "supplier_misread" in out["flags"]:
            summary["supplier_name"] = None
        msgs = [{"role": "system", "content": (PROMPTS / "resolve_refs.md").read_text()},
                {"role": "user", "content": "INVOICE (extracted)\n" + json.dumps(summary, indent=1)
                                            + "\n\nINVOICE (original text)\n<<<\n" + intake.get("text", "")[:3000] + "\n>>>"}]
        try:
            final, trace = run_tool_loop(client, msgs, model_tools(erp), "resolve", max_steps=4)
            out["model_trace"] = trace
            reply = parse_json_object(final)
            for ref in reply.get("po_numbers") or []:
                po = erp.lookup_po(str(ref))
                if "error" in po:
                    out["how"].append(f"model proposed {ref!r}, which does not exist; ignored")
                elif out["supplier"] and po["supplier_id"] != out["supplier"]["supplier_id"]:
                    out["how"].append(f"model proposed {po['po_number']}, which belongs to another supplier; ignored")
                else:
                    out["pos"].append(po)
                    out["how"].append(f"{po['po_number']} proposed by the model ({reply.get('confidence')}): "
                                      f"{reply.get('reason', '')}"[:300])
            if out["pos"]:
                out["flags"].append("po_matched_by_inference")
                if out["supplier"] is None:
                    _supplier_from_po(erp, out)
        except (LLMError, ValueError) as e:
            out["how"].append(f"model search failed ({str(e)[:120]})")
    return out


def match_lines(client: OpenAICompatibleClient | None, invoice: dict, pos: list[dict]) -> tuple[dict[int, str], list[str]]:
    """Invoice line number -> po_number. Code by part reference first; the model only for the rest."""
    by_part = {po["component_id"]: po["po_number"] for po in pos}
    matched: dict[int, str] = {}
    notes: list[str] = []
    for ln in invoice["lines"]:
        text = f"{ln.get('part_ref') or ''} {ln.get('description') or ''}"
        for cid, po in by_part.items():
            if cid.lower() in text.lower():
                matched[ln["line"]] = po
                notes.append(f"line {ln['line']} matched by part number {cid}")
                break
    todo = [ln for ln in invoice["lines"] if ln["line"] not in matched]
    if todo and len(pos) == 1 and len(invoice["lines"]) == 1:
        matched[todo[0]["line"]] = pos[0]["po_number"]
        notes.append(f"line {todo[0]['line']} matched: single line, single purchase order")
        todo = []
    if todo and client is not None:
        free = [po for po in pos if po["po_number"] not in matched.values()]
        payload = {"INVOICE_LINES": [{k: ln[k] for k in ("line", "description", "quantity", "unit_price")} for ln in todo],
                   "PO_LINES": [{k: po[k] for k in ("po_number", "part_name", "unit_of_measure", "ordered_qty", "po_unit_price")} for po in free]}
        allowed = {po["po_number"] for po in free}
        valid_lines = {ln["line"] for ln in todo}

        def validate(obj: dict) -> None:
            ms = obj.get("matches")
            if not isinstance(ms, list):
                raise ValueError("matches must be a list")
            used = set()
            for m in ms:
                if m.get("line") not in valid_lines:
                    raise ValueError(f"line {m.get('line')} is not one of the invoice lines asked about")
                if m.get("po_number") is not None and m["po_number"] not in allowed:
                    raise ValueError(f"{m.get('po_number')} is not one of the PO lines offered")
                if m.get("po_number") in used:
                    raise ValueError(f"{m['po_number']} used for two lines")
                used.add(m.get("po_number"))
        try:
            obj, _ = ask_json(client, [{"role": "system", "content": (PROMPTS / "match_lines.md").read_text()},
                                       {"role": "user", "content": json.dumps(payload, indent=1)}], "match_lines", validate)
            for m in obj["matches"]:
                if m.get("po_number"):
                    matched[int(m["line"])] = m["po_number"]
                    notes.append(f"line {m['line']} matched by the model to {m['po_number']}")
        except LLMError as e:
            notes.append(f"model line matching failed ({str(e)[:100]})")
    for ln in invoice["lines"]:
        if ln["line"] not in matched:
            notes.append(f"line {ln['line']} could not be matched to a purchase order")
    return matched, notes


def _supplier_from_po(erp: ERP, out: dict) -> None:
    """The invoice's supplier name was unreadable or wrong, but the purchase order names the supplier."""
    ids = {po["supplier_id"] for po in out["pos"]}
    if len(ids) == 1:
        out["supplier"] = erp.supplier(ids.pop())
        out["flags"] = [f for f in out["flags"] if f != "supplier_unknown"] + ["supplier_from_po"]
        out["how"].append(f"supplier taken from the purchase order: {out['supplier']['name']}")
