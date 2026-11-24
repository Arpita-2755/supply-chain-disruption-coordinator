"""Tools used by the CoordinatorAgent: signal checking, viability rules, contacts.

Why it exists: the Coordinator must (1) refuse to decide when a required
blackboard signal is missing or malformed, (2) judge which options are viable
using only blackboard evidence, and (3) look up who to notify. Keeping these
rules as plain deterministic functions means an LLM can never override them.
"""
from __future__ import annotations

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json

# Fields each kind of signal must contain (and not be null) to count as well-formed.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "disruption": ["type", "delay_days", "needed_by_days"],
    "affected_items": ["items"],
    "affected_sites": ["sites"],
    "inventory": ["on_hand", "safety_stock", "daily_demand", "days_of_cover", "below_safety"],
    "supplier_options": ["primary_supplier", "alternatives"],
    "route_options": ["routes", "alternatives"],
    "cost_options": ["options"],
}


@kernel_function(name="check_required_signals",
                 description="Check that every required blackboard key exists, is ok, and is well-formed.")
def check_required_signals(postings: dict, required_keys: list) -> dict:
    """postings maps key -> {"status": ..., "value": ...}. Returns missing and malformed keys."""
    missing, malformed = [], []
    for key in required_keys:
        entry = postings.get(key)
        if entry is None or entry.get("status") != "ok":
            missing.append(key)
            continue
        fields = REQUIRED_FIELDS.get(key.split(":", 1)[0], [])
        value = entry.get("value")
        if not isinstance(value, dict) or any(value.get(f) is None for f in fields):
            malformed.append(key)
    return {"complete": not missing and not malformed, "missing": missing, "malformed": malformed}


@kernel_function(name="assess_options",
                 description="Mark each priced mitigation option viable or not, using blackboard evidence only.")
def assess_options(disruption: dict, inventory: dict, cost_options: list) -> list:
    """Viability rules:
    hold    -> stock is at/above safety stock AND days of cover >= the delay
    reorder -> supplier lead time <= needed-by days
    reroute -> the disruption is a route block AND the alternative route arrives by needed-by
    """
    needed_by = disruption["needed_by_days"]
    assessed = []
    for opt in cost_options:
        o = dict(opt)
        if o["option"] == "hold":
            ok = (not inventory["below_safety"]) and inventory["days_of_cover"] >= disruption["delay_days"]
            o["eta_days"] = 0
            o["reason"] = (f"stock {inventory['on_hand']} vs safety {inventory['safety_stock']}, "
                           f"cover {inventory['days_of_cover']}d vs delay {disruption['delay_days']}d")
        elif o["option"] == "reorder":
            ok = o["eta_days"] <= needed_by
            o["reason"] = f"{o['supplier_id']} lead time {o['eta_days']}d vs needed-by {needed_by}d"
        else:  # reroute
            is_route_issue = disruption["type"] == "route_block"
            ok = is_route_issue and o["eta_days"] <= needed_by
            o["reason"] = (f"{o['route_id']} arrives in {o['eta_days']}d vs needed-by {needed_by}d"
                           if is_route_issue else "not applicable: disruption is not on a route")
        o["viable"] = bool(ok)
        assessed.append(o)
    return assessed


def notification_roles(action: str, escalate: bool, site: str | None, chosen: dict | None,
                       disrupted_supplier: str | None, at_risk: bool) -> list[str]:
    """Plain rule table: which parties must hear about this decision."""
    roles: list[str] = []
    if escalate:
        roles += ["escalation", "procurement", "customer_service"]
    elif action == "reorder":
        roles += ["procurement", f"suppliers:{chosen['supplier_id']}"]
        if disrupted_supplier:
            roles.append(f"suppliers:{disrupted_supplier}")  # tell the late supplier we sourced elsewhere
    elif action == "reroute":
        roles.append(f"logistics_partners:{chosen['carrier']}")
    else:  # plain hold
        roles.append("procurement")
    if site:
        roles.append(f"warehouse_managers:{site}")
    if at_risk and "customer_service" not in roles:
        roles.append("customer_service")  # delivery at risk: stock runs out before relief arrives
    return roles


@kernel_function(name="lookup_contacts",
                 description="Resolve role requests like 'procurement' or 'warehouse_managers:WH-DEL' to contacts.")
def lookup_contacts(requests: list) -> list:
    contacts = load_json("contacts")
    found = []
    for req in requests:
        group, _, key = req.partition(":")
        entry = contacts.get(group)
        if key and isinstance(entry, dict):
            entry = entry.get(key)
        if isinstance(entry, dict) and "email" in entry:
            found.append({"role": req, "name": entry["name"], "email": entry["email"]})
    return found
