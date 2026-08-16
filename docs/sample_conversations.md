# Sample Conversations

Each conversation shows the route the router chose, the tools the agent decided
to call, and the reply. Nothing here is scripted — the agent picks its own tool
sequence at run time.

> **On these transcripts.** The routes, retrieval scores, tool sequences and all
> facility figures below are taken from the real components — the routing rules,
> the retriever/reranker and the MCP tools were run directly to produce them.
> The agent's spoken wording is representative rather than a verbatim capture,
> because it is generated fresh on every run and varies between runs.
>
> Re-run any of these with the buttons in the demo UI or with `POST /api/chat`,
> and paste your own output over these examples before you submit — a transcript
> from your own machine is worth more than an illustrative one.

---

## 1. Documentation question — RAG route

**User:** "What is an AHU?"

```
route      rag        confidence 0.90   method rule
agent      rag_agent
retrieval  hvac_operating_procedures.md > 1. What is an AHU?    score 0.98
```

**Agent:** "An air handling unit conditions and circulates air through a
building. It contains a supply fan, filters, a cooling coil and mixing dampers,
and it delivers conditioned air to the zones through ductwork and VAV boxes."

**Sources:** `hvac_operating_procedures.md > HVAC Operating Procedures > 1. What is an AHU?`

---

## 2. Troubleshooting procedure — RAG with reranking

**User:** "What should I check if AHU airflow is low?"

```
route      rag        confidence 0.80   method rule
retrieval  ahu_troubleshooting_guide.md > 1.1 Checklist    rerank 0.996
```

**Agent:** "Check the filter differential pressure first — a dirty filter causes
about sixty percent of low airflow cases, and anything above one point two
inches of water needs replacing. Then confirm the dampers are opening, check the
fan belt, and check the VFD output frequency."

**Sources:** `ahu_troubleshooting_guide.md > AHU Troubleshooting Guide > 1. Low Supply Airflow > 1.1 Checklist`

Worth noting: plain vector search ranked the *Escalation Rules* section second
at 0.665. The reranker pushed the actual checklist to 0.996 and demoted the
escalation section, because it re-scores against the exact query wording.

---

## 3. The refusal test — question not in the knowledge base

**User:** "What is the wifi password for the cafeteria?"

```
route         rag        confidence 0.80   method rule
retrieval     best rerank score 0.000  →  below MIN_RELEVANCE_SCORE (0.15)
llm calls     0          the relevance gate refused before any generation
```

**Agent:** "I could not find that in the facility documentation. The knowledge
base covers HVAC procedures, chiller and AHU manuals, maintenance, safety and
facility policies. Would you like me to check the live building data instead?"

This is the "important test" from the brief. The agent refuses **without calling
the LLM at all** — the numeric relevance gate catches it first, which is both
safer and cheaper than asking a model to admit ignorance.

---

## 4. Live reading — MCP route

**User:** "What is the current status of Chiller-01?"

```
route      live_data   confidence 0.85   method rule
agent      live_data_agent   (fast model, read-only tools)
tools      get_asset_status(asset="Chiller-01")   ✓
steps      2
```

**Agent:** "Chiller-01 is running but drawing two hundred eighteen kilowatts,
about eighteen percent above its baseline, and its chilled water supply is three
degrees above setpoint. Its health score is sixty-three out of a hundred."

The deviation figures come from `get_asset_status`, computed in Python. The model
is never asked to do arithmetic.

---

## 5. Energy summary — data agent

**User:** "Summarize today's energy usage."

```
route      data_analysis   confidence 0.85   method rule
tools      get_energy_consumption(building="Building A")   ✓
```

**Agent:** "Building A used five thousand one hundred eighty kilowatt hours
today, about twenty-three percent above its baseline, and consumption has been
rising all week. The week so far comes to around three thousand four hundred
dollars."

---

## 6. The headline scenario — autonomous multi-step investigation

**User:** "The temperature in Building A is too high. Can you check what's
happening with the HVAC system?"

```
route   investigate   confidence 0.90   method rule
agent   investigation_agent   (smart model, all tools, 6 steps)

step 1  get_zone_conditions(building="Building A")                          ✓
        → floor 3 at 26.8 °C (setpoint 22, breach), floor 2 at 24.9 °C
          floor 3 served by AHU-02
step 2  get_asset_status(asset="AHU-02")                                    ✓
        → airflow 34.7% below design, fan 98%, filter dP 1.9 inWC (limit 1.2)
        get_asset_relationships(asset="AHU-02")                             ✓
        → fed by Chiller-01
step 3  get_asset_status(asset="Chiller-01")                                ✓
        → power +18.1% vs baseline, CHW supply 9.8 °C vs 6.7 setpoint
        get_active_alerts(building="Building A")                            ✓
        → 4 active alarms
step 4  search_knowledge_base("AHU low airflow high filter pressure")       ✓
        → 3 sources, top score 0.99
step 5  final answer
```

**Agent:** "Building A is in cooling mode and the third floor is the worst
affected at nearly twenty-seven degrees. AHU-02 is the main problem — airflow is
thirty-five percent below design with the fan already at ninety-eight percent,
and its filter pressure is above the replacement limit. Chiller-01 is also
drawing eighteen percent more power than baseline. Would you like me to
investigate AHU-02 further or raise a maintenance request?"

