"""The model slot: how the agent talks to LFM2.5-2.6B (or any OpenAI-compatible server).

Reused from an earlier procurement-planning agent of mine, with three additions this agent needs:
  call log      every request and raw reply is appended to a JSONL file per run (prompt, reply,
                reasoning, tool calls, tokens, seconds), so a reviewer can see what the model
                actually said
  tool loop     native tool calling with an allowlist, JSON-schema argument validation and a
                step budget; the host executes, the model only proposes
  JSON retry    one retry with the parse error fed back, because a small model's JSON fails
                occasionally and the failure is transient

Standard library only. Config lives in data/model_profiles.json.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "data" / "model_profiles.json"


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "not-needed"
    timeout_s: float = 300.0
    max_tokens: int = 4000      # LFM2.5 thinks before it answers; the budget must cover the thinking
    profile: str = ""

    @classmethod
    def from_profile(cls, name: str, path: str | Path = DEFAULT_CONFIG) -> "LLMConfig | None":
        if not name or name == "none":
            return None
        profiles = json.loads(Path(path).read_text()).get("profiles", {})
        if name not in profiles:
            raise LLMError(f"unknown model profile {name!r}; choose one of: {', '.join(sorted(profiles))}")
        p = profiles[name]
        key = os.environ.get(p.get("api_key_env", ""), "") or "not-needed"
        return cls(p["base_url"], p["model"], key, profile=name,
                   max_tokens=int(p.get("max_tokens", 4000)), timeout_s=float(p.get("timeout_s", 300)))


def resolve_config(profile: str | None = None, base_url: str | None = None, model: str | None = None,
                   config_path: str | Path = DEFAULT_CONFIG) -> LLMConfig | None:
    if base_url and model:
        return LLMConfig(base_url, model, profile="command line")
    if os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_MODEL"):
        return LLMConfig(os.environ["LLM_BASE_URL"], os.environ["LLM_MODEL"], profile="environment")
    chosen = profile or os.environ.get("LLM_PROFILE")
    if not chosen and Path(config_path).exists():
        chosen = json.loads(Path(config_path).read_text()).get("active_profile")
    return LLMConfig.from_profile(chosen or "none", config_path)


class OpenAICompatibleClient:
    def __init__(self, cfg: LLMConfig, log_path: Path | None = None):
        self.cfg = cfg
        self.model_name = cfg.model
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"
        self.log_path = Path(log_path) if log_path else None
        self.calls: list[dict] = []          # in-memory copy of the log for the run packet

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.cfg.api_key}"})
        with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
            return json.load(resp)

    def _log(self, record: dict) -> None:
        self.calls.append(record)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps(record) + "\n")

    def chat_message(self, messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False,
                     stage: str = "") -> dict:
        """One call. Returns the assistant message dict (content, reasoning_content, tool_calls, finish_reason)."""
        body: dict[str, Any] = {"model": self.cfg.model, "messages": messages, "temperature": 0,
                                "max_tokens": self.cfg.max_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_mode and not getattr(self, "_json_mode_unsupported", False):
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        try:
            try:
                data = self._post(body)
            except urllib.error.HTTPError as e:
                if "response_format" in body and e.code in (400, 422):
                    # LM Studio accepts only json_schema or text here: stop asking, and parse the reply instead
                    self._json_mode_unsupported = True
                    body.pop("response_format")
                    try:
                        data = self._post(body)
                    except urllib.error.HTTPError as e2:
                        raise ValueError(f"HTTP {e2.code}: {e2.read().decode(errors='replace')[:300]}") from e2
                else:
                    raise ValueError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
            choice = data["choices"][0]
            msg = dict(choice.get("message") or {})
            msg["finish_reason"] = choice.get("finish_reason")
            usage = data.get("usage") or {}
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, ValueError) as e:
            self._log({"stage": stage, "seconds": round(time.time() - t0, 2), "error": f"{type(e).__name__}: {e}",
                       "messages": messages})
            raise LLMError(f"{type(e).__name__}: {e}") from e
        self._log({"stage": stage, "model": self.cfg.model, "seconds": round(time.time() - t0, 2), "usage": usage,
                   "tools": [t["function"]["name"] for t in tools or []], "messages": messages,
                   "reply": {k: msg.get(k) for k in ("content", "reasoning_content", "tool_calls", "finish_reason")}})
        return msg

    def chat(self, messages: list[dict], json_mode: bool = True, stage: str = "") -> str:
        msg = self.chat_message(messages, json_mode=json_mode, stage=stage)
        content = msg.get("content") or ""
        if not content.strip():
            why = ("ran out of tokens while thinking (finish_reason=length); raise max_tokens"
                   if msg.get("finish_reason") == "length" else "returned an empty answer")
            raise LLMError(f"model {why}")
        return content


# ---- helpers the stages use ---------------------------------------------------------------------

def parse_json_object(raw: str) -> dict:
    """The first {...} block in the reply, fences and prose around it ignored."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise ValueError("reply is JSON but not an object")
    return obj


