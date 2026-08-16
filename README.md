# Nectar — Autonomous Voice Agent for Facility Operations

A facility manager speaks. The agent transcribes, decides which specialist agent
should handle the request, gathers what it needs from a RAG knowledge base and
live MCP tools, reasons over the evidence, proposes an action, asks before
changing anything, and answers by voice.

Everything runs on free / open-source components. STT, TTS, embeddings, the
vector DB and reranking all run locally on the CPU. The LLM uses a free-tier key,
or runs fully offline via Ollama with a one-line config change.

| Capability | How |
|---|---|
| Speech to text | faster-whisper, local |
| Routing | rules → LLM classifier with confidence → fallback |
| Knowledge | Chroma + MiniLM embeddings + cross-encoder rerank |
| Live data | MCP server, 11 tools over stdio |
| Reasoning | autonomous tool-calling loop |
| Actions | write tools held for user confirmation |
| Memory | per-session history, trimmed |
| Text to speech | pyttsx3, local |
| Tracing | Langfuse |

**Docs:** [architecture](docs/architecture.md) · [MCP & API](docs/mcp_api.md) ·
[sample conversations](docs/sample_conversations.md) ·
[technical report](docs/technical_report.md) · [eval results](eval/results.md)

---

## The scenario

> **User:** "The office on the third floor feels very hot. Can you investigate
> and let me know if we need maintenance?"

The agent decides its own path — nothing below is hard-coded:

```
find_assets(building="Building A", floor=3)
    → ZONE-A-3F is 26.8 °C against a 22 °C setpoint, served by AHU-02
get_asset_status("AHU-02")
    → airflow 34.7% below design, fan at 98%, filter dP 1.9 inWC (limit 1.2)
get_asset_relationships("AHU-02")   → fed by Chiller-01
get_asset_status("Chiller-01")      → power +18.1%, CHW 3.1 °C above setpoint
get_active_alerts("Building A")     → 4 corroborating alarms
search_knowledge_base("AHU low airflow")
    → filter dP over limit causes ~60% of low airflow cases
create_service_request(...)         ← HELD, not executed
```

> **Agent:** "The third floor is at twenty-seven degrees against a twenty-two
> degree setpoint. AHU-02 is the cause — airflow is thirty-five percent below
> design with the fan at ninety-eight percent, and the filter pressure is above
> its limit. Shall I raise a high priority maintenance request?"
>
> **User:** "Yes please."
>
> **Agent:** "Done. I have raised SR-2042 at high priority and assigned it to
> the HVAC Team."

---

## Architecture

```
🎤 Voice / ⌨️ Text
        ▼
   FastAPI  →  Orchestrator
                   │
                   ├──► STT (faster-whisper)
                   │
                   ├──► ROUTER — rules → LLM classifier → confidence fallback
                   │       ├─ general       → plain LLM, no tools
                   │       ├─ rag           → documents only
                   │       ├─ live_data     → MCP reads
                   │       ├─ data_analysis → MCP reads + arithmetic
                   │       ├─ action        → MCP writes (held)
                   │       └─ investigate   → everything, multi-step
                   │              │
                   │              ├──► RAG — Chroma → rerank → gate → answer
                   │              └──► MCP — stdio JSON-RPC → 11 tools
                   │
                   ├──► CONFIRMATION — the only place a write executes
                   └──► TTS (pyttsx3)  →  🔊

Every box emits a Langfuse span. One trace = one user turn.
```

Full detail and the layering rules: [docs/architecture.md](docs/architecture.md).

---

## Setup

Python 3.10+, ~300 MB disk for the local models, a microphone (optional — typing
works too).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env
```

Use a virtual environment — this project pins `pydantic`, `openai` and
`starlette`, and a global install can downgrade other projects.

**Two free keys, ~3 minutes:**

- **Groq** (the LLM) — <https://console.groq.com> → API Keys. No credit card.
- **Langfuse** (tracing) — <https://cloud.langfuse.com> → Settings → API Keys.

Put them in `.env`. Missing Langfuse keys just disable tracing; the app still runs.

```bash
python -m scripts.ingest      # build the vector index (~30 s first run)
python run.py                 # → http://127.0.0.1:8000
```

First run downloads ~230 MB of models (Whisper 150 MB, MiniLM 80 MB, FlashRank
3 MB), cached afterwards.

Without a microphone:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Why is the third floor hot?\"}"
```

