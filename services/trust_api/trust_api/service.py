"""Tenant-scoped trust operations backed by SQLAlchemy + in-process network."""

from __future__ import annotations

import base64
import threading
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ieotbsm_core import AgentRole, SensitivityLevel
from ieotbsm_core.pedigree_chain import (
    link_digest,
    payload_digest,
    prev_root_from_row,
    sign_link_digest,
)
from ieotbsm_core.provenance_persist import provenance_from_dict, provenance_to_dict
from ieotbsm_core.schemas import (
    GateDecisionV1,
    GateEvaluateResponseV1,
    LedgerMatrixResponseV1,
    RunCreateResponseV1,
    StateResponseV1,
)
from trust_api.db import RunRow, TenantStateRow
from trust_api.repo_path import ensure_repo_root
from trust_api.config import Settings
from trust_api.signing import jwks_document, load_signing_private_key

ensure_repo_root()
from network import IEOTBSMAgenticNetwork  # noqa: E402


class TrustApiService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        api_settings: Settings | None = None,
    ):
        from trust_api.config import settings as default_settings

        self._settings = api_settings or default_settings
        self._session_factory = session_factory
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._signing_key = load_signing_private_key(self._settings)

    def jwks_public(self) -> dict[str, Any]:
        return jwks_document(self._settings, self._signing_key)

    def _session(self) -> Session:
        return self._session_factory()

    def load_network(self, tenant_id: str) -> IEOTBSMAgenticNetwork:
        with self._session() as s:
            row = s.get(TenantStateRow, tenant_id)
            if row is None:
                net = IEOTBSMAgenticNetwork()
                self.save_network(tenant_id, net)
                return net
            net = IEOTBSMAgenticNetwork()
            net.import_trust_snapshot(row.payload)
            return net

    def save_network(self, tenant_id: str, net: IEOTBSMAgenticNetwork) -> None:
        payload = net.export_trust_snapshot()
        with self._session() as s:
            row = s.get(TenantStateRow, tenant_id)
            if row is None:
                s.add(TenantStateRow(tenant_id=tenant_id, payload=payload))
            else:
                row.payload = payload
            s.commit()

    def seed_tenant(self, tenant_id: str) -> None:
        with self._locks[tenant_id]:
            net = IEOTBSMAgenticNetwork()
            self.save_network(tenant_id, net)

    def get_state(self, tenant_id: str) -> StateResponseV1:
        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            tm = net.get_trust_matrix()
            return StateResponseV1(
                cycle=net.cycle,
                human_review_queue_size=len(net.human_review_queue),
                trust_matrix=tm,
                orgs=[{"id": oid, "name": net.org_names[oid]} for oid in tm["org_ids"]],
            )

    def ledger_matrix(self, tenant_id: str) -> LedgerMatrixResponseV1:
        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            tm = net.get_trust_matrix()
            return LedgerMatrixResponseV1(
                org_ids=tm["org_ids"],
                labels=tm["labels"],
                matrix=tm["matrix"],
            )

    def export_tenant_snapshot(self, tenant_id: str) -> dict:
        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            return net.export_trust_snapshot()

    def run_simulation_events(
        self,
        tenant_id: str,
        query_text: str,
        requesting_org_id: str,
        sensitivity: int,
        *,
        description: str | None = None,
    ) -> list[dict]:
        """Run the reference simulation; returns all events (for dashboard / clients)."""
        from ieotbsm_core import SensitivityLevel

        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            events = list(
                net.iter_query_simulation_events(
                    query_text,
                    requesting_org_id,
                    SensitivityLevel(sensitivity),
                    throttle_ms=0,
                    description=description,
                )
            )
            self.save_network(tenant_id, net)
            return events

    def replace_tenant_snapshot(self, tenant_id: str, snap: dict) -> None:
        """Overwrite tenant trust state from a local ``export_trust_snapshot`` payload."""
        with self._locks[tenant_id]:
            net = IEOTBSMAgenticNetwork()
            net.import_trust_snapshot(snap)
            self.save_network(tenant_id, net)

    def create_run(
        self,
        tenant_id: str,
        query_text: str,
        requesting_org_id: str,
        requesting_agent_id: str,
        sensitivity: int,
    ) -> RunCreateResponseV1:
        from ieotbsm_core.models import QueryProvenance

        with self._locks[tenant_id]:
            run_id = str(uuid.uuid4())
            prov = QueryProvenance(
                query_text=query_text,
                sensitivity=SensitivityLevel(sensitivity),
                originating_org=requesting_org_id,
                originating_agent=requesting_agent_id
                or f"orchestrator_{requesting_org_id}",
            )
            with self._session() as s:
                s.add(
                    RunRow(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        provenance=provenance_to_dict(prov),
                    )
                )
                s.commit()
            return RunCreateResponseV1(run_id=run_id, query_id=prov.query_id)

    def _get_run(self, tenant_id: str, run_id: str) -> dict:
        with self._session() as s:
            row = s.get(RunRow, run_id)
            if row is None or row.tenant_id != tenant_id:
                raise KeyError("run not found")
            return dict(row.provenance)

    def _save_run_prov(self, tenant_id: str, run_id: str, prov_dict: dict) -> None:
        with self._session() as s:
            row = s.get(RunRow, run_id)
            if row is None or row.tenant_id != tenant_id:
                raise KeyError("run not found")
            row.provenance = prov_dict
            s.commit()

    def evaluate_gate(
        self,
        tenant_id: str,
        run_id: str,
        trustor_org_id: str,
        trustee_org_id: str,
        trustor_agent_id: str | None,
        trustee_agent_id: str | None,
        sensitivity: int,
        commit: bool,
    ) -> GateEvaluateResponseV1:
        from ieotbsm_core.models import TrustViolation

        sens = SensitivityLevel(sensitivity)
        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            prov = provenance_from_dict(self._get_run(tenant_id, run_id))
            req_bs = net.get_boundary_spanner(trustor_org_id)
            tgt_bs = net.get_boundary_spanner(trustee_org_id)
            ta = trustor_agent_id or (req_bs.agent_id if req_bs else "")
            tb = trustee_agent_id or (tgt_bs.agent_id if tgt_bs else "")

            if req_bs and tgt_bs and ta and tb:
                passed, eff = net.gate.check_inter_org(
                    ta,
                    tb,
                    trustor_org_id,
                    trustee_org_id,
                    sens,
                    prov,
                )
                kind = "inter_org_blend"
            else:
                passed, eff, _ = net.ledger.check(
                    trustor_org_id, trustee_org_id, sens
                )
                kind = "ledger_only"

            threshold = net.ledger.threshold_for(sens)
            human_required = False
            violation_id_out: str | None = None
            if not passed:
                v = TrustViolation(
                    query_id=prov.query_id,
                    requesting_org=trustor_org_id,
                    target_org=trustee_org_id,
                    requesting_agent=ta,
                    trust_value=eff,
                    required_threshold=threshold,
                    sensitivity=sens,
                    query_text=prov.query_text,
                    agent_chain_at_violation=list(prov.agent_chain),
                )
                violation_id_out = v.violation_id
                action = net.tpm.apply(
                    prov,
                    net.agent_trust,
                    net.ledger,
                    v,
                    net.human_review_queue,
                )
                human_required = action.startswith("TPM4")

            decision_str = (
                "allow"
                if passed
                else ("human_required" if human_required else "deny")
            )

            if commit and passed and req_bs and tgt_bs:
                net.ledger.update(
                    trustor_org_id,
                    trustee_org_id,
                    [eff],
                    len(net.boundary_spanners[trustor_org_id]),
                )
                net.gate.record_outcome(ta, tb, True)

            if commit:
                self.save_network(tenant_id, net)

            self._save_run_prov(tenant_id, run_id, provenance_to_dict(prov))

            return GateEvaluateResponseV1(
                decision=GateDecisionV1(
                    decision=decision_str,  # type: ignore[arg-type]
                    trust_value=eff,
                    threshold=threshold,
                    effective_kind=kind,  # type: ignore[arg-type]
                ),
                violation_id=violation_id_out,
            )

    def append_run_event(
        self, tenant_id: str, run_id: str, event_type: str, payload: dict
    ) -> dict[str, object]:
        with self._locks[tenant_id]:
            with self._session() as s:
                row = s.get(RunRow, run_id)
                if row is None or row.tenant_id != tenant_id:
                    raise KeyError("run not found")
                prov = provenance_from_dict(dict(row.provenance))
                if event_type == "pedigree_sign":
                    prov.sign(
                        payload["agent_id"],
                        payload["org_id"],
                        AgentRole(payload["role"]),
                        payload["action"],
                    )
                elif event_type == "context":
                    prov.add_context(
                        payload["org_id"],
                        payload["agent_id"],
                        payload["content"],
                        SensitivityLevel(int(payload["sensitivity"])),
                    )
                prov_dict = provenance_to_dict(prov)
                ph = payload_digest(dict(payload))
                prev = prev_root_from_row(row.chain_seq, row.chain_root_b64)
                next_seq = row.chain_seq + 1
                ld = link_digest(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    seq=next_seq,
                    event_type=event_type,
                    payload_hash=ph,
                    prev_root=prev,
                )
                sig = sign_link_digest(self._signing_key, ld)
                row.provenance = prov_dict
                row.chain_seq = next_seq
                row.chain_root_b64 = base64.standard_b64encode(ld).decode(
                    "ascii"
                )
                row.chain_sig_b64 = base64.standard_b64encode(sig).decode("ascii")
                row.chain_key_id = self._settings.signing_key_id
                s.commit()
                qid = prov.query_id
                out_chain_root = row.chain_root_b64
                out_chain_sig = row.chain_sig_b64
                out_chain_key_id = row.chain_key_id
        return {
            "ok": True,
            "query_id": qid,
            "chain_seq": next_seq,
            "chain_root_b64": out_chain_root,
            "chain_signature_b64": out_chain_sig,
            "chain_key_id": out_chain_key_id,
        }

    def get_pedigree_chain_head(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        with self._locks[tenant_id]:
            with self._session() as s:
                row = s.get(RunRow, run_id)
                if row is None or row.tenant_id != tenant_id:
                    raise KeyError("run not found")
                return {
                    "schema_version": 1,
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "seq": row.chain_seq,
                    "root_b64": row.chain_root_b64 or "",
                    "signature_b64": row.chain_sig_b64 or "",
                    "key_id": row.chain_key_id or "",
                }

    def get_run_snapshot(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        """Provenance JSON + chain head for A2A/introspection."""
        with self._locks[tenant_id]:
            with self._session() as s:
                row = s.get(RunRow, run_id)
                if row is None or row.tenant_id != tenant_id:
                    raise KeyError("run not found")
                prov = dict(row.provenance)
                chain = {
                    "schema_version": 1,
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "seq": row.chain_seq,
                    "root_b64": row.chain_root_b64 or "",
                    "signature_b64": row.chain_sig_b64 or "",
                    "key_id": row.chain_key_id or "",
                }
        return {"provenance": prov, "pedigree_chain": chain}

    def patch_violation(
        self,
        tenant_id: str,
        violation_id: str,
        status: str,
        reviewer_notes: str,
    ) -> dict[str, Any]:
        with self._locks[tenant_id]:
            net = self.load_network(tenant_id)
            found = False
            for v in net.human_review_queue:
                if v.violation_id == violation_id:
                    v.status = status
                    v.reviewer_notes = reviewer_notes
                    found = True
                    break
            if not found:
                raise KeyError("violation not found")
            self.save_network(tenant_id, net)
        return {"ok": True, "violation_id": violation_id, "status": status}
