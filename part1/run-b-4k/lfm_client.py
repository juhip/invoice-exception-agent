"""Small client and measurement helpers for the local LM Studio server."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests

API_BASE = os.getenv("LM_STUDIO_API_BASE", "http://127.0.0.1:1234/v1")
MODEL = os.getenv("LFM_MODEL", "lfm2.5-2.6b")
MODEL_PROCESS_PATTERN = os.getenv(
    "LFM_MODEL_PROCESS_PATTERN", "LFM2.5-2.6B-Q5_K_M.gguf"
)


@dataclass
class GenerationMetrics:
    elapsed_seconds: float
    time_to_first_token_seconds: float | None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    output_tokens: int
    generation_tokens_per_second: float | None
    effective_prompt_tokens_per_second: float | None
    model_rss_before_mib: float | None
    model_rss_after_mib: float | None


def model_rss_mib() -> float | None:
    """Return RSS for processes that have the selected model in their command."""
    found = subprocess.run(
        ["pgrep", "-f", MODEL_PROCESS_PATTERN],
        capture_output=True,
        text=True,
        check=False,
    )
    if not found.stdout.strip():
        return None

    total_kib = 0
    for pid in found.stdout.split():
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", pid],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            total_kib += int(result.stdout)
    return total_kib / 1024


def list_models() -> dict[str, Any]:
    response = requests.get(f"{API_BASE}/models", timeout=5)
    response.raise_for_status()
    return response.json()


def streamed_chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 512,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], GenerationMetrics]:
    """Run a streamed completion and collect output plus client-side metrics."""
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    rss_before = model_rss_mib()
    started_at = time.perf_counter()
    first_token_at: float | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    usage: dict[str, Any] = {}

    with requests.post(
        f"{API_BASE}/chat/completions", json=payload, stream=True, timeout=300
    ) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            if raw_line == "data: [DONE]":
                continue

            event = json.loads(raw_line[6:])
            if event.get("usage"):
                usage = event["usage"]

            for choice in event.get("choices", []):
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta", {})
                token_piece = delta.get("reasoning_content") or delta.get("content")
                if token_piece and first_token_at is None:
                    first_token_at = time.perf_counter()
                reasoning_parts.append(delta.get("reasoning_content") or "")
                content_parts.append(delta.get("content") or "")

                for call_delta in delta.get("tool_calls") or []:
                    index = call_delta.get("index", 0)
                    call = tool_calls_by_index.setdefault(
                        index,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    call["id"] += call_delta.get("id") or ""
                    function_delta = call_delta.get("function") or {}
                    call["function"]["name"] += function_delta.get("name") or ""
                    call["function"]["arguments"] += (
                        function_delta.get("arguments") or ""
                    )

    ended_at = time.perf_counter()
    rss_after = model_rss_mib()
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    reasoning_tokens = int(
        (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    )
    output_tokens = max(0, completion_tokens - reasoning_tokens)
    ttft = first_token_at - started_at if first_token_at else None
    generation_time = ended_at - (first_token_at or started_at)

    metrics = GenerationMetrics(
        elapsed_seconds=round(ended_at - started_at, 4),
        time_to_first_token_seconds=round(ttft, 4) if ttft is not None else None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        output_tokens=output_tokens,
        generation_tokens_per_second=(
            round(completion_tokens / generation_time, 2)
            if generation_time > 0
            else None
        ),
        effective_prompt_tokens_per_second=(
            round(prompt_tokens / ttft, 2) if ttft and prompt_tokens else None
        ),
        model_rss_before_mib=round(rss_before, 1) if rss_before is not None else None,
        model_rss_after_mib=round(rss_after, 1) if rss_after is not None else None,
    )
    result = {
        "role": "assistant",
        "content": "".join(content_parts).strip(),
        "reasoning_content": "".join(reasoning_parts).strip(),
        "tool_calls": [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)],
        "finish_reason": finish_reason,
    }
    return result, metrics


def metrics_dict(metrics: GenerationMetrics) -> dict[str, Any]:
    return asdict(metrics)
