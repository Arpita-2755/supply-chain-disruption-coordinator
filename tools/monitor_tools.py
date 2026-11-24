"""Tools used by the MonitorAgent to read a free-text disruption report.

Why it exists: the raw report is unstructured text. These two tools turn it into
structured facts (disruption type, delay, deadline, affected items and sites)
that the other agents can rely on. They are plain Python functions; the
@kernel_function decorator only adds metadata so Semantic Kernel can expose them.
"""
from __future__ import annotations

import re

from semantic_kernel.functions import kernel_function

from tools.data_store import load_json

_DELAY_RE = re.compile(r"(?:delayed by|closure(?: expected)?(?: for)?)\s+(\d+)\s*days?", re.I)
_NEEDED_RE = re.compile(r"(?:due in|within|stops in)\s+(\d+)\s*days?", re.I)


@kernel_function(name="parse_disruption",
                 description="Classify a disruption report and extract delay, deadline, supplier and route.")
def parse_disruption(report_text: str) -> dict:
    """Return {type, delay_days, needed_by_days, disrupted_supplier, blocked_route}."""
    header = report_text.split(":", 1)[0].upper()
    if "ROUTE" in header or "BLOCK" in header:
        dtype = "route_block"
    elif "DELAY" in header:
        dtype = "supplier_delay"
    elif "STOCKOUT" in header:
        dtype = "stockout"
    else:
        dtype = "unknown"

    delay = _DELAY_RE.search(report_text)
    needed = _NEEDED_RE.search(report_text)
    supplier = re.search(r"SUP-\d{2}", report_text)
    route = re.search(r"RT-\d{2}", report_text)
    return {
        "type": dtype,
        "delay_days": int(delay.group(1)) if delay else 0,
        "needed_by_days": int(needed.group(1)) if needed else None,
        # Only a supplier-delay report names a *disrupted* supplier; other SUP ids are just mentions.
        "disrupted_supplier": supplier.group(0) if (supplier and dtype == "supplier_delay") else None,
        "blocked_route": route.group(0) if (route and dtype == "route_block") else None,
    }


@kernel_function(name="extract_items_and_sites",
                 description="Find item ids (ITM-xxx) and site ids (WH-XXX) in a report and validate them.")
def extract_items_and_sites(report_text: str) -> dict:
    """Return known items/sites mentioned in the text, plus any unknown ids."""
    items_catalog = load_json("items")["items"]
    sites_catalog = load_json("sites")["sites"]
    item_ids = list(dict.fromkeys(re.findall(r"ITM-\d{3}", report_text)))  # de-duplicate, keep order
    site_ids = list(dict.fromkeys(re.findall(r"WH-[A-Z]{3}", report_text)))
    return {
        "items": [i for i in item_ids if i in items_catalog],
        "sites": [s for s in site_ids if s in sites_catalog],
        "unknown_items": [i for i in item_ids if i not in items_catalog],
        "unknown_sites": [s for s in site_ids if s not in sites_catalog],
    }
