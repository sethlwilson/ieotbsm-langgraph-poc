"""
IEOTBSM Agentic AI — LangGraph Extension
=========================================
Proof of Concept Runner

Usage (simulation mode, no API key needed):
    python3 run_poc.py

Usage (LangGraph + Claude, requires API key):
    ANTHROPIC_API_KEY=sk-... python3 run_poc.py --langgraph

Usage (LangGraph + local Ollama, no API key):
    python3 run_poc.py --langgraph --llm ollama
    # optional: --model llama3.2 --ollama-base-url http://127.0.0.1:11434

Usage (LangGraph + LangSmith tracing — graph/steps in the Smith UI):
    pip install -r requirements.txt
    export LANGSMITH_TRACING=true
    export LANGSMITH_API_KEY=lsv2_...
    python3 run_poc.py --langgraph --langsmith

Usage (pick demo preset + stream graph state each superstep):
    python3 run_poc.py --langgraph --demo-id vault_seven --stream
    python3 run_poc.py --langgraph --llm ollama --demo-index 2 --stream

Based on: Hexmoor, Wilson & Bhattaram (2006)
The Knowledge Engineering Review, 21(2), 127-161.

Browser dashboard (FastAPI + SSE):
    uvicorn dashboard_app:app --host 127.0.0.1 --port 8765
    Open http://127.0.0.1:8765/
"""

import sys
import os
import json
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import IEOTBSMAgenticNetwork
from ieotbsm_core import SensitivityLevel


DEMO_QUERIES = [
    {
        "id": "silicon_ledger",
        "title": "Operation Silicon Ledger",
        "tagline": "Acme Corp needs a live picture of fabs, DRAM, and hyperscaler GPU economics.",
        "query": "What are the current semiconductor supply chain risks and market pricing trends?",
        "sensitivity": SensitivityLevel.INTERNAL,
        "requesting_org": "org_0",
        "description": "Cross-org market + supply chain intelligence — trust gates open for partners with tau above INTERNAL threshold.",
    },
    {
        "id": "red_cell_brief",
        "title": "Red-Cell Briefing",
        "tagline": "Sentinel AI escalates to CONFIDENTIAL: APT campaigns and patch urgency.",
        "query": "Are there any active threat actors or vulnerabilities affecting our sector?",
        "sensitivity": SensitivityLevel.CONFIDENTIAL,
        "requesting_org": "org_2",
        "description": "Stricter thresholds: more gate failures, TPM4 human-review, trust ledger stress test.",
    },
    {
        "id": "capacity_wars",
        "title": "Capacity Wars",
        "tagline": "Vertex benchmarks AI infra spend against Orionis pricing intel.",
        "query": "What are benchmark performance metrics and cloud GPU pricing for AI workloads?",
        "sensitivity": SensitivityLevel.INTERNAL,
        "requesting_org": "org_3",
        "description": "Supply chain org crosses into benchmarks domain — watch BS pairs and tau updates per hop.",
    },
    {
        "id": "regulatory_horizon",
        "title": "Regulatory Horizon",
        "tagline": "Nexus maps EU AI Act timelines against Caldwell workforce signals.",
        "query": "What is the regulatory compliance status and workforce talent landscape?",
        "sensitivity": SensitivityLevel.CONFIDENTIAL,
        "requesting_org": "org_1",
        "description": "Mixed-domain query; CONFIDENTIAL sensitivity tightens ISP thresholds across the mesh.",
    },
    {
        "id": "vault_seven",
        "title": "Vault Seven",
        "tagline": "Orionis requests RESTRICTED threat telemetry — the highest bar in the model.",
        "query": "Share restricted threat intelligence on APT campaigns and semiconductor sector targeting including IOCs.",
        "sensitivity": SensitivityLevel.RESTRICTED,
        "requesting_org": "org_4",
        "description": "RESTRICTED tau threshold (0.80): widespread denials unless trust grew from earlier scenes.",
    },
    {
        "id": "talent_pipeline",
        "title": "Talent Pipeline",
        "tagline": "Caldwell runs an INTERNAL talent-market pulse before a board review.",
        "query": "What are workforce analytics on AI talent attrition compensation and hiring pipeline metrics?",
        "sensitivity": SensitivityLevel.INTERNAL,
        "requesting_org": "org_5",
        "description": "Workforce domain RAG; gentler threshold — contrast after Vault Seven.",
    },
]


