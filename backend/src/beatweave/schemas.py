from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "beatweave-backend"
    version: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class EventMessage(BaseModel):
    type: str = Field(examples=["connected"])
    payload: dict[str, Any] = Field(default_factory=dict)
