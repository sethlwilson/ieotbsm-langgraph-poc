# IEOTBSM LangGraph / agentic PoC

Proof-of-concept that extends **Hexmoor, Wilson & Bhattaram (2006)**, *A Theoretical Inter-organizational Trust-based Security Model* ([*The Knowledge Engineering Review*, 21(2), 127–161](https://doi.org/10.1017/S0269888906000732)) into an **agentic, cross-organizational RAG** setting: multiple enterprises, boundary spanners, sensitivity-aware trust gates (ISP-style), inter-org trust dynamics (τ), and TPM4-style human review. The codebase is educational and not production-hardened.

## What this PoC demonstrates

- A **multi-organization agent mesh** with an inter-org trust ledger, provenance, and gate outcomes you can inspect run to run.
- A **pure simulation** path (no API keys) that runs scripted demos and prints trust matrices and synthesized answers, plus the same trust logic driving a **FastAPI dashboard** over **Server-Sent Events** for live playback.
- An optional **LangGraph + LLM** path (Claude or local Ollama) that compiles the same conceptual workflow: **sequential multi-org fan-out** (each partner org runs trust gate → optional human review → boundary spanner → internal RAG, then advances to the next partner), **`--demo-id` / `--demo-index`** to pick a scripted preset, optional **`--stream`** to print accumulated state after each graph superstep, and **LangSmith** tracing when enabled.
- A teaching-oriented slice of the 2006 model—not a production security or compliance product.

## Concepts (sketch)

These terms match the paper’s spirit; see the article for formal definitions.

- **Sensitivity** — Each query carries a label **INTERNAL**, **CONFIDENTIAL**, or **RESTRICTED**. Higher tiers raise the trust bar for cross-organization retrieval and cooperation (ISP-style enforcement at “edges” between orgs).
- **Inter-organizational trust (τ)** — Directed trust values between organizations, updated as the simulation runs. Gates compare τ (and related state) against thresholds that depend on sensitivity.
- **Trust gate** — Decides whether a cross-org hop is allowed, may **deny**, **approve**, or route to **human review** depending on policy and state.
- **Trust Policy Models (TPM)** — After a violation, the ledger applies one of four modes (see `AgenticTPM` in [`trust_engine.py`](trust_engine.py)):
  - **TPM1** — Proportional trust decay along the query / agent chain (paper Definition 24, TPM1).
  - **TPM2** — Uniform decay on each edge in the chain (Definition 24, TPM2).
  - **TPM3** — The initiator’s trust toward downstream chain agents is cut; inter-org trust is penalized (Definition 24, TPM3).
  - **TPM4** — **Agentic extension:** queue the violation for **human review** before modifying trust. The implementation also enqueues human review for **CONFIDENTIAL** / **RESTRICTED** violations or **repeated** breaches between the same org pair, even when the selected TPM mode is 1–3.

## What’s in the repo

| Piece | Role |
|--------|------|
| [`trust_engine.py`](trust_engine.py) | Trust ledger, gates, provenance, violations, metrics |
| [`network.py`](network.py) | Multi-org agent mesh, simulation runner, **SSE-friendly** `iter_query_simulation_events()` |
| [`langgraph_impl.py`](langgraph_impl.py) | LangGraph workflow + simulated per-org knowledge / RAG |
| [`run_poc.py`](run_poc.py) | CLI: full **simulation** (six scripted demos) or **LangGraph + LLM** |
| [`dashboard_app.py`](dashboard_app.py) | **FastAPI** app: REST + **Server-Sent Events** live simulation UI |
| [`static/`](static/) | Dashboard HTML/CSS/JS |
| [`packages/ieotbsm_core/`](packages/ieotbsm_core/) | Installable trust core (`pip install -e ./packages/ieotbsm_core`) |
| [`services/trust_api/`](services/trust_api/) | Trust HTTP service (OpenAPI `/docs`, Postgres/SQLite) |
| [`services/trust_mcp/`](services/trust_mcp/) | MCP stdio server exposing Trust API tools |
| [`adapters/langgraph_ieotbsm/`](adapters/langgraph_ieotbsm/) | LangGraph ↔ HTTP trust client |

### Trust API and MCP (quick start)

1. Install deps: `pip install -r requirements.txt`
2. Run API (SQLite file `./trust_service.db` by default):

   ```bash
   uvicorn trust_api.main:app --host 127.0.0.1 --port 8088
   ```

   Override DB: `TRUST_API_DATABASE_URL=postgresql+psycopg2://user:pass@host/db` (install `psycopg2-binary` alongside the service). API key header matches `TRUST_API_API_KEY` (default `dev-key`).

3. LangGraph with remote gate: start the API, then e.g. `IEOTBSM_TRUST_API_URL=http://127.0.0.1:8088 python3 run_poc.py --langgraph --llm ollama --trust-backend http`

4. MCP (stdio): with API running, configure your host with command `python -m trust_mcp.server` from `services/trust_mcp` on `PYTHONPATH`, or `trust-mcp` after `pip install -e ./services/trust_mcp`. Set `TRUST_API_BASE_URL`, `TRUST_API_KEY`, `TRUST_API_TENANT` as needed.

5. Dashboard backed by API: `DASHBOARD_TRUST_API_URL=http://127.0.0.1:8088 uvicorn dashboard_app:app --port 8765` (optional `DASHBOARD_TRUST_API_KEY`). Omit the env var to keep the original in-memory dashboard.

## LangGraph workflow

![LangGraph workflow: org orchestrator, trust gate, optional human review, boundary spanner, internal agent, synthesizer](diagram.png)

The figure above is a high-level illustration; the **current** topology (including **`advance_org`** and orchestrator shortcuts) matches [`langgraph_impl.py`](langgraph_impl.py) and the Mermaid text from **`python3 run_poc.py --langgraph --print-graph-mermaid`**.

Compiled LangGraph for the PoC (trust gate, human-review branches, and per-partner fan-out). Node naming and roles mirror the header comments in [`langgraph_impl.py`](langgraph_impl.py).

- **`org_orchestrator`** — Organization-level supervisor: builds the partner list (`target_org_ids`), optional LLM sensitivity hint, and provenance. If there are **no** partner orgs with positive τ, the graph routes **directly** to **`synthesizer`**.
- **`trust_gate`** — Enforces ISP-style rules at org boundaries for the **current** partner; may **approve** (continue to retrieval), **deny** (record a reason in `org_denials` when not escalated to human review), or send the run to **`human_review`** (CONFIDENTIAL / RESTRICTED failures).
- **`human_review`** — TPM4-style pause: a simulated approver may **approve** (resume via boundary spanner) or **deny** (record `org_denials` for that partner).
- **`boundary_spanner`** — Cross-org “edge” agent that spans boundaries when the gate allows.
- **`internal_agent`** — In-org retrieval / RAG against simulated per-org knowledge.
- **`advance_org`** — After one partner’s branch completes (denied, human-denied, or post-RAG), moves to the **next** partner (back to **`trust_gate`**) or, when all partners are done, routes to **`synthesizer`**.
- **`synthesizer`** — Assembles the final answer from accumulated **`org_answers`** and **`org_denials`** (LLM or markdown fallback).

**Edges (multi-org):** Denied or completed paths go to **`advance_org`**, not immediately to **`synthesizer`**, so every partner in `target_org_ids` is visited in order. **`synthesizer`** runs **once** at the end.

## Requirements

- **Python 3.10+** (see [`.python-version`](.python-version) if you use `pyenv`).

Install all PoC dependencies (simulation, LangGraph, both LLM integrations, LangSmith client, and the dashboard server):

```bash
pip install -r requirements.txt
```

For a **minimal** install you only need `langgraph` and `langchain-core` to run `run_poc.py` in simulation mode; the full file above matches every documented feature (Claude, Ollama, LangSmith, FastAPI).

**LangSmith** (when using `--langgraph --langsmith`):

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
```

## Quick start

### 1. Simulation mode (no API keys)

Runs six scripted “scenes” (trust arc including INTERNAL → CONFIDENTIAL → RESTRICTED) and prints trust matrices, gate outcomes, and synthesized answers.

```bash
python3 run_poc.py
```

Optional trust knobs:

```bash
python3 run_poc.py --tpm 4 --alpha 0.65 --decrement 0.06
```

**Scripted demos** (in run order; defined as `DEMO_QUERIES` in [`run_poc.py`](run_poc.py)):

| Preset id (`--demo-id`) | Title | What it stresses |
|----------------|--------|------------------|
| `silicon_ledger` | Operation Silicon Ledger | Cross-org market and supply-chain intel at **INTERNAL** sensitivity; gates open when τ is high enough. |
| `red_cell_brief` | Red-Cell Briefing | **CONFIDENTIAL** threat / vulnerability brief; stricter thresholds, human-review and ledger stress. |
| `capacity_wars` | Capacity Wars | Benchmarks vs cloud GPU pricing across orgs; boundary-spanner pairs and τ updates per hop. |
| `regulatory_horizon` | Regulatory Horizon | **CONFIDENTIAL** mixed-domain query (compliance + workforce); tighter ISP behavior. |
| `vault_seven` | Vault Seven | **RESTRICTED** threat telemetry and IOCs; highest τ bar—many denials unless trust grew in earlier scenes. |
| `talent_pipeline` | Talent Pipeline | **INTERNAL** workforce analytics; softer bar—contrast after Vault Seven. |

### 2. Live dashboard (FastAPI + SSE)

```bash
# after: pip install -r requirements.txt
uvicorn dashboard_app:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765/** (use `/` so the session cookie is set). You can run the full storyline, a single scenario, or a custom query; the trust matrix updates over SSE as the simulation advances.

**API (same origin, session cookie):**

- `GET /api/state` — trust matrix, org list, cycle, human-review queue size  
- `GET /api/demo-scenarios` — catalog of scripted scenarios  
- `GET /api/simulation/stream` — SSE event stream (`demo=1`, or `scenario_id=...`, or `query` + `requesting_org_id` + `sensitivity`)  
- `POST /api/session/reset` — reset the in-memory network for your session  

### 3. LangGraph + Claude

```bash
export ANTHROPIC_API_KEY=sk-...
python3 run_poc.py --langgraph --llm claude
```

Optional: `--model <claude-model-id>`.

**Demo preset** (defaults to the first entry in `DEMO_QUERIES` if omitted):

```bash
python3 run_poc.py --langgraph --demo-id vault_seven
python3 run_poc.py --langgraph --demo-index 2
```

`--demo-id` and `--demo-index` are mutually exclusive; ids match the **`id`** column in the [Scripted demos](#1-simulation-mode-no-api-keys) table.

**Stream graph supersteps** (prints accumulated state after each LangGraph step; useful with `--langgraph`):

```bash
python3 run_poc.py --langgraph --stream
python3 run_poc.py --langgraph --demo-id silicon_ledger --stream
```

### 4. LangGraph + Ollama

```bash
python3 run_poc.py --langgraph --llm ollama
# optional:
python3 run_poc.py --langgraph --llm ollama --model llama3.2 --ollama-base-url http://127.0.0.1:11434
```

You can combine Ollama with **`--demo-id`**, **`--demo-index`**, and **`--stream`** the same way as in §3.

### 5. LangSmith (with LangGraph)

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
python3 run_poc.py --langgraph --langsmith
```

Optional: `export LANGSMITH_PROJECT=your-project`. Use `--print-graph-mermaid` to print a structural Mermaid diagram of the graph (matches the compiled graph, including **`advance_org`** and the orchestrator “no partners” shortcut). **`--stream`** and **`--langsmith`** can be used together.

## CLI flags (summary)

| Flag | Purpose |
|------|---------|
| `--langgraph` | Use LangGraph + LLM instead of pure simulation |
| `--llm claude` / `--llm ollama` | LLM backend |
| `--model` | Override model name |
| `--ollama-base-url` | Ollama server URL |
| `--langsmith` | Enable LangSmith tracing (requires `--langgraph`) |
| `--print-graph-mermaid` | Print Mermaid graph (requires `--langgraph`) |
| `--demo-id ID` | LangGraph: run one preset from `DEMO_QUERIES` by **`id`** (mutually exclusive with `--demo-index`) |
| `--demo-index N` | LangGraph: run preset by index `0 … n-1` (default **0** if neither demo flag is set) |
| `--stream` | LangGraph: print accumulated state after each graph superstep (`stream_mode="values"`) |
| `--tpm` | Trust policy mode (default `4` = human review path) |
| `--alpha`, `--decrement` | Inter-org trust parameters |

## Trust knobs

Simulation and LangGraph runs share the same trust-engine parameters via [`run_poc.py`](run_poc.py):

- **`--tpm`** — Selects TPM **1**, **2**, **3**, or **4** (default **4**). See [Concepts (sketch)](#concepts-sketch) for behavior; defaults favor human-review escalation where the engine applies it.
- **`--alpha`** — Weight **α** in the blend of inter-org τ and boundary-spanner trust when applying BS influence (paper Eq. 7; default **0.65**). Larger **α** weights inter-org τ more heavily in that blend.
- **`--decrement`** — Base decrement applied in TPM decay paths (default **0.06**); larger values penalize violations more sharply when TPM1–3 apply.

## Design notes

- **Simulation** path is self-contained and streams fine-grained events for the dashboard without requiring an LLM.
- **LangGraph** path compiles a supervisor-style graph with **sequential multi-org fan-out**: orchestrator → (per partner) trust gate → optional human review → boundary spanner → internal RAG → **`advance_org`** loop → single **`synthesizer`**. It can be traced in LangSmith and optionally streamed with **`--stream`**. See [LangGraph workflow](#langgraph-workflow).
- **Session state** for the dashboard lives in memory on the server; restarting `uvicorn` clears all sessions.

## Troubleshooting

- **Dashboard, LangSmith, or FastAPI errors** — Install the full stack: `pip install -r requirements.txt`. A minimal install is enough for simulation-only CLI runs, not for `uvicorn` or `--langsmith`.
- **`ANTHROPIC_API_KEY not set`** — LangGraph with default `--llm claude` needs this env var; use `--llm ollama` for a local model instead.
- **`--langsmith requires --langgraph`** / **`--print-graph-mermaid requires --langgraph`** / **`--stream requires --langgraph`** — Pass `--langgraph` on the same command.
- **Dashboard API 401 or empty state** — Open the app at **`/`** on the same host/port first so the session cookie is set (see **Live dashboard** in Quick start).

## License / citation

### Software (this repository)

The **agentic extension and implementation** in this repository (Python code, dashboard, and related assets) is licensed under the **Business Source License 1.1** (**SPDX: `BUSL-1.1`**). See [`LICENSE`](LICENSE) for the full terms, including:

- **Non-production** use is permitted under the BSL terms; **Additional Use Grant** is currently **None** (see `LICENSE`—adjust with legal advice if you need broader production rights before the Change Date).
- **Production deployment** of this codebase (including the Trust API/MCP) for external redistribution or SaaS still requires your own **license/legal review** (BSL terms, Additional Use Grant, or a separate agreement with the licensor).
- On **Change Date** **2030-04-04** (or the fourth anniversary of first public distribution of a given version, whichever is earlier), that version of the Licensed Work is additionally licensed under **Apache License, Version 2.0** (the **Change License**).
- BSL is **not** an OSI-approved open-source license until the Change License applies; plan accordingly for redistribution and production use.

**Third-party packages** installed via [`requirements.txt`](requirements.txt) (e.g. LangChain, LangGraph, FastAPI) remain under their respective licenses.

### Theory (2006 paper)

The **published journal article** (Hexmoor, Wilson & Bhattaram, 2006) is separate from this repo: cite it for the underlying model; journal/publisher copyright on the **paper** is unchanged by this software license.

### Parameters you may customize

The `LICENSE` file names **Seth Wilson** as Licensor and sets **Change Date** / **Change License** as above. Update those fields (and **Additional Use Grant**) if another entity owns the rights or your counsel recommends different terms.