def print_separator(char="─", width=70):
    print(char * width)


def print_header():
    print()
    print_separator("═")
    print("  IEOTBSM AGENTIC AI — LANGGRAPH EXTENSION")
    print("  Cross-Org RAG with Trust-Gated Agent Hierarchy")
    print_separator("─")
    print("  Based on: Hexmoor, Wilson & Bhattaram (2006)")
    print("  The Knowledge Engineering Review, 21(2), 127–161")
    print_separator("═")
    print()


def print_trust_matrix(network: IEOTBSMAgenticNetwork):
    tm = network.get_trust_matrix()
    labels = tm["labels"]
    matrix = tm["matrix"]

    print("  INITIAL INTER-ORGANIZATIONAL TRUST MATRIX (τ_0 — Equation 5)")
    print_separator()
    header = "             " + "  ".join(f"{l[:8]:>9}" for l in labels)
    print(header)
    for i, row in enumerate(matrix):
        label = f"  {labels[i][:12]:14}"
        vals = "  ".join(
            "  [self]" if i == j else f"  {v:.3f} " + ("🟩" if v >= 0.5 else "🟨" if v >= 0.3 else "🟥")
            for j, v in enumerate(row)
        )
        print(f"{label}{vals}")
    print()


def print_query_result(result: dict, idx: int, desc: str):
    print_separator("─")
    print(f"  QUERY {idx+1}: {desc}")
    print_separator("─")
    print(f"  From  : {result['requesting_org']}")
    sens = result['sensitivity']
    sens_str = sens if isinstance(sens, str) else SensitivityLevel(sens).name
    print(f"  Sensitivity : {sens_str}")
    print(f"  Query : {result['query_text'][:80]}...")
    print()

    print("  TRUST GATE RESULTS (ISP3/ISP4 — Definition 14):")
    for check in result["trust_checks"]:
        icon = "✅" if check["passed"] else "🚫"
        print(f"    {icon} {check['target_org']:20} "
              f"trust={check['trust']:.3f}  "
              f"threshold={check['threshold']:.2f}  "
              f"{'PASS' if check['passed'] else 'FAIL'}")

    if result["human_reviews"]:
        print()
        print("  HUMAN REVIEW QUEUE (TPM4 — Agentic Extension):")
        for hr in result["human_reviews"]:
            icon = "✔" if hr["decision"] == "approved" else "✘"
            print(f"    {icon} Violation {hr['violation_id']} → "
                  f"{hr['target_org']}: {hr['decision'].upper()}")
            print(f"      Notes: {hr['notes'][:80]}")

    print()
    print("  ORG RETRIEVAL RESULTS:")
    for org_res in result["org_results"]:
        icon = "📄" if org_res["status"] == "retrieved" else "—"
        print(f"    {icon} {org_res['org']:20} "
              f"docs={org_res['doc_count']}  "
              f"{org_res['preview'][:60]}{'...' if len(org_res['preview']) > 60 else ''}")

    print()
    print("  FACT PEDIGREE (Definition 19 — Agent Chain):")
    for i, entry in enumerate(result["pedigree"]):
        connector = "└─" if i == len(result["pedigree"]) - 1 else "├─"
        print(f"    {connector} [{entry['role']:18}] {entry['agent_id']:25} "
              f"→ {entry['action']}")

    print()
    print("  METRICS:")
    print(f"    IA%: {result['ia_pct']:.1f}%  |  "
          f"SM%: {result['sm_pct']:.1f}%  |  "
          f"Human Reviews: {result['human_review_count']}")
    print()
    print("  SYNTHESIZED ANSWER (truncated):")
    answer_lines = result["final_answer"][:500].split("\n")
    for line in answer_lines[:8]:
        print(f"    {line}")
    if len(result["final_answer"]) > 500:
        print("    [... truncated ...]")
    print()


