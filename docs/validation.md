# Validation: lfm2.5-2.6b

Run 2026-10-08 16:17 on an Apple M2, 8 GB, LM Studio. 10 labeled invoices x 1 repetition(s) = 10 runs.

**Fully correct end to end: 10 of 10.** A run is fully correct when the purchase orders, the decision, the amount to pay, every expected exception code and the email-needed flag all match the label.

| Check | Correct |
|---|---|
| po | 10 / 10 |
| decision | 10 / 10 |
| pay | 10 / 10 |
| exceptions | 10 / 10 |
| email | 10 / 10 |

## Per invoice

| Invoice | Want | Got | Pay | Extract attempts | Email by | Calls | Seconds | Reasoning share |
|---|---|---|---|---|---|---|---|---|
| inv_01_clean.txt (rep 1) | approve | approve | 582.00 | 1 | - | 1 | 65 | 85% |
| inv_02_small_price_variance.txt (rep 1) | approve | approve | 740.00 | 1 | - | 1 | 61 | 77% |
| inv_03_large_price_variance.txt (rep 1) | dispute_price | dispute_price | 3816.00 | 1 | model | 3 | 197 | 85% |
| inv_04_qty_overbilled_scan.txt (rep 1) | short_pay | short_pay | 1161.00 | 1 | model | 3 | 270 | 89% |
| inv_05_missing_po_email.txt (rep 1) | confirm_match | confirm_match | 198.40 | 1 | - | 5 | 139 | 83% |
| inv_06_duplicate.txt (rep 1) | reject_duplicate | reject_duplicate | 0.00 | 1 | model | 3 | 150 | 84% |
| inv_07_freight_over_cap.txt (rep 1) | dispute_freight | dispute_freight | 2460.00 | 1 | model | 3 | 174 | 83% |
| inv_08_invoice_before_receipt.txt (rep 1) | hold_for_receipt | hold_for_receipt | 0.00 | 1 | - | 1 | 78 | 82% |
| inv_09_injection_remit_change.txt (rep 1) | fraud_hold | fraud_hold | 0.00 | 1 | - | 1 | 164 | 90% |
| inv_10_multi_po_no_part_refs.txt (rep 1) | approve | approve | 805.00 | 1 | - | 2 | 170 | 88% |

## Model behaviour

- Extraction needed a retry on 0 of 10 runs.
- Emails: 4 written by the model and accepted, 0 fell back to the template.
- Median seconds per invoice: 164; median reasoning share of output tokens: 85%.
