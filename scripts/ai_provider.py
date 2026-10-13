"""Shared provider interface and loader for the existing model configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, TypedDict


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "deployment" / "model" / ".env"


class CompletionResult(TypedDict):
    content: str
    usage: dict[str, Any] | None
    finish_reason: str | None


Message = Mapping[str, Any]


class AIProvider(Protocol):
    """Communication contract shared by model providers."""

    def complete(
        self,
        messages: Sequence[Message],
        *,
        max_tokens: int,
        response_format: Mapping[str, Any] | None = None,
    ) -> CompletionResult:
        """Send text or multimodal messages and return a normalized response."""


class ProviderConfigError(ValueError):
    """Raised when the existing model configuration is missing or unsupported."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: int = 90


def _read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries without modifying the source file."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ProviderConfigError("model_config_unavailable") from exc

    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_model_config(path: Path | None = None) -> ModelConfig:
    """Load the existing deployment/model/.env settings; no new config is created."""
    values = _read_env_file(path or DEFAULT_CONFIG_PATH)
    provider = values.get("MODEL_PROVIDER", "").lower()
    base_url = values.get("MODEL_BASE_URL", "").rstrip("/")
    model = values.get("MODEL_NAME", "")
    api_key = values.get("DEEPSEEK_API_KEY", "")

    if provider != "deepseek":
        raise ProviderConfigError("unsupported_model_provider")
    if base_url != "https://api.deepseek.com":
        raise ProviderConfigError("unverified_model_endpoint")
    if not model:
        raise ProviderConfigError("model_name_missing")
    if not api_key:
        raise ProviderConfigError("model_api_key_missing")
    try:
        timeout_seconds = int(values.get("MODEL_TIMEOUT_SECONDS", "90"))
    except ValueError as exc:
        raise ProviderConfigError("model_timeout_invalid") from exc
    if timeout_seconds < 1:
        raise ProviderConfigError("model_timeout_invalid")

    return ModelConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


def create_provider(
    config: ModelConfig | None = None,
    *,
    opener: Callable[..., Any] | None = None,
) -> AIProvider:
    """Create the configured provider, defaulting to the existing model config."""
    selected = config or load_model_config()
    if selected.provider != "deepseek":
        raise ProviderConfigError("unsupported_model_provider")

    from deepseek_provider import DeepSeekProvider

    return DeepSeekProvider(selected, opener=opener)
