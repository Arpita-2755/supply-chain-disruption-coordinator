"""Tools used by the InventoryAgent to look up stock data.

Why it exists: the Coordinator must know whether an affected item is above or
below its safety stock and how many days the current stock lasts. These tools
read data/inventory.json and data/items.json and report "found": False instead
of inventing a number when a record is missing.
"""
from __future__ import annotations

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json


def _find_record(item_id: str, site_id: str) -> dict | None:
    for rec in load_json("inventory")["records"]:
        if rec["item_id"] == item_id and rec["site_id"] == site_id:
            return rec
    return None


@kernel_function(name="get_stock_level", description="Current on-hand units of an item at a site.")
def get_stock_level(item_id: str, site_id: str) -> dict:
    rec = _find_record(item_id, site_id)
    if rec is None:
        return {"found": False, "item_id": item_id, "site_id": site_id}
    return {"found": True, "item_id": item_id, "site_id": site_id, "on_hand": rec["on_hand"]}


@kernel_function(name="get_safety_stock", description="Safety-stock level of an item at a site.")
def get_safety_stock(item_id: str, site_id: str) -> dict:
    rec = _find_record(item_id, site_id)
    if rec is None:
        return {"found": False, "item_id": item_id, "site_id": site_id}
    return {"found": True, "item_id": item_id, "site_id": site_id, "safety_stock": rec["safety_stock"]}


@kernel_function(name="get_daily_demand", description="Average daily demand (units/day) of an item.")
def get_daily_demand(item_id: str) -> dict:
    item = load_json("items")["items"].get(item_id)
    if item is None:
        return {"found": False, "item_id": item_id}
    return {"found": True, "item_id": item_id, "daily_demand": item["daily_demand"]}
