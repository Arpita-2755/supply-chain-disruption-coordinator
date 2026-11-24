"""Tools used by the SupplierAgent to find other sources for an item.

Why it exists: when the usual supplier is late or stock has run out, the
Coordinator needs to know which OTHER suppliers can ship the item and how fast.
An empty list is a valid, honest answer ("no alternative supplier").
"""
from __future__ import annotations

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json


@kernel_function(name="get_primary_supplier", description="The usual (primary) supplier of an item.")
def get_primary_supplier(item_id: str) -> dict:
    item = load_json("items")["items"].get(item_id)
    if item is None:
        return {"found": False, "item_id": item_id}
    return {"found": True, "item_id": item_id, "supplier_id": item["primary_supplier"]}


@kernel_function(name="find_alt_suppliers",
                 description="Suppliers that carry an item, excluding a comma-separated list of supplier ids.")
def find_alt_suppliers(item_id: str, exclude: str = "") -> list:
    excluded = {s.strip() for s in exclude.split(",") if s.strip()}
    options = []
    for sup_id, sup in load_json("suppliers")["suppliers"].items():
        if sup_id in excluded or item_id not in sup["catalog"]:
            continue
        options.append({"supplier_id": sup_id, "name": sup["name"],
                        "unit_price": sup["catalog"][item_id]["unit_price"]})
    return options


@kernel_function(name="get_lead_time", description="Lead time in days for a supplier to deliver an item.")
def get_lead_time(supplier_id: str, item_id: str) -> dict:
    sup = load_json("suppliers")["suppliers"].get(supplier_id)
    if sup is None or item_id not in sup["catalog"]:
        return {"found": False, "supplier_id": supplier_id, "item_id": item_id}
    return {"found": True, "supplier_id": supplier_id, "item_id": item_id,
            "lead_time_days": sup["catalog"][item_id]["lead_time_days"]}
