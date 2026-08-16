"""Tool registry: the single source of truth for what the MCP server exposes.

The server, the client and the docs all read from TOOL_SPECS.
"""

from __future__ import annotations

from typing import Any, Callable

from app.mcp_server import tools
from app.mcp_server.tools import WRITE_TOOLS

STR = {"type": "string"}

# Numbers accept a string too. LLMs routinely emit {"floor": "3"} instead of
# {"floor": 3}, and Groq validates tool arguments server-side and rejects the
# whole call with a 400. Accepting both and coercing in Python (see _as_int in
# tools.py) removes an entire class of failure.
INT = {"type": ["integer", "string"]}


def _spec(
    handler: Callable[..., dict],
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    name = handler.__name__
    return {
        "name": name,
        "handler": handler,
        "description": description,
        "is_write": name in WRITE_TOOLS,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _spec(
        tools.find_assets,
        "Discover which assets exist, filtered by building, floor or type. Use this "
        "first when the user names a place rather than a piece of equipment.",
        {
            "building": {**STR, "description": "Building name or ID, e.g. 'Building A'"},
            "floor": {**INT, "description": "Floor number, e.g. 3"},
            "asset_type": {**STR, "description": "chiller | ahu | cooling_tower | vav"},
        },
    ),
    _spec(
        tools.get_asset_details,
        "Nameplate data for one asset: manufacturer, model, capacity, criticality "
        "and service dates.",
        {"asset": {**STR, "description": "Asset name or ID, e.g. 'Chiller-01'"}},
        ["asset"],
    ),
    _spec(
        tools.get_asset_status,
        "Live status of one asset: running state, health score, power, metrics and "
        "computed deviations from normal.",
        {"asset": {**STR, "description": "Asset name or ID, e.g. 'AHU-02'"}},
        ["asset"],
    ),
    _spec(
        tools.get_sensor_data,
        "Recent hourly sensor readings with a trend label, for an asset or a zone.",
        {
            "entity": {**STR, "description": "Asset or zone ID, e.g. 'CH-01' or 'ZONE-A-3F'"},
            "metric": {**STR, "description": "Optional metric filter, e.g. 'power'"},
            "hours": {**INT, "description": "Hours of history (default 8)"},
        },
        ["entity"],
    ),
    _spec(
        tools.get_energy_consumption,
        "Daily energy use for a building, with baseline comparison and cost.",
        {
            "building": {**STR, "description": "Building name or ID"},
            "days": {**INT, "description": "Days to include (default 7)"},
        },
        ["building"],
    ),
    _spec(
        tools.get_active_alerts,
        "Active alarms, optionally filtered by building, asset or severity.",
        {
            "building": {**STR, "description": "Optional building filter"},
            "asset": {**STR, "description": "Optional asset filter"},
            "severity": {**STR, "description": "critical | high | medium | low"},
        },
    ),
    _spec(
        tools.get_asset_relationships,
        "Which assets feed this one and which assets or zones it serves. Use this to "
        "confirm what serves a zone instead of guessing from the numbering.",
        {"asset": {**STR, "description": "Asset name or ID"}},
        ["asset"],
    ),
    _spec(
        tools.get_zone_conditions,
        "Temperature, humidity, setpoint deviation and comfort status for zones.",
        {
            "building": {**STR, "description": "Optional building filter"},
            "floor": {**INT, "description": "Optional floor filter"},
        },
    ),
    _spec(
        tools.list_service_requests,
        "List existing maintenance requests. Check this before creating a new one so "
        "duplicates are not raised.",
        {"asset": {**STR, "description": "Optional asset filter"}},
    ),
    _spec(
        tools.create_service_request,
        "Prepare a maintenance request. Always safe to call: it does NOT execute "
        "immediately - the system holds it and asks the user to confirm on your "
        "behalf. Call this whenever maintenance is warranted; do not ask in plain "
        "text first, because calling this tool IS how you ask.",
        {
            "asset": {**STR, "description": "Asset name or ID"},
            "priority": {**STR, "description": "critical | high | medium | low"},
            "description": {**STR, "description": "Symptom plus supporting measurements"},
        },
        ["asset", "priority", "description"],
    ),
    _spec(
        tools.update_service_request,
        "Prepare an update to an existing request's status or notes. Always safe to "
        "call: the system holds it and asks the user to confirm before it executes.",
        {
            "request_id": {**STR, "description": "Request ID, e.g. 'SR-2041'"},
            "status": {**STR, "description": "open | in_progress | on_hold | closed"},
            "note": {**STR, "description": "Optional note to append"},
        },
        ["request_id"],
    ),
]

TOOLS_BY_NAME: dict[str, dict[str, Any]] = {s["name"]: s for s in TOOL_SPECS}