def run_simulation_mode(args):
    """Run full PoC in simulation mode (no LLM, no LangGraph required)."""
    print_header()
    print("  Mode: SIMULATION (no API key required)")
    print(f"  TPM Mode: TPM{args.tpm}  |  Alpha: {args.alpha}  |  "
          f"Decrement: {args.decrement}")
    print()

    # Initialize network
    print("  Initializing IEOTBSM Agentic Network...")
    network = IEOTBSMAgenticNetwork(
        alpha=args.alpha,
        tpm_mode=args.tpm,
        decrement=args.decrement,
    )
    print(f"  ✅ {len(network.orgs)} organizations | "
          f"{sum(len(v) for v in network.internal_agents.values())} internal agents | "
          f"{sum(len(v) for v in network.boundary_spanners.values())} boundary spanners")
    print()

    print_trust_matrix(network)

    # Run demo queries
    all_results = []
    for i, demo in enumerate(DEMO_QUERIES):
        result = network.execute_query_simulation(
            query_text=demo["query"],
            requesting_org_id=demo["requesting_org"],
            sensitivity=demo["sensitivity"],
        )
        all_results.append(result)
        print_query_result(result, i, demo["description"])

    # Final trust matrix (after interactions)
    print_separator("═")
    print("  FINAL INTER-ORG TRUST MATRIX (after interactions — Equation 5 logistic growth)")
    print_separator("═")
    print_trust_matrix(network)

    # Human review summary
    if network.human_review_queue:
        print_separator()
        print(f"  HUMAN REVIEW QUEUE SUMMARY: {len(network.human_review_queue)} violations")
        print_separator()
        for v in network.human_review_queue:
            org_name = network.org_names.get(v.requesting_org, v.requesting_org)
            tgt_name = network.org_names.get(v.target_org, v.target_org)
            print(f"    [{v.status.upper():8}] {v.violation_id}  "
                  f"{org_name:15} → {tgt_name:15}  "
                  f"trust={v.trust_value:.3f}  "
                  f"required={v.required_threshold:.2f}  "
                  f"sensitivity={v.sensitivity.value}")
        print()

    # Cumulative metrics
    print_separator("═")
    print("  CUMULATIVE METRICS ACROSS ALL QUERIES")
    print_separator("═")
    total_ia = sum(r["ia_pct"] for r in all_results) / len(all_results)
    total_sm = sum(r["sm_pct"] for r in all_results) / len(all_results)
    total_hr = sum(r["human_review_count"] for r in all_results)
    total_pedigree = sum(len(r["pedigree"]) for r in all_results)
    print(f"  Avg IA%            : {total_ia:.1f}%  (target: 100%)")
    print(f"  Avg SM%            : {total_sm:.1f}%  (target: 0%)")
    print(f"  Total Human Reviews: {total_hr}")
    print(f"  Total Pedigree Hops: {total_pedigree}")
    print_separator("═")
    print()

    return network, all_results


def _print_langgraph_stream_step(step: int, snap: dict) -> None:
    """One-line summary for ``stream_mode=\"values\"`` snapshots."""
    targets = snap.get("target_org_ids") or []
    cur = snap.get("current_target_org") or "—"
    idx = snap.get("fanout_org_idx", 0)
    oa = snap.get("org_answers") or {}
    od = snap.get("org_denials") or {}
    fa = (snap.get("final_answer") or "").strip()
    preview = (fa[:100] + "…") if len(fa) > 100 else (fa or "—")
    print(
        f"  [stream {step}] partners={len(targets)} fanout_idx={idx} "
        f"current={cur} answers={list(oa.keys())} denials={list(od.keys())}"
    )
    if fa:
        print(f"            └─ {preview}")


def resolve_langgraph_demo(args) -> dict:
    """Resolve ``DEMO_QUERIES`` entry from ``--demo-id`` or ``--demo-index``."""
    if getattr(args, "demo_id", None) is not None:
        for d in DEMO_QUERIES:
            if d["id"] == args.demo_id:
                return d
        print("❌ Unknown --demo-id. Valid ids:")
        for d in DEMO_QUERIES:
            print(f"     {d['id']}")
        sys.exit(1)
    idx = args.demo_index if args.demo_index is not None else 0
    if idx < 0 or idx >= len(DEMO_QUERIES):
        print(f"❌ --demo-index must be between 0 and {len(DEMO_QUERIES) - 1}.")
        sys.exit(1)
    return DEMO_QUERIES[idx]


