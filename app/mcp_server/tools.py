"""Facility tool implementations.

Tools never raise. Bad input returns {"error", "hint"} so the agent can read the
message and correct itself instead of the whole request failing.
"""

from __future__ import annotations

from typing import Any

from app.mcp_server.repository import get_repository

# Tools that change state. The agent must ask the user before running these.
WRITE_TOOLS: set[str] = {"create_service_request", "update_service_request"}


def _not_found(kind: str, value: str, options: list[str], extra: str = "") -> dict[str, Any]:
    return {
        "error": f"{kind} '{value}' was not found.",
        "hint": f"Valid {kind.lower()}s are: {', '.join(options)}.{extra}",
    }


def _building_not_found(repo, value: str) -> dict[str, Any]:
    """Buildings get their own hint.

    Users say "the office on the third floor", and models turn "office" into a
    building name. Telling the model it can simply drop the parameter turns a
    two-call recovery into a one-call one.
    """
    return _not_found(
        "Building",
        value,
        [b["name"] for b in repo.buildings()],
        extra=" If the user did not name a building, omit the 'building' "
              "argument entirely and search every building instead.",
    )


def _deviation_pct(actual: float | None, reference: float | None) -> float | None:
    if actual is None or not reference:
        return None
    return round((actual - reference) / reference * 100, 1)


def _as_int(value: Any, default: int | None = None) -> int | None:
    """Coerce a numeric argument that arrived as a string.

    Models emit {"floor": "3"} as often as {"floor": 3}, so every tool that
    takes a number normalises it here rather than failing.
    """
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _summary(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset["id"],
        "name": asset["name"],
        "type": asset["type"],
        "building_id": asset["building_id"],
        "status": asset["status"],
        "health_score": asset["health_score"],
    }


def _trend(values: list[float]) -> str:
    """Turn a series into a word the LLM can reason with."""
    if len(values) < 2:
        return "insufficient_data"
    pct = (values[-1] - values[0]) / (abs(values[0]) or 1) * 100
    if pct > 5:
        return "rising"
    return "falling" if pct < -5 else "stable"


# --- read tools ---

def find_assets(
    building: str | None = None,
    floor: int | None = None,
    asset_type: str | None = None,
) -> dict[str, Any]:
    repo = get_repository()
    building_id = None
    floor = _as_int(floor)

    if building:
        record = repo.find_building(building)
        if not record:
            return _building_not_found(repo, building)
        building_id = record["id"]

    matches = [
        a
        for a in repo.assets()
        if (building_id is None or a["building_id"] == building_id)
        and (asset_type is None or a["type"] == asset_type.lower())
    ]
    result: dict[str, Any] = {
        "building_id": building_id,
        "count": len(matches),
        "assets": [_summary(a) for a in matches],
    }

    # With a floor given, also say which assets actually serve that floor.
    # Works without a building too - "the third floor" often has no building.
    if floor is not None:
        zone = repo.find_zone(building_id, floor)
        if zone:
            result["zone"] = {
                "zone_id": zone["id"],
                "name": zone["name"],
                "floor": zone["floor"],
                "current_temp_c": zone["current_temp_c"],
                "setpoint_c": zone["setpoint_c"],
                "served_by": repo.serving_assets(zone["id"]),
            }
    return result


def get_asset_details(asset: str) -> dict[str, Any]:
    repo = get_repository()
    record = repo.find_asset(asset)
    if not record:
        return _not_found("Asset", asset, [a["name"] for a in repo.assets()])

    keys = [
        "type", "building_id", "location", "manufacturer", "model", "capacity",
        "criticality", "installed_on", "last_service_date", "next_service_due",
        "warranty_expiry",
    ]
    return {"asset_id": record["id"], "name": record["name"], **{k: record[k] for k in keys}}


