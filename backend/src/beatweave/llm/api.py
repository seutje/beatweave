from typing import Annotated

from fastapi import APIRouter, Depends, Request

from beatweave.database import Database
from beatweave.llm.schemas import (
    LLMProviderConfigUpdate,
    LLMProviderConfigView,
    ProviderAvailability,
)
from beatweave.llm.service import LLMService

router = APIRouter(prefix="/llm", tags=["llm"])


def service(request: Request) -> LLMService:
    database: Database = request.app.state.database
    return LLMService(database)


LLMServiceDep = Annotated[LLMService, Depends(service)]


@router.get("/config", response_model=LLMProviderConfigView)
def get_config(llm_service: LLMServiceDep) -> LLMProviderConfigView:
    return llm_service.config_view()


@router.put("/config", response_model=LLMProviderConfigView)
def update_config(
    body: LLMProviderConfigUpdate, llm_service: LLMServiceDep
) -> LLMProviderConfigView:
    return llm_service.update_config(body)


@router.post("/test", response_model=ProviderAvailability)
def test_connection(llm_service: LLMServiceDep) -> ProviderAvailability:
    return llm_service.provider().availability()
