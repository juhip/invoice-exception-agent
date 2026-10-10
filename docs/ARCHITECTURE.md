# Architecture: one exception, arrival to resolution

```
 invoice file ──► 1 INTAKE ──► 2 EXTRACT ──► 3 RESOLVE ──► 4 MATCH & DECIDE ──► 5 DRAFT ──► packet for approval
 (txt/eml/pdf)    code         model+code     code, model     code only           model+code    runs/<id>/
                                              on one branch
```

| Stage | Input | Output | Who | Failure handling |
|---|---|---|---|---|
| 1 Intake | file: text, email thread, PDF | plain text; PO references found by an OCR-tolerant regex; injection and bank-change phrases found by regex | code | unreadable file: escalate |
| 2 Extract | text, inside data delimiters | fixed JSON: invoice no, supplier, date, PO refs, lines (qty, unit price, extended), subtotal, freight, tax, total, payment instructions, text addressed to the processor | **model** (LFM2.5-2.6B, JSON mode) | code validates structure and arithmetic (line = qty x price, subtotal = lines, total = subtotal + freight + tax). A line that fails is **repaired by code** when exactly one pair of numbers printed on the invoice multiplies to the printed amount (the model read 2 x 80 for a line printed 80 x 32.00 = 2,560.00). Otherwise one retry with the error fed back. Still failing: **escalate** to a person or a frontier model; nothing is guessed |
| 3 Resolve | extracted invoice, intake flags | supplier id, purchase order(s), invoice line to PO line map | code first; **model** only on two branches | supplier by fuzzy name in code. PO from the invoice's reference or the regex. **No usable reference:** model investigates with four read-only tools (search_pos_by_part, find_supplier, find_candidate_pos, lookup_po), allowlisted, arguments schema-checked, 4 steps max, and sees the original text as well as the extracted fields; its answer must exist in the ERP and belong to the matched supplier, and the result is held for a person to confirm. If the model named the buyer as the supplier, that is discarded and the supplier is taken from the purchase order. **Lines without part numbers:** model picks from the PO lines offered, one-to-one, or the line is unmatched and the invoice escalates |
| 4 Match & decide | invoice, POs, receipts, policy | findings with exact numbers; decision; amount to pay; approver; whether an email is needed | code only | price tolerance, quantity vs received, freight cap, duplicate, not received, remittance change, unapproved supplier. Priority order: fraud hold, duplicate, escalate, hold for receipt, dispute price, short pay, dispute freight, confirm match, needs manager, approve. Same input, same answer, every time |
| 5 Draft | facts packet (invoice, PO, problems, what we will do, amount) | supplier email | **model** rewrites a code-written template | every number, date, ID and supplier name in the model's email must appear in the facts, compared numerically; every figure written with a currency sign must be one of the facts' amounts, so a quantity dressed as "$220" is rejected; any mention of bank or payment details is rejected; on rejection or failure the template is sent |
| Packet | all of the above | `summary.md` for the approver, `packet.json`, `model_calls.jsonl` | code | a person approves, edits or rejects; nothing is paid or sent by the agent |

**Where language is used, and why.** Extraction (layouts vary, scans are noisy, emails bury the
numbers). Finding a purchase order when the invoice does not name one (judgment over candidates).
Matching a line described in words to a part (semantics). Writing to a supplier (tone). Everything
else is arithmetic and policy, and is code.

**Where the model is not trusted.** It never computes a variance, never decides an outcome, never
chooses the amount to pay, has no tool that writes, pays, approves or sends, and cannot pick a
purchase order that belongs to another supplier. Text inside the invoice is wrapped as data and
the injection checks run in code regardless of what the model reports.

**Reliability.** Two model calls on a typical invoice (extract, and draft when a dispute exists),
up to five on a hard one. Each is validated with a defined fallback, so the chain's failure mode is
"escalated or template" rather than "wrong payment". Across the labeled set the measured numbers
are in `docs/validation.md`.