def get_asset_status(asset: str) -> dict[str, Any]:
    """Live status, with deviations computed here rather than by the LLM."""
    repo = get_repository()
    record = repo.find_asset(asset)
    if not record:
        return _not_found("Asset", asset, [a["name"] for a in repo.assets()])

    metrics = record.get("metrics", {})
    notes: list[str] = []

    power_dev = _deviation_pct(record.get("power_kw"), record.get("baseline_power_kw"))
    if power_dev is not None and power_dev > 15:
        notes.append(f"Power draw is {power_dev}% above baseline.")

    airflow_dev = _deviation_pct(
        metrics.get("supply_airflow_cfm"), metrics.get("design_airflow_cfm")
    )
    if airflow_dev is not None and airflow_dev < -15:
        notes.append(f"Supply airflow is {abs(airflow_dev)}% below design.")

    dp, limit = metrics.get("filter_dp_inwc"), metrics.get("filter_dp_limit_inwc")
    if dp and limit and dp > limit:
        notes.append(f"Filter differential pressure {dp} inWC exceeds the {limit} inWC limit.")

    supply, setpoint = metrics.get("chw_supply_temp_c"), metrics.get("chw_supply_setpoint_c")
    if supply and setpoint and supply - setpoint > 1.5:
        notes.append(f"Chilled water supply is {round(supply - setpoint, 1)} C above setpoint.")

    if record["health_score"] < 60:
        notes.append(f"Health score is low ({record['health_score']}/100).")

    return {
        "asset_id": record["id"],
        "name": record["name"],
        "status": record["status"],
        "health_score": record["health_score"],
        "power_kw": record.get("power_kw"),
        "baseline_power_kw": record.get("baseline_power_kw"),
        "power_deviation_pct": power_dev,
        "airflow_deviation_pct": airflow_dev,
        "metrics": metrics,
        "observations": notes or ["Operating within normal limits."],
        "notes": record.get("notes", ""),
    }


def get_sensor_data(entity: str, metric: str | None = None, hours: int = 8) -> dict[str, Any]:
    repo = get_repository()
    hours = _as_int(hours, 8) or 8
    record = repo.find_asset(entity)
    entity_id = record["id"] if record else entity.upper()

    history = repo.sensor_history(entity_id)
    if not history:
        return {
            "error": f"No sensor history is recorded for '{entity}'.",
            "hint": "Try one of: CH-01, AHU-01, AHU-02, ZONE-A-2F, ZONE-A-3F",
        }

    if metric:
        filtered = {k: v for k, v in history.items() if metric.lower() in k.lower()}
        if not filtered:
            return {
                "error": f"Metric '{metric}' is not recorded for {entity_id}.",
                "hint": f"Available metrics: {', '.join(history)}",
            }
        history = filtered

    series = {}
    for name, values in history.items():
        window = values[-hours:]
        series[name] = {
            "readings": window,
            "oldest": window[0],
            "latest": window[-1],
            "change": round(window[-1] - window[0], 2),
            "trend": _trend(window),
        }
    return {"entity_id": entity_id, "hours": hours, "series": series}


def get_energy_consumption(building: str, days: int = 7) -> dict[str, Any]:
    repo = get_repository()
    days = _as_int(days, 7) or 7
    record = repo.find_building(building)
    if not record:
        return _not_found("Building", building, [b["name"] for b in repo.buildings()])

    energy = repo.energy(record["id"])
    if not energy:
        return {"error": f"No energy data recorded for {record['name']}."}

    dates, values = energy["dates"][-days:], energy["kwh"][-days:]
    today, baseline = values[-1], energy["baseline_kwh"]
    cost = round(sum(values) * energy["tariff_per_kwh"], 2)

    # A ready-made sentence. Given several similar numbers the model will
    # sometimes read out the wrong one or invent a total, so we state the
    # headline fact for it rather than leaving it to choose.
    summary = (
        f"{record['name']} used {today:,} kWh today, "
        f"{_deviation_pct(today, baseline)}% against a {baseline:,} kWh baseline. "
        f"Estimated cost {energy['currency']} {cost:,}."
    )
    if len(values) > 1:
        summary += f" The last {len(values)} days total {sum(values):,} kWh, trend {_trend(values)}."

    return {
        "summary": summary,
        "building_id": record["id"],
        "building_name": record["name"],
        "days": len(values),
        "daily_kwh": dict(zip(dates, values)),
        "today_kwh": today,
        "baseline_kwh": baseline,
        "deviation_pct": _deviation_pct(today, baseline),
        "period_total_kwh": sum(values),
        "estimated_cost": cost,
        "currency": energy["currency"],
        "trend": _trend(values),
    }


