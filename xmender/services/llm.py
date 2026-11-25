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

from . import pricing

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

# Display order of model families in pickers, most capable first. Unknown
# families go last. Within a family the API's newest-first order is kept.
_TIER_ORDER = ("fable", "mythos", "opus", "sonnet", "haiku")


class LLMError(Exception):
    """User-presentable failure."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str
    max_tokens: int | None


@dataclass(frozen=True)
class UsageAttempt:
    """Token usage of one model attempt within a call. A call with a refusal
    fallback has one attempt per model that ran; each bills at its own rates."""

    model: str
    tokens: pricing.Tokens
    # message: served the reply; declined: refused, a fallback took over;
    # refused: the final reply is a refusal.
    kind: str = "message"
    billed: bool = True
    inference_geo: str | None = None

    def cost_nanos(self) -> int | None:
        if not self.billed:
            return 0
        return pricing.cost_nanos(self.model, self.tokens, inference_geo=self.inference_geo)


@dataclass(frozen=True)
class LLMResult:
    text: str
    stop_reason: str | None
    model: str
    usage: tuple[UsageAttempt, ...] = ()


_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
_cache_lock = threading.Lock()


def _client(api_key: str) -> anthropic.Anthropic:
    # Explicit key so nothing is picked up from the host's environment.
    return anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=300.0)


def _key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _tier_rank(model_id: str) -> int:
    parts = model_id.lower().split("-")
    for rank, tier in enumerate(_TIER_ORDER):
        if tier in parts:
            return rank
    return len(_TIER_ORDER)


def sort_models(models: list[ModelInfo]) -> list[ModelInfo]:
    """Group by tier; stable, so the API's newest-first order holds per tier."""
    return sorted(models, key=lambda m: _tier_rank(m.id))


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
    models = sort_models(models)
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
    return LLMResult(
        text=text, stop_reason=resp.stop_reason, model=resp.model, usage=usage_attempts(resp, model)
    )


def _int(obj: object, name: str) -> int:
    return int(getattr(obj, name, None) or 0)


def _tokens(u: object) -> pricing.Tokens:
    write_total = _int(u, "cache_creation_input_tokens")
    cc = getattr(u, "cache_creation", None)
    if cc is not None:
        w5, w1 = _int(cc, "ephemeral_5m_input_tokens"), _int(cc, "ephemeral_1h_input_tokens")
        # Anything the breakdown does not cover bills at the cheaper 5-minute rate.
        w5 += max(0, write_total - w5 - w1)
    else:
        w5, w1 = write_total, 0
    return pricing.Tokens(
        input=_int(u, "input_tokens"),
        output=_int(u, "output_tokens"),
        cache_write_5m=w5,
        cache_write_1h=w1,
        cache_read=_int(u, "cache_read_input_tokens"),
    )


def usage_attempts(resp: object, requested_model: str) -> tuple[UsageAttempt, ...]:
    """Billable usage of a Messages response, split per model attempt.

    With server-side fallbacks, `usage.iterations` is the per-attempt billing
    record and top-level `usage` covers only the final attempt.
    """
    usage = getattr(resp, "usage", None)
    if usage is None:
        return ()
    geo = getattr(usage, "inference_geo", None)
    served = getattr(resp, "model", None) or requested_model
    stop_details = getattr(resp, "stop_details", None)
    refused = getattr(resp, "stop_reason", None) == "refusal"

    iterations = [
        it for it in (getattr(usage, "iterations", None) or [])
        if getattr(it, "type", None) in ("message", "fallback_message")
    ]
    if iterations:
        raw = [
            (getattr(it, "model", None) or (requested_model if i == 0 else served), _tokens(it))
            for i, it in enumerate(iterations)
        ]
    else:
        raw = [(served, _tokens(usage))]

    out: list[UsageAttempt] = []
    last = len(raw) - 1
    for i, (model, toks) in enumerate(raw):
        if i < last:
            # An earlier attempt declined and a fallback ran. Its refusal
            # category is not reported, so it is counted as billed (worst case).
            out.append(UsageAttempt(model, toks, kind="declined", inference_geo=geo))
            continue
        billed = True
        if refused and toks.output == 0:
            category = getattr(stop_details, "category", None)
            billed = category in pricing.BILLED_REFUSAL_CATEGORIES
        out.append(
            UsageAttempt(
                model, toks, kind="refused" if refused else "message", billed=billed,
                inference_geo=geo,
            )
        )
    return tuple(out)
