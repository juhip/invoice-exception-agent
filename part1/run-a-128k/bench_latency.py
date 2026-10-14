#!/usr/bin/env python3
"""
Part 1 benchmark: measure prefill (TTFT) and decode (tok/s) for LFM2.5-2.6B
across context lengths, plus resident memory (RSS) of the inference engine.

Requires: LM Studio server running with lfm2.5-2.6b loaded (lms server start; lms load lfm2.5-2.6b)

Usage: python3 bench_latency.py
Writes: bench_results.md
"""

import json
import subprocess
import time
import urllib.request

API = "http://localhost:1234/v1/chat/completions"
MODEL = "lfm2.5-2.6b"
ENGINE = "llama-server"

# Target prompt sizes in tokens (approximate; actuals read back from usage)
TARGETS = [512, 2_000, 8_000, 32_000, 64_000, 100_000]

FILLER_TEMPLATE = (
    "Acme Industrial Supply received shipment {n} from vendor V{m} on "
    "2026-03-{d}. The packing slip lists {q} units of part P-{n} at unit price "
    "${p}. The receiving clerk noted a {qty} discrepancy against PO-20{k}. "
    "The invoice references a partially-applied credit memo CM-{n} dated last "
    "quarter. Finance flagged it because the extended total does not match the "
    "receiving report, and the freight terms were FOB origin instead of FOB "
    "destination. The vendor contact email bounced twice. "
)


def build_filler(approx_tokens: int) -> str:
    """~3.5 chars/token for English; build slightly more than needed."""
    chars = int(approx_tokens * 4.2)
    parts, n = [], 0
    while sum(len(p) for p in parts) < chars:
        n += 1
        parts.append(FILLER_TEMPLATE.format(n=n, m=n % 40, k=n % 99, d=(n % 28) + 1,
                                            q=(n * 7) % 90 + 3,
                                            p=(n * 13) % 400 + 5, qty=n % 3))
    return "".join(parts)


def engine_rss_mb() -> float:
    out = subprocess.run(["ps", "axo", "rss,comm"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if ENGINE in line:
            return int(line.split()[0]) / 1024.0
    return 0.0


def stream_one(prompt: str, max_tokens: int = 250):
    """Stream one completion. Returns (ttft_s, decode_tok_s, prompt_tokens, completion_tokens)."""
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a terse assistant. Do not show your reasoning."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode()

    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    ttft = None
    token_times = []
    prompt_tokens = completion_tokens = 0
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if obj.get("usage"):
                prompt_tokens = obj["usage"].get("prompt_tokens", 0)
                completion_tokens = obj["usage"].get("completion_tokens", 0)
            choices = obj.get("choices") or [{}]
            delta = choices[0].get("delta", {}) if choices else {}
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or ""
            now = time.perf_counter()
            if (content.strip() or reasoning.strip()) and ttft is None:  # first token of ANY kind
                ttft = now - t0
            if content.strip():  # visible tokens only
                token_times.append(now)
    total = time.perf_counter() - t0
    if token_times and len(token_times) > 2:
        # decode rate over the visible tokens after the first
        span = token_times[-1] - token_times[0]
        decode_rate = (len(token_times) - 1) / span if span > 0 else 0.0
    else:
        decode_rate = 0.0
    # honest throughput: ALL generated tokens (incl. hidden reasoning) over decode phase
    all_rate = (completion_tokens - 1) / (total - ttft) if (ttft and completion_tokens > 1) else 0.0
    return ttft, decode_rate, all_rate, prompt_tokens, completion_tokens, total


def main():
    print(f"Engine RSS before warmup: {engine_rss_mb():.0f} MB")
    print("Warming up...")

    # warm-up (first request after load compiles kernels etc.)
    for _ in range(3):
        stream_one("Reply with the single word: ready.", max_tokens=8)
    print(f"Engine RSS after warmup: {engine_rss_mb():.0f} MB")

    rows = []
    for target in TARGETS:
        filler = build_filler(target)
        prompt = filler + "\n\nHow many units of part P-2 were mentioned in the first shipment entry? Answer with a number only."
        ttft, rate, all_rate, ptoks, ctoks, total = stream_one(prompt)
        time.sleep(1.0)
        rss = engine_rss_mb()
        rows.append((ptoks, ttft, rate, all_rate, rss, total))
        print(f"ctx~{target:>7}: prompt_tokens={ptoks:>7}  TTFT={ttft:6.2f}s  "
              f"decode={rate:6.1f}/{all_rate:6.1f} tok/s  RSS={rss:7.0f} MB  total={total:6.2f}s")

    md = ["# LFM2.5-2.6B latency/memory benchmark (local, LM Studio, Apple M2 / 8 GB)\n",
          "| Prompt tokens | TTFT (s) | Decode, visible (tok/s) | Decode, all tokens (tok/s) | Engine RSS (MB) | Total req (s) |",
          "|---|---|---|---|---|---|"]
    for ptoks, ttft, rate, all_rate, rss, total in rows:
        md.append(f"| {ptoks} | {ttft:.2f} | {rate:.1f} | {all_rate:.1f} | {rss:.0f} | {total:.2f} |")
    with open("bench_results.md", "w") as f:
        f.write("\n".join(md) + "\n")
    print("\nWrote bench_results.md")


if __name__ == "__main__":
    main()
