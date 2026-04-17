from __future__ import annotations

from sqlalchemy import JSON, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class TenantStateRow(Base):
    __tablename__ = "tenant_trust_state"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    provenance: Mapped[dict] = mapped_column(JSON)
    chain_seq: Mapped[int] = mapped_column(Integer, default=0)
    chain_root_b64: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chain_sig_b64: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chain_key_id: Mapped[str] = mapped_column(String(64), default="")


def _ensure_sqlite_run_chain_columns(engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(runs)")).fetchall()
        names = {r[1] for r in rows}
        stmts: list[str] = []
        if "chain_seq" not in names:
            stmts.append(
                "ALTER TABLE runs ADD COLUMN chain_seq INTEGER NOT NULL DEFAULT 0"
            )
        if "chain_root_b64" not in names:
            stmts.append("ALTER TABLE runs ADD COLUMN chain_root_b64 VARCHAR(128)")
        if "chain_sig_b64" not in names:
            stmts.append("ALTER TABLE runs ADD COLUMN chain_sig_b64 VARCHAR(128)")
        if "chain_key_id" not in names:
            stmts.append(
                "ALTER TABLE runs ADD COLUMN chain_key_id VARCHAR(64) NOT NULL DEFAULT ''"
            )
        for sql in stmts:
            conn.execute(text(sql))


def _ensure_run_chain_columns(engine) -> None:
    insp = inspect(engine)
    if not insp.has_table("runs"):
        return
    if str(engine.url).startswith("sqlite"):
        _ensure_sqlite_run_chain_columns(engine)
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    alters: list[str] = []
    if "chain_seq" not in cols:
        alters.append("ALTER TABLE runs ADD COLUMN chain_seq INTEGER DEFAULT 0")
    if "chain_root_b64" not in cols:
        alters.append("ALTER TABLE runs ADD COLUMN chain_root_b64 VARCHAR(128)")
    if "chain_sig_b64" not in cols:
        alters.append("ALTER TABLE runs ADD COLUMN chain_sig_b64 VARCHAR(128)")
    if "chain_key_id" not in cols:
        alters.append("ALTER TABLE runs ADD COLUMN chain_key_id VARCHAR(64) DEFAULT ''")
    if alters:
        with engine.begin() as conn:
            for sql in alters:
                conn.execute(text(sql))


def make_session_factory(database_url: str):
    connect_args: dict = {}
    engine_kw: dict = {"future": True}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in database_url:
            engine_kw["poolclass"] = StaticPool
    engine = create_engine(
        database_url, connect_args=connect_args, **engine_kw
    )
    Base.metadata.create_all(engine)
    _ensure_run_chain_columns(engine)
    return sessionmaker(engine, expire_on_commit=False, future=True)
