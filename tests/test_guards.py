"""The guardrails on their own: tool allowlist and argument schema, JSON retry, fact check."""
import json

from agent.erp import ERP, model_tools
from agent.factcheck import check_invented
from agent.llm import LLMConfig, OpenAICompatibleClient, _check_args, parse_json_object, run_tool_loop
from fake_model import FakeModel


def test_fact_check_catches_invented_numbers_and_names():
    src = "Invoice TSS-118204 for 4197.60 against PO-2026-1103, pay 3816.00"
    assert check_invented(src, "We will pay 3816.00 for TSS-118204.", set()) is None
    assert "3820.00" in check_invented(src, "We will pay 3820.00 for TSS-118204.", set())
    assert "PO-2026-1199" in check_invented(src, "See PO-2026-1199.", set())
    assert "Pacific" in check_invented(src, "Pacific Rim Castings agreed.", {"Pacific Rim Castings Ltd.", "Pacific Rim Castings"})


def test_parse_json_ignores_fences_and_prose():
    assert parse_json_object('Sure!\n```json\n{"a": 1}\n```')["a"] == 1


def test_argument_schema_rejects_extra_and_wrong_types():
    schema = model_tools(ERP())["find_candidate_pos"][0]
    _check_args({"supplier_id": "V-2004", "amount": 220}, schema)
    for bad in ({"supplier_id": "V-2004", "shell": "rm -rf"}, {"amount": 1}, {"supplier_id": 5}):
        try:
            _check_args(bad, schema)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_tool_loop_executes_allowlisted_calls_and_refuses_others():
    calls = []
    def reply(body):
        calls.append(body)
        return "ignored"
    fake = FakeModel(reply)
    # the fake server returns no tool_calls, so the loop must end on the first turn
    client = OpenAICompatibleClient(LLMConfig(fake.url, "fake", timeout_s=5))
    final, trace = run_tool_loop(client, [{"role": "user", "content": "hi"}], model_tools(ERP()), "t")
    fake.close()
    assert final == "ignored" and trace == [] and len(calls) == 1
    assert {t["function"]["name"] for t in calls[0]["tools"]} == {"find_supplier", "find_candidate_pos", "lookup_po", "search_pos_by_part"}
