"""RouteAgent: posts alternative shipping routes and their current delays.

Why it exists: a "reroute" mitigation is only possible if another open lane
reaches the same warehouse in time. For each affected site it posts:
  route_options:<site> = blocked_route, routes[] (all lanes + live status), alternatives[] (open lanes)
Tools: list_routes, get_route_delay.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from tools.route_tools import get_route_delay, list_routes


class RouteAgent(BaseAgent):
    name = "RouteAgent"
    plugin_name = "route"
    tools = [list_routes, get_route_delay]
    instructions = ("You are the Route agent. In one sentence, state which lanes into the site "
                    "are open and how many days each takes, using only the facts given.")

    async def run(self) -> None:
        sites = (self.bb.read("affected_sites") or {}).get("sites", [])
        disruption = self.bb.read("disruption") or {}
        if not sites:
            self.ctx.emit(f"[{self.name}] nothing to check: affected sites not on blackboard")
            return
        for site in sites:
            await self._routes_for(site, disruption.get("blocked_route"))

    async def _routes_for(self, site: str, blocked: str | None) -> None:
        key = f"route_options:{site}"
        lanes = await self.call_tool("list_routes", site_id=site)
        routes = []
        for lane in lanes:
            live = await self.call_tool("get_route_delay", route_id=lane["route_id"])
            if live["found"]:
                routes.append({**lane, "status": live["status"], "transit_days": live["transit_days"],
                               "current_delay_days": live["current_delay_days"],
                               "effective_days": live["effective_days"]})

        # An alternative must be open AND not the lane named as blocked in the report.
        alternatives = [r for r in routes if r["status"] == "open" and r["route_id"] != blocked]
        value = {"site_id": site, "blocked_route": blocked, "routes": routes, "alternatives": alternatives}
        draft = ("open alternatives: " + ", ".join(f"{r['route_id']} {r['mode']} {r['effective_days']}d"
                                                   for r in alternatives)) if alternatives \
            else f"no open alternative lane into {site}"
        if blocked:
            draft = f"{blocked} blocked; " + draft
        note = await self.explain(facts=f"Route facts: {value}", draft=draft)
        self.post(key, value, note=note, tools=["list_routes", "get_route_delay"])
