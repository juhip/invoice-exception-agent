# Part 1 findings — LFM2.5-2.6B on an 8 GB M2 MacBook

Setup: LM Studio, GGUF Q5_K_M (1.94 GB), llama.cpp backend, full GPU offload,
single slot, full 128K context. No cloud, no GPU server — a consumer laptop.

## Measurements

| Prompt tokens | TTFT (s) | Prefill (tok/s) | Decode (tok/s) | Engine RSS (GB) |
|---|---|---|---|---|
| 581 | 1.9 | ~300 | 29.9 | 2.82 |
| 2,075 | 8.2 | ~250 | 10.3 | 2.78 |
| 7,746 | 41.0 | ~189 | 11.7 | 2.79 |
| 30,731 | 143.8 | ~214 | 8.9 | 2.69 |
| 61,196 | 368.5 | ~166 | 8.3 | 2.44 |
| 95,510 | 459.4 | ~208 | 10.4 | 2.39 |

Tool-call demo: given a free-text invoice, the model extracted `PO-2026-88142`
correctly, called `lookup_purchase_order()` against a mock ERP, and on the second
turn produced a correct reconciliation — flagging that the $85.33 variance was
the tax line and that freight matched the PO's cap.

## Notes for the three write-up paragraphs

### What surprised you
- Decode speed is flat as context grows (8–11 tok/s from 2K to 95K prompt
  tokens). The no-growing-KV-cache story is real and visible in my own numbers.
- Memory never ballooned: ~2.4–2.8 GB resident at every context length, and the
  128K context allocation fit alongside everything else on an 8 GB machine.
- It's a hidden-reasoning model: at every context length it spent its entire
  token budget thinking and produced no visible answer until the budget was
  raised. Small model, but "spends" like a big one when reasoning is on.
- Tool calling worked first try with a 2.6B model — argument extraction from
  messy text was exact, and it reasoned correctly about the variance.

### What was harder than you expected
- Getting an honest measurement at all. Defaults lie: LM Studio loaded the
  model with 4 parallel slots, which silently truncated every prompt over 32K —
  the first benchmark looked fine and was wrong. Real measurement meant
  controlling context length, slot count, warm-up, and token accounting
  (reasoning tokens vs. visible tokens).
- Long-context prefill is expensive on consumer hardware: ~7.5 minutes to
  ingest 100K tokens at ~200 tok/s. The architecture saves you at decode, not
  at prefill.
- The gap between advertised (220 tok/s) and measured (~10 tok/s) decode.
  Quantization path, 8 GB memory pressure, and thermal budget all matter; the
  headline number is hardware- and runtime-specific, not model-intrinsic.

### What you still don't understand (scored positively — keep honest)
- Why decode is an order of magnitude below the advertised number. Is it the
  GGUF/llama.cpp path vs. MLX? Quantization (Q5_K_M)? Memory pressure or
  thermals on 8 GB? I have not yet run the MLX build side-by-side — that's the
  obvious next experiment.
- Where exactly the memory goes: resident RSS ~2.4–2.8 GB vs. a 1.81 GB model
  file, and *decreasing* at long context (macOS compression/swap behavior?).
  I can't fully account for the delta from the outside.
- The reasoning budget: whether thinking length is controllable at inference
  time (a chat-template flag didn't take effect in my setup), and what that
  does to effective cost per useful output token.
- How the hybrid graph splits work across attention / convolution /
  recurrent layers at runtime on Metal — i.e., which part of the decode cost is
  architecture vs. runtime.