def ask_json(client: OpenAICompatibleClient, messages: list[dict], stage: str,
             validate: Callable[[dict], None] | None = None, retries: int = 1) -> tuple[dict, int]:
    """Ask for JSON, validate it in code, and retry once with the error fed back. Returns (obj, attempts)."""
    msgs = list(messages)
    attempts = 0
    last = ""
    while True:
        attempts += 1
        raw = client.chat(msgs, json_mode=True, stage=f"{stage}#{attempts}")
        try:
            obj = parse_json_object(raw)
            if validate:
                validate(obj)
            return obj, attempts
        except ValueError as e:
            last = str(e)
            if attempts > retries:
                raise LLMError(f"{stage}: unusable after {attempts} attempts: {last}") from e
            msgs = msgs + [{"role": "assistant", "content": raw},
                           {"role": "user", "content": f"That answer was rejected: {last}. "
                                                       "Reply again with only the corrected JSON object."}]


def _check_args(args: dict, schema: dict) -> None:
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in args:
            raise ValueError(f"missing argument {k!r}")
    for k, v in args.items():
        if k not in props:
            raise ValueError(f"unexpected argument {k!r}")
        want = props[k].get("type")
        ok = {"string": str, "number": (int, float), "integer": int, "boolean": bool}.get(want)
        if ok and not isinstance(v, ok) or isinstance(v, bool) and want in ("number", "integer"):
            raise ValueError(f"argument {k!r} should be {want}")


def run_tool_loop(client: OpenAICompatibleClient, messages: list[dict], tools: dict[str, tuple[dict, Callable]],
                  stage: str, max_steps: int = 4) -> tuple[str, list[dict]]:
    """Native tool calling with guardrails. `tools` maps name -> (JSON schema for parameters, function).
    The model proposes calls; the host checks the name against the allowlist and the arguments against
    the schema, executes, and feeds the result back. Stops at the first reply without tool calls or
    after max_steps. Returns (final text, trace of executed calls)."""
    specs = [{"type": "function", "function": {"name": n, "description": fn.__doc__ or n, "parameters": schema}}
             for n, (schema, fn) in tools.items()]
    msgs = list(messages)
    trace: list[dict] = []
    for step in range(max_steps + 1):
        msg = client.chat_message(msgs, tools=specs, stage=f"{stage}#{step + 1}")
        calls = msg.get("tool_calls") or []
        if not calls or step == max_steps:
            return msg.get("content") or "", trace
        msgs.append({"role": "assistant", "content": msg.get("content") or None, "tool_calls": calls})
        for call in calls:
            name = (call.get("function") or {}).get("name", "")
            try:
                if name not in tools:
                    raise ValueError(f"tool {name!r} is not allowed")
                args = json.loads((call.get("function") or {}).get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
                _check_args(args, tools[name][0])
                result = tools[name][1](**args)
            except (ValueError, TypeError) as e:
                result = {"error": str(e)}
            trace.append({"tool": name, "args": args if "args" in dir() else None, "result": result})
            msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result)})
    return "", trace
