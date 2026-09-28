import json
import logging
from abc import ABC, abstractmethod
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from beatweave.errors import BeatweaveError
from beatweave.llm.schemas import (
    LLMProviderConfig,
    ProviderAvailability,
    StructuredGenerationRequest,
    StructuredGenerationResponse,
)

logger = logging.getLogger(__name__)
OutputModel = TypeVar("OutputModel", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    def availability(self) -> ProviderAvailability:
        """Return provider reachability without raising for an offline provider."""

    @abstractmethod
    def generate_structured(
        self, request: StructuredGenerationRequest, output_type: type[OutputModel]
    ) -> StructuredGenerationResponse[OutputModel]:
        """Generate and validate one structured response."""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    def availability(self) -> ProviderAvailability:
        request = Request(self._url("models"), headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                if 200 <= response.status < 300:
                    return ProviderAvailability(available=True, message="Provider is available.")
                return ProviderAvailability(
                    available=False, message=f"Provider returned HTTP {response.status}."
                )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return ProviderAvailability(available=False, message=self._safe_error(exc))

    def generate_structured(
        self, request: StructuredGenerationRequest, output_type: type[OutputModel]
    ) -> StructuredGenerationResponse[OutputModel]:
        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]
        validation_error = ""
        for attempt in range(2):
            attempt_messages = [*messages]
            if attempt:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Return only corrected JSON matching the requested schema. "
                            f"The previous response failed validation: {validation_error}"
                        ),
                    }
                )
            try:
                content = self._completion(attempt_messages, request)
                output = output_type.model_validate_json(content)
                return StructuredGenerationResponse(
                    output=output, model=self.config.model, repaired=bool(attempt)
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                validation_error = str(exc)[:1000]
                logger.warning(
                    "Rejected invalid structured output from model %s (attempt %d)",
                    self.config.model,
                    attempt + 1,
                )
        raise BeatweaveError(
            "invalid_llm_output",
            "The provider did not return valid structured output.",
            status_code=422,
            details={"validation_error": validation_error},
        )

    def _completion(
        self, messages: list[dict[str, str]], generation: StructuredGenerationRequest
    ) -> str:
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "temperature": generation.temperature,
                "max_tokens": generation.max_tokens,
                "response_format": {"type": "json_object"},
            }
        ).encode()
        logger.info(
            "Requesting structured completion from %s with model %s",
            self.config.base_url,
            self.config.model,
        )
        request = Request(
            self._url("chat/completions"),
            data=payload,
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise BeatweaveError(
                "llm_provider_unavailable",
                self._safe_error(exc),
                status_code=503,
            ) from exc
        except json.JSONDecodeError as exc:
            raise BeatweaveError(
                "invalid_provider_response",
                "The provider returned an invalid response envelope.",
                status_code=502,
            ) from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BeatweaveError(
                "invalid_provider_response",
                "The provider response did not contain a completion.",
                status_code=502,
            ) from exc
        if not isinstance(content, str):
            raise BeatweaveError(
                "invalid_provider_response",
                "The provider completion was not text.",
                status_code=502,
            )
        return content

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}/{path}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, HTTPError):
            return f"Provider returned HTTP {error.code}."
        if isinstance(error, TimeoutError):
            return "Provider connection timed out."
        return "Provider is offline or unreachable."
