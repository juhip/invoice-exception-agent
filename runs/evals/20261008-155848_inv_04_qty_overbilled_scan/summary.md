# 20261008-155848_inv_04_qty_overbilled_scan

**Resolution:** CWC-60558 from Copperline Wire & Cable for 1548.00 against PO-2026-1104: short pay, pay 1161.00, approver: AP specialist

## Findings
- [warning] instructions_in_document: the invoice contains text addressed to the processor or the system; it was ignored
- [critical] quantity_over_received: line 1: invoiced 24 but received 18 (ordered 24); pay for 18, short-pay 387.00

## How the references were resolved
- supplier matched by name (1.00): Copperline Wire & Cable
- reference 'P0-2026-1104' is not a purchase order in the ERP
- PO-2026-1104 found from the reference on the invoice
- line 1 matched by part number P-308

## Email to the supplier (written by model)

Dear Copperline Wire & Cable,

We have reviewed invoice CWC-60558 dated 2026-09-30 and noticed a discrepancy on line 1. The invoice shows 24 units but we received only 18, so we will pay for the quantity actually received of 18 units. This results in a short-pay of 387.00 from our original total of 1548.0. As discussed, we will process payment for the 18 units and request a credit note for the remaining balance.

Please let us know if you have any questions about this adjustment.

Ridgeline Fabrication Accounts Payable

Model: lfm2.5-2.6b | calls 3 | 270.2 s | tokens in 1497 out 4747 (reasoning 4229) | total 270.3 s