def get_active_alerts(
    building: str | None = None,
    asset: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    repo = get_repository()
    alerts = [a for a in repo.alerts() if a["status"] == "active"]

    if building:
        record = repo.find_building(building)
        if not record:
            return _building_not_found(repo, building)
        alerts = [a for a in alerts if a["building_id"] == record["id"]]

    if asset:
        record = repo.find_asset(asset)
        if not record:
            return _not_found("Asset", asset, [a["name"] for a in repo.assets()])
        alerts = [a for a in alerts if a["asset_id"] == record["id"]]

    if severity:
        alerts = [a for a in alerts if a["severity"] == severity.lower()]

    return {
        "count": len(alerts),
        "alerts": sorted(alerts, key=lambda a: a["raised_at"], reverse=True),
    }


def get_asset_relationships(asset: str) -> dict[str, Any]:
    """What feeds this asset and what it serves - so the agent never guesses."""
    repo = get_repository()
    record = repo.find_asset(asset) or repo.find_zone_by_id(asset)
    if not record:
        return _not_found("Asset", asset, [a["name"] for a in repo.assets()])

    asset_id = record["id"]
    return {
        "asset_id": asset_id,
        "name": record["name"],
        "upstream": [
            {"asset_id": r["parent"], "relation": r["relation"]}
            for r in repo.relationships()
            if r["child"] == asset_id
        ],
        "downstream": [
            {"asset_id": r["child"], "relation": r["relation"]}
            for r in repo.relationships()
            if r["parent"] == asset_id
        ],
    }


def get_zone_conditions(building: str | None = None, floor: int | None = None) -> dict[str, Any]:
    repo = get_repository()
    floor = _as_int(floor)
    building_id = None

    if building:
        record = repo.find_building(building)
        if not record:
            return _building_not_found(repo, building)
        building_id = record["id"]

    zones = [
        z
        for z in repo.zones()
        if (building_id is None or z["building_id"] == building_id)
        and (floor is None or z["floor"] == floor)
    ]
    if not zones:
        return {
            "error": "No zone matches that building/floor combination.",
            "hint": f"Known zones: {', '.join(z['name'] for z in repo.zones())}",
        }

    enriched = []
    for zone in zones:
        deviation = round(zone["current_temp_c"] - zone["setpoint_c"], 1)
        enriched.append(
            {
                **zone,
                "deviation_c": deviation,
                "comfort_status": "breach" if abs(deviation) > 2 else "acceptable",
                "served_by": repo.serving_assets(zone["id"]),
            }
        )
    return {"count": len(enriched), "zones": enriched}


def list_service_requests(asset: str | None = None) -> dict[str, Any]:
    repo = get_repository()
    requests = repo.service_requests()

    if asset:
        record = repo.find_asset(asset)
        if not record:
            return _not_found("Asset", asset, [a["name"] for a in repo.assets()])
        requests = [r for r in requests if r["asset_id"] == record["id"]]

    return {"count": len(requests), "service_requests": requests}


# --- write tools (held for confirmation by app/agents/tool_agent.py) ---

PRIORITIES = {"critical", "high", "medium", "low"}
STATUSES = {"open", "in_progress", "on_hold", "closed"}
HVAC_TYPES = {"chiller", "ahu", "cooling_tower", "vav"}


def create_service_request(asset: str, priority: str, description: str) -> dict[str, Any]:
    repo = get_repository()
    record = repo.find_asset(asset)
    if not record:
        return _not_found("Asset", asset, [a["name"] for a in repo.assets()])

    if priority.lower() not in PRIORITIES:
        return {
            "error": f"Priority '{priority}' is not valid.",
            "hint": f"Use one of: {', '.join(sorted(PRIORITIES))}",
        }

    created = repo.add_service_request(
        {
            "asset_id": record["id"],
            "priority": priority.lower(),
            "description": description,
            "assigned_to": "HVAC Team" if record["type"] in HVAC_TYPES else "General",
        }
    )
    return {"created": True, "service_request": created}


def update_service_request(
    request_id: str, status: str | None = None, note: str | None = None
) -> dict[str, Any]:
    repo = get_repository()
    if status and status.lower() not in STATUSES:
        return {
            "error": f"Status '{status}' is not valid.",
            "hint": f"Use one of: {', '.join(sorted(STATUSES))}",
        }

    updated = repo.update_service_request(request_id, status, note)
    if not updated:
        return _not_found("Service request", request_id, [r["id"] for r in repo.service_requests()])
    return {"updated": True, "service_request": updated}