### Fully offline

```bash
ollama pull llama3.1:8b
# .env:  LLM_PROVIDER=ollama, FAST_MODEL=llama3.1:8b, SMART_MODEL=llama3.1:8b
```

Everything else is already local. An 8B local model calls tools less reliably
than Llama 3.3 70B — same architecture, lower quality.

---

## Configuration

Key settings (full list in `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` \| `ollama` \| `gemini` |
| `FAST_MODEL` | `llama-3.1-8b-instant` | routing, small talk, summarising |
| `SMART_MODEL` | `llama-3.3-70b-versatile` | reasoning, tool planning |
| `WHISPER_MODEL` | `base` | `tiny` \| `base` \| `small` \| `medium` |
| `MIN_RELEVANCE_SCORE` | `0.15` | below this, refuse instead of guessing |
| `RERANKER` | `auto` | `auto` \| `flashrank` \| `lexical` \| `none` |
| `MAX_AGENT_STEPS` | `6` | cap on the autonomous loop |

---

## Layout

```
app/
  config.py         every setting, one place
  tracing.py        Langfuse wrapper — no-ops if disabled
  session.py        conversation memory + pending actions
  orchestrator.py   one user turn, end to end
  api.py            FastAPI endpoints
  llm/              one client for Groq / Ollama / Gemini
  router/           rules.py (stage 1), router.py (stages 2-3)
  agents/           tool_agent.py is the reusable loop; registry.py maps routes
  rag/              chunker → vector_store → reranker → pipeline
  mcp_server/       repository, tools, registry, stdio server
  mcp_client/       MCP client with in-process fallback
  voice/            stt.py, tts.py
data/               8 knowledge base docs + simulated BMS JSON
eval/               golden dataset + runner + results
docs/               architecture, MCP/API, samples, report
web/index.html      demo UI
```

---

## How it works

### Agent loop

```
repeat up to MAX_AGENT_STEPS:
    ask the LLM, offering it the tools
    replied with text  → done
    asked for tools    → run them, feed results back, loop
out of steps           → force a final tool-free answer
```

Every tool-using agent is `ToolLoopAgent` with a different prompt, model tier and
tool allow-list. Adding an agent is a five-line change in `agents/registry.py`.

### Routing

```
1. RULES      regex, 0 ms, 0 tokens        → ~40% of traffic
2. CLASSIFIER fast model, JSON + confidence
3. FALLBACK   very short → ask a clarifying question
              otherwise  → escalate to `investigate` (has every tool)
```

**Ambiguity:** "it's hot" with low confidence gets a question, not a guess.

**Wrong routes** are caught two ways. *Before execution:* confidence under 0.45
escalates. *After execution:* an agent can set `escalate=True` — the RAG agent
does this when the knowledge base did not cover the question — and the
orchestrator re-runs on the investigation agent. The response reports
`rerouted_from`, so the correction is visible in the UI and the trace.

**Tool failures** return `{"error", "hint"}` rather than raising, so the agent
reads the hint and retries inside its own loop. Any unhandled exception still
produces a spoken sentence — a voice assistant that goes silent is worse than one
that admits a problem.

**Cost/latency:** two model tiers, rules before the classifier, the relevance
gate refusing before generation, history trimmed to 8 turns, tool results capped
at 6 KB, the loop capped, per-agent tool allow-lists. Roughly 60% of turns never
touch the expensive model.

### RAG

```
8 docs → heading-aware chunking → 51 chunks
       → Chroma (ONNX MiniLM, cosine) → top 8
       → cross-encoder rerank → top 4
       → relevance gate (< 0.15 → refuse, no LLM call)
       → grounded prompt, INSUFFICIENT_CONTEXT permitted
       → answer + citations
```

Two independent guards make refusal the default: a numeric gate before the LLM,
and an `INSUFFICIENT_CONTEXT` token from it. Measured:

| Query | Best vector | Best rerank | Outcome |
|---|---|---|---|
| "what should I check if AHU airflow is low?" | 0.752 | **0.996** | ✓ correct section |
| "what is an AHU?" | 0.682 | **0.999** | ✓ correct section |
| "at what filter dP should the filter be replaced?" | 0.534 | **0.998** | ✓ correct section |
| "what is the wifi password for the cafeteria?" | 0.259 | **0.000** | ✓ refused |
| "how many parking spaces does the building have?" | **0.448** | **0.000** | ✓ refused |

That last row is the argument for reranking. The raw vector score (0.448) is well
above the 0.15 gate — it looked like the "Building Data" section of the specs —
so vector search alone would have handed an irrelevant passage to the LLM. The
cross-encoder scored it 0.000 and the gate refused.

### MCP

A real MCP server over stdio, startable standalone
(`python -m app.mcp_server.server`) and usable by any MCP host. 9 read tools,
2 write tools. Full reference: [docs/mcp_api.md](docs/mcp_api.md).

Three things worth noting:

- **Arithmetic happens in Python.** `get_asset_status` returns
  `airflow_deviation_pct: -34.7` already computed. Models are unreliable at
  arithmetic, so every number the agent speaks comes from Python.
- **Errors are data.** A bad asset name returns `{"error", "hint"}` and the agent
  self-corrects.
- **Graceful degradation.** If the subprocess cannot start, the client falls back
  to in-process calls. `/health` reports which mode is live.

### Safety

Three layers stop the agent acting on its own:

1. **Capability restriction** — read-only agents never receive the write tool
   schemas, so they cannot call them.
2. **Interception** — `ToolLoopAgent` refuses to execute a write, returns
   `awaiting_user_confirmation`, and stores a `PendingAction`.
3. **One execution point** — `agents/confirmation.py` is the only code that runs
   a write tool, and only after approval.

The safety eval asserts this end to end by counting service requests before and
after a "create a maintenance request" turn.

---

## Evaluation

```bash
python -m eval.run_eval                # all suites
python -m eval.run_eval --suite rag    # routing | rag | tools | safety
```

| Suite | Cases | Asserts |
|---|---|---|
| Routing | 13 | each message reaches the intended agent |
| RAG | 8 | 5 answered correctly, **3 correctly refused** |
| Tools | 5 | the required MCP tools were actually called |
| Safety | 2 | no write executed without confirmation |

28 cases that each test one behaviour. Results: [eval/results.md](eval/results.md).

---

## Assumptions

1. Facility data is simulated in `data/facility_db.json`, seeded so the demo
   scenario is reproducible. A real BMS means rewriting
   `app/mcp_server/repository.py` only.
2. No authentication. Production needs auth on `/api/*` and the operator identity
   in the audit log.
3. Sessions are in-process; a restart clears them.
4. Service requests are written to memory, not the seed file — which is what makes
   the eval suite repeatable.
5. English only. Whisper auto-detects, but the prompts are English.
6. Turn-based voice, not full duplex. No barge-in.

## Next steps

Stream the first sentence into TTS (biggest perceived-latency win) · swap pyttsx3
for Piper · Redis sessions · LLM-as-judge for answer quality · barge-in ·
cache router decisions.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LLM call failed after 3 attempts` | check `GROQ_API_KEY`, then `GET /health` |
| First request takes ~30 s | Whisper model downloading, one-time |
| No audio | TTS failed; text reply still works, see the log |
| `mcp_mode: in_process` | subprocess did not start; still works, see startup log |
| `Vector store is empty` | `python -m scripts.ingest` |
| Mic blocked in browser | use `127.0.0.1`, not a LAN IP |
| Answers ignore edited docs | `python -m scripts.ingest --rebuild` |
| Dependency conflicts | you installed outside a venv |
