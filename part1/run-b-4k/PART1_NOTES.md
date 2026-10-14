# Part 1: Hands-on notes

## Setup

I ran LiquidAI's LFM2.5-2.6B entirely on an Apple M2 MacBook with 8 GB of
unified memory. I used the official Q5_K_M GGUF in LM Studio, with all layers
offloaded to the Apple GPU and a 4,096-token runtime context.

The model has 2.69 billion parameters and a 128K trained context window. Its 30
layers are not a standard Transformer stack: 22 are double-gated short
convolution blocks and eight are grouped-query-attention blocks. The attention
layers use 32 query heads but only eight key/value heads. This architecture
retains occasional long-range mixing while reducing the amount of KV state that
grows with the context.

The Q5_K_M file is 1.94 GB on disk, or 1.81 GiB. After inference, the LM Studio
model worker used approximately 1.86-1.91 GiB of resident memory. LM Studio
estimated 2.02 GiB total memory at a 4K context, 3.05 GiB at 32K, and 6.58 GiB
at 128K. The 128K setting exceeded the runtime's resource guardrails on this
8 GB machine, so advertised context support does not mean every device can use
the full window.

## Measurements

I used a retrieval task with the answer at the end of each prompt. Each row is
one local request. Time to first token includes prompt processing and local API
overhead. Generation throughput includes hidden reasoning and visible output.

| Prompt tokens | Time to first token | Total latency | Generation rate | Answer |
|---:|---:|---:|---:|---|
| 97 | 0.63 s | 4.80 s | 33.55 tok/s | Correct |
| 698 | 2.08 s | 7.18 s | 32.73 tok/s | Correct |
| 2,693 | 7.81 s | 12.58 s | 32.50 tok/s | Correct |

Generation remained close to 33 tokens per second as the prompt grew. Prompt
processing was much faster than generation, approximately 335-345 prompt
tokens per second in the two larger cases. These are measurements from my
machine, not vendor benchmark numbers.

## Tool call

I gave the model a request for shipment `ORD-1042`: 12.5 kg, destination zone
3, expedited delivery. I exposed one function with a JSON schema. The model
selected `calculate_shipping_quote` and supplied:

```json
{
  "shipment_id": "ORD-1042",
  "weight_kg": 12.5,
  "destination_zone": 3,
  "expedited": true
}
```

The application checked the function against an allowlist, parsed the arguments
as JSON, enforced the exact schema and business ranges, and then called a real
deterministic Python function. The tool returned a quote of `$32.60` and a
two-business-day estimate. After receiving that result, the model explained
the quote correctly.

The model does not directly execute arbitrary Python. It proposes a structured
call, and the host application decides whether and how to execute it. That
boundary is essential for reliability and security.

## What surprised me

The first surprise was that a 2.69B-parameter model was genuinely interactive
on an 8 GB laptop. It stayed below 2 GiB of resident model-worker memory and
generated around 33 tokens per second while still performing native tool
selection.

The second surprise was how much work happened in hidden reasoning. A request
limited to 128 completion tokens spent 127 on reasoning and returned no visible
answer. Even a task whose visible answer was a single code used 132 hidden
reasoning tokens and eight visible tokens. Token budgets for this model must
cover reasoning, not just the response shown to the user.

The third surprise was the quality of argument extraction. From ordinary prose,
the model correctly mapped an identifier, decimal weight, integer zone, and
implicit boolean ("needs expedited delivery") into a typed function call.

## What was harder than expected

Measuring "latency" required separating several different quantities: model
load time, time to first token, prompt-processing time, decode rate, and total
request time. A single wall-clock measurement would hide why longer prompts
felt slower.

Memory was also less simple than the model's file size. The weights, attention
KV cache, convolution state, runtime buffers, prompt cache, and operating-system
memory accounting are different things. On Apple Silicon, CPU and GPU use the
same physical memory, so familiar dedicated-VRAM measurements do not apply.

The reasoning behavior also forced me to change my first benchmark. A counting
prompt caused the model to use the full completion budget without returning an
answer. I replaced it with a controlled retrieval task so prompt length, rather
than task complexity, was the main variable.

## What I still do not understand

- How much quality the Q5_K_M quantization loses relative to BF16 on the
  agentic tasks that matter for a customer.
- Why LM Studio's full-context memory estimate grows faster than a simple
  calculation based only on the eight attention-layer KV caches. Runtime
  buffers, parallel slots, and context checkpointing may explain the gap, but I
  have not isolated each contribution.
- How reliable native tool selection remains when requests are ambiguous,
  required fields are missing, or several tools have overlapping descriptions.
- How retrieval quality changes near the 128K trained context limit.
- Whether reasoning length can be controlled reliably without reducing tool
  accuracy.

## Sources

- [LFM2.5-2.6B model card](https://huggingface.co/LiquidAI/LFM2.5-2.6B)
- [LFM2.5-2.6B GGUF files](https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF)
- [LFM2 technical report](https://arxiv.org/abs/2511.23404)
