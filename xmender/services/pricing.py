"""Anthropic token prices and per-call cost calculation.

The Models API does not publish prices, so they live here. Source:
https://platform.claude.com/docs/en/about-claude/pricing (checked `PRICES_AS_OF`).
Costs are kept as integer nano-dollars (1e-9 USD) so sums stay exact; the
cheapest rate (Claude Haiku 5.5 cache reads, $0.01/MTok) is 10 nano-dollars
per token, so nothing is lost to rounding before the 6th decimal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PRICES_AS_OF = "2026-11-25"
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"

NANOS_PER_USD = 1_000_000_000
# `inference_geo: "us"` multiplies every token price by 1.1 (Claude 4.6+).
US_GEO_MULTIPLIER = Decimal("1.1")
# Refusals before any output are billed only in these categories.
BILLED_REFUSAL_CATEGORIES = {"bio", "frontier_llm", "reasoning_extraction"}


@dataclass(frozen=True)
class Rates:
    """USD per million tokens."""

    input: Decimal
    output: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal

    def as_dict(self) -> dict[str, str]:
        return {k: _fmt(getattr(self, k)) for k in self.__dataclass_fields__}


@dataclass(frozen=True)
class ModelPricing:
    rates: Rates
    # Claude Haiku 5.5 bills prompts over a threshold at a second rate card.
    long_rates: Rates | None = None
    long_threshold: int = 0

    def rates_for(self, prompt_tokens: int) -> Rates:
        if self.long_rates is not None and prompt_tokens > self.long_threshold:
            return self.long_rates
        return self.rates


def _fmt(d: Decimal) -> str:
    return format(d.normalize(), "f")


def _r(inp: str, out: str, read: str) -> Rates:
    i = Decimal(inp)
    # Cache writes are 1.25x (5 min) and 2x (1 h) base input on every model.
    return Rates(i, Decimal(out), i * Decimal("1.25"), i * 2, Decimal(read))


_PRICES: dict[str, ModelPricing] = {
    "claude-fable-5-2": ModelPricing(_r("8", "40", "0.20")),
    "claude-mythos-5-2": ModelPricing(_r("8", "40", "0.20")),
    "claude-fable-5-1": ModelPricing(_r("10", "50", "0.25")),
    "claude-mythos-5-1": ModelPricing(_r("10", "50", "0.25")),
    "claude-fable-5": ModelPricing(_r("10", "50", "1")),
    "claude-mythos-5": ModelPricing(_r("10", "50", "1")),
    "claude-opus-5-5": ModelPricing(_r("4", "20", "0.20")),
    "claude-opus-5": ModelPricing(_r("5", "25", "0.50")),
    "claude-opus-4-8": ModelPricing(_r("5", "25", "0.50")),
    "claude-opus-4-7": ModelPricing(_r("5", "25", "0.50")),
    "claude-opus-4-6": ModelPricing(_r("5", "25", "0.50")),
    "claude-opus-4-5": ModelPricing(_r("5", "25", "0.50")),
    "claude-opus-4-1": ModelPricing(_r("15", "75", "1.50")),
    "claude-opus-4": ModelPricing(_r("15", "75", "1.50")),
    "claude-sonnet-5-5": ModelPricing(_r("2", "10", "0.10")),
    "claude-sonnet-5": ModelPricing(_r("2", "10", "0.20")),
    "claude-sonnet-4-6": ModelPricing(_r("3", "15", "0.30")),
    "claude-sonnet-4-5": ModelPricing(_r("3", "15", "0.30")),
    "claude-sonnet-4": ModelPricing(_r("3", "15", "0.30")),
    "claude-haiku-5-5": ModelPricing(
        _r("0.10", "0.50", "0.01"), long_rates=_r("0.50", "2.50", "0.05"), long_threshold=100_000
    ),
    "claude-haiku-4-5": ModelPricing(_r("1", "5", "0.10")),
}
# Aliases the API has used for some models.
_PRICES["claude-opus-4-0"] = _PRICES["claude-opus-4"]
_PRICES["claude-sonnet-4-0"] = _PRICES["claude-sonnet-4"]

_DATE_SUFFIX = re.compile(r"-\d{8}$")


def normalize_model(model_id: str) -> str:
    m = model_id.strip().lower()
    m = m.removeprefix("anthropic.").split("@", 1)[0]
    return _DATE_SUFFIX.sub("", m)


def lookup(model_id: str | None) -> ModelPricing | None:
    if not model_id:
        return None
    return _PRICES.get(normalize_model(model_id))


@dataclass(frozen=True)
class Tokens:
    input: int = 0
    output: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0

    @property
    def prompt(self) -> int:
        return self.input + self.cache_write_5m + self.cache_write_1h + self.cache_read


def cost_nanos(model_id: str | None, t: Tokens, *, inference_geo: str | None = None) -> int | None:
    """Cost of one billed attempt in nano-dollars, or None if the model's price
    is unknown."""
    p = lookup(model_id)
    if p is None:
        return None
    r = p.rates_for(t.prompt)
    per_mtok = (
        t.input * r.input
        + t.output * r.output
        + t.cache_write_5m * r.cache_write_5m
        + t.cache_write_1h * r.cache_write_1h
        + t.cache_read * r.cache_read
    )
    if (inference_geo or "").lower() == "us":
        per_mtok *= US_GEO_MULTIPLIER
    # $/MTok * tokens / 1e6 = USD; * 1e9 = nano-dollars.
    nanos = per_mtok * (NANOS_PER_USD // 1_000_000)
    return int(nanos.quantize(Decimal(1), rounding=ROUND_HALF_UP))
