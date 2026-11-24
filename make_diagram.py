"""Draws architecture.png with matplotlib (no Node/Graphviz needed on Windows).

Why it exists: the project needs a rendered architecture image next to the
Mermaid source in architecture.md. Run:  python make_diagram.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

AGENT_ROWS = [  # (agent, tools, data files, y)
    ("MonitorAgent", "parse_disruption\nextract_items_and_sites", "reports/*.json, items, sites", 8.3),
    ("InventoryAgent\n(parallel step)", "get_stock_level, get_safety_stock\nget_daily_demand",
     "inventory.json, items.json", 6.95),
    ("SupplierAgent\n(parallel step)", "get_primary_supplier, find_alt_suppliers\nget_lead_time",
     "suppliers.json, items.json", 5.6),
    ("RouteAgent\n(parallel step)", "list_routes\nget_route_delay", "routes.json", 4.25),
    ("CostAgent\n(optional extension)", "estimate_hold_cost, estimate_reorder_cost\nestimate_reroute_cost",
     "items, suppliers, routes", 2.9),
    ("CoordinatorAgent", "check_required_signals, assess_options\nlookup_contacts", "contacts.json", 1.55),
]


def box(ax, x, y, w, h, text, face, edge="#333333", style="-", size=10, weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.15",
                                facecolor=face, edgecolor=edge, linewidth=1.6, linestyle=style))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, weight=weight)


def arrow(ax, start, end, label="", color="#333333", style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=14, color=color,
                                 linewidth=1.4, linestyle=ls))
    if label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.12, label, ha="center",
                fontsize=8, color=color)


def main() -> None:
    fig, ax = plt.subplots(figsize=(17, 11))
    ax.set_xlim(0, 17)
    ax.set_ylim(-0.3, 10.9)
    ax.axis("off")
    ax.set_title("Supply Chain Disruption Response Coordinator - Blackboard architecture (Semantic Kernel)",
                 fontsize=15, weight="bold")

    # Orchestrator + report
    box(ax, 4.0, 9.65, 4.2, 0.85, "Disruption report\n(data/reports/*.json)", "#fde2e4")
    box(ax, 9.0, 9.65, 7.6, 0.85, "Orchestrator: 1 Monitor -> 2 Inventory | Supplier | Route (parallel)\n"
        "-> 3 Cost -> 4 Coordinator   (schedules only; never decides)", "#eeeeee", size=9.5)
    arrow(ax, (6.1, 9.65), (6.1, 9.27))

    # Blackboard
    box(ax, 0.2, 1.2, 3.0, 8.2, "", "#fff3b0", edge="#b08900")
    ax.text(1.7, 8.95, "SHARED BLACKBOARD", ha="center", fontsize=12, weight="bold")
    keys = ["disruption", "affected_items", "affected_sites", "inventory:<item>@<site>",
            "supplier_options:<item>", "route_options:<site>", "cost_options:<item>@<site>",
            "decision:<item>@<site>", "", "each posting =", "key, value, author,", "status (ok/missing/error),",
            "timestamp, tools"]
    for i, k in enumerate(keys):
        ax.text(0.4, 8.4 - i * 0.52, k, fontsize=9, family="monospace")

    # Agents, tools, data
    for name, tools, data, y in AGENT_ROWS:
        is_coord = name.startswith("Coordinator")
        is_cost = name.startswith("Cost")
        face = "#ffd6a5" if is_coord else ("#e0e7ff" if is_cost else "#cfe1ff")
        box(ax, 4.0, y, 3.4, 0.95, name, face, style="--" if is_cost else "-", size=10.5, weight="bold")
        box(ax, 8.3, y, 4.9, 0.95, tools, "#d8f3dc", size=8.5)
        box(ax, 13.9, y, 2.8, 0.95, data, "#f1f1f1", size=8.5)
        arrow(ax, (7.4, y + 0.48), (8.3, y + 0.48), "calls", color="#2d6a4f")
        arrow(ax, (13.2, y + 0.48), (13.9, y + 0.48), "reads", color="#555555")
        if is_coord:
            arrow(ax, (3.2, y + 0.65), (4.0, y + 0.65), "reads ALL", color="#c1121f")
            arrow(ax, (4.0, y + 0.25), (3.2, y + 0.25), "decision", color="#c1121f")
        else:
            arrow(ax, (4.0, y + 0.48), (3.2, y + 0.48), "posts", color="#1d3557")
            if not name.startswith("Monitor"):
                arrow(ax, (3.2, y + 0.82), (4.0, y + 0.82), "reads", color="#1d3557", ls=":")


    # Output
    box(ax, 4.0, -0.15, 12.7, 1.15,
        "OUTPUT per run: decision (reorder / reroute / hold, or hold + ESCALATE TO HUMAN when a signal is missing)\n"
        "+ parties to notify + full attributed blackboard snapshot  |  every step appended to run_log.jsonl",
        "#ffe5ec", size=10)
    arrow(ax, (5.7, 1.55), (5.7, 1.0), color="#c1121f")

    fig.savefig("architecture.png", dpi=130, bbox_inches="tight")
    print("wrote architecture.png")


if __name__ == "__main__":
    main()
