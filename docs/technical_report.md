# Technical Report

**Project:** Autonomous Voice Agent for Intelligent Facility Operations
**Challenge:** Nectar AI Engineer — Agentic AI Challenge

---

## 1. Summary

I built an autonomous facility operations agent that a manager can talk to. It
transcribes speech, decides which specialist agent should handle the request,
gathers evidence from a documentation knowledge base and from live facility data
over MCP, reasons across both, proposes an action, asks permission before
changing anything, and replies by voice.

The whole system runs on free and open-source components. Speech-to-text,
text-to-speech, embeddings, the vector database and the reranker all execute
locally on the CPU. The only hosted dependency is the LLM, on a free-tier key —
and switching to a fully local model via Ollama is a one-line change in `.env`,
because all three supported providers speak the same OpenAI-compatible protocol.

The design goal I set was **autonomy with restraint**: the agent should decide
its own investigation path, and should not be able to change anything without a
human saying yes.

---

## 2. What each task required, and how it is met

| Task | Implementation |
|---|---|
| 1 — Voice agent | faster-whisper STT → agent → pyttsx3 TTS, session memory, browser mic UI |
| 2 — LLM routing | 3-stage hybrid router: rules → LLM classifier with confidence → fallback |
| 3 — RAG | 8 documents → heading-aware chunking → Chroma → cross-encoder rerank → relevance gate → grounded answer with citations |
| 4 — MCP tools | a real MCP stdio server with 11 tools; writes held for confirmation |
| 5 — End to end | one orchestrator running the full pipeline, with self-correction |

---

## 3. The four decisions that shaped the system

### 3.1 Hybrid routing rather than pure-LLM routing

A single LLM classifier is the obvious approach and it is wasteful. Roughly 40%
of real traffic is trivially classifiable — greetings, yes/no answers, "create a
work order for AHU-02". A regex answers those in zero milliseconds for zero
tokens, and it is *more* reliable than a model, because it is deterministic.

So stage 1 is rules. Stage 2 is the small model, asked to return
`{route, confidence, reason}`. Stage 3 uses that confidence:

- **Very short and unclear** → ask a clarifying question. "It's hot" is not
  enough to act on, and one extra turn is far cheaper than a wrong five-tool
  investigation.
- **Long but unclear** → escalate to `investigate`, the route that holds every
  tool and can therefore find its own way.

Making the classifier report confidence is what turns routing from a guess into
a decision with a defined failure path.

### 3.2 Wrong routes are caught at run time, not at review time

Two mechanisms, one before execution and one after.

*Before:* low confidence escalates to the superset route.

*After:* an agent can report that it was given the wrong job. The RAG agent sets
`escalate=True` when the relevance gate rejects the query; the orchestrator then
re-runs the turn on the investigation agent, which can also read live data. The
response carries `rerouted_from`, so the correction shows up in the UI and in
the Langfuse trace and can be counted.

This matters because routing is the one component that is *silently* wrong. A
failed tool call is loud. A request sent to the wrong agent just produces a
slightly worse answer, and nobody notices.

### 3.3 Safety by capability, not by instruction

The brief requires that the agent must not blindly execute actions. Prompting a
model not to do something is the weakest available guarantee, so there are three
layers instead:

1. **Read-only agents never receive the write tool schemas.** The live-data
   agent cannot create a service request; the capability is not in its context.
2. **Interception.** When an agent that *does* have write tools calls one,
   `ToolLoopAgent` refuses to execute it, returns `awaiting_user_confirmation`
   to the model, and stores a `PendingAction` on the session. The model then
   asks its yes/no question naturally.
3. **A single execution point.** `app/agents/confirmation.py` is the only code
   in the repository that runs a write tool. One place to audit.

The safety evaluation suite asserts this end to end: it counts service requests
before and after a "create a maintenance request" turn and fails if the count
changed without a confirmation.

### 3.4 Arithmetic belongs in Python

`get_asset_status` does not return raw numbers and hope. It returns
`airflow_deviation_pct: -34.7`, `power_deviation_pct: 18.1`, and plain-English
`observations` like *"Filter differential pressure 1.9 inWC exceeds the 1.2 inWC
limit."*

Language models are unreliable at arithmetic and very good at reading. Moving
every calculation into the tool layer removes a whole class of hallucinated
figures: every number the agent speaks came out of Python.

---

## 4. RAG: making refusal the default

Retrieval always returns *something*. The interesting engineering is in deciding
when what came back is not good enough.

Two independent guards:

1. **A numeric relevance gate** before the LLM. If the best reranked score is
   below `MIN_RELEVANCE_SCORE`, the system refuses without generating at all —
   safer *and* cheaper.
2. **A prompt gate.** The LLM may reply with `INSUFFICIENT_CONTEXT`, which the
   pipeline converts into the standard refusal.

The reranker is what makes the numeric gate trustworthy. Measured on this
knowledge base:

| Query | Best vector | Best rerank |
|---|---|---|
| "what should I check if AHU airflow is low?" | 0.752 | **0.996** |
| "what is an AHU?" | 0.682 | **0.999** |
| "what is the wifi password for the cafeteria?" | 0.259 | **0.000** |
| "how many parking spaces does the building have?" | **0.448** | **0.000** |

