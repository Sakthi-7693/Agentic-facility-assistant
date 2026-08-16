# Architecture

## 1. System overview

```
                            ┌──────────────┐
   🎤 Browser microphone ──►│  FastAPI     │
   ⌨️  Typed message    ──►│  app/api.py  │
                            └──────┬───────┘
                                   │
                            ┌──────▼────────────────────────────────┐
                            │        Orchestrator                    │
                            │        app/orchestrator.py             │
                            └──────┬────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
      ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
      │     STT      │     │    Router    │     │     TTS      │
      │faster-whisper│     │ rules + LLM  │     │   pyttsx3    │
      └──────────────┘     └──────┬───────┘     └──────────────┘
                                  │
        ┌──────────┬──────────┬───┴──────┬────────────┬────────────┐
        ▼          ▼          ▼          ▼            ▼            ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  ┌──────────┐ ┌──────────┐
   │General │ │  RAG   │ │  Live  │ │  Data  │  │  Action  │ │Investigate│
   │ Agent  │ │ Agent  │ │  Data  │ │ Agent  │  │  Agent   │ │  Agent    │
   └────────┘ └───┬────┘ └───┬────┘ └───┬────┘  └────┬─────┘ └────┬─────┘
                  │          │          │            │            │
                  ▼          └──────────┴────────────┴────────────┘
           ┌─────────────┐                     │
           │ RAG Pipeline│                     ▼
           │  Chroma +   │             ┌────────────────┐
           │  reranker   │             │  MCP Client    │
           └─────────────┘             └───────┬────────┘
                                               │ stdio (JSON-RPC)
                                       ┌───────▼────────┐
                                       │   MCP Server   │
                                       │  11 tools      │
                                       └───────┬────────┘
                                               ▼
                                       ┌────────────────┐
                                       │ Facility data  │
                                       │ (simulated BMS)│
                                       └────────────────┘

   Every step above is traced to Langfuse — one trace per user turn.
```

## 2. Request lifecycle

A single turn (`app/orchestrator.py`):

| # | Step | Module |
|---|---|---|
| 1 | Audio arrives (webm from the browser) | `app/api.py` |
| 2 | Speech to text | `app/voice/stt.py` |
| 3 | Load the session (history + pending action) | `app/session.py` |
| 4 | Route the request | `app/router/` |
| 5 | Run the chosen agent, which calls tools autonomously | `app/agents/` |
| 6 | RAG lookups and MCP tool calls as the agent decides | `app/rag/`, `app/mcp_client/` |
| 7 | Hold any write action, ask the user | `app/agents/tool_agent.py` |
| 8 | Store the turn in the session | `app/session.py` |
| 9 | Text to speech | `app/voice/tts.py` |
| 10 | Return JSON + audio to the browser | `app/api.py` |

## 3. Layer responsibilities

| Layer | Owns | Knows nothing about |
|---|---|---|
| `api.py` | HTTP, uploads, static files | agents, tools, models |
| `orchestrator.py` | the sequence of a turn | how any single step works |
| `router/` | which agent handles a message | what agents do |
| `agents/` | the reasoning loop | HTTP, audio, storage |
| `rag/` | retrieval + grounding | MCP, agents |
| `mcp_client/` | speaking MCP | facility data |
| `mcp_server/` | the tools | LLMs, agents |
| `llm/` | provider protocol | prompts, business logic |
| `voice/` | audio conversion | everything else |

Each arrow points one way. No module imports the layer above it, which is why
each one can be tested on its own.

## 4. Design decisions

### 4.1 One LLM client for three providers
Groq, Ollama and Gemini all expose an OpenAI-compatible endpoint. `app/llm/client.py`
is therefore a single class; the provider is a base URL in `.env`. Switching from
a hosted model to a fully local one is a one-line configuration change.

### 4.2 Two model tiers
`FAST_MODEL` handles routing, small talk and grounded summarising. `SMART_MODEL`
handles multi-step reasoning and action planning. Roughly 60% of turns never
touch the expensive model. See §7.

### 4.3 Hybrid routing instead of pure-LLM routing
Regex rules resolve the obvious traffic at zero cost and with perfect
repeatability; the LLM classifier only sees what the rules could not settle.
The classifier returns a confidence, which gives a principled hook for handling
ambiguity and for escalation.

### 4.4 One reusable agent class
`ToolLoopAgent` implements the entire autonomous loop once. The Live Data, Data,
Action and Investigation agents are the same class with a different prompt,
model tier and tool allow-list. Adding an agent is a five-line change in
`app/agents/registry.py`.

### 4.5 Capability restriction over instruction
The Live Data agent cannot create a service request because the write tools are
never placed in its tool list. Removing a capability is a stronger guarantee
than telling the model not to use it.

### 4.6 A real MCP server, not direct function calls
The tools run in a separate process and speak MCP over stdio, so they are
reusable by any MCP host (Claude Desktop, another agent framework) and the agent
process is isolated from the facility system. If the subprocess cannot start,
the client falls back to in-process calls so a demo never dies on a spawn error.

### 4.7 Arithmetic in Python, not in the LLM
`get_asset_status` returns `power_deviation_pct` and `airflow_deviation_pct`
already computed. Language models are unreliable at arithmetic; every number the
agent speaks therefore comes from Python, not from the model.

