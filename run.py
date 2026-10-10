#!/usr/bin/env python3
"""Resolve one supplier invoice exception, or a folder of them.

    python3 run.py --invoice data/invoices/inv_03_large_price_variance.txt --llm-profile lmstudio
    python3 run.py --all data/invoices --llm-profile lmstudio

Writes runs/<timestamp>_<invoice>/packet.json, summary.md and model_calls.jsonl.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent.llm import resolve_config  # noqa: E402
from agent.pipeline import render, run_one  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--invoice", help="one invoice file (.txt, .eml-style text, or .pdf)")
    ap.add_argument("--all", help="a folder of invoices")
    ap.add_argument("--llm-profile", default="lmstudio", help="profile in data/model_profiles.json (default lmstudio; 'none' = no model)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    cfg = resolve_config(args.llm_profile)
    paths = sorted(Path(args.all).glob("*.txt")) + sorted(Path(args.all).glob("*.pdf")) if args.all else [Path(args.invoice)]
    for p in paths:
        packet = run_one(p, cfg)
        print(render(packet) if not args.quiet else packet["resolution"]["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