def run_langgraph_mode(args):
    """Run PoC with actual LangGraph + LLM (Claude or local Ollama)."""
    try:
        from langgraph_impl import (
            IEOTBSMLangGraph,
            ANTHROPIC_AVAILABLE,
            OLLAMA_AVAILABLE,
        )
    except ImportError as e:
        print(f"❌ LangGraph import failed: {e}")
        print("   Install with: pip install -r requirements.txt")
        return

    if args.llm == "claude" and not ANTHROPIC_AVAILABLE:
        print("❌ langchain-anthropic not installed.")
        print("   pip install -r requirements.txt")
        return
    if args.llm == "ollama" and not OLLAMA_AVAILABLE:
        print("❌ langchain-ollama not installed.")
        print("   pip install -r requirements.txt")
        return

    if args.langsmith:
        if not os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
            print("❌ LangSmith: set LANGSMITH_API_KEY (or LANGCHAIN_API_KEY).")
            return
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        try:
            import langsmith  # noqa: F401
        except ImportError:
            print("❌ LangSmith: pip install -r requirements.txt")
            return

    print_header()
    backend_label = "CLAUDE API" if args.llm == "claude" else "OLLAMA (local)"
    print(f"  Mode: LANGGRAPH + {backend_label}")
    if getattr(args, "trust_backend", "local") == "http":
        print(
            "  Trust: HTTP service (IEOTBSM_TRUST_API_URL / X-API-Key dev-key default)"
        )
    if args.model:
        print(f"  Model: {args.model}")
    if args.stream:
        print("  Stream: on (full state after each superstep)")
    print()

    demo = resolve_langgraph_demo(args)
    from ieotbsm_core import QueryProvenance

    prov = QueryProvenance(
        query_text=demo["query"],
        sensitivity=demo["sensitivity"],
        originating_org=demo["requesting_org"],
        originating_agent=f"orchestrator_{demo['requesting_org']}",
    )

    trust_client = None
    if getattr(args, "trust_backend", "local") == "http":
        from adapters.langgraph_ieotbsm.http_trust import TrustApiClient

        trust_client = TrustApiClient(base_url=args.trust_api_url)

    network = IEOTBSMAgenticNetwork(
        alpha=args.alpha,
        tpm_mode=args.tpm,
        decrement=args.decrement,
    )

    if trust_client is not None:
        trust_client.put_snapshot(network.export_trust_snapshot())

    graph_engine = IEOTBSMLangGraph(
        network,
        llm_backend=args.llm,
        llm_model=args.model,
        ollama_base_url=args.ollama_base_url,
        trust_api_client=trust_client,
    )

    if args.print_graph_mermaid:
        print("  Graph structure (Mermaid — paste into LangSmith notes or a Mermaid viewer):")
        print_separator()
        print(graph_engine.graph_mermaid())
        print_separator()
        print()

    initial_state = {
        "query_id": prov.query_id,
        "query_text": demo["query"],
        "sensitivity": demo["sensitivity"],
        "requesting_org_id": demo["requesting_org"],
        "requesting_agent_id": f"orchestrator_{demo['requesting_org']}",
        "provenance": prov,
        "trust_passed": False,
        "trust_value": 0.0,
        "target_org_ids": [],
        "current_target_org": "",
        "org_answers": {},
        "org_denials": {},
        "fanout_org_idx": 0,
        "human_review_queue": [],
        "pending_violation": None,
        "final_answer": "",
        "metrics": {},
        "trust_run_id": "",
        "trust_remote_decision": None,
    }

    if args.langsmith:
        print("  LangSmith: tracing enabled — open https://smith.langchain.com and check")
        print(f"  project '{os.getenv('LANGSMITH_PROJECT', 'default')}' for this run.")
        print()

    print(f"  Demo: {demo.get('title', demo['id'])} ({demo['id']})")
    print(f"  Executing query via LangGraph: {demo['query'][:60]}...")
    if args.stream:
        print_separator("·")

    run_kwargs: dict = {}
    if args.langsmith:
        run_kwargs.update(
            run_name="IEOTBSM trust-gated RAG",
            run_tags=["ieotbsm", "langgraph", f"llm:{args.llm}"],
            run_metadata={
                "llm_backend": args.llm,
                "llm_model": graph_engine.llm_model,
                "demo_id": demo["id"],
            },
        )
    if args.stream:
        run_kwargs["stream"] = True
        run_kwargs["stream_step"] = _print_langgraph_stream_step

    result_state = graph_engine.run(initial_state, **run_kwargs)

    if args.stream:
        print_separator("·")
        print()

    print()
    print("  FINAL ANSWER:")
    print_separator()
    print(result_state.get("final_answer", "No answer generated."))
    print_separator()
    print()
    print(f"  Pedigree length: {len(result_state['provenance'].agent_chain)}")
    print(f"  Trust checks   : {len(result_state['provenance'].trust_checks)}")
    print(f"  Violations     : {len(result_state['provenance'].violations)}")

    if args.langsmith:
        try:
            from langsmith import Client
            Client().flush()
        except Exception:
            pass


