"""CoordinatorAgent: reads the whole blackboard and decides reorder / reroute / hold.

Why it exists: it is the single decision-maker, and it is deliberately constrained:
  * it decides ONLY from blackboard postings (it never reads data files itself);
  * if any required signal is missing or malformed it REFUSES to choose and
    returns "hold + escalate to human", naming the missing keys and who owned them;
  * among viable options it picks the cheapest (viability rules live in a tool);
  * its rationale cites the blackboard keys and authors it used. In LLM mode the
    LLM may reword the rationale, but the text is rejected if it contradicts the decision.
Tools: check_required_signals, assess_options, lookup_contacts.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from run_log import log_event
from tools.coordinator_tools import assess_options, check_required_signals, lookup_contacts, notification_roles


class CoordinatorAgent(BaseAgent):
    name = "CoordinatorAgent"
    plugin_name = "coordinator"
    tools = [check_required_signals, assess_options, lookup_contacts]
    instructions = ("You are the Coordinator of a supply-chain blackboard system. Rewrite the DRAFT "
                    "rationale clearly in 2-3 sentences. Keep the same decision word and cite the same "
                    "blackboard keys. Never add facts that are not in the draft.")

    async def run(self) -> list[dict]:
        items = (self.bb.read("affected_items") or {}).get("items", [])
        sites = (self.bb.read("affected_sites") or {}).get("sites", [])
        pairs = [(i, s) for i in items for s in sites]
        required = ["disruption", "affected_items", "affected_sites"]
        for item, site in pairs:
            required += [f"inventory:{item}@{site}", f"supplier_options:{item}",
                         f"route_options:{site}", f"cost_options:{item}@{site}"]

        postings = {p["key"]: {"status": p["status"], "value": p["value"]} for p in self.bb.snapshot()}
        check = await self.call_tool("check_required_signals", postings=postings, required_keys=required)
        if not check["complete"]:
            return [await self._escalate(pairs[0] if pairs else (None, sites[0] if sites else None),
                                         "required blackboard signals missing or malformed: " + self._gaps(check),
                                         check["missing"] + check["malformed"])]
        return [await self._decide(item, site) for item, site in pairs]

    def _gaps(self, check: dict) -> str:
        """Describe each gap with its author and note, so the human knows where to look."""
        parts = []
        for key in check["missing"] + check["malformed"]:
            p = self.bb.get(key)
            kind = "malformed" if key in check["malformed"] else "missing"
            parts.append(f"{key} [{kind}; " + (f"{p.author}: {p.note or p.status}]" if p else "never posted]"))
        return "; ".join(parts)

    async def _decide(self, item: str, site: str) -> dict:
        d = self.bb.read("disruption")
        inv_key, cost_key = f"inventory:{item}@{site}", f"cost_options:{item}@{site}"
        inv, cost = self.bb.read(inv_key), self.bb.read(cost_key)
        assessed = await self.call_tool("assess_options", disruption=d, inventory=inv, cost_options=cost["options"])
        viable = [o for o in assessed if o["viable"]]
        rejected = "; ".join(f"{_name(o)} ${o['cost']:,.0f} ({o['reason']})" for o in assessed if not o["viable"])
        if not viable:
            return await self._escalate((item, site), f"no viable option on the blackboard - rejected: {rejected}",
                                        [inv_key, f"supplier_options:{item}", f"route_options:{site}", cost_key])

        chosen = min(viable, key=lambda o: o["cost"])            # cheapest VIABLE option
        costlier = "; ".join(f"{_name(o)} ${o['cost']:,.0f}" for o in viable if o is not chosen)
        action = chosen["option"]
        at_risk = chosen["eta_days"] > inv["days_of_cover"]      # stock runs out before relief arrives
        roles = notification_roles(action, False, site, chosen, d.get("disrupted_supplier"), at_risk)
        notify = await self.call_tool("lookup_contacts", requests=roles)
        evidence = ["disruption", inv_key, f"supplier_options:{item}", f"route_options:{site}", cost_key]
        via = "" if action == "hold" else f" via {_label(chosen)}"
        draft = (f"{action.upper()}{via} at ${chosen['cost']:,.0f}, the cheapest of "
                 f"{len(viable)} viable option(s) in {cost_key} (CostAgent). Evidence: disruption (MonitorAgent) "
                 f"= {d['type']}, delay {d['delay_days']}d, needed by {d['needed_by_days']}d; {inv_key} "
                 f"(InventoryAgent) = {inv['on_hand']} on hand vs safety {inv['safety_stock']}, "
                 f"{inv['days_of_cover']}d cover; chosen because {chosen['reason']}. "
                 f"Also viable but costlier: {costlier or 'none'}. Rejected as not viable: {rejected or 'none'}."
                 + (" Delivery at risk: stock runs out before relief arrives." if at_risk else ""))
        decision = {"item_id": item, "site_id": site, "action": action, "escalate": False,
                    "chosen_option": chosen, "options_considered": assessed, "evidence_keys": evidence,
                    "notify": notify, "rationale": await self._rationale(draft, action, evidence)}
        self.post(f"decision:{item}@{site}", decision, note=f"{action}{via}",
                  tools=["check_required_signals", "assess_options", "lookup_contacts"])
        return decision

    async def _escalate(self, pair: tuple, reason: str, evidence: list[str]) -> dict:
        """Refuse to choose: hold + escalate to a human, with the reason logged."""
        item, site = pair
        roles = notification_roles("hold", True, site, None, None, True)
        notify = await self.call_tool("lookup_contacts", requests=roles)
        decision = {"item_id": item, "site_id": site, "action": "hold", "escalate": True,
                    "chosen_option": None, "evidence_keys": evidence, "notify": notify,
                    "rationale": f"HOLD + ESCALATE TO HUMAN: {reason}. The Coordinator will not guess."}
        log_event(self.ctx.run_id, self.name, "escalate", "", reason)
        key = f"decision:{item}@{site}" if item and site else "decision"
        self.post(key, decision, note="hold + escalate to human", tools=["check_required_signals", "lookup_contacts"])
        return decision

    async def _rationale(self, draft: str, action: str, evidence: list[str]) -> str:
        """Let the agent (LLM or offline) word the rationale, then VALIDATE it against the decision."""
        text = await self.explain(facts=f"Decision: {action}. Blackboard keys used: {evidence}", draft=draft)
        other = {"reorder", "reroute", "hold"} - {action}
        mentions_other_first = any(w in text.lower().split(".")[0] for w in other)
        if action not in text.lower() or not any(k in text for k in evidence) or mentions_other_first:
            log_event(self.ctx.run_id, self.name, "llm_rationale_rejected", "", text[:200])
            return draft  # deterministic text wins if the LLM drifts from the evidence
        return text


def _label(option: dict) -> str:
    return option.get("supplier_id") or option.get("route_id") or "hold"


def _name(option: dict) -> str:
    """e.g. 'reorder SUP-03', 'reroute RT-04', 'hold'."""
    return option["option"] if option["option"] == "hold" else f"{option['option']} {_label(option)}"
