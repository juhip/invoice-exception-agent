"""The mock ERP: the backends an accounts-payable agent would call, as plain functions over SQLite.

Each function is deterministic and side-effect free. The ones the model may call during reference
resolution carry a JSON schema (TOOL_SCHEMAS); the rest are called by code in a fixed order.
"""
from __future__ import annotations

import difflib
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "erp.sqlite"


class ERP:
    def __init__(self, path: Path = DB):
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row

    def _rows(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    # ---- fixed lookups (code calls these) --------------------------------------------------------
    def lookup_po(self, po_number: str) -> dict:
        """Fetch one purchase order by its number, with the supplier and the part it is for."""
        rows = self._rows("""select p.po_number, p.supplier_id, s.name as supplier_name, p.component_id,
                                    c.name as part_name, c.unit_of_measure, p.quantity as ordered_qty,
                                    p.unit_price as po_unit_price, p.order_date, p.expected_delivery_date
                             from purchase_orders p join suppliers s on s.supplier_id = p.supplier_id
                                                    join components c on c.component_id = p.component_id
                             where upper(p.po_number) = upper(?)""", po_number.strip())
        return rows[0] if rows else {"error": f"purchase order {po_number!r} not found"}

    def lookup_receipts(self, po_number: str) -> dict:
        """Goods receipts recorded against a purchase order, and the total quantity received."""
        rows = self._rows("select receipt_id, received_qty, received_date, notes from goods_receipts "
                          "where upper(po_number) = upper(?) order by received_date", po_number.strip())
        return {"po_number": po_number, "received_qty": sum(r["received_qty"] for r in rows), "receipts": rows}

    def find_supplier(self, name: str) -> dict:
        """Find suppliers whose name resembles the given name. Returns the closest matches with a score."""
        rows = self._rows("select supplier_id, name, country, on_approved_list from suppliers")
        scored = []
        for r in rows:
            score = difflib.SequenceMatcher(None, _norm(name), _norm(r["name"])).ratio()
            first = _norm(name).split()[:1] == _norm(r["name"]).split()[:1]
            scored.append((round(max(score, 0.9 if first and score > 0.5 else score), 3), r))
        scored.sort(key=lambda t: -t[0])
        return {"matches": [{"supplier_id": r["supplier_id"], "name": r["name"], "country": r["country"],
                             "on_approved_list": bool(r["on_approved_list"]), "score": s} for s, r in scored[:3]]}

    def find_candidate_pos(self, supplier_id: str, amount: float | None = None) -> dict:
        """Open purchase orders for a supplier, closest in value to the given amount first."""
        rows = self._rows("""select p.po_number, c.name as part_name, p.quantity as ordered_qty,
                                    p.unit_price as po_unit_price, round(p.quantity * p.unit_price, 2) as po_value,
                                    p.order_date, p.expected_delivery_date,
                                    (select count(*) from invoices i where i.po_number = p.po_number) as invoices_already
                             from purchase_orders p join components c on c.component_id = p.component_id
                             where p.supplier_id = ?""", supplier_id)
        if amount is not None:
            rows.sort(key=lambda r: abs(r["po_value"] - float(amount)))
        return {"supplier_id": supplier_id, "candidates": rows[:6]}

    def search_pos_by_part(self, description: str) -> dict:
        """Purchase orders whose part name resembles a description from the invoice, any supplier."""
        rows = self._rows("""select p.po_number, s.name as supplier_name, p.supplier_id, c.name as part_name,
                                    p.quantity as ordered_qty, p.unit_price as po_unit_price,
                                    round(p.quantity * p.unit_price, 2) as po_value
                             from purchase_orders p join components c on c.component_id = p.component_id
                                                    join suppliers s on s.supplier_id = p.supplier_id""")
        words = set(_norm(description).split())
        scored = []
        for r in rows:
            name = set(_norm(r["part_name"]).replace("(", " ").replace(")", " ").split())
            overlap = len(words & name) + 0.5 * sum(1 for w in words for n in name if w != n and (w.startswith(n[:5]) or n.startswith(w[:5])))
            ratio = difflib.SequenceMatcher(None, _norm(description), _norm(r["part_name"])).ratio()
            scored.append((round(overlap + ratio, 3), r))
        scored.sort(key=lambda t: -t[0])
        return {"candidates": [dict(r, score=s) for s, r in scored[:5] if s > 0.3]}

    def check_duplicate(self, invoice_number: str, supplier_id: str) -> dict:
        """Whether an invoice with this number from this supplier was already processed."""
        rows = self._rows("select invoice_number, po_number, amount, invoice_date, status from invoices "
                          "where upper(invoice_number) = upper(?) and supplier_id = ?", invoice_number.strip(), supplier_id)
        return {"duplicate": bool(rows), "existing": rows[0] if rows else None}

    def supplier(self, supplier_id: str) -> dict | None:
        rows = self._rows("select * from suppliers where supplier_id = ?", supplier_id)
        return rows[0] if rows else None

    def supplier_names(self) -> set[str]:
        return {r["name"] for r in self._rows("select name from suppliers")}


def _norm(s: str) -> str:
    s = s.lower().replace(".", " ").replace(",", " ")
    for suffix in (" inc", " llc", " co", " ltd", " gmbh", " corp", " company"):
        s = s.replace(suffix, " ")
    return " ".join(s.split())


# JSON schemas for the tools the model may call while resolving references
TOOL_SCHEMAS = {
    "find_supplier": {"type": "object", "properties": {"name": {"type": "string", "description": "supplier name as written on the invoice"}},
                      "required": ["name"]},
    "find_candidate_pos": {"type": "object", "properties": {"supplier_id": {"type": "string"},
                                                            "amount": {"type": "number", "description": "invoice total, to rank candidates"}},
                           "required": ["supplier_id"]},
    "lookup_po": {"type": "object", "properties": {"po_number": {"type": "string"}}, "required": ["po_number"]},
    "search_pos_by_part": {"type": "object", "properties": {"description": {"type": "string", "description": "the part as described on the invoice"}},
                           "required": ["description"]},
}


def model_tools(erp: ERP) -> dict:
    return {name: (TOOL_SCHEMAS[name], getattr(erp, name)) for name in TOOL_SCHEMAS}
