"""Plans and model prices.

They live in code, not in the database, so a change to a limit is reviewed and deployed like any
other change. The user row only stores the plan name.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    label: str
    price_usd_month: int
    daily_messages: int
    daily_tokens: int
    burst_per_minute: int
    max_output_tokens: int

    def public(self) -> dict[str, object]:
        return asdict(self)


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", 0, daily_messages=20, daily_tokens=20_000,
                 burst_per_minute=5, max_output_tokens=400),
    "pro": Plan("pro", "Pro", 19, daily_messages=500, daily_tokens=1_000_000,
                burst_per_minute=30, max_output_tokens=1200),
}
DEFAULT_PLAN = "free"

# USD per one million tokens, (input, output). Check the provider's current price list before
# relying on these: they are configuration, not a measurement. Unknown and local models cost 0.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS[DEFAULT_PLAN])


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = MODEL_PRICES.get(model, (0.0, 0.0))
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
