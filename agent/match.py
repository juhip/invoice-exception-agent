"""Stage 3, all code: compare the invoice with the purchase order and the goods receipt, apply the
AP policy, and decide. No model here: every number in the decision is computed, and the same
invoice always gets the same answer."""
from __future__ import annotations

from .erp import ERP

# decision codes, most serious first; the first one present wins
PRIORITY = ["fraud_hold", "reject_duplicate", "escalate", "hold_for_receipt", "dispute_price", "short_pay",
            "dispute_freight", "confirm_match", "needs_manager", "approve"]


def money(x: float) -> float:
    return round(x + 1e-9, 2)


def decide(erp: ERP, policy: dict, invoice: dict, resolved: dict, intake: dict, line_to_po: dict[int, str]) -> dict:
    findings: list[dict] = []
    flags: set[str] = set(resolved.get("flags", []))
    pos = {po["po_number"]: po for po in resolved.get("pos", [])}
    supplier = resolved.get("supplier")
    pay_lines = 0.0
    line_results = []

    # untrusted-input checks are code, not the model's opinion
    if intake.get("remittance_change_phrases") or (invoice.get("payment_instructions") and
            any(w in invoice["payment_instructions"].lower() for w in ("new bank", "new account", "swift", "iban", "routing"))):
        findings.append({"code": "remittance_change", "severity": "critical",
                         "detail": "the invoice asks for payment to new or changed bank details; treated as suspected fraud "
                                   "until verified with the supplier by phone on a known number"})
        flags.add("fraud_hold")
    if intake.get("injection_phrases") or invoice.get("text_addressed_to_processor"):
        findings.append({"code": "instructions_in_document", "severity": "warning",
                         "detail": "the invoice contains text addressed to the processor or the system; it was ignored"})

    if supplier is None:
        findings.append({"code": "supplier_unknown", "severity": "critical", "detail": "supplier not found in the ERP"})
        flags.add("escalate")
    elif not supplier.get("on_approved_list", 1):
        findings.append({"code": "supplier_not_approved", "severity": "critical",
                         "detail": f"{supplier['name']} is not on the approved supplier list"})
        flags.add("escalate")

    if supplier:
        dup = erp.check_duplicate(invoice["invoice_number"], supplier["supplier_id"])
        if dup["duplicate"]:
            ex = dup["existing"]
            findings.append({"code": "duplicate_invoice", "severity": "critical",
                             "detail": f"invoice {invoice['invoice_number']} was already processed on {ex['invoice_date']} "
                                       f"for {ex['amount']:.2f} ({ex['status']}) against {ex['po_number']}"})
            flags.add("reject_duplicate")

    if not pos:
        findings.append({"code": "po_reference_missing", "severity": "critical",
                         "detail": "no purchase order could be found for this invoice"})
        flags.add("escalate")
    elif "po_matched_by_inference" in flags:
        findings.append({"code": "po_reference_missing", "severity": "warning",
                         "detail": "the invoice did not state a valid purchase order; the match below was inferred "
                                   "from supplier, quantity and price and needs a person to confirm"})
        if policy.get("match_without_po_reference_needs_confirmation", True):
            flags.add("confirm_match")

    tol = policy["price_tolerance"]
    for ln in invoice["lines"]:
        po = pos.get(line_to_po.get(ln["line"], ""))
        res = {"line": ln["line"], "po_number": po["po_number"] if po else None, "invoiced_qty": ln["quantity"],
               "invoiced_unit_price": ln["unit_price"]}
        if not po:
            findings.append({"code": "line_unmatched", "severity": "critical",
                             "detail": f"line {ln['line']} ({ln['description'][:40]}) matches no purchase order line"})
            flags.add("escalate")
            line_results.append(res)
            continue
        received = erp.lookup_receipts(po["po_number"])["received_qty"]
        res.update({"po_unit_price": po["po_unit_price"], "ordered_qty": po["ordered_qty"], "received_qty": received})
        # price
        diff = ln["unit_price"] - po["po_unit_price"]
        allowed = max(po["po_unit_price"] * tol["percent"] / 100, tol["absolute"] / max(ln["quantity"], 1))
        pay_price = ln["unit_price"]
        if abs(diff) > 1e-9 and abs(diff) <= allowed:
            findings.append({"code": "price_within_tolerance", "severity": "info",
                             "detail": f"line {ln['line']}: unit price {ln['unit_price']:.2f} vs PO {po['po_unit_price']:.2f} "
                                       f"({diff / po['po_unit_price'] * 100:+.1f}%), within tolerance"})
        elif diff > allowed:
            findings.append({"code": "price_over_tolerance", "severity": "critical",
                             "detail": f"line {ln['line']}: unit price {ln['unit_price']:.2f} vs PO {po['po_unit_price']:.2f} "
                                       f"({diff / po['po_unit_price'] * 100:+.1f}%), over the {tol['percent']}% / ${tol['absolute']:.2f} tolerance; "
                                       f"pay at the PO price and dispute {money(diff * min(ln['quantity'], received)):.2f}"})
            pay_price = po["po_unit_price"]
            flags.add("dispute_price")
        elif diff < -allowed:
            findings.append({"code": "price_below_po", "severity": "info",
                             "detail": f"line {ln['line']}: invoiced below the PO price; pay as invoiced"})
        # quantity
        pay_qty = ln["quantity"]
        if received <= 0:
            findings.append({"code": "not_received", "severity": "critical",
                             "detail": f"line {ln['line']}: nothing received yet against {po['po_number']} "
                                       f"(expected {po['expected_delivery_date']}); hold until goods are received"})
            flags.add("hold_for_receipt")
            pay_qty = 0
        elif ln["quantity"] > received + 1e-9:
            findings.append({"code": "quantity_over_received", "severity": "critical",
                             "detail": f"line {ln['line']}: invoiced {ln['quantity']:g} but received {received:g} "
                                       f"(ordered {po['ordered_qty']:g}); pay for {received:g}, "
                                       f"short-pay {money((ln['quantity'] - received) * pay_price):.2f}"})
            flags.add("short_pay")
            pay_qty = received
        if ln["quantity"] > po["ordered_qty"] + 1e-9 and received >= ln["quantity"]:
            findings.append({"code": "quantity_over_ordered", "severity": "warning",
                             "detail": f"line {ln['line']}: invoiced {ln['quantity']:g} vs ordered {po['ordered_qty']:g}, but received in full"})
        res.update({"pay_qty": pay_qty, "pay_unit_price": pay_price, "pay_amount": money(pay_qty * pay_price)})
        pay_lines += pay_qty * pay_price
        line_results.append(res)

    # freight and tax
    goods = sum(ln["quantity"] * ln["unit_price"] for ln in invoice["lines"])
    freight = invoice.get("freight") or 0.0
    cap = max(goods * policy["freight"]["max_percent_of_goods"] / 100, policy["freight"]["max_absolute"])
    pay_freight = freight
    if freight > cap + 1e-9:
        findings.append({"code": "freight_over_cap", "severity": "critical",
                         "detail": f"freight {freight:.2f} exceeds the allowance of {cap:.2f} "
                                   f"(larger of {policy['freight']['max_percent_of_goods']}% of goods or ${policy['freight']['max_absolute']:.2f}) "
                                   f"and is not on the purchase order; pay the goods and dispute the freight"})
        flags.add("dispute_freight")
        pay_freight = 0.0
    tax = invoice.get("tax") or 0.0
    if goods and tax / goods * 100 > policy["tax_rate_max_percent"]:
        findings.append({"code": "tax_unusual", "severity": "warning", "detail": f"tax {tax:.2f} is {tax / goods * 100:.1f}% of goods"})

    payable = money(pay_lines + pay_freight + tax)
    if "fraud_hold" in flags or "reject_duplicate" in flags or "escalate" in flags or "hold_for_receipt" in flags:
        payable = 0.0
    if payable > policy["auto_approve_limit"]:
        flags.add("needs_manager")
    decision = next(d for d in PRIORITY if d in flags or d == "approve")
    approver = (policy["approvers"]["fraud"] if decision == "fraud_hold" else
                policy["approvers"]["over_limit"] if "needs_manager" in flags else policy["approvers"]["default"])
    auto = decision == "approve" and "needs_manager" not in flags
    email_needed = decision in ("dispute_price", "short_pay", "dispute_freight", "reject_duplicate")
    return {"decision": decision, "payable": payable, "invoice_total": invoice.get("total"),
            "auto_release": auto, "approver": None if auto else approver, "email_needed": email_needed,
            "findings": findings, "lines": line_results, "flags": sorted(flags)}