Nine tool calls across five steps, none of them scripted. The agent found the
zone, followed the equipment chain, corroborated with alarms, and checked the
documentation before concluding.

---

## 7. Multi-step investigation ending in an action — with confirmation

### Turn 1

**User:** "The office on the third floor feels very hot. Can you investigate and
let me know if we need maintenance?"

```
route   investigate   confidence 0.90   method rule

find_assets(building="Building A", floor=3)          ✓
get_asset_status(asset="AHU-02")                     ✓
get_active_alerts(asset="AHU-02")                    ✓
search_knowledge_base("AHU low airflow escalation")  ✓
list_service_requests(asset="AHU-02")                ✓  no duplicate exists
create_service_request(asset="AHU-02", priority="high", …)   ⏸ HELD

awaiting_confirmation = true
pending_action        = "Create a high priority maintenance request for AHU-02"
```

**Agent:** "The third floor is at twenty-seven degrees against a twenty-two
degree setpoint. AHU-02 is the cause — airflow is thirty-five percent below
design with the fan at ninety-eight percent, and the filter pressure is above
its limit, which the troubleshooting guide says is the most common cause. Shall
I raise a high priority maintenance request?"

### Turn 2

**User:** "Yes please."

```
route   confirmation   confidence 0.99   method rule
        (matched because the session was holding a pending action)
agent   confirmation_agent
tool    create_service_request(...)   ✓ EXECUTED — the only place this can happen
```

**Agent:** "Done. I have raised SR-2042 at high priority and assigned it to the
HVAC Team."

### Turn 2 (alternative) — the user declines

**User:** "No, not yet."

**Agent:** "Understood, I have not made any changes. Let me know if you need
anything else."

The pending action is discarded. Nothing was written.

---

## 8. Conversational memory — a follow-up with a pronoun

**User:** "What's the status of AHU-02?"
**Agent:** "AHU-02 is running but degraded. Airflow is thirty-five percent below
design and the filter pressure is above its limit."

**User:** "Why is that happening?"

```
route   investigate   (the classifier saw the history and resolved "that")
tools   get_asset_status(asset="AHU-02"), search_knowledge_base(...)
```

**Agent:** "The filter differential pressure is one point nine inches of water
against a one point two limit, so the filter is severely blocked. The guide says
a restriction like that cuts airflow by thirty to forty percent, which matches
what we are seeing."

The word "that" is never sent to a tool — the session history let the router and
the agent resolve it.

---

## 9. Ambiguity — the router asks instead of guessing

**User:** "It's hot."

```
rules       no confident match
classifier  route=investigate  confidence=0.35   →  below the 0.45 threshold
fallback    message is 2 words  →  ask a clarifying question, do not guess
```

**Agent:** "I want to make sure I check the right thing. Which building or piece
of equipment do you mean?"

**User:** "Building A, third floor."
→ routes to `investigate` and runs the full investigation from conversation 6.

One clarifying turn is cheaper and friendlier than a wrong investigation.

---

## 10. Self-correction — a wrong route caught at runtime

**User:** "How many parking spaces does the building have?"

```
route      rag   confidence 0.80   method rule
rag_agent  relevance gate rejected (score 0.04)  →  escalate = true
orchestrator re-routes  →  investigate
rerouted_from = "rag"

investigation_agent: find_assets(...), get_zone_conditions(...)
                     → no parking data exists in the facility system either
```

**Agent:** "I do not have parking information. I can see building areas,
occupancy and HVAC equipment, but parking is not in the documentation or the
building management system."

The RAG agent recognised it had been given the wrong job and said so; the
orchestrator escalated to the agent with every tool; that agent confirmed the
data genuinely does not exist and said so honestly rather than inventing a
number. The `rerouted_from` field makes the correction visible in the UI and in
the Langfuse trace.

---

## 11. Tool failure recovery

**User:** "What's the status of Chiller-05?"

```
route  live_data
step 1 get_asset_status(asset="Chiller-05")   ✗
       → {"error": "Asset 'Chiller-05' was not found.",
          "hint": "Valid assets are: Chiller-01, Chiller-02, AHU-01, AHU-02, …"}
step 2 the agent reads the hint and answers — it does not repeat the failing call
```

**Agent:** "There is no Chiller-05 in the system. Building A has Chiller-01 and
Chiller-02. Which one did you mean?"

The tool returned an error *as data*, so the agent recovered inside its own loop.
Nothing was raised, and the user got a useful answer instead of a stack trace.

---

## 12. Small talk — the cheapest possible path

**User:** "Hi, what can you do?"

```
route   general   confidence 0.95   method rule
agent   general_agent   (fast model, no tools, no retrieval)
tools   none            llm calls 1
```

**Agent:** "I'm Nectar, your facility operations assistant. I can check live
equipment status and sensor trends, look at alarms and energy use, search the
facility documentation, and raise maintenance requests once you approve them.
What would you like to look at?"

Routed by regex, so this turn costs zero routing tokens and no expensive model.
