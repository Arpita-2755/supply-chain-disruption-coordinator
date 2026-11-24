"""Scenario tests for the Supply Chain Disruption Response Coordinator.

Why it exists: proves, by actually running the agents, that each disruption type
leads to the right mitigation, that the Coordinator refuses to guess when the
blackboard is incomplete, that cost picks the cheapest VIABLE option, and that
the run log is append-only. All tests run in offline mode (no API key needed).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import AuthorRole, ChatMessageContent

from agents.coordinator_agent import CoordinatorAgent
from agents.monitor_agent import MonitorAgent
from config import load_settings
from orchestrator import REPORTS_DIR, new_context, run
from tools.coordinator_tools import assess_options

R = REPORTS_DIR


def notified_roles(decision: dict) -> set[str]:
    return {n["role"] for n in decision["notify"]}


# ---------------- 1. the five required scenarios ----------------

def test_supplier_delay_leads_to_reorder_or_reroute():
    result = run(R / "01_supplier_delay.json", verbose=False)
    d = result.decisions[0]
    assert d["action"] in ("reorder", "reroute") and not d["escalate"]
    assert d["action"] == "reorder" and d["chosen_option"]["supplier_id"] == "SUP-03"
    assert "suppliers:SUP-03" in notified_roles(d) and "procurement" in notified_roles(d)


def test_stockout_reorders_from_alternative_supplier():
    result = run(R / "02_stockout.json", verbose=False)
    d = result.decisions[0]
    assert d["action"] == "reorder" and not d["escalate"]
    assert d["chosen_option"]["supplier_id"] == "SUP-04"       # not the primary SUP-02
    assert "customer_service" in notified_roles(d)                # zero stock => delivery at risk


def test_route_block_leads_to_reroute():
    result = run(R / "03_route_block.json", verbose=False)
    d = result.decisions[0]
    assert d["action"] == "reroute" and d["chosen_option"]["route_id"] == "RT-04"
    assert "logistics_partners:BlueDart Air Cargo" in notified_roles(d)


def test_missing_signal_holds_and_escalates(offline_and_temp_log: Path):
    result = run(R / "04_missing_data.json", verbose=False)
    d = result.decisions[0]
    assert d["action"] == "hold" and d["escalate"] is True
    assert "inventory:ITM-008@WH-BLR" in d["rationale"] and "escalation" in notified_roles(d)
    snapshot = {p["key"]: p for p in result.blackboard}
    assert snapshot["inventory:ITM-008@WH-BLR"]["status"] == "missing"
    assert snapshot["supplier_options:ITM-008"]["value"]["alternatives"] == []   # no alt supplier either
    log = [json.loads(line) for line in offline_and_temp_log.read_text().splitlines()]
    assert any(r["action"] == "escalate" and r["agent"] == "CoordinatorAgent" for r in log)


def test_coordinator_refuses_when_blackboard_incomplete():
    """Only the Monitor has run: the Coordinator must refuse, not guess."""
    async def scenario():
        bb, ctx = new_context(verbose=False)
        await MonitorAgent(bb, ctx).run(json.loads((R / "01_supplier_delay.json").read_text()))
        return await CoordinatorAgent(bb, ctx).run()
    d = asyncio.run(scenario())[0]
    assert d["action"] == "hold" and d["escalate"] is True and d["chosen_option"] is None
    for key in ("inventory:ITM-001@WH-DEL", "supplier_options:ITM-001", "cost_options:ITM-001@WH-DEL"):
        assert key in d["evidence_keys"]
    assert "never posted" in d["rationale"]


def test_malformed_signal_is_detected():
    """A report with no deadline produces a disruption signal without needed_by_days."""
    report = {"report_id": "T-1", "text": "SUPPLIER DELAY: SUP-01 delayed by 5 days for ITM-003 at WH-DEL."}
    d = run(report, verbose=False).decisions[0]
    assert d["escalate"] is True and "disruption [malformed" in d["rationale"]


# ---------------- 2. cost picks the cheapest VIABLE option ----------------

def test_cost_picks_cheapest_viable_option():
    d = run(R / "05_conflicting.json", verbose=False).decisions[0]
    opts = {o["option"] + (o.get("supplier_id") or o.get("route_id") or ""): o for o in d["options_considered"]}
    assert opts["hold"]["cost"] < opts["rerouteRT-06"]["cost"] and not opts["hold"]["viable"]  # cheaper but not viable
    assert opts["reorderSUP-05"]["viable"] and opts["rerouteRT-06"]["viable"]                  # genuine conflict
    assert d["action"] == "reroute" and d["chosen_option"]["route_id"] == "RT-06"            # cheapest viable wins


def test_assess_options_rules_unit():
    disruption = {"type": "supplier_delay", "delay_days": 10, "needed_by_days": 7}
    inventory = {"on_hand": 90, "safety_stock": 120, "days_of_cover": 4.5, "below_safety": True}
    opts = [{"option": "hold", "cost": 10.0},
            {"option": "reorder", "supplier_id": "A", "cost": 50.0, "eta_days": 12},
            {"option": "reorder", "supplier_id": "B", "cost": 90.0, "eta_days": 4},
            {"option": "reroute", "route_id": "R", "cost": 5.0, "eta_days": 1}]
    viable = [o for o in assess_options(disruption, inventory, opts) if o["viable"]]
    assert [o.get("supplier_id") for o in viable] == ["B"]   # only B meets the 7-day deadline


def test_hold_when_stock_is_healthy():
    d = run(R / "06_false_alarm_hold.json", verbose=False).decisions[0]
    assert d["action"] == "hold" and d["escalate"] is False


# ---------------- 3. blackboard, tools, log, modes ----------------

def test_every_posting_is_attributed_and_timestamped():
    result = run(R / "01_supplier_delay.json", verbose=False)
    authors = {p["author"] for p in result.blackboard}
    assert authors == {"MonitorAgent", "InventoryAgent", "SupplierAgent", "RouteAgent", "CostAgent", "CoordinatorAgent"}
    assert all(p["timestamp"] and p["status"] in ("ok", "missing", "error") for p in result.blackboard)
    assert "inventory:ITM-001@WH-DEL" in result.decisions[0]["rationale"]   # rationale cites blackboard keys


def test_each_agent_calls_at_least_two_distinct_tools(offline_and_temp_log: Path):
    run(R / "03_route_block.json", verbose=False)
    tools: dict[str, set[str]] = {}
    for line in offline_and_temp_log.read_text().splitlines():
        rec = json.loads(line)
        if rec["action"] == "tool_call":
            tools.setdefault(rec["agent"], set()).add(rec["tool"])
    for agent in ("MonitorAgent", "InventoryAgent", "SupplierAgent", "RouteAgent", "CostAgent", "CoordinatorAgent"):
        assert len(tools.get(agent, set())) >= 2, agent


def test_run_log_is_append_only(offline_and_temp_log: Path):
    run(R / "02_stockout.json", verbose=False)
    first = offline_and_temp_log.read_text()
    run(R / "03_route_block.json", verbose=False)
    second = offline_and_temp_log.read_text()
    assert second.startswith(first) and len(second) > len(first)   # old lines untouched, new lines appended
    for line in second.splitlines():
        assert set(json.loads(line)) == {"timestamp", "run_id", "agent", "action", "tool", "result_summary"}
    source = (Path(__file__).resolve().parent.parent / "run_log.py").read_text()
    assert 'open(log_path(), "a"' in source and '"w"' not in source


def test_offline_mode_with_no_api_key():
    settings = load_settings()
    assert settings.mode == "offline"
    assert run(R / "01_supplier_delay.json", verbose=False).mode == "offline"


def test_llm_rationale_that_contradicts_evidence_is_rejected():
    """A misbehaving 'LLM' that argues for the wrong action must be overruled by the deterministic draft."""
    class LyingLLM(ChatCompletionClientBase):
        async def _inner_get_chat_message_contents(self, chat_history, settings):
            return [ChatMessageContent(role=AuthorRole.ASSISTANT, content="You should REORDER everything now.")]

    async def scenario():
        bb, ctx = new_context(verbose=False)
        ctx.service = LyingLLM(ai_model_id="liar")
        from orchestrator import CostAgent, InventoryAgent, RouteAgent, SupplierAgent
        await MonitorAgent(bb, ctx).run(json.loads((R / "03_route_block.json").read_text()))
        for agent in (InventoryAgent, SupplierAgent, RouteAgent, CostAgent):
            await agent(bb, ctx).run()
        return await CoordinatorAgent(bb, ctx).run()
    d = asyncio.run(scenario())[0]
    assert d["action"] == "reroute"
    assert d["rationale"].startswith("REROUTE") and "REORDER everything" not in d["rationale"]
