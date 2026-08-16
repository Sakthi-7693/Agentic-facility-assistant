# MCP & API Documentation

## Part 1 — MCP Server

**Server name:** `nectar-facility-mcp`
**Transport:** stdio (JSON-RPC), the standard MCP transport
**Entry point:** `python -m app.mcp_server.server`
**Tool count:** 11 (9 read, 2 write)

The server is a normal MCP server. Any MCP host can use it, not just this agent.
To attach it to Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nectar-facility": {
      "command": "python",
      "args": ["-m", "app.mcp_server.server"],
      "cwd": "/absolute/path/to/nectar-facility-agent"
    }
  }
}
```

The live tool list is also served by the running app at `GET /api/tools`.

---

### Read tools

#### `find_assets`
Discover which assets exist. Call this first when the user names a *place*
rather than a piece of equipment.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `building` | string | no | Name or ID, e.g. `Building A` |
| `floor` | integer | no | Floor number |
| `asset_type` | string | no | `chiller` \| `ahu` \| `cooling_tower` \| `vav` |

Returns `{building_id, count, assets[], zone?}`. When `floor` is supplied, `zone`
also reports the temperature, setpoint and which assets serve that floor.

```json
{
  "building_id": "BLDG-A", "count": 6,
  "assets": [{"asset_id": "CH-01", "name": "Chiller-01", "type": "chiller",
              "status": "running", "health_score": 63}],
  "zone": {"zone_id": "ZONE-A-3F", "current_temp_c": 26.8, "setpoint_c": 22.0,
           "served_by": ["AHU-02", "VAV-A-3F-01"]}
}
```

#### `get_asset_details`
Static nameplate data.

| Parameter | Type | Required |
|---|---|---|
| `asset` | string | **yes** |

Returns manufacturer, model, capacity, criticality, install date, last service,
next service due, warranty expiry.

#### `get_asset_status`
Live operating status **with deviations already computed in Python** — the agent
never has to do arithmetic.

| Parameter | Type | Required |
|---|---|---|
| `asset` | string | **yes** |

```json
{
  "asset_id": "AHU-02", "status": "running_degraded", "health_score": 41,
  "power_kw": 9.1, "power_deviation_pct": -27.2, "airflow_deviation_pct": -34.7,
  "metrics": {"supply_airflow_cfm": 6200, "design_airflow_cfm": 9500,
              "filter_dp_inwc": 1.9, "filter_dp_limit_inwc": 1.2, "fan_speed_pct": 98},
  "observations": [
    "Supply airflow is 34.7% below design.",
    "Filter differential pressure 1.9 inWC exceeds the 1.2 inWC limit.",
    "Health score is low (41/100)."
  ]
}
```

#### `get_sensor_data`
Hourly history with a trend label (`rising` / `falling` / `stable`).

| Parameter | Type | Required | Default |
|---|---|---|---|
| `entity` | string | **yes** | — |
| `metric` | string | no | all metrics |
| `hours` | integer | no | 8 |

#### `get_energy_consumption`
Daily kWh with baseline comparison and estimated cost.

| Parameter | Type | Required | Default |
|---|---|---|---|
| `building` | string | **yes** | — |
| `days` | integer | no | 7 |

#### `get_active_alerts`
Active alarms, newest first.

| Parameter | Type | Required |
|---|---|---|
| `building` | string | no |
| `asset` | string | no |
| `severity` | string | no |

#### `get_asset_relationships`
Which assets feed this one, and which assets or zones it serves. This is what
lets the agent answer "which unit serves floor 3?" from data instead of guessing
from the numbering.

| Parameter | Type | Required |
|---|---|---|
| `asset` | string | **yes** |

#### `get_zone_conditions`
Temperature, humidity, deviation from setpoint and comfort status.

| Parameter | Type | Required |
|---|---|---|
| `building` | string | no |
| `floor` | integer | no |

#### `list_service_requests`
Existing requests — checked before creating a new one so duplicates are avoided.

| Parameter | Type | Required |
|---|---|---|
| `asset` | string | no |

---

### Write tools — confirmation required

Both are visible to the agent but **cannot be executed inside the agent loop**.
`ToolLoopAgent` intercepts them, returns `awaiting_user_confirmation` to the
model, and stores a `PendingAction` on the session. `app/agents/confirmation.py`
is the single place where either one actually runs, and only after the user has
said yes.

#### `create_service_request`

| Parameter | Type | Required |
|---|---|---|
| `asset` | string | **yes** |
| `priority` | string | **yes** — `critical` \| `high` \| `medium` \| `low` |
| `description` | string | **yes** |

#### `update_service_request`

| Parameter | Type | Required |
|---|---|---|
| `request_id` | string | **yes** |
| `status` | string | no — `open` \| `in_progress` \| `on_hold` \| `closed` |
| `note` | string | no |

---

### Error contract

A tool never raises. Invalid input returns a structured error the agent can act on:

```json
{
  "error": "Asset 'Chiller-99' was not found.",
  "hint": "Valid assets are: Chiller-01, Chiller-02, AHU-01, AHU-02, ..."
}
```

The agent reads `hint`, corrects its arguments and retries within the same loop.

---

## Part 2 — HTTP API

Base URL `http://127.0.0.1:8000`. Interactive docs at `/docs`.

### `POST /api/chat`
Text in, agent reply out.

```json
{ "message": "Why is the third floor hot?", "session_id": "sess-abc123" }
```

`session_id` is optional on the first call; use the value returned.

**Response**

| Field | Type | Meaning |
|---|---|---|
| `session_id` | string | pass back on the next turn |
| `transcript` | string | what the user said |
| `reply` | string | the agent's answer |
| `audio_file` | string \| null | fetch via `/api/audio/{name}` |
| `route` | string | which agent handled it |
| `route_confidence` | float | 0–1 |
| `route_reason` | string | why the router chose it |
| `route_method` | string | `rule` \| `llm` \| `fallback` \| `escalation` |
| `agent` | string | the agent that ran |
| `sources` | string[] | document citations |
| `tools_used` | object[] | `{tool, arguments, ok, summary}` |
| `awaiting_confirmation` | bool | a write action is held |
| `pending_action` | string \| null | what it would do |
| `rerouted_from` | string \| null | set when self-correction fired |
| `timings_ms` | object | `stt`, `agent`, `tts` |

### `POST /api/voice`
`multipart/form-data` with an `audio` file (webm/wav/mp3) and optional
`session_id`. Same response shape, with `transcript` filled in by Whisper.

### `GET /api/audio/{filename}`
Returns the synthesised WAV. The filename is validated against path traversal.

### `POST /api/session/reset`
`{"session_id": "sess-abc123"}` — clears history and any pending action.

### `GET /api/tools`
Live MCP tool documentation generated from the running server, including a
`write_action` flag per tool.

### `GET /health`
```json
{
  "status": "ok", "llm_provider": "groq",
  "models": {"fast": "llama-3.1-8b-instant", "smart": "llama-3.3-70b-versatile"},
  "mcp_mode": "mcp_stdio", "mcp_tools": 11, "kb_chunks": 51,
  "tracing": true, "active_sessions": 1
}
```

### Errors

| Code | Meaning |
|---|---|
| 400 | empty message, empty audio, or an invalid audio filename |
| 404 | audio file not found |
| 500 | unexpected server error |

Failures *inside* a turn never produce a 500. A tool error, an LLM timeout or a
TTS failure all still return 200 with a spoken explanation, because a voice
assistant that goes silent is worse than one that admits a problem.
