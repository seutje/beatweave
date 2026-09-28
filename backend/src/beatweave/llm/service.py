import json

from beatweave.database import Database
from beatweave.llm.provider import LLMProvider, OpenAICompatibleProvider
from beatweave.llm.schemas import (
    LLMProviderConfig,
    LLMProviderConfigUpdate,
    LLMProviderConfigView,
)
from beatweave.models import ApplicationSettingRecord

LLM_CONFIG_KEY = "llm_provider_config"


class LLMService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def config(self) -> LLMProviderConfig:
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, LLM_CONFIG_KEY)
        if setting is None:
            return LLMProviderConfig()
        return LLMProviderConfig.model_validate_json(setting.value)

    def config_view(self) -> LLMProviderConfigView:
        config = self.config()
        return LLMProviderConfigView(**config.model_dump(), api_key_configured=bool(config.api_key))

    def update_config(self, update: LLMProviderConfigUpdate) -> LLMProviderConfigView:
        current = self.config()
        values = update.model_dump()
        if update.api_key is None:
            values["api_key"] = current.api_key
        elif not update.api_key.strip():
            values["api_key"] = None
        config = LLMProviderConfig.model_validate(values)
        encoded = json.dumps(
            {
                "provider": config.provider,
                "base_url": config.base_url,
                "model": config.model,
                "timeout_seconds": config.timeout_seconds,
                "api_key": config.api_key,
            }
        )
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, LLM_CONFIG_KEY)
            if setting is None:
                session.add(ApplicationSettingRecord(key=LLM_CONFIG_KEY, value=encoded))
            else:
                setting.value = encoded
        return self.config_view()

    def provider(self) -> LLMProvider:
        return OpenAICompatibleProvider(self.config())
