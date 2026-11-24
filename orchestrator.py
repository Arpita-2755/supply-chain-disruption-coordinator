"""Orchestrator: runs one blackboard cycle per disruption report and prints the trace.

Why it exists: it is the "control shell" of the blackboard architecture. It does
not make decisions; it just schedules agents in order:
  1. MonitorAgent                                   (posts disruption, items, sites)
  2. InventoryAgent | SupplierAgent | RouteAgent    (run IN PARALLEL with asyncio.gather)
  3. CostAgent                                      (prices options from their postings)
  4. CoordinatorAgent                               (decides from the blackboard only)
and then prints the final decision, the parties to notify and the full blackboard.

Usage:
  python orchestrator.py                 # run all sample reports in data/reports
  python orchestrator.py data/reports/01_supplier_delay.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.base_agent import RunContext
from agents.coordinator_agent import CoordinatorAgent
from agents.cost_agent import CostAgent
from agents.inventory_agent import InventoryAgent
from agents.monitor_agent import MonitorAgent
from agents.route_agent import RouteAgent
from agents.supplier_agent import SupplierAgent
from blackboard import Blackboard
from config import build_chat_service, load_settings
from run_log import log_event

REPORTS_DIR = Path(__file__).resolve().parent / "data" / "reports"


@dataclass
class RunResult:
    """Everything a run produces: decision(s), notify list, blackboard, trace."""
    run_id: str
    report_id: str
    mode: str
    decisions: list[dict]
    blackboard: list[dict]
    trace: list[str]

    @property
    def action(self) -> str:
        """Headline decision, e.g. 'reorder' or 'hold + escalate'."""
        labels = {d["action"] + (" + escalate" if d["escalate"] else "") for d in self.decisions}
        return labels.pop() if len(labels) == 1 else "mixed: " + ", ".join(sorted(labels))


def new_context(verbose: bool = True) -> tuple[Blackboard, RunContext]:
    """Create a fresh blackboard + run context (also used by tests)."""
    settings = load_settings()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    ctx = RunContext(run_id=run_id, mode=settings.mode, service=build_chat_service(settings), verbose=verbose)
    return Blackboard(run_id), ctx


def load_report(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def run_disruption(report: dict | str | Path, verbose: bool = True) -> RunResult:
    """Run the full blackboard loop for one disruption report."""
    if not isinstance(report, dict):
        report = load_report(report)
    bb, ctx = new_context(verbose)
    ctx.emit("=" * 100)
    ctx.emit(f"RUN {ctx.run_id} | report {report.get('report_id')} ({report.get('scenario', '-')}) | mode={ctx.mode}")
    ctx.emit("=" * 100)
    log_event(ctx.run_id, "Orchestrator", "run_start", "", f"{report.get('report_id')} mode={ctx.mode}")

    ctx.emit("-- step 1: MonitorAgent --")
    await MonitorAgent(bb, ctx).run(report)

    ctx.emit("-- step 2: InventoryAgent | SupplierAgent | RouteAgent (parallel) --")
    await asyncio.gather(InventoryAgent(bb, ctx).run(), SupplierAgent(bb, ctx).run(), RouteAgent(bb, ctx).run())

    ctx.emit("-- step 3: CostAgent --")
    await CostAgent(bb, ctx).run()

    ctx.emit("-- step 4: CoordinatorAgent --")
    decisions = await CoordinatorAgent(bb, ctx).run()

    ctx.emit("")
    ctx.emit(bb.render())
    for d in decisions:
        ctx.emit("")
        ctx.emit(format_decision(d))
    result = RunResult(ctx.run_id, str(report.get("report_id")), ctx.mode, decisions, bb.snapshot(), ctx.trace)
    log_event(ctx.run_id, "Orchestrator", "run_end", "", f"decision={result.action}")
    return result


def format_decision(d: dict[str, Any]) -> str:
    """Human-readable decision block."""
    head = d["action"].upper() + (" + ESCALATE TO HUMAN" if d["escalate"] else "")
    lines = [f">>> DECISION for {d['item_id']} @ {d['site_id']}: {head}",
             f"    Rationale: {d['rationale']}",
             "    Notify: " + "; ".join(f"{n['name']} <{n['email']}>" for n in d["notify"])]
    return "\n".join(lines)


def run(report: dict | str | Path, verbose: bool = True) -> RunResult:
    """Synchronous wrapper for scripts and tests."""
    return asyncio.run(run_disruption(report, verbose))


def main(argv: list[str]) -> None:
    paths = [Path(a) for a in argv] or sorted(REPORTS_DIR.glob("*.json"))
    summary = []
    for path in paths:
        result = run(path)
        summary.append((path.name, result.action))
        print()
    print("SUMMARY")
    for name, action in summary:
        print(f"  {name:<28} -> {action}")


if __name__ == "__main__":
    main(sys.argv[1:])
