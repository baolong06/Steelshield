"""Minimal OpenAI Responses-wire client for the server-configured LLM gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.settings import Settings, get_settings


class LlmGatewayError(RuntimeError):
    """A declared model gateway failure. Campaigns record it as unsafe/not-run."""


@dataclass(frozen=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LlmResponse:
    text: str
    function_calls: tuple[FunctionCall, ...]
    response_id: str | None
    request_bytes: int
    response_bytes: int


class ResponsesClient:
    """Calls the configured {base_url}/responses endpoint."""

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.assert_allowed_gateway()
        self._client = client or httpx.Client(
            timeout=self.settings.timeout_s, follow_redirects=False
        )

    @property
    def endpoint(self) -> str:
        return f"{self.settings.base_url}/responses"

    def health(self) -> dict[str, Any]:
        if not self.settings.api_key:
            raise LlmGatewayError("STEELSHIELD_LLM_API_KEY is not configured")
        response = self._post(
            {"model": self.settings.model, "input": "Reply with READY.", "max_output_tokens": 16}
        )
        return {
            "configured": True,
            "model": self.settings.model,
            "egress_host": self.settings.egress_host,
            "response_id": response.response_id,
        }

    def complete(
        self,
        *,
        instructions: str,
        input: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        max_output_tokens: int = 700,
    ) -> LlmResponse:
        """Run one Responses API turn with text or structured input items.

        Tool continuations should echo each ``function_call`` item together with a
        matching ``function_call_output``. ``previous_response_id`` is optional and
        is rejected by the declared gateway when ``store=false``.
        """
        if not self.settings.api_key:
            raise LlmGatewayError("STEELSHIELD_LLM_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": instructions,
            "input": input,
            "max_output_tokens": max_output_tokens,
            "store": self.settings.store,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        # Gateways may not implement reasoning yet; only transmit the approved effort when present.
        if self.settings.reasoning_effort:
            payload["reasoning"] = {"effort": self.settings.reasoning_effort}
        if tools:
            payload["tools"] = tools
        return self._post(payload)

    def _post(self, payload: dict[str, Any]) -> LlmResponse:
        if not self.settings.live_llm_enabled:
            raise LlmGatewayError(
                "Live LLM egress is disabled; set STEELSHIELD_LIVE_LLM=1 explicitly"
            )
        try:
            response = self._client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LlmGatewayError(_gateway_http_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise LlmGatewayError(f"Declared LLM gateway request failed: {exc}") from exc
        raw_bytes = response.content
        try:
            body = response.json()
        except ValueError as exc:
            raise LlmGatewayError("Declared LLM gateway returned non-JSON response") from exc
        if body.get("error"):
            raise LlmGatewayError(f"Declared LLM gateway error: {body['error']}")
        return LlmResponse(
            text=_output_text(body),
            function_calls=tuple(_function_calls(body)),
            response_id=body.get("id"),
            request_bytes=len(response.request.content or b""),
            response_bytes=len(raw_bytes),
        )


def _gateway_http_error(exc: httpx.HTTPStatusError) -> str:
    detail = ""
    try:
        body = exc.response.json()
        error = body.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or error)
        elif error:
            detail = str(error)
    except ValueError:
        detail = (exc.response.text or "")[:400]
    message = f"Declared LLM gateway request failed: {exc}"
    return f"{message} ({detail})" if detail else message


def _output_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    texts: list[str] = []
    for item in body.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(
                content.get("text"), str
            ):
                texts.append(content["text"])
    return "\n".join(texts)


def _function_calls(body: dict[str, Any]) -> list[FunctionCall]:
    calls: list[FunctionCall] = []
    for item in body.get("output", []) or []:
        if item.get("type") != "function_call":
            continue
        name, call_id = item.get("name"), item.get("call_id")
        if isinstance(name, str) and isinstance(call_id, str):
            calls.append(FunctionCall(call_id, name, str(item.get("arguments", "{}"))))
    return calls
