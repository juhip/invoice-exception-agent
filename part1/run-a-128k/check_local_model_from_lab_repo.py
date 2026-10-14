"""Part 1 of the Liquid exercise: is a local model reachable, how fast, how big?
Usage: python scripts/check_local_model.py <model-id> [--base-url http://localhost:1234/v1]
Start LM Studio's local server first and load LFM2.5-2.6B.

Memory note: model RAM lives in the LM Studio process, not this one. Read it from
Activity Monitor (or `ps -o rss= -p <pid>`) while this runs; the script prints a reminder."""
import json
import sys
import time
import urllib.request

model = sys.argv[1] if len(sys.argv) > 1 else "lfm2.5-2.6b"
base = sys.argv[sys.argv.index("--base-url") + 1] if "--base-url" in sys.argv else "http://localhost:1234/v1"

tools = [{"type": "function", "function": {
    "name": "get_order_total", "description": "Look up an order total.",
    "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}]
body = {"model": model, "temperature": 0, "tools": tools,
        "messages": [{"role": "user", "content": "What is the total for order A-4471?"}]}

lat = []
for i in range(3):
    t = time.perf_counter()
    req = urllib.request.Request(f"{base}/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=120))
    lat.append(time.perf_counter() - t)

usage = resp.get("usage", {})
msg = resp["choices"][0]["message"]
print(f"latency s (3 runs): {[round(x, 2) for x in lat]}")
print(f"completion tokens: {usage.get('completion_tokens')}  ->  ~{(usage.get('completion_tokens') or 0) / lat[-1]:.0f} tok/s")
print("tool call:", msg.get("tool_calls") or f"NONE (text: {msg.get('content', '')[:120]!r})")
print("Now record the LM Studio process memory from Activity Monitor.")
