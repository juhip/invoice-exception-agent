"""One exception, arrival to resolution. Each stage records its input, output and failure handling
in the run packet, which is what a person approves."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from . import intake as intake_mod
from .draft import draft, facts_for
from .erp import ERP
from .extract import extract
from .llm import LLMConfig, OpenAICompatibleClient
from .match import decide
from .resolve import match_lines, resolve

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "data" / "policy.json"


def run_one(path: str | Path, cfg: LLMConfig | None, runs_dir: Path | None = ROOT / "runs",
            policy_path: Path = POLICY, erp: ERP | None = None) -> dict:
    t0 = time.time()
    policy = json.loads(Path(policy_path).read_text())
    erp = erp or ERP()
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{Path(path).stem}"
    run_dir = (Path(runs_dir) / run_id) if runs_dir else None
    client = OpenAICompatibleClient(cfg, run_dir / "model_calls.jsonl" if run_dir else None) if cfg else None
    packet: dict = {"run_id": run_id, "source": str(path), "model": cfg.model if cfg else None, "stages": {}}

    # 1 intake (code)
    inv_in = intake_mod.read(path)
    packet["stages"]["intake"] = {k: v for k, v in inv_in.items() if k != "text"}

    # 2 extract (model, validated by code)
    if client is None:
        packet["stages"]["extract"] = {"error": "no model configured; extraction needs one", "attempts": 0}
        return _finish(packet, "escalate", "no model available to read the invoice", t0, run_dir, client)
    invoice, info = extract(client, inv_in["text"])
    packet["stages"]["extract"] = {**info, "invoice": invoice}
    if not invoice:
        return _finish(packet, "escalate", f"the invoice could not be read reliably: {info['error']}", t0, run_dir, client)

    # 3 resolve references (code; model with tools only when references are missing)
    resolved = resolve(client, erp, invoice, inv_in)
    line_to_po, notes = match_lines(client, invoice, resolved["pos"]) if resolved["pos"] else ({}, [])
    packet["stages"]["resolve"] = {"supplier": (resolved["supplier"] or {}).get("name"),
                                   "purchase_orders": [po["po_number"] for po in resolved["pos"]],
                                   "how": resolved["how"] + notes, "flags": resolved["flags"],
                                   "model_tool_calls": resolved["model_trace"], "line_to_po": {str(k): v for k, v in line_to_po.items()}}

    # 4 match and decide (code only)
    outcome = decide(erp, policy, invoice, resolved, inv_in, line_to_po)
    packet["stages"]["decide"] = outcome

    # 5 draft the supplier email where one is needed (model, fact-checked, template fallback)
    if outcome["email_needed"]:
        facts = facts_for(invoice, resolved, outcome)
        packet["stages"]["draft"] = {"facts": facts, **draft(client, facts, erp.supplier_names())}
    return _finish(packet, outcome["decision"], None, t0, run_dir, client)


def _finish(packet: dict, decision: str, reason: str | None, t0: float, run_dir: Path | None,
            client: OpenAICompatibleClient | None) -> dict:
    out = packet["stages"].get("decide") or {"decision": decision, "payable": 0.0, "auto_release": False,
                                            "approver": "AP specialist", "findings": [{"code": "escalate", "severity": "critical", "detail": reason}],
                                            "email_needed": False}
    packet["resolution"] = {"decision": out["decision"], "payable": out["payable"], "auto_release": out["auto_release"],
                            "approver": out["approver"], "summary": summary_line(packet)}
    calls = client.calls if client else []
    packet["model_usage"] = {"calls": len(calls), "seconds": round(sum(c.get("seconds", 0) for c in calls), 1),
                             "prompt_tokens": sum((c.get("usage") or {}).get("prompt_tokens", 0) for c in calls),
                             "completion_tokens": sum((c.get("usage") or {}).get("completion_tokens", 0) for c in calls),
                             "reasoning_tokens": sum(((c.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0) for c in calls),
                             "stages": [c.get("stage") for c in calls]}
    packet["seconds"] = round(time.time() - t0, 1)
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "packet.json").write_text(json.dumps(packet, indent=1, default=str))
        (run_dir / "summary.md").write_text(render(packet))
    return packet


def summary_line(packet: dict) -> str:
    d = packet["stages"].get("decide") or {}
    inv = packet["stages"].get("extract", {}).get("invoice") or {}
    res = packet["stages"].get("resolve", {})
    who = res.get("supplier") or inv.get("supplier_name") or "unknown supplier"
    return (f"{inv.get('invoice_number', '?')} from {who} for {inv.get('total', 0) or 0:.2f} against "
            f"{', '.join(res.get('purchase_orders', [])) or 'no PO'}: {d.get('decision', 'escalate').replace('_', ' ')}, "
            f"pay {d.get('payable', 0):.2f}" + (" (auto-released)" if d.get("auto_release") else f", approver: {d.get('approver')}"))


def render(packet: dict) -> str:
    s = packet["stages"]
    d = s.get("decide") or {}
    lines = [f"# {packet['run_id']}", "", f"**Resolution:** {packet['resolution']['summary']}", ""]
    lines += ["## Findings"] + [f"- [{f['severity']}] {f['code']}: {f['detail']}" for f in d.get("findings", [])] or ["- none"]
    if s.get("resolve"):
        lines += ["", "## How the references were resolved"] + [f"- {h}" for h in s["resolve"]["how"]]
        for t in s["resolve"].get("model_tool_calls", []):
            lines.append(f"- model called {t['tool']}({json.dumps(t['args'])})")
    if s.get("draft"):
        lines += ["", f"## Email to the supplier (written by {s['draft']['written_by']}"
                  + (f"; model draft rejected: {s['draft']['model_rejected']}" if s['draft']['model_rejected'] else "") + ")", "",
                  s["draft"]["email"]]
    u = packet.get("model_usage", {})
    lines += ["", f"Model: {packet.get('model')} | calls {u.get('calls')} | {u.get('seconds')} s | tokens in {u.get('prompt_tokens')} "
              f"out {u.get('completion_tokens')} (reasoning {u.get('reasoning_tokens')}) | total {packet.get('seconds')} s"]
    return "\n".join(lines) + "\n"