def parse_args():
    p = argparse.ArgumentParser(description="IEOTBSM Agentic AI PoC")
    p.add_argument("--langgraph", action="store_true",
                   help="Use LangGraph + LLM (--llm claude needs ANTHROPIC_API_KEY; ollama is local)")
    p.add_argument(
        "--llm",
        choices=["claude", "ollama"],
        default="claude",
        help="LLM backend with --langgraph (default: claude)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Model name: Claude id or Ollama tag (defaults per backend)",
    )
    p.add_argument(
        "--ollama-base-url",
        default=None,
        help="Ollama base URL (default: http://127.0.0.1:11434 or OLLAMA_BASE_URL)",
    )
    p.add_argument(
        "--langsmith",
        action="store_true",
        help="Send traces to LangSmith (needs LANGSMITH_API_KEY + LANGSMITH_TRACING; use with --langgraph)",
    )
    p.add_argument(
        "--print-graph-mermaid",
        action="store_true",
        help="With --langgraph, print the graph as Mermaid text before running",
    )
    demo_grp = p.add_mutually_exclusive_group()
    demo_grp.add_argument(
        "--demo-id",
        metavar="ID",
        default=None,
        help="With --langgraph, demo preset id (e.g. silicon_ledger, vault_seven)",
    )
    demo_grp.add_argument(
        "--demo-index",
        type=int,
        default=None,
        metavar="N",
        help="With --langgraph, demo preset by index (0 .. n-1; default 0 if omitted)",
    )
    p.add_argument(
        "--stream",
        action="store_true",
        help="With --langgraph, print accumulated state after each graph superstep",
    )
    p.add_argument("--tpm", type=int, default=4, choices=[1, 2, 3, 4],
                   help="Trust policy model (4=human review, default)")
    p.add_argument("--alpha", type=float, default=0.65,
                   help="Inter-org trust weight α (default: 0.65)")
    p.add_argument("--decrement", type=float, default=0.06,
                   help="Trust decrement on violation (default: 0.06)")
    p.add_argument(
        "--trust-backend",
        choices=["local", "http"],
        default="local",
        help="With --langgraph: local gate (default) or remote Trust API (http)",
    )
    p.add_argument(
        "--trust-api-url",
        default=None,
        help="Trust API base URL for --trust-backend http (default IEOTBSM_TRUST_API_URL or http://127.0.0.1:8088)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.langsmith and not args.langgraph:
        print("❌ --langsmith requires --langgraph.")
        sys.exit(1)
    if args.print_graph_mermaid and not args.langgraph:
        print("❌ --print-graph-mermaid requires --langgraph.")
        sys.exit(1)
    if args.stream and not args.langgraph:
        print("❌ --stream requires --langgraph.")
        sys.exit(1)
    if args.langgraph:
        if args.llm == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
            print("❌ ANTHROPIC_API_KEY not set. Export it or use --llm ollama.")
            sys.exit(1)
        if args.trust_backend == "http":
            if not args.trust_api_url and not os.getenv("IEOTBSM_TRUST_API_URL"):
                print(
                    "❌ --trust-backend http requires a running Trust API "
                    "(set IEOTBSM_TRUST_API_URL or pass --trust-api-url)."
                )
                sys.exit(1)
        run_langgraph_mode(args)
    else:
        run_simulation_mode(args)
