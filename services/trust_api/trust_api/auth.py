from fastapi import Header, HTTPException

from trust_api.config import settings


def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def tenant_id(x_tenant_id: str | None = Header(None, alias="X-Tenant-ID")) -> str:
    return (x_tenant_id or settings.default_tenant).strip() or settings.default_tenant
