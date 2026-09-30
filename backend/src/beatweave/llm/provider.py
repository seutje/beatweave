import json
import logging
from abc import ABC, abstractmethod
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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
        self,
        request: StructuredGenerationRequest,
        output_type: type[OutputModel],
        *,
        release_after: bool = False,
    ) -> StructuredGenerationResponse[OutputModel]:
        """Generate and validate one structured response."""

    @abstractmethod
    def release(self) -> None:
        """Release provider resources after a related request sequence."""


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

    def release(self) -> None:
        self._release_ollama_model()

    def generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_type: type[OutputModel],
        *,
        release_after: bool = False,
    ) -> StructuredGenerationResponse[OutputModel]:
        try:
            return self._generate_structured(request, output_type)
        finally:
            if release_after:
                self._release_ollama_model()

    def _generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_type: type[OutputModel],
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
                content = self._completion(attempt_messages, request, output_type)
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
        self,
        messages: list[dict[str, str]],
        generation: StructuredGenerationRequest,
        output_type: type[OutputModel],
    ) -> str:
        if self._is_ollama():
            body: dict[str, object] = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
                # Structured planning benefits from deterministic JSON, not a hidden
                # reasoning trace that consumes Ollama's output-token allowance.
                "think": False,
                "format": self._ollama_schema(output_type),
                "options": {
                    "temperature": generation.temperature,
                    "num_predict": generation.max_tokens,
                },
            }
            request_url = self._ollama_url("chat")
        else:
            body = {
                "model": self.config.model,
                "messages": messages,
                "temperature": generation.temperature,
                "max_tokens": generation.max_tokens,
                "response_format": self._response_format(output_type),
            }
            request_url = self._url("chat/completions")
        payload = json.dumps(body).encode()
        logger.info(
            "Requesting structured completion from %s with model %s",
            self.config.base_url,
            self.config.model,
        )
        request = Request(
            request_url,
            data=payload,
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                body = json.loads(response.read())
        except HTTPError as exc:
            provider_error = self._http_error_detail(exc)
            raise BeatweaveError(
                "llm_provider_rejected_request",
                f"Provider returned HTTP {exc.code}: {provider_error}",
                status_code=502,
                details={"provider_error": provider_error},
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
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
        if self._is_ollama() and body.get("done_reason") == "length":
            raise BeatweaveError(
                "llm_output_truncated",
                "Ollama reached its output limit before completing the structured response.",
                status_code=422,
            )
        if not self._is_ollama():
            choices = body.get("choices", [])
            if choices and choices[0].get("finish_reason") == "length":
                raise BeatweaveError(
                    "llm_output_truncated",
                    "The provider reached its output limit before completing the response.",
                    status_code=422,
                )
        try:
            content = (
                body["message"]["content"]
                if self._is_ollama()
                else body["choices"][0]["message"]["content"]
            )
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

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str:
        try:
            body = error.read().decode("utf-8", errors="replace")
            decoded = json.loads(body)
            detail = decoded.get("error", body) if isinstance(decoded, dict) else body
        except (OSError, UnicodeError, json.JSONDecodeError):
            detail = "Request rejected."
        return str(detail).strip()[:1000] or "Request rejected."

    def _release_ollama_model(self) -> None:
        if not self._is_ollama():
            return
        unload_url = self._ollama_url("generate")
        request = Request(
            unload_url,
            data=json.dumps({"model": self.config.model, "keep_alive": 0}).encode(),
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds):  # noqa: S310
                logger.info("Released Ollama model %s", self.config.model)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise BeatweaveError(
                "llm_release_failed",
                "The plan was generated, but Ollama could not release the model.",
                status_code=503,
            ) from exc

    def _response_format(self, output_type: type[OutputModel]) -> dict[str, object]:
        schema = output_type.model_json_schema()
        if self._is_ollama():
            return schema
        return {
            "type": "json_schema",
            "json_schema": {
                "name": output_type.__name__,
                "strict": True,
                "schema": schema,
            },
        }

    @staticmethod
    def _ollama_schema(output_type: type[OutputModel]) -> dict[str, object]:
        schema = output_type.model_json_schema()
        definitions = schema.get("$defs", {})
        unsupported = {
            "default",
            "description",
            "examples",
            "maximum",
            "maxItems",
            "maxLength",
            "minimum",
            "minItems",
            "minLength",
            "title",
        }

        def simplify(value: object, *, property_names: bool = False) -> object:
            if isinstance(value, dict):
                reference = value.get("$ref")
                if isinstance(reference, str) and reference.startswith("#/$defs/"):
                    name = reference.removeprefix("#/$defs/")
                    resolved = definitions.get(name)
                    if isinstance(resolved, dict):
                        additions = {key: item for key, item in value.items() if key != "$ref"}
                        return simplify({**resolved, **additions})
                return {
                    key: simplify(item, property_names=key == "properties")
                    for key, item in value.items()
                    if (property_names or key not in unsupported) and key != "$defs"
                }
            if isinstance(value, list):
                return [simplify(item) for item in value]
            return value

        return simplify(schema)

    def _is_ollama(self) -> bool:
        parsed = urlparse(self.config.base_url)
        return parsed.port == 11434 and parsed.path.rstrip("/").endswith("/v1")

    def _ollama_url(self, path: str) -> str:
        parsed = urlparse(self.config.base_url)
        return f"{parsed.scheme}://{parsed.netloc}/api/{path}"

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
