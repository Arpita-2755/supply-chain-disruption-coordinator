"""Tools used by the CostAgent to price each mitigation option.

Why it exists: several mitigations can work at once (for example both reorder
and reroute). These deterministic formulas give each one a dollar cost so the
Coordinator can choose the cheapest option that is also viable.

Formulas (simple on purpose, easy to explain):
  reorder = qty * supplier unit price + supplier order fee
  reroute = route cost per shipment + qty * route cost per unit
  hold    = expected shortfall units * stockout penalty per unit
"""
from __future__ import annotations

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json


@kernel_function(name="estimate_reorder_cost", description="Cost of ordering qty units of an item from a supplier.")
def estimate_reorder_cost(item_id: str, supplier_id: str, qty: int) -> dict:
    sup = load_json("suppliers")["suppliers"][supplier_id]
    unit_price = sup["catalog"][item_id]["unit_price"]
    cost = qty * unit_price + sup["order_fee"]
    return {"option": "reorder", "supplier_id": supplier_id, "qty": qty, "cost": round(float(cost), 2)}


@kernel_function(name="estimate_reroute_cost", description="Cost of moving qty units over an alternative route.")
def estimate_reroute_cost(route_id: str, qty: int) -> dict:
    route = load_json("routes")["routes"][route_id]
    cost = route["cost_per_shipment"] + qty * route["cost_per_unit"]
    return {"option": "reroute", "route_id": route_id, "qty": qty, "cost": round(float(cost), 2)}


@kernel_function(name="estimate_hold_cost", description="Expected stockout penalty if we hold and wait out the delay.")
def estimate_hold_cost(item_id: str, shortfall_units: int) -> dict:
    penalty = load_json("items")["items"][item_id]["stockout_penalty_per_unit"]
    cost = max(0, shortfall_units) * penalty
    return {"option": "hold", "shortfall_units": max(0, shortfall_units), "cost": round(float(cost), 2)}
