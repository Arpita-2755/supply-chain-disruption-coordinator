"""CostAgent (optional extension beyond the required five agents): prices every option.

Why it exists: when more than one mitigation could work, the Coordinator should
pick the CHEAPEST VIABLE one. This agent reads the other agents' postings and
prices: hold, reorder from each alternative supplier, reroute over each open lane.
It posts cost_options:<item>@<site>. It does NOT judge viability - that is the
Coordinator's job - and if an input signal is missing it posts MISSING.
Tools: estimate_hold_cost, estimate_reorder_cost, estimate_reroute_cost.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from tools.cost_tools import estimate_hold_cost, estimate_reorder_cost, estimate_reroute_cost


class CostAgent(BaseAgent):
    name = "CostAgent"
    plugin_name = "cost"
    tools = [estimate_hold_cost, estimate_reorder_cost, estimate_reroute_cost]
    instructions = ("You are the Cost agent. In one sentence, list the price of each mitigation "
                    "option you were given. Do not recommend one.")

    async def run(self) -> None:
        items = (self.bb.read("affected_items") or {}).get("items", [])
        sites = (self.bb.read("affected_sites") or {}).get("sites", [])
        for item in items:
            for site in sites:
                await self._price(item, site)

    async def _price(self, item: str, site: str) -> None:
        key = f"cost_options:{item}@{site}"
        inputs = {"disruption": "disruption", "inventory": f"inventory:{item}@{site}",
                  "suppliers": f"supplier_options:{item}", "routes": f"route_options:{site}"}
        missing = [k for k in inputs.values() if not self.bb.has_ok(k)]
        disruption = self.bb.read("disruption") or {}
        if disruption.get("needed_by_days") is None:
            missing.append("disruption.needed_by_days")
        if missing:
            self.post(key, {"item_id": item, "site_id": site}, status="missing",
                      note="cannot price, missing: " + ", ".join(missing))
            return

        inv = self.bb.read(inputs["inventory"])
        sup = self.bb.read(inputs["suppliers"])
        rts = self.bb.read(inputs["routes"])
        needed_by, delay = disruption["needed_by_days"], disruption["delay_days"]
        # Quantity to cover demand until the deadline and restore safety stock.
        qty = max(inv["daily_demand"], inv["daily_demand"] * needed_by + inv["safety_stock"] - inv["on_hand"])
        # If we hold, demand over the longer of (delay, deadline) beyond on-hand stock is lost.
        shortfall = inv["daily_demand"] * max(delay, needed_by) - inv["on_hand"]

        options = [await self.call_tool("estimate_hold_cost", item_id=item, shortfall_units=shortfall)]
        for alt in sup["alternatives"]:
            opt = await self.call_tool("estimate_reorder_cost", item_id=item,
                                       supplier_id=alt["supplier_id"], qty=qty)
            options.append({**opt, "eta_days": alt["lead_time_days"]})
        for lane in rts["alternatives"]:
            opt = await self.call_tool("estimate_reroute_cost", route_id=lane["route_id"], qty=qty)
            options.append({**opt, "eta_days": lane["effective_days"], "carrier": lane["carrier"]})

        draft = "; ".join(f"{o['option']} {o.get('supplier_id') or o.get('route_id') or ''} ${o['cost']:,.0f}"
                          for o in options)
        note = await self.explain(facts=f"Priced options: {options}", draft=draft)
        self.post(key, {"item_id": item, "site_id": site, "qty": qty, "options": options}, note=note,
                  tools=["estimate_hold_cost", "estimate_reorder_cost", "estimate_reroute_cost"])
