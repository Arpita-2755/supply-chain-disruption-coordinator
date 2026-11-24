"""Shared plumbing for all six agents (not an agent itself).

Why it exists: every agent does the same three mechanical things:
  1. call its tools through a Semantic Kernel plugin (kernel.invoke),
  2. post results to the shared Blackboard,
  3. write a trace line and an append-only run-log line for each step.
Putting that here keeps each agent file short and focused on its ONE role.
Each agent also owns a real Semantic Kernel ChatCompletionAgent that writes its
short explanation (an LLM in LLM mode, the offline rule-based service otherwise).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import KernelArguments

from blackboard import Blackboard
from offline_llm import DRAFT_MARKER
from run_log import log_event


@dataclass
class RunContext:
    """Everything an agent needs to know about the current run."""
    run_id: str
    mode: str                          # "offline" or "llm"
    service: Any                       # Semantic Kernel chat-completion service
    verbose: bool = True
    trace: list[str] = field(default_factory=list)

    def emit(self, line: str) -> None:
        """Record a trace line and (optionally) print it."""
        self.trace.append(line)
        if self.verbose:
            print(line)


class BaseAgent:
    """Base class: subclasses set name, instructions, plugin_name, tools and implement run()."""
    name: str = "BaseAgent"
    instructions: str = ""
    plugin_name: str = ""
    tools: list[Callable] = []

    def __init__(self, blackboard: Blackboard, ctx: RunContext) -> None:
        self.bb = blackboard
        self.ctx = ctx
        self.kernel = Kernel()
        self.kernel.add_functions(plugin_name=self.plugin_name, functions=self.tools)  # tools as SK plugin
        self.sk_agent = ChatCompletionAgent(service=ctx.service, kernel=self.kernel,
                                            name=self.name, instructions=self.instructions)

    async def call_tool(self, function_name: str, **kwargs: Any) -> Any:
        """Invoke one tool via the kernel; trace + log it; return the plain Python result."""
        result = await self.kernel.invoke(plugin_name=self.plugin_name, function_name=function_name,
                                          arguments=KernelArguments(**kwargs))
        value = result.value if result is not None else None
        args = ", ".join(f"{k}={_brief(v, 40)}" for k, v in kwargs.items())
        self.ctx.emit(f"    [{self.name}] tool {function_name}({args}) -> {_brief(value, 110)}")
        log_event(self.ctx.run_id, self.name, "tool_call", function_name, _brief(value, 300))
        return value

    def post(self, key: str, value: Any, status: str = "ok", note: str = "",
             tools: list[str] | None = None) -> None:
        """Write a signal to the blackboard; trace + log it."""
        self.bb.post(key, value, author=self.name, status=status, note=note, tools=tools)
        flag = "" if status == "ok" else f"  <-- {status.upper()}"
        self.ctx.emit(f"[{self.name}] posted '{key}' to blackboard{flag}" + (f" ({note})" if note else ""))
        log_event(self.ctx.run_id, self.name, f"post:{status}", ",".join(tools or []), f"{key}: {note}")

    async def explain(self, facts: str, draft: str) -> str:
        """Ask this agent's ChatCompletionAgent for a short explanation.
        Offline: the service returns the rule-based draft verbatim.
        LLM: the model rewrites the draft; on any error we fall back to the draft."""
        prompt = f"{facts}\n{DRAFT_MARKER} {draft}"
        try:
            response = await self.sk_agent.get_response(messages=prompt)
            text = str(response.message.content).strip()
            return text or draft
        except Exception as exc:  # network / quota problems must not break the run
            log_event(self.ctx.run_id, self.name, "llm_error", "", repr(exc))
            return draft


def _brief(value: Any, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
