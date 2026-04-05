# IEOTBSM LangGraph / agentic PoC

Proof-of-concept that extends **Hexmoor, Wilson & Bhattaram (2006)**, *A Theoretical Inter-organizational Trust-based Security Model* ([*The Knowledge Engineering Review*, 21(2), 127–161](https://doi.org/10.1017/S0269888906000732)) into an **agentic, cross-organizational RAG** setting: multiple enterprises, boundary spanners, sensitivity-aware trust gates (ISP-style), inter-org trust dynamics (τ), and TPM4-style human review. The codebase is educational and not production-hardened.

## What’s in the repo

| Piece | Role |
|--------|------|
| [`trust_engine.py`](trust_engine.py) | Trust ledger, gates, provenance, violations, metrics |
| [`network.py`](network.py) | Multi-org agent mesh, simulation runner, **SSE-friendly** `iter_query_simulation_events()` |
| [`langgraph_impl.py`](langgraph_impl.py) | LangGraph workflow + simulated per-org knowledge / RAG |
| [`run_poc.py`](run_poc.py) | CLI: full **simulation** (six scripted demos) or **LangGraph + LLM** |
| [`dashboard_app.py`](dashboard_app.py) | **FastAPI** app: REST + **Server-Sent Events** live simulation UI |
| [`static/`](static/) | Dashboard HTML/CSS/JS |

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

### 4. LangGraph + Ollama

```bash
python3 run_poc.py --langgraph --llm ollama
# optional:
python3 run_poc.py --langgraph --llm ollama --model llama3.2 --ollama-base-url http://127.0.0.1:11434
```

### 5. LangSmith (with LangGraph)

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
python3 run_poc.py --langgraph --langsmith
```

Optional: `export LANGSMITH_PROJECT=your-project`. Use `--print-graph-mermaid` to print a structural Mermaid diagram of the graph.

## CLI flags (summary)

| Flag | Purpose |
|------|---------|
| `--langgraph` | Use LangGraph + LLM instead of pure simulation |
| `--llm claude` / `--llm ollama` | LLM backend |
| `--model` | Override model name |
| `--ollama-base-url` | Ollama server URL |
| `--langsmith` | Enable LangSmith tracing (requires `--langgraph`) |
| `--print-graph-mermaid` | Print Mermaid graph (requires `--langgraph`) |
| `--tpm` | Trust policy mode (default `4` = human review path) |
| `--alpha`, `--decrement` | Inter-org trust parameters |

## Design notes

- **Simulation** path is self-contained and streams fine-grained events for the dashboard without requiring an LLM.
- **LangGraph** path compiles a supervisor-style graph (orchestrator → trust gate → boundary spanner → internal RAG → synthesizer, with human-review branches) and can be traced in LangSmith.
- **Session state** for the dashboard lives in memory on the server; restarting `uvicorn` clears all sessions.

## License / citation

### Software (this repository)

The **agentic extension and implementation** in this repository (Python code, dashboard, and related assets) is licensed under the **Business Source License 1.1** (**SPDX: `BUSL-1.1`**). See [`LICENSE`](LICENSE) for the full terms, including:

- **Non-production** use is permitted under the BSL terms; **Additional Use Grant** is currently **None** (see `LICENSE`—adjust with legal advice if you need broader production rights before the Change Date).
- On **Change Date** **2030-04-04** (or the fourth anniversary of first public distribution of a given version, whichever is earlier), that version of the Licensed Work is additionally licensed under **Apache License, Version 2.0** (the **Change License**).
- BSL is **not** an OSI-approved open-source license until the Change License applies; plan accordingly for redistribution and production use.

**Third-party packages** installed via [`requirements.txt`](requirements.txt) (e.g. LangChain, LangGraph, FastAPI) remain under their respective licenses.

### Theory (2006 paper)

The **published journal article** (Hexmoor, Wilson & Bhattaram, 2006) is separate from this repo: cite it for the underlying model; journal/publisher copyright on the **paper** is unchanged by this software license.

### Parameters you may customize

The `LICENSE` file names **Seth Wilson** as Licensor and sets **Change Date** / **Change License** as above. Update those fields (and **Additional Use Grant**) if another entity owns the rights or your counsel recommends different terms.
