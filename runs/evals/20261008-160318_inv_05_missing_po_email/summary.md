# 20261008-160318_inv_05_missing_po_email

**Resolution:** NEC-2026-5512 from Northgate Electrical Components for 198.40 against PO-2026-1105: confirm match, pay 198.40, approver: AP specialist

## Findings
- [warning] po_reference_missing: the invoice did not state a valid purchase order; the match below was inferred from supplier, quantity and price and needs a person to confirm

## How the references were resolved
- the model named Ridgeline Fabrication (the buyer) as the supplier; ignored
- PO-2026-1105 proposed by the model (high): The invoice NEC-2026-5512 for 16 motor run capacitors at $12.40 each ($198.40 total) matches PO-2026-1105 from Northgate Electrical Components, which has the same quantity (16), unit price ($12.40), and total value ($198.4).
- supplier taken from the purchase order: Northgate Electrical Components
- line 1 matched: single line, single purchase order
- model called find_supplier({"name": "Northgate Electrical"})
- model called find_candidate_pos({"supplier_id": "V-2004", "amount": 198.4})
- model called lookup_po({"po_number": "PO-2026-1105"})

Model: lfm2.5-2.6b | calls 5 | 138.9 s | tokens in 5744 out 2213 (reasoning 1829) | total 139.3 s
