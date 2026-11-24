"""MonitorAgent: reads the raw disruption report and posts what is affected.

Why it exists: it is the entry point of every run. It turns free text into three
blackboard signals that all other agents depend on:
  disruption      - type, delay, needed-by deadline, disrupted supplier / blocked route
  affected_items  - item ids found in the report (validated against the catalogue)
  affected_sites  - warehouse ids found in the report (validated)
Tools: parse_disruption, extract_items_and_sites.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from tools.monitor_tools import extract_items_and_sites, parse_disruption


class MonitorAgent(BaseAgent):
    name = "MonitorAgent"
    plugin_name = "monitor"
    tools = [parse_disruption, extract_items_and_sites]
    instructions = ("You are the Monitor agent of a supply-chain blackboard system. "
                    "Summarise the disruption in one sentence using only the facts given.")

    async def run(self, report: dict) -> None:
        text = report["text"]
        self.ctx.emit(f"[{self.name}] reading report {report.get('report_id', '?')}: \"{text[:80]}...\"")

        parsed = await self.call_tool("parse_disruption", report_text=text)
        found = await self.call_tool("extract_items_and_sites", report_text=text)

        # 1) The disruption itself. Unknown type is an error signal, not a guess.
        disruption = {**parsed, "report_id": report.get("report_id")}
        if parsed["type"] == "unknown":
            self.post("disruption", disruption, status="error", note="could not classify report",
                      tools=["parse_disruption"])
        else:
            note = "" if parsed["needed_by_days"] is not None else "deadline not stated in report"
            summary = await self.explain(
                facts=f"Parsed disruption: {parsed}",
                draft=(f"{parsed['type']} reported; delay {parsed['delay_days']}d, "
                       f"needed by {parsed['needed_by_days']}d"))
            self.post("disruption", disruption, note=note or summary, tools=["parse_disruption"])

        # 2) Affected items and sites. An empty list is posted as MISSING.
        self.post("affected_items", {"items": found["items"], "unknown": found["unknown_items"]},
                  status="ok" if found["items"] else "missing",
                  note=", ".join(found["items"]) or "no known item id in report",
                  tools=["extract_items_and_sites"])
        self.post("affected_sites", {"sites": found["sites"], "unknown": found["unknown_sites"]},
                  status="ok" if found["sites"] else "missing",
                  note=", ".join(found["sites"]) or "no known site id in report",
                  tools=["extract_items_and_sites"])