### 4.8 Two independent grounding guards
A numeric relevance gate (before the LLM) and an `INSUFFICIENT_CONTEXT` token
(from the LLM). Either one alone leaks; together they make refusal the default.

## 5. LLM routing strategy

```
message
  │
  ├─ 1. RULES  (regex, 0 ms, 0 tokens)
  │     confident?  ──yes──►  route
  │     no
  ▼
  ├─ 2. LLM CLASSIFIER  (fast model, JSON, ~150 tokens)
  │     returns {route, confidence, reason}
  │     confidence ≥ 0.45?  ──yes──►  route
  │     no
  ▼
  └─ 3. FALLBACK
        message very short  ──►  ask the user a clarifying question
        otherwise           ──►  escalate to INVESTIGATE (all tools available)
```

Routing inputs, as required by the brief:

| Input | Where it is used |
|---|---|
| User intent | rules + classifier prompt |
| Required data source | route definitions (docs vs live vs both) |
| Tool availability | per-agent allow-lists in `registry.py` |
| Query complexity | `INVESTIGATE` gets more steps and the smart model |
| Confidence | returned by the classifier, drives the fallback branch |
| Cost / latency | model tier + `ROUTE_COST` per route |

**Handling ambiguity.** A short vague message ("it's hot") with low confidence
produces a clarifying question rather than a guess. One extra turn is cheaper
than a wrong investigation.

**Detecting a wrong route.** Two mechanisms. Before execution, low confidence
escalates to the superset route. After execution, an agent can set
`escalate=True` — the RAG agent does this when the knowledge base did not cover
the question — and the orchestrator re-runs the turn on the investigation agent.
Both paths are recorded in the trace as `rerouted_from`.

**When a tool fails.** Tools return `{"error": ..., "hint": ...}` instead of
raising. The agent reads the hint inside its own loop and retries with corrected
arguments. If the MCP transport itself fails, the client returns an error
payload rather than an exception. If the agent exhausts its step budget, a final
tool-free call forces an answer. The user always gets a spoken reply.

## 6. RAG architecture

```
8 markdown documents
   ↓  app/rag/chunker.py       split on ## headings, then 800 chars / 120 overlap
~70 chunks (heading trail prepended to each)
   ↓  app/rag/vector_store.py  Chroma + ONNX all-MiniLM-L6-v2, cosine
persistent index in .chroma/
   ↓  retrieve top 8
   ↓  app/rag/reranker.py      FlashRank cross-encoder, or lexical BM25-style
keep top 4
   ↓  relevance gate           top score < 0.15 → refuse without calling the LLM
   ↓  app/rag/pipeline.py      grounded prompt, INSUFFICIENT_CONTEXT allowed
grounded answer + citations
```

Retrieve wide and cheap, then rerank narrow and accurate. Vector search alone
confuses "AHU filter" with "chiller filter"; the reranker re-scores against the
exact query wording and fixes it.

The reranker is pluggable. FlashRank (a ~4 MB ONNX cross-encoder) is used when
installed; otherwise a pure-Python lexical reranker takes over, so the project
works on a machine with nothing extra installed. Set `RERANKER=none` to measure
what reranking is actually contributing.

## 7. Cost and latency

Measures already in place:

1. **Tier the model.** Routing, small talk and grounded summarising use the
   8B model; only reasoning and action planning use the 70B.
2. **Rules before the model.** Roughly 40% of turns are routed without any LLM
   call at all.
3. **Relevance gate before generation.** An out-of-scope question is refused
   without an LLM call.
4. **Trim the history.** Eight turns maximum, so the prompt cannot grow forever.
5. **Truncate tool results.** Tool JSON is capped at 6 KB before it enters the
   context.
6. **Cap the loop.** `MAX_AGENT_STEPS` bounds the worst case.
7. **Restrict tool lists.** Fewer tool schemas per agent means fewer prompt
   tokens on every step of the loop.

Further steps for a production deployment: cache the router decision for
repeated phrasings, stream the first sentence into TTS so the user hears speech
before generation finishes, batch the embedding calls, and add a semantic cache
for frequently asked documentation questions.

## 8. Swapping components

| Component | Current | Swap by editing | Alternative |
|---|---|---|---|
| LLM | Groq Llama 3.3 | `.env` only | Ollama, Gemini |
| STT | faster-whisper | `app/voice/stt.py` | Deepgram, Sarvam |
| TTS | pyttsx3 | `app/voice/tts.py` | Piper, Coqui, ElevenLabs |
| Vector DB | Chroma | `app/rag/vector_store.py` | Qdrant, pgvector, FAISS |
| Reranker | FlashRank / lexical | `app/rag/reranker.py` | bge-reranker, Cohere |
| Sessions | in-memory dict | `app/session.py` | Redis |
| Facility data | JSON file | `app/mcp_server/repository.py` | real BMS API |

## 9. Assumptions

1. Facility data is simulated. The dates in `data/facility_db.json` are seeded
   so the demo scenario (Building A, 3rd floor, AHU-02) is reproducible.
2. Single tenant, single operator, no authentication. A real deployment needs
   auth on `/api/*` and the operator identity written into the audit log.
3. Sessions are in-process, so restarting the server clears conversations.
4. Service requests are written to memory, not back to `facility_db.json`, so
   every run starts from the same state — which is what makes the evaluation
   suite repeatable.
5. English only. Whisper auto-detects language, but the prompts are English.
6. Turn-based voice, not full duplex. No barge-in or interruption handling.
