import json
import unittest

from tool_demo import calculate_shipping_quote, validate_tool_call


class ShippingToolTests(unittest.TestCase):
    def test_quote_is_deterministic(self) -> None:
        result = calculate_shipping_quote(
            shipment_id="ORD-1042",
            weight_kg=12.5,
            destination_zone=3,
            expedited=True,
        )
        self.assertEqual(result["quoted_price"], 32.60)
        self.assertEqual(result["estimated_business_days"], 2)

    def test_rejects_out_of_range_zone(self) -> None:
        with self.assertRaises(ValueError):
            calculate_shipping_quote("ORD-1042", 12.5, 8, True)

    def test_rejects_unknown_tool(self) -> None:
        with self.assertRaises(ValueError):
            validate_tool_call(
                {
                    "function": {
                        "name": "run_anything",
                        "arguments": json.dumps(
                            {
                                "shipment_id": "ORD-1042",
                                "weight_kg": 12.5,
                                "destination_zone": 3,
                                "expedited": True,
                            }
                        ),
                    }
                }
            )

    def test_rejects_extra_arguments(self) -> None:
        with self.assertRaises(ValueError):
            validate_tool_call(
                {
                    "function": {
                        "name": "calculate_shipping_quote",
                        "arguments": json.dumps(
                            {
                                "shipment_id": "ORD-1042",
                                "weight_kg": 12.5,
                                "destination_zone": 3,
                                "expedited": True,
                                "shell_command": "ignored",
                            }
                        ),
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
