"""Tools used by the RouteAgent to inspect shipping lanes.

Why it exists: when a lane is blocked, the Coordinator needs the alternative
lanes into the same warehouse and how long each takes right now (transit time
plus any live delay from the carrier feed in data/routes.json).
"""
from __future__ import annotations

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json


@kernel_function(name="list_routes", description="All inbound shipping routes into a site.")
def list_routes(site_id: str) -> list:
    routes = load_json("routes")["routes"]
    return [{"route_id": rid, "origin": r["origin"], "mode": r["mode"], "carrier": r["carrier"]}
            for rid, r in routes.items() if r["destination"] == site_id]


@kernel_function(name="get_route_delay", description="Live status, transit days and current delay of a route.")
def get_route_delay(route_id: str) -> dict:
    route = load_json("routes")["routes"].get(route_id)
    if route is None:
        return {"found": False, "route_id": route_id}
    return {"found": True, "route_id": route_id, "status": route["status"],
            "transit_days": route["transit_days"], "current_delay_days": route["current_delay_days"],
            "effective_days": route["transit_days"] + route["current_delay_days"]}
