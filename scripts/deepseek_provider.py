"""DeepSeek Chat Completions transport used by the shared AI Provider layer."""
from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ai_provider import CompletionResult, Message, ModelConfig


class ProviderResponseError(ValueError):
    """Raised when the provider response cannot be normalized."""


class DeepSeekProvider:
    def __init__(
        self,
        config: ModelConfig,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._opener = opener

    def complete(
        self,
        messages: Sequence[Message],
        *,
        max_tokens: int,
        response_format: Mapping[str, Any] | None = None,
    ) -> CompletionResult:
        if not messages:
            raise ValueError("messages_required")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
            raise ValueError("max_tokens_invalid")

        normalized_messages = []
        for message in messages:
            if not isinstance(message, Mapping) or "role" not in message or "content" not in message:
                raise ValueError("message_shape_invalid")
            # Copy the outer mapping while preserving multimodal content blocks.
            normalized_messages.append(dict(message))

        payload: dict[str, Any] = {
            "model": self._config.model,
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": max_tokens,
            "response_format": dict(response_format or {"type": "json_object"}),
            "messages": normalized_messages,
        }
        request = urllib.request.Request(
            self._config.base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._config.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        opener = self._opener or urllib.request.urlopen
        with opener(request, timeout=self._config.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))

        try:
            choice = result["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError("model_response_shape_invalid") from exc
        if not isinstance(content, str):
            raise ProviderResponseError("model_response_content_invalid")

        usage = result.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ProviderResponseError("model_response_usage_invalid")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ProviderResponseError("model_response_finish_reason_invalid")

        return {
            "content": content,
            "usage": usage,
            "finish_reason": finish_reason,
        }
