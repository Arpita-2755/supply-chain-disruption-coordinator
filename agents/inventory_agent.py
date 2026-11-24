"""InventoryAgent: posts stock and safety-stock status for each affected item.

Why it exists: whether we can simply "hold" depends on how much stock is left.
For every (item, site) pair the Monitor posted, it posts:
  inventory:<item>@<site> = on_hand, safety_stock, daily_demand, days_of_cover, below_safety
If the stock record does not exist it posts status MISSING instead of guessing.
Tools: get_stock_level, get_safety_stock, get_daily_demand.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from tools.inventory_tools import get_daily_demand, get_safety_stock, get_stock_level


class InventoryAgent(BaseAgent):
    name = "InventoryAgent"
    plugin_name = "inventory"
    tools = [get_stock_level, get_safety_stock, get_daily_demand]
    instructions = ("You are the Inventory agent. State in one sentence whether stock is above "
                    "or below safety stock and how many days it covers, using only the facts given.")

    async def run(self) -> None:
        items = (self.bb.read("affected_items") or {}).get("items", [])
        sites = (self.bb.read("affected_sites") or {}).get("sites", [])
        if not items or not sites:
            self.ctx.emit(f"[{self.name}] nothing to check: affected items/sites not on blackboard")
            return
        for item in items:
            for site in sites:
                await self._check(item, site)

    async def _check(self, item: str, site: str) -> None:
        key = f"inventory:{item}@{site}"
        tools_used = ["get_stock_level", "get_safety_stock", "get_daily_demand"]
        stock = await self.call_tool("get_stock_level", item_id=item, site_id=site)
        safety = await self.call_tool("get_safety_stock", item_id=item, site_id=site)
        demand = await self.call_tool("get_daily_demand", item_id=item)

        if not (stock["found"] and safety["found"] and demand["found"]):
            # Honest failure: report the gap, do not invent a number.
            self.post(key, {"item_id": item, "site_id": site}, status="missing",
                      note=f"no stock record for {item} at {site}", tools=tools_used)
            return

        on_hand, safety_stock, daily = stock["on_hand"], safety["safety_stock"], demand["daily_demand"]
        value = {"item_id": item, "site_id": site, "on_hand": on_hand, "safety_stock": safety_stock,
                 "daily_demand": daily, "days_of_cover": round(on_hand / daily, 1),
                 "below_safety": on_hand < safety_stock}
        state = "BELOW" if value["below_safety"] else "above"
        note = await self.explain(
            facts=f"Inventory facts: {value}",
            draft=f"{on_hand} on hand, {state} safety {safety_stock}, covers {value['days_of_cover']}d")
        self.post(key, value, note=note, tools=tools_used)
