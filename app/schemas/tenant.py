from pydantic import BaseModel

class TenantResponse(BaseModel):
    tenants: list[str]
