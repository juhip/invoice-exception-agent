#!/usr/bin/env python3
"""
Part 1 tool-calling demo: LFM2.5-2.6B reads an invoice and must call a REAL
local function with arguments it filled in from context.

The function actually executes against a mock "ERP" and the result is fed back
for a final answer. Requires LM Studio server with lfm2.5-2.6b loaded.
"""

import json
import urllib.request

API = "http://localhost:1234/v1/chat/completions"
MODEL = "lfm2.5-2.6b"

INVOICE = """INVOICE #INV-2026-0347          Date: 2026-09-14
From: Meridian Fastener Corp, 412 Cobbler Ln, Aurora IL
Bill to: Acme Industrial Supply
PO Reference: PO-2026-88142
Terms: Net 45

Qty  Part        Description            Unit      Ext.
480  F-0891      Flanged bolt M10x40    0.42     201.60
120  W-1120      Lock washer pack       3.75     450.00
 30  S-7741      Stainless shim stock   18.00    540.00
                                   Subtotal:  1191.60
                                   Freight:     85.00
                                   Tax:         95.33
                                   TOTAL DUE: 1371.93
"""

# --- The real functions the model is allowed to call -----------------------

MOCK_ERP = {
    "PO-2026-88142": {"po_number": "PO-2026-88142", "vendor": "Meridian Fastener Corp",
                      "po_total": 1286.60, "status": "OPEN", "freight_cap": 85.00},
    "PO-2026-77381": {"po_number": "PO-2026-77381", "vendor": "Meridian Fastener Corp",
                      "po_total": 540.00, "status": "CLOSED", "freight_cap": 40.00},
}


def lookup_purchase_order(po_number: str) -> dict:
    """Look up a purchase order in the mock ERP by its PO number."""
    record = MOCK_ERP.get(po_number.strip().upper())
    return record if record else {"error": f"PO {po_number} not found"}


# ----------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_purchase_order",
            "description": "Look up a purchase order in the ERP by its PO number, e.g. 'PO-2026-88142'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "po_number": {"type": "string",
                                  "description": "The PO reference number from the invoice"},
                },
                "required": ["po_number"],
            },
        },
    }
]


def call_model(messages, tools=None, max_tokens=1500):
    body = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def main():
    messages = [
        {"role": "system",
         "content": "You are an accounts-payable assistant. Use the lookup_purchase_order tool "
                    "to verify invoices against their PO. Do not invent data."},
        {"role": "user",
         "content": f"Here is an invoice that landed in the exception queue:\n\n{INVOICE}\n"
                    "Look up the referenced purchase order and tell me whether the invoice total "
                    "matches the PO, and flag anything else that looks off."},
    ]

    print("=" * 70)
    print("Sending invoice to LFM2.5-2.6B with one available tool: lookup_purchase_order")
    print("=" * 70)

    resp = call_model(messages, tools=TOOLS)
    msg = resp["choices"][0]["message"]

    tool_calls = msg.get("tool_calls") or []
    print(f"\nModel raw content: {msg.get('content')!r}")
    print(f"Model reasoning (truncated): {(msg.get('reasoning_content') or '')[:300]!r}")
    print(f"Tool calls requested: {len(tool_calls)}")

    if not tool_calls:
        print("\nNo tool call made. This is a finding for the write-up.")
        return

    for tc in tool_calls:
        fn = tc["function"]
        args = json.loads(fn["arguments"])
        print(f"\n-> Model called: {fn['name']}(**{args})")
        result = lookup_purchase_order(**args)          # <-- real function executes here
        print(f"<- Function returned: {json.dumps(result)}")
        messages.append({"role": "assistant", "tool_calls": [tc]})
        messages.append({"role": "tool",
                         "tool_call_id": tc["id"],
                         "content": json.dumps(result)})

    print("\n" + "=" * 70)
    print("Feeding result back for the final verdict:")
    print("=" * 70)
    final = call_model(messages)
    fmsg = final["choices"][0]["message"]
    if not fmsg.get("content") and fmsg.get("reasoning_content"):
        print(f"[NOTE: empty content; reasoning was:\n{fmsg['reasoning_content'][:800]}")
    print(fmsg.get("content", ""))
    print(f"\nfinish_reason: {final['choices'][0].get('finish_reason')}  "
          f"usage: {final.get('usage')}")


if __name__ == "__main__":
    main()
