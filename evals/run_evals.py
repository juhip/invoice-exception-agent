#!/usr/bin/env python3
"""Run every labeled invoice through the agent and grade it against data/invoices/expected.json.

    python3 evals/run_evals.py --llm-profile lmstudio        # the real model
    python3 evals/run_evals.py --repeat 2                    # also measures run-to-run consistency

Grades, per invoice: purchase orders found, decision, amount to pay, every expected exception
present, email drafted when needed. Also reports per-stage model behaviour: extraction attempts,
whether the model's email passed the fact check, calls, tokens, seconds. Writes docs/validation.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.llm import resolve_config  # noqa: E402
from agent.pipeline import run_one  # noqa: E402

INV = ROOT / "data" / "invoices"


def grade(packet: dict, exp: dict) -> dict:
    s = packet["stages"]
    d = s.get("decide") or {}
    res = packet["resolution"]
    codes = {f["code"] for f in d.get("findings", [])}
    return {"po": sorted(s.get("resolve", {}).get("purchase_orders", [])) == sorted(exp["po"]),
            "decision": res["decision"] == exp["decision"],
            "pay": abs(res["payable"] - exp["pay"]) < 0.01,
            "exceptions": set(exp["exceptions"]) <= codes,
            "email": (("draft" in s) == exp["email"]),
            "extract_attempts": s.get("extract", {}).get("attempts"),
            "email_by": s.get("draft", {}).get("written_by"),
            "email_rejected": s.get("draft", {}).get("model_rejected"),
            "calls": packet["model_usage"]["calls"], "seconds": packet["seconds"],
            "reasoning_share": round(packet["model_usage"]["reasoning_tokens"] / max(packet["model_usage"]["completion_tokens"], 1), 2)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-profile", default="lmstudio")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--only", help="substring filter on invoice file names")
    args = ap.parse_args(argv)
    cfg = resolve_config(args.llm_profile)
    expected = {k: v for k, v in json.loads((INV / "expected.json").read_text()).items() if not k.startswith("_")}
    rows, decisions = [], {}
    for rep in range(args.repeat):
        for name, exp in expected.items():
            if args.only and args.only not in name:
                continue
            packet = run_one(INV / name, cfg, runs_dir=ROOT / "runs" / "evals")
            g = grade(packet, exp)
            g.update({"invoice": name, "rep": rep + 1, "got": packet["resolution"]["decision"], "want": exp["decision"],
                      "got_pay": packet["resolution"]["payable"]})
            rows.append(g)
            decisions.setdefault(name, []).append(packet["resolution"]["decision"])
            ok = all(g[k] for k in ("po", "decision", "pay", "exceptions", "email"))
            print(f"{'PASS' if ok else 'FAIL'} {name:40s} {g['got']:18s} pay {g['got_pay']:9.2f} | extract x{g['extract_attempts']} "
                  f"| email {g['email_by'] or '-'} | {g['calls']} calls {g['seconds']:.0f}s", flush=True)
    write_report(rows, decisions, cfg.model if cfg else "none", args.repeat)
    return 0


def write_report(rows, decisions, model, repeat):
    n = len(rows)
    checks = ("po", "decision", "pay", "exceptions", "email")
    full = sum(all(r[k] for k in checks) for r in rows)
    lines = [f"# Validation: {model}", "", f"Run {datetime.now():%Y-%m-%d %H:%M} on an Apple M2, 8 GB, LM Studio. "
             f"{len(decisions)} labeled invoices x {repeat} repetition(s) = {n} runs.", "",
             f"**Fully correct end to end: {full} of {n}.** A run is fully correct when the purchase orders, the decision, "
             "the amount to pay, every expected exception code and the email-needed flag all match the label.", "",
             "| Check | Correct |", "|---|---|"]
    for k in checks:
        lines.append(f"| {k} | {sum(r[k] for r in rows)} / {n} |")
    lines += ["", "## Per invoice", "", "| Invoice | Want | Got | Pay | Extract attempts | Email by | Calls | Seconds | Reasoning share |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        mark = "" if all(r[k] for k in checks) else " **(wrong)**"
        lines.append(f"| {r['invoice']} (rep {r['rep']}) | {r['want']} | {r['got']}{mark} | {r['got_pay']:.2f} | {r['extract_attempts']} | "
                     f"{r['email_by'] or '-'}{' (rejected: ' + r['email_rejected'] + ')' if r['email_rejected'] else ''} | {r['calls']} | {r['seconds']:.0f} | {r['reasoning_share']:.0%} |")
    if repeat > 1:
        unstable = [k for k, v in decisions.items() if len(set(v)) > 1]
        lines += ["", "## Run-to-run consistency", "", f"Invoices whose decision changed between repetitions: {', '.join(unstable) or 'none'}."]
    att = [r["extract_attempts"] for r in rows if r["extract_attempts"]]
    emails = [r for r in rows if r["email_by"]]
    lines += ["", "## Model behaviour", "",
              f"- Extraction needed a retry on {sum(a > 1 for a in att)} of {len(att)} runs.",
              f"- Emails: {sum(r['email_by'] == 'model' for r in emails)} written by the model and accepted, "
              f"{sum(r['email_by'] == 'template' for r in emails)} fell back to the template"
              + (" (" + "; ".join(f"{r['invoice']}: {r['email_rejected']}" for r in emails if r['email_rejected']) + ")" if any(r['email_rejected'] for r in emails) else "") + ".",
              f"- Median seconds per invoice: {sorted(r['seconds'] for r in rows)[n // 2]:.0f}; median reasoning share of output tokens: "
              f"{sorted(r['reasoning_share'] for r in rows)[n // 2]:.0%}.", ""]
    out = ROOT / "docs" / "validation.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"\n{full}/{n} fully correct. Report: {out}")


if __name__ == "__main__":
    raise SystemExit(main())
