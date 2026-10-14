"""Demonstrate native LFM tool selection and safe local execution."""

from __future__ import annotations

import json
from typing import Any

from lfm_client import metrics_dict, streamed_chat

SHIPPING_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_shipping_quote",
        "description": (
            "Calculate a shipping quote from package weight, destination zone, "
            "and service level."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "shipment_id": {
                    "type": "string",
                    "description": "Customer-visible shipment identifier",
                },
                "weight_kg": {"type": "number", "exclusiveMinimum": 0},
                "destination_zone": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                },
                "expedited": {"type": "boolean"},
            },
            "required": [
                "shipment_id",
                "weight_kg",
                "destination_zone",
                "expedited",
            ],
            "additionalProperties": False,
        },
    },
}


def calculate_shipping_quote(
    shipment_id: str,
    weight_kg: float,
    destination_zone: int,
    expedited: bool,
) -> dict[str, Any]:
    """A deterministic backend function that the model cannot approximate."""
    if not shipment_id or len(shipment_id) > 50:
        raise ValueError("shipment_id must contain 1-50 characters")
    if isinstance(weight_kg, bool) or not isinstance(weight_kg, (int, float)):
        raise TypeError("weight_kg must be numeric")
    if not 0 < weight_kg <= 100:
        raise ValueError("weight_kg must be between 0 and 100")
    if isinstance(destination_zone, bool) or not isinstance(destination_zone, int):
        raise TypeError("destination_zone must be an integer")
    if destination_zone not in range(1, 6):
        raise ValueError("destination_zone must be between 1 and 5")
    if not isinstance(expedited, bool):
        raise TypeError("expedited must be a boolean")

    base_charge = 4.50
    weight_charge = weight_kg * 0.85
    zone_charge = destination_zone * 1.75
    subtotal = base_charge + weight_charge + zone_charge
    service_multiplier = 1.60 if expedited else 1.0
    total = round(subtotal * service_multiplier, 2)
    return {
        "shipment_id": shipment_id,
        "currency": "USD",
        "quoted_price": total,
        "service": "expedited" if expedited else "standard",
        "estimated_business_days": (
            max(1, destination_zone - 1) if expedited else destination_zone + 3
        ),
        "calculation": {
            "base_charge": base_charge,
            "weight_charge": round(weight_charge, 2),
            "zone_charge": round(zone_charge, 2),
            "service_multiplier": service_multiplier,
        },
    }


def validate_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    if function.get("name") != "calculate_shipping_quote":
        raise ValueError(f"Tool is not allowlisted: {function.get('name')!r}")
    arguments = json.loads(function.get("arguments") or "{}")
    expected = {"shipment_id", "weight_kg", "destination_zone", "expedited"}
    if set(arguments) != expected:
        raise ValueError(
            f"Arguments must be exactly {sorted(expected)}; got {sorted(arguments)}"
        )
    return arguments


def run_demo(user_request: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_request}]
    decision, decision_metrics = streamed_chat(
        messages, tools=[SHIPPING_TOOL], max_tokens=512
    )
    if not decision["tool_calls"]:
        raise RuntimeError("The model did not request a tool call")

    tool_call = decision["tool_calls"][0]
    arguments = validate_tool_call(tool_call)
    tool_result = calculate_shipping_quote(**arguments)

    messages.extend(
        [
            {
                "role": "assistant",
                "content": decision["content"] or None,
                "tool_calls": decision["tool_calls"],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result),
            },
        ]
    )
    final, final_metrics = streamed_chat(messages, tools=[SHIPPING_TOOL], max_tokens=512)
    return {
        "user_request": user_request,
        "model_reasoning": decision["reasoning_content"],
        "tool_call": tool_call,
        "validated_arguments": arguments,
        "tool_result": tool_result,
        "final_answer": final["content"],
        "decision_metrics": metrics_dict(decision_metrics),
        "final_answer_metrics": metrics_dict(final_metrics),
    }


def main() -> None:
    result = run_demo(
        "Quote shipment ORD-1042. It weighs 12.5 kg, goes to zone 3, and needs "
        "expedited delivery. Use the shipping tool; do not calculate it yourself."
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
