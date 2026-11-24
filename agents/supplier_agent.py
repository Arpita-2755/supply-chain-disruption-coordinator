"""SupplierAgent: posts alternative-supplier options and their lead times.

Why it exists: a "reorder" mitigation is only possible if some OTHER supplier
can deliver the item in time. For each affected item it posts:
  supplier_options:<item> = primary supplier, disrupted supplier, alternatives[]
Each alternative carries its lead time and unit price. An empty alternatives
list is posted honestly (with a note) - it is a real finding, not an error.
Tools: get_primary_supplier, find_alt_suppliers, get_lead_time.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from tools.supplier_tools import find_alt_suppliers, get_lead_time, get_primary_supplier


class SupplierAgent(BaseAgent):
    name = "SupplierAgent"
    plugin_name = "supplier"
    tools = [get_primary_supplier, find_alt_suppliers, get_lead_time]
    instructions = ("You are the Supplier agent. In one sentence, list the alternative suppliers "
                    "and lead times you were given, or say clearly that none exist.")

    async def run(self) -> None:
        items = (self.bb.read("affected_items") or {}).get("items", [])
        disruption = self.bb.read("disruption") or {}
        if not items:
            self.ctx.emit(f"[{self.name}] nothing to check: affected items not on blackboard")
            return
        for item in items:
            await self._options_for(item, disruption.get("disrupted_supplier"))

    async def _options_for(self, item: str, disrupted: str | None) -> None:
        key = f"supplier_options:{item}"
        tools_used = ["get_primary_supplier", "find_alt_suppliers", "get_lead_time"]
        primary = await self.call_tool("get_primary_supplier", item_id=item)
        if not primary["found"]:
            self.post(key, {"item_id": item}, status="missing", note="item not in catalogue", tools=tools_used)
            return

        # Alternatives = everyone who stocks the item except the usual and the disrupted supplier.
        exclude = ",".join(dict.fromkeys(s for s in [primary["supplier_id"], disrupted] if s))
        candidates = await self.call_tool("find_alt_suppliers", item_id=item, exclude=exclude)
        alternatives = []
        for cand in candidates:
            lead = await self.call_tool("get_lead_time", supplier_id=cand["supplier_id"], item_id=item)
            if lead["found"]:
                alternatives.append({**cand, "lead_time_days": lead["lead_time_days"]})
        primary_lead = await self.call_tool("get_lead_time", supplier_id=primary["supplier_id"], item_id=item)

        value = {"item_id": item, "primary_supplier": primary["supplier_id"],
                 "primary_lead_time_days": primary_lead.get("lead_time_days"),
                 "disrupted_supplier": disrupted, "alternatives": alternatives}
        if alternatives:
            draft = "; ".join(f"{a['supplier_id']} {a['lead_time_days']}d @ ${a['unit_price']}" for a in alternatives)
        else:
            draft = f"NO alternative supplier for {item} (sole source {primary['supplier_id']})"
        note = await self.explain(facts=f"Supplier facts: {value}", draft=draft)
        self.post(key, value, note=note, tools=tools_used)
