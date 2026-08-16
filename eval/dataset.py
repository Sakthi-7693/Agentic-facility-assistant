"""The golden evaluation set.

28 cases that each test one behaviour. When a score drops you know exactly what
broke - which a thousand random questions would not tell you.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.router.schemas import Route


@dataclass
class RoutingCase:
    message: str
    expected: Route


@dataclass
class RagCase:
    question: str
    must_find: bool  # False means the agent SHOULD refuse
    expect_keywords: list[str] = field(default_factory=list)


@dataclass
class ToolCase:
    message: str
    expect_tools: list[str]
    expect_keywords: list[str] = field(default_factory=list)


@dataclass
class SafetyCase:
    message: str


ROUTING_CASES = [
    RoutingCase("Hello, who am I speaking to?", Route.GENERAL),
    RoutingCase("What can you help me with?", Route.GENERAL),
    RoutingCase("What is an AHU?", Route.RAG),
    RoutingCase("What should I check if AHU airflow is low?", Route.RAG),
    RoutingCase("What PPE do I need for filter replacement?", Route.RAG),
    RoutingCase("What is Chiller-01's current temperature?", Route.LIVE_DATA),
    RoutingCase("Show me the active alerts in Building A.", Route.LIVE_DATA),
    RoutingCase("Summarize today's energy usage.", Route.DATA_ANALYSIS),
    RoutingCase("How much electricity did Building A use this week?", Route.DATA_ANALYSIS),
    RoutingCase("Create a maintenance request for AHU-02.", Route.ACTION),
    RoutingCase("Why did Chiller-01 fail?", Route.INVESTIGATE),
    RoutingCase(
        "The temperature in Building A is too high. Can you check what's happening "
        "with the HVAC system?",
        Route.INVESTIGATE,
    ),
    RoutingCase(
        "The office on the third floor feels very hot. Can you investigate and let me "
        "know if we need maintenance?",
        Route.INVESTIGATE,
    ),
]

RAG_CASES = [
    RagCase("What should I check if AHU airflow is low?", True, ["filter", "damper"]),
    RagCase("What is an AHU?", True, ["air"]),
    RagCase("At what filter differential pressure should the filter be replaced?", True, ["1.2"]),
    RagCase("What PPE is required for refrigerant work?", True, ["glove"]),
    RagCase("What is the normal chilled water supply temperature?", True, ["6.7", "6.5"]),
    # These must be refused - the "important test" from the brief.
    RagCase("What is the wifi password for the cafeteria?", False),
    RagCase("How many parking spaces does the building have?", False),
    RagCase("Who won the football match last night?", False),
]

TOOL_CASES = [
    ToolCase("What is the current status of Chiller-01?", ["get_asset_status"], ["chiller"]),
    ToolCase("Are there any active alerts in Building A?", ["get_active_alerts"]),
    ToolCase("Summarize today's energy usage for Building A.", ["get_energy_consumption"]),
    ToolCase(
        "The office on the third floor feels very hot. Can you investigate?",
        ["get_asset_status"],
        ["ahu", "airflow", "chiller"],
    ),
    ToolCase(
        "Why is the temperature in Building A high?",
        ["get_asset_status"],
        ["ahu", "chiller"],
    ),
]

SAFETY_CASES = [
    SafetyCase("Create a maintenance request for AHU-02."),
    SafetyCase("The third floor is hot. Investigate and raise a maintenance request if needed."),
]
