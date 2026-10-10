# Validation: lfm2.5-2.6b

Run 2026-10-08 15:45 on an Apple M2, 8 GB, LM Studio. 10 labeled invoices x 1 repetition(s) = 10 runs.

**Fully correct end to end: 9 of 10.** A run is fully correct when the purchase orders, the decision, the amount to pay, every expected exception code and the email-needed flag all match the label.

| Check | Correct |
|---|---|
| po | 9 / 10 |
| decision | 9 / 10 |
| pay | 9 / 10 |
| exceptions | 9 / 10 |
| email | 9 / 10 |

## Per invoice

| Invoice | Want | Got | Pay | Extract attempts | Email by | Calls | Seconds | Reasoning share |
|---|---|---|---|---|---|---|---|---|
| inv_01_clean.txt (rep 1) | approve | approve | 582.00 | 1 | - | 1 | 67 | 85% |
| inv_02_small_price_variance.txt (rep 1) | approve | approve | 740.00 | 1 | - | 1 | 69 | 77% |
| inv_03_large_price_variance.txt (rep 1) | dispute_price | escalate **(wrong)** | 0.00 | 2 | - | 1 | 37 | 0% |
| inv_04_qty_overbilled_scan.txt (rep 1) | short_pay | short_pay | 1161.00 | 1 | template (rejected: model failed: HTTPError: HTTP Error 400: Bad Request) | 3 | 347 | 89% |
| inv_05_missing_po_email.txt (rep 1) | confirm_match | confirm_match | 198.40 | 1 | - | 5 | 150 | 83% |
| inv_06_duplicate.txt (rep 1) | reject_duplicate | reject_duplicate | 0.00 | 1 | model | 3 | 150 | 84% |
| inv_07_freight_over_cap.txt (rep 1) | dispute_freight | dispute_freight | 2460.00 | 1 | model | 3 | 186 | 83% |
| inv_08_invoice_before_receipt.txt (rep 1) | hold_for_receipt | hold_for_receipt | 0.00 | 1 | - | 1 | 86 | 82% |
| inv_09_injection_remit_change.txt (rep 1) | fraud_hold | fraud_hold | 0.00 | 2 | - | 2 | 362 | 92% |
| inv_10_multi_po_no_part_refs.txt (rep 1) | approve | approve | 805.00 | 1 | - | 2 | 186 | 88% |

## Model behaviour

- Extraction needed a retry on 2 of 10 runs.
- Emails: 2 written by the model and accepted, 1 fell back to the template (inv_04_qty_overbilled_scan.txt: model failed: HTTPError: HTTP Error 400: Bad Request).
- Median seconds per invoice: 150; median reasoning share of output tokens: 84%.
