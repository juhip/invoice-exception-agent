# LFM2.5-2.6B Part 1 Lab

This project runs LiquidAI's LFM2.5-2.6B locally through LM Studio, measures
latency and memory, and demonstrates a native tool call.

## Current local configuration

- Hardware: Apple M2, 8 GB unified memory
- Runtime: LM Studio local server at `http://127.0.0.1:1234`
- Model: LFM2.5-2.6B
- Quantization: Q5_K_M, 1.94 GB on disk
- Context configured for the experiment: 4,096 tokens
- GPU offload: 100%

## Run

Start LM Studio and load the model:

```bash
lms server start
lms load lfm2.5-2.6b --context-length 4096 --gpu max \
  --identifier lfm2.5-2.6b --yes
```

Install the small Python environment:

```bash
uv sync
```

Run the benchmark:

```bash
uv run python benchmark.py
```

Run the tool-calling example:

```bash
uv run python tool_demo.py
```

Open the visual lab:

```bash
uv run streamlit run app.py
```

## What the scripts measure

- End-to-end request latency
- Time to first generated token
- Effective prompt-processing rate
- Generation throughput, including hidden reasoning tokens
- Resident memory of the LM Studio model worker
- Hidden reasoning versus visible response token use

These are client-side measurements. Time to first token includes local API
overhead, and operating-system RSS is not the same as peak allocated memory.

## Safety properties of the tool demo

The model can select a tool and propose arguments, but it cannot execute
arbitrary code. The host application:

1. Checks the requested tool against an allowlist.
2. Parses arguments as JSON, never with `eval`.
3. Requires an exact set of argument names.
4. Validates types and business ranges.
5. Executes a deterministic function.
6. Returns the result to the model for explanation.
