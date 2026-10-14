# Part 1: LFM2.5-2.6B on an 8 GB laptop

Before building the agent, I ran LFM2.5-2.6B locally to measure speed and
memory and to check native tool calling. Both runs used the same model
(Q5_K_M GGUF, 1.94 GB) in LM Studio on an Apple M2 with 8 GB, on 2 October 2026.
The only setup difference was the context window.

| | Run A: `run-a-128k/` | Run B: `run-b-4k/` |
|---|---|---|
| Context window | 128K | 4K |
| Prompt sizes | 581 to 95,510 tokens | 97 to 2,693 tokens |
| Generation speed | ~30 tok/s at 581 tokens, then 8 to 12 tok/s | ~33 tok/s at every size |
| Time to first token | 1.9 s, up to 7.7 min at 95K | 0.6 to 7.8 s |
| Model memory | 2.4 to 2.8 GB | 1.8 to 1.9 GB |
| Answers checked | No (hidden reasoning used the whole budget) | Yes, 3 of 3 correct |
| Tool demo | Purchase-order lookup from a free-text invoice | Shipping quote, with a Streamlit lab and tests |

Run A was about 3x slower than Run B at the same prompt size (about 2K tokens).
My best guess is memory pressure from the 128K window on an 8 GB machine, but I
have not tested it. `benchmark_comparison.md` sets out what holds in both runs
and what I would not claim yet.

## What is here

| Path | What |
|---|---|
| `benchmark_comparison.md` | the two runs side by side: what holds, what is unproven |
| `run-a-128k/PART1_FINDINGS.md` | Run A measurements, tool-call trace, open questions |
| `run-a-128k/bench_results.md` | Run A raw benchmark table |
| `run-a-128k/bench_latency.py` | Run A streaming latency and memory benchmark |
| `run-a-128k/tool_call_demo.py` | Run A purchase-order tool-call demo |
| `run-a-128k/check_local_model_from_lab_repo.py` | quick reachability, speed and tool-call check |
| `run-b-4k/PART1_NOTES.md` | Run B setup, measurements, tool call, what surprised me, what I still don't understand |
| `run-b-4k/benchmark-results.json` | Run B raw results |
| `run-b-4k/README.md` | how to run Run B: benchmark, tool demo, Streamlit lab |
| `run-b-4k/outputs/LFM2.5-Part-1-CTO-Brief.docx` | Part 1 summary for a technical decision-maker |

Run B runs with `uv sync`, then the commands in `run-b-4k/README.md`. LM Studio
must be serving the model at `http://127.0.0.1:1234`.
