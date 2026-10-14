"""Streamlit interface for the Part 1 model exploration."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from lfm_client import list_models, metrics_dict, streamed_chat
from tool_demo import run_demo

st.set_page_config(page_title="LFM2.5 Local Lab", page_icon="🧪", layout="wide")
st.title("LFM2.5-2.6B Local Lab")
st.caption("Running locally through LM Studio on an Apple M2 with 8 GB unified memory")

with st.sidebar:
    st.subheader("Runtime")
    try:
        models = list_models().get("data", [])
        st.success(f"LM Studio connected · {len(models)} model(s) available")
    except Exception as exc:
        st.error(f"LM Studio is unavailable: {exc}")
    st.markdown(
        """
        **Loaded configuration**

        - Model: LFM2.5-2.6B
        - Quantization: Q5_K_M
        - Context: 4,096 tokens
        - GPU offload: 100%
        """
    )

overview_tab, chat_tab, tool_tab, benchmark_tab = st.tabs(
    ["Architecture", "Chat", "Tool call", "Benchmarks"]
)

with overview_tab:
    st.subheader("Hybrid architecture")
    col1, col2, col3 = st.columns(3)
    col1.metric("Parameters", "2.69B")
    col2.metric("Convolution blocks", "22 / 30")
    col3.metric("Attention blocks", "8 / 30")
    st.markdown(
        """
        Most layers use gated short convolutions with a tiny fixed state.
        Eight grouped-query-attention layers preserve long-range mixing while
        reducing the growing KV cache compared with an all-attention model.

        **Measured locally**

        - Model file: 1.94 GB
        - Loaded worker RSS: approximately 1.86 GiB
        - Initial generation: approximately 31 tokens/second
        - Time to first token: approximately 0.42 seconds
        """
    )

with chat_tab:
    prompt = st.text_area(
        "Prompt",
        "Explain when a small on-device model is preferable to a cloud frontier model.",
        height=120,
    )
    if st.button("Generate", type="primary"):
        with st.spinner("Running locally..."):
            response, metrics = streamed_chat(
                [{"role": "user", "content": prompt}], max_tokens=512
            )
        st.write(response["content"] or "No visible answer was generated.")
        with st.expander("Reasoning and metrics"):
            st.code(response["reasoning_content"])
            st.json(metrics_dict(metrics))

with tool_tab:
    tool_prompt = st.text_area(
        "Shipping request",
        "Quote shipment ORD-1042. It weighs 12.5 kg, goes to zone 3, and needs "
        "expedited delivery. Use the shipping tool; do not calculate it yourself.",
        height=120,
    )
    if st.button("Run tool demo", type="primary"):
        with st.spinner("Selecting, validating, and executing the tool..."):
            result = run_demo(tool_prompt)
        st.subheader("Model-selected arguments")
        st.json(result["validated_arguments"])
        st.subheader("Deterministic tool result")
        st.json(result["tool_result"])
        st.subheader("Final model response")
        st.write(result["final_answer"])
        with st.expander("Full trace"):
            st.json(result)

with benchmark_tab:
    results_path = Path(__file__).parent / "benchmark-results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text())
        st.dataframe(results["results"], width="stretch")
        st.caption("Run `uv run python benchmark.py` to refresh these measurements.")
    else:
        st.info("Run `uv run python benchmark.py` to generate benchmark results.")
