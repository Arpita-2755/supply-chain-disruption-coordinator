# Architecture - Supply Chain Disruption Response Coordinator

**Group 6, Supply Chain Disruption Response Coordinator**
Student: Arpita Mishra
Course: CSE476 Agentic AI and Intelligent Automation | Instructor: Rohit Bharti | School of Computer Science and Engineering, Lovely Professional University

Rendered image: [`architecture.png`](architecture.png) (drawn by `make_diagram.py` with matplotlib).

## Data flow (Mermaid)

```mermaid
flowchart LR
    R[/"Disruption report<br/>data/reports/*.json"/] --> M

    subgraph AGENTS["Agents (Semantic Kernel ChatCompletionAgents)"]
        M["MonitorAgent"]
        I["InventoryAgent"]
        S["SupplierAgent"]
        RT["RouteAgent"]
        C["CostAgent<br/>(optional extension)"]
        CO["CoordinatorAgent"]
    end

    BB[("SHARED BLACKBOARD<br/>disruption, affected_items, affected_sites<br/>inventory:item@site, supplier_options:item<br/>route_options:site, cost_options:item@site<br/>decision:item@site<br/><i>each posting: author, status, timestamp</i>")]

    subgraph TOOLS["Tools = kernel plugins (@kernel_function)"]
        TM["parse_disruption<br/>extract_items_and_sites"]
        TI["get_stock_level, get_safety_stock<br/>get_daily_demand"]
        TS["get_primary_supplier<br/>find_alt_suppliers, get_lead_time"]
        TR["list_routes<br/>get_route_delay"]
        TC["estimate_hold_cost<br/>estimate_reorder_cost, estimate_reroute_cost"]
        TCO["check_required_signals<br/>assess_options, lookup_contacts"]
    end

    D[("data/*.json<br/>items, sites, inventory,<br/>suppliers, routes, contacts")]

    M -- calls --> TM
    I -- calls --> TI
    S -- calls --> TS
    RT -- calls --> TR
    C -- calls --> TC
    CO -- calls --> TCO
    TM & TI & TS & TR & TC & TCO -. read .-> D

    M -- posts --> BB
    BB -- reads --> I & S & RT
    I & S & RT -- post --> BB
    BB -- reads --> C
    C -- posts --> BB
    BB == "reads ALL" ==> CO
    CO -- "posts decision" --> BB
    CO --> OUT[["Decision: reorder / reroute / hold<br/>or HOLD + ESCALATE TO HUMAN<br/>+ parties to notify + blackboard snapshot"]]
    AGENTS -. every step .-> LOG[("run_log.jsonl<br/>append-only")]
```

## Control flow (orchestrator.py)

| Step | Agent(s) | Runs | Reads from blackboard | Posts to blackboard |
|---|---|---|---|---|
| 1 | MonitorAgent | alone | - (reads the report) | `disruption`, `affected_items`, `affected_sites` |
| 2 | InventoryAgent, SupplierAgent, RouteAgent | **in parallel** (`asyncio.gather`) | `affected_*`, `disruption` | `inventory:*`, `supplier_options:*`, `route_options:*` |
| 3 | CostAgent | alone | all step-1 and step-2 postings | `cost_options:*` |
| 4 | CoordinatorAgent | alone | **everything** | `decision:*` |

The orchestrator only schedules agents. It never makes or changes decisions.

## Guard rails on the Coordinator

1. **Completeness check** (`check_required_signals`). Every required key must exist, have status `ok`, and contain its required non-null fields. If any key fails, the Coordinator decides **HOLD + ESCALATE TO HUMAN**. The reason names each missing key and the agent responsible.
2. **Viability** (`assess_options`): fixed rules, as follows:
   - **Hold** needs stock at or above safety stock, with days of cover at least as long as the delay.
   - **Reorder** needs supplier lead time ≤ needed-by days.
   - **Reroute** needs a route-block disruption and an alternative route arriving within the needed-by days.
3. **Selection**: the cheapest *viable* option. If nothing is viable, the Coordinator holds and escalates.
4. **Rationale**: in LLM mode the model may reword the rationale. The text is rejected and replaced by the deterministic draft if:
   - it does not name the chosen action,
   - it does not cite a blackboard key, or
   - its first sentence argues for another action.
