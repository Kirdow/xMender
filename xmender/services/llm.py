"""Anthropic access. Blocking; call through `asyncio.to_thread`.

The selectable models always come from the provider's Models API; nothing is
hard-coded except which models accept server-side refusal fallbacks.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

import anthropic

MODEL_CACHE_SECONDS = 600
DEFAULT_MAX_TOKENS = 16000

# Models that accept `fallbacks: "default"` (server-side refusal fallback).
_FALLBACK_MODELS = {
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """User-presentable failure."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str
    max_tokens: int | None


@dataclass(frozen=True)
class LLMResult:
    text: str
    stop_reason: str | None
    model: str


_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
_cache_lock = threading.Lock()


def _client(api_key: str) -> anthropic.Anthropic:
    # Explicit key so nothing is picked up from the host's environment.
    return anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=300.0)


def _key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def list_models(api_key: str, *, refresh: bool = False) -> list[ModelInfo]:
    kid = _key_id(api_key)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(kid)
        if hit and not refresh and now - hit[0] < MODEL_CACHE_SECONDS:
            return hit[1]
    try:
        models = [
            ModelInfo(
                id=m.id,
                display_name=getattr(m, "display_name", None) or m.id,
                max_tokens=getattr(m, "max_tokens", None),
            )
            for m in _client(api_key).models.list(limit=100)
        ]
    except anthropic.AuthenticationError as e:
        raise LLMError("Anthropic rejected the API key.") from e
    except anthropic.PermissionDeniedError as e:
        raise LLMError("The API key lacks permission to list models.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the Anthropic API.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code} while listing models.") from e
    with _cache_lock:
        _cache[kid] = (now, models)
    return models


def find_model(api_key: str, model_id: str) -> ModelInfo | None:
    return next((m for m in list_models(api_key) if m.id == model_id), None)


def complete(api_key: str, model: str, system: str, user: str) -> LLMResult:
    info = find_model(api_key, model)
    if info is None:
        raise LLMError(f"Model `{model}` is not offered by the provider for this API key.")
    max_tokens = min(DEFAULT_MAX_TOKENS, info.max_tokens or DEFAULT_MAX_TOKENS)

    client = _client(api_key)
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    try:
        if model in _FALLBACK_MODELS:
            try:
                resp = client.beta.messages.create(
                    **kwargs, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                resp = client.messages.create(**kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise LLMError("Anthropic rejected the API key.") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Model `{model}` was not found.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Anthropic rate limit hit; try again later.") from e
    except anthropic.BadRequestError as e:
        raise LLMError(f"Anthropic rejected the request: {getattr(e, 'message', e)}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the Anthropic API.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}.") from e

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return LLMResult(text=text, stop_reason=resp.stop_reason, model=resp.model)
