"""Measure LFM latency and memory through LM Studio's local API."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from lfm_client import list_models, metrics_dict, streamed_chat

PROMPT_SIZES = {
    "short": 40,
    "medium": 400,
    "long": 1600,
}


def make_prompt(word_count: int, label: str) -> str:
    facts = [
        f"Record {i}: sensor {i % 7} reported status normal in zone {i % 5}."
        for i in range(max(1, word_count // 9))
    ]
    verification_code = {
        "short": "EMBER-104",
        "medium": "VIOLET-731",
        "long": "COPPER-592",
    }[label]
    return (
        f"Dataset {label}. Read the records. "
        + " ".join(facts)
        + f" Final record: the verification code is {verification_code}. "
        "Reply with only that verification code."
    )


def main() -> None:
    available = list_models()
    print("Connected to LM Studio:", json.dumps(available, indent=2))

    results = []
    for label, approximate_words in PROMPT_SIZES.items():
        print(f"\nRunning {label} prompt...")
        response, metrics = streamed_chat(
            [{"role": "user", "content": make_prompt(approximate_words, label)}],
            max_tokens=256,
        )
        result = {
            "label": label,
            "approximate_input_words": approximate_words,
            **metrics_dict(metrics),
            "answer": response["content"],
        }
        results.append(result)
        print(json.dumps(result, indent=2))

    output = {
        "created_at": datetime.now().astimezone().isoformat(),
        "model": "LFM2.5-2.6B Q5_K_M",
        "runtime": "LM Studio",
        "context_length": 4096,
        "results": results,
        "notes": [
            "Time to first token includes local API and prompt-processing overhead.",
            "Generation rate includes both hidden reasoning and visible answer tokens.",
            "RSS is the resident memory of the local model worker process.",
        ],
    }
    output_path = Path(__file__).parent / "benchmark-results.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"\nSaved {output_path}")


if __name__ == "__main__":
    main()
