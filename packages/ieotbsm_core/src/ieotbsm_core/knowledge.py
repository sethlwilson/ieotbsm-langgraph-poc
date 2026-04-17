"""Demo org knowledge bases (simulated RAG), shared by simulation and LangGraph."""

from ieotbsm_core.enums import SensitivityLevel

ORG_KNOWLEDGE_BASE: dict[str, list[dict]] = {
    "org_0": [
        {
            "topic": "market",
            "content": "Q3 semiconductor demand up 18% YoY. DRAM spot prices stabilizing at $3.20/GB. Key driver: AI accelerator procurement by hyperscalers.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
        {
            "topic": "competitor",
            "content": "Competitor X launching new edge AI chip Q1 next year. Performance claims: 45 TOPS at 8W. Supply chain: TSMC 3nm.",
            "sensitivity": SensitivityLevel.CONFIDENTIAL,
        },
    ],
    "org_1": [
        {
            "topic": "threat",
            "content": "APT-41 campaign targeting supply chain APIs. IOCs: 203.0.113.42, malware hash a3f2c1d9. Affected sectors: semiconductor, defense.",
            "sensitivity": SensitivityLevel.RESTRICTED,
        },
        {
            "topic": "vulnerability",
            "content": "CVE-2024-38112 actively exploited in enterprise VPN appliances. Patch available. CVSS 9.8. Recommend immediate patching.",
            "sensitivity": SensitivityLevel.CONFIDENTIAL,
        },
    ],
    "org_2": [
        {
            "topic": "regulatory",
            "content": "EU AI Act enforcement begins August 2026. High-risk AI systems require conformity assessment. Fines up to 3% global revenue.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
        {
            "topic": "compliance",
            "content": "SOC 2 Type II audit findings: 2 minor exceptions in access control logging. Remediation deadline: 30 days.",
            "sensitivity": SensitivityLevel.CONFIDENTIAL,
        },
    ],
    "org_3": [
        {
            "topic": "supply_chain",
            "content": "TSMC CoWoS packaging capacity constrained through Q2 2026. Lead times extending to 52 weeks for advanced packaging.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
        {
            "topic": "vendor",
            "content": "Tier-2 supplier risk: 3 vendors flagged for single-source dependency. Recommended: dual-source qualification for capacitors.",
            "sensitivity": SensitivityLevel.CONFIDENTIAL,
        },
    ],
    "org_4": [
        {
            "topic": "pricing",
            "content": "Cloud GPU pricing: H100 $2.80/hr spot, $3.40/hr on-demand. Utilization rates: 94% across top-3 hyperscalers.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
        {
            "topic": "benchmark",
            "content": "Internal LLM benchmark: Model A scores 87.3 on MMLU, 72.1 on HumanEval. Inference latency: 43ms p50, 210ms p99.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
    ],
    "org_5": [
        {
            "topic": "workforce",
            "content": "AI talent attrition rate: 23% annually at director level. Compensation benchmarks: ML Engineer median $195k TC in SF.",
            "sensitivity": SensitivityLevel.CONFIDENTIAL,
        },
        {
            "topic": "hiring",
            "content": "Pipeline analysis: 340 active ML roles across portfolio. Time-to-fill averaging 94 days. Top source: university partnerships.",
            "sensitivity": SensitivityLevel.INTERNAL,
        },
    ],
}


def retrieve_from_org(
    org_id: str, query: str, max_sensitivity: SensitivityLevel
) -> list[dict]:
    kb = ORG_KNOWLEDGE_BASE.get(org_id, [])
    results = []
    for doc in kb:
        if doc["sensitivity"].value <= max_sensitivity.value:
            query_lower = query.lower()
            if any(
                word in doc["content"].lower()
                for word in query_lower.split()
                if len(word) > 3
            ):
                results.append(doc)
    return results