The last row is the whole argument. Vector similarity scored the parking
question 0.448 — comfortably above the gate — because it looked superficially
like the "Building Data" section of the equipment specifications. The
cross-encoder scored it 0.000 and the gate refused. Without reranking, that
question would have reached the LLM with an irrelevant passage attached, which
is exactly the setup for a confident wrong answer.

The reranker is pluggable and falls back to a pure-Python lexical scorer when
FlashRank is not installed, so the system degrades rather than breaking on a
clean machine.

---

## 5. MCP: a real server, with a fallback

The tool layer is a genuine MCP server (`app/mcp_server/server.py`) speaking
JSON-RPC over stdio. The agent starts it as a child process exactly the way
Claude Desktop would, so the tools are reusable by any MCP host and the agent
process is isolated from the facility system.

That isolation has an operational cost: a subprocess can fail to spawn for
reasons that have nothing to do with the code — antivirus, a sandbox, a broken
interpreter path. So the client detects the failure, logs it, and falls back to
calling the same tool functions in-process. `GET /health` reports which mode is
live. A demo that dies because a subprocess would not start is not production
grade.

Tool errors are returned as data, never raised:

```json
{"error": "Asset 'Chiller-05' was not found.",
 "hint": "Valid assets are: Chiller-01, Chiller-02, AHU-01, AHU-02, ..."}
```

The agent reads the hint and corrects itself inside its own loop. In testing,
asking for a non-existent chiller produced *"There is no Chiller-05 in the
system. Building A has Chiller-01 and Chiller-02. Which one did you mean?"* —
recovery, not a stack trace.

---

## 6. Cost and latency

Seven measures are already in the code:

| Measure | Effect |
|---|---|
| Two model tiers | ~60% of turns never touch the 70B model |
| Rules before the classifier | ~40% of turns route with zero LLM tokens |
| Relevance gate before generation | out-of-scope questions cost no generation at all |
| History trimmed to 8 turns | the prompt cannot grow without bound |
| Tool results truncated to 6 KB | one verbose tool cannot flood the context |
| `MAX_AGENT_STEPS` cap | bounds the worst case |
| Per-agent tool allow-lists | fewer schemas re-sent on every loop step |

The next largest win is not a cost win but a *perceived latency* win: streaming
the first sentence into TTS so the operator hears speech while the rest is still
generating. That is the change I would make first with more time.

---

## 7. Observability

Every turn is one Langfuse trace, with nested spans for STT, routing, the agent
loop, each LLM call, each MCP tool call, each RAG stage and TTS. Trace metadata
carries `route`, `confidence`, `agent`, `tools` and `rerouted_from`, so you can
filter for every turn where routing self-corrected, or compare latency by route
— which is how you would actually tune the confidence threshold on real traffic.

The integration sits behind `app/tracing.py`, and every helper becomes a no-op
if the keys are missing or the SDK is absent. Observability must never be able
to take production down.

---

## 8. Evaluation

28 cases across four suites, run with `python -m eval.run_eval`:

| Suite | Cases | What it asserts |
|---|---|---|
| Routing accuracy | 13 | each message reaches the intended agent |
| RAG grounding | 8 | 5 answered with the right facts, **3 correctly refused** |
| Tool selection | 5 | the required MCP tools were actually called |
| Safety | 2 | no write executed without confirmation |

The suite is deliberately small. 28 cases that each test one behaviour tell you
what broke when a score moves; a thousand random questions do not.

Verified without an LLM (deterministic components, run directly):

- **13/13 routing rules** classify correctly, including the distinction between
  "what is a chiller" (definition → RAG) and "what is Chiller-01's current
  temperature" (reading → live data), which needed a negative lookahead and a
  reordering of the rules to get right.
- **Retrieval and reranking** produce the scores in §4.
- **All 11 MCP tools** return correct values over real stdio JSON-RPC, including
  the error contract for bad input.

---

## 9. What I would do next

1. **Stream TTS.** The single largest perceived-latency improvement available.
2. **Swap pyttsx3 for Piper.** The OS voice is functional but noticeably robotic.
3. **Redis-backed sessions.** In-memory sessions block horizontal scaling.
4. **LLM-as-judge evaluation.** The current suite checks routing, tools, grounding
   and safety, but not answer *quality*.
5. **Barge-in.** A facility manager should be able to interrupt a long reply.
6. **A router-decision cache.** Repeated phrasings should not be re-classified.

---

## 10. Honest limitations

- Facility data is simulated. It is seeded so the demo scenario is reproducible,
  but a real BMS would bring latency, missing readings and dirty data that this
  system has never faced. Only `app/mcp_server/repository.py` would change.
- No authentication. A real deployment needs auth on `/api/*` and the operator
  identity written into the audit log for every confirmed action.
- Sessions are in-process, so a restart clears conversations.
- English only. Whisper auto-detects the language, but every prompt is English.
- Turn-based voice, not full duplex — no barge-in.
- The knowledge base is 8 curated documents: enough to exercise retrieval,
  reranking and refusal honestly, not enough to claim anything about behaviour
  on a real corpus of thousands of manuals.
